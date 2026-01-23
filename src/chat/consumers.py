from __future__ import annotations

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from chat.services import commands as cmd
from chat.services import repositories as repo


def _choose_subprotocol(scope) -> str | None:
    subs = scope.get("subprotocols") or []
    return next((p for p in subs if isinstance(p, str) and not p.startswith("rt.")), None)


class ThreadConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.thread_pid = self.scope["url_route"]["kwargs"]["public_id"]
        self.group = f"chat.thread.{self.thread_pid}"

        user = self.scope.get("user")
        chosen = _choose_subprotocol(self.scope)

        if not getattr(user, "is_authenticated", False):
            if chosen:
                await self.accept(subprotocol=chosen)
            else:
                await self.accept()
            await self.close(code=4401)
            return

        ok = await self._user_has_access(user.id, self.thread_pid)
        if not ok:
            if chosen:
                await self.accept(subprotocol=chosen)
            else:
                await self.accept()
            await self.close(code=4403)
            return

        await self._ensure_participant(user.id, self.thread_pid)
        await self.channel_layer.group_add(self.group, self.channel_name)

        if chosen:
            await self.accept(subprotocol=chosen)
        else:
            await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            try:
                await self.channel_layer.group_discard(self.group, self.channel_name)
            except Exception:
                pass

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "{}")
        except Exception:
            return

        user = self.scope.get("user")
        if not getattr(user, "is_authenticated", False):
            return

        typ = data.get("type") or "message"

        if typ == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))
            return

        if typ == "typing":
            await self.channel_layer.group_send(
                self.group,
                {
                    "type": "chat.typing",
                    "user_id": str(getattr(user, "public_id", user.id)),
                    "state": bool(data.get("state", True)),
                },
            )
            return

        if typ == "message":
            content = (data.get("content") or "").strip()
            if not content or len(content) > 5000:
                return

            res = await self._send_with_inbox_updates(user.id, self.thread_pid, content)

            await self.channel_layer.group_send(self.group, {"type": "chat.message", "payload": res["message"]})

            for it in res["inbox_updates"]:
                grp = f"chat.inbox.{it['user_public_id']}"
                await self.channel_layer.group_send(grp, {"type": "inbox.thread_updated", "payload": it["thread_updated"]})
                await self.channel_layer.group_send(grp, {"type": "inbox.unread_counts", "payload": it["unread_counts"]})
                await self.channel_layer.group_send(grp, {"type": "inbox.unread_total", "unread_messages": it["unread_total"]})

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({"type": "message", **event["payload"]}))

    async def chat_typing(self, event):
        await self.send(
            text_data=json.dumps(
                {"type": "typing", "user_id": str(event["user_id"]), "state": event["state"]}
            )
        )

    @database_sync_to_async
    def _user_has_access(self, user_id: int, thread_pid: str) -> bool:
        th = repo.get_thread_by_public_id(thread_pid)
        if not th:
            return False
        from identity.models import User
        u = User.objects.filter(id=user_id).first()
        if not u:
            return False
        return repo.user_has_access_to_thread(u, th)

    @database_sync_to_async
    def _ensure_participant(self, user_id: int, thread_pid: str):
        th = repo.get_thread_by_public_id(thread_pid)
        if not th:
            return
        from identity.models import User
        u = User.objects.filter(id=user_id).first()
        if not u:
            return
        repo.ensure_participant(th, u)

    @database_sync_to_async
    def _send_with_inbox_updates(self, user_id: int, thread_pid: str, content: str) -> dict:
        from identity.models import User
        from chat.services import queries as q

        user = User.objects.get(id=user_id)
        th = repo.get_thread_by_public_id(thread_pid)
        msg = cmd.send_message(thread=th, sender=user, content=content)

        if user.first_name or user.last_name:
            display_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
        else:
            display_name = (user.email.split("@", 1)[0] if user.email else "Użytkownik")

        avatar = None
        if getattr(user, "user_image", None):
            try:
                avatar = user.user_image.url
            except Exception:
                avatar = None

        th.refresh_from_db(fields=["last_message_preview", "last_message_at"])

        parts = list(th.participants.select_related("user").all())

        inbox_updates = []
        for p in parts:
            u = p.user
            unread = int(p.unread_count or 0)
            if u.id == user_id:
                unread = 0

            counts = q.unread_counts_by_bucket(u)
            total = int(counts.get("total", {}).get("unread_messages") or 0)

            inbox_updates.append(
                {
                    "user_public_id": str(u.public_id),
                    "thread_updated": {
                        "thread_public_id": str(th.public_id),
                        "last_message_preview": th.last_message_preview,
                        "last_message_at": th.last_message_at.isoformat() if th.last_message_at else None,
                        "unread_count": unread,
                    },
                    "unread_counts": counts,
                    "unread_total": total,
                }
            )

        return {
            "message": {
                "public_id": str(msg.public_id),
                "content": msg.content,
                "sent_at": msg.sent_at.isoformat(),
                "sender_public_id": str(user.public_id),
                "sender_display_name": display_name,
                "sender_user_image": avatar,
            },
            "inbox_updates": inbox_updates,
        }


class InboxConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        chosen = _choose_subprotocol(self.scope)

        if not getattr(user, "is_authenticated", False):
            if chosen:
                await self.accept(subprotocol=chosen)
            else:
                await self.accept()
            await self.close(code=4401)
            return

        self.group = f"chat.inbox.{user.public_id}"
        await self.channel_layer.group_add(self.group, self.channel_name)

        if chosen:
            await self.accept(subprotocol=chosen)
        else:
            await self.accept()

        total = await self._unread_total_for_user(user.id)
        await self.send(text_data=json.dumps({"type": "inbox.unread_total", "unread_messages": total}))

    async def disconnect(self, code):
        if hasattr(self, "group"):
            try:
                await self.channel_layer.group_discard(self.group, self.channel_name)
            except Exception:
                pass

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "{}")
        except Exception:
            return

        user = self.scope.get("user")
        if not getattr(user, "is_authenticated", False):
            return

        typ = data.get("type") or ""

        if typ == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))
            return

    async def inbox_thread_updated(self, event):
        await self.send(text_data=json.dumps({"type": "inbox.thread_updated", **event["payload"]}))

    async def inbox_unread_counts(self, event):
        await self.send(text_data=json.dumps({"type": "inbox.unread_counts", **event["payload"]}))

    async def inbox_unread_total(self, event):
        await self.send(text_data=json.dumps({"type": "inbox.unread_total", "unread_messages": int(event.get("unread_messages") or 0)}))

    @database_sync_to_async
    def _unread_total_for_user(self, user_id: int) -> int:
        from identity.models import User
        from chat.services import queries as q
        u = User.objects.filter(id=user_id).first()
        if not u:
            return 0
        return q.unread_total(u)
