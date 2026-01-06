from __future__ import annotations

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from chat.services import commands as cmd
from chat.services import repositories as repo


class ThreadConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.thread_pid = self.scope["url_route"]["kwargs"]["public_id"]
        self.group = f"chat.thread.{self.thread_pid}"

        user = self.scope.get("user")
        if not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return

        ok = await self._user_has_access(user.id, self.thread_pid)
        if not ok:
            await self.close(code=4403)
            return

        await self._ensure_participant(user.id, self.thread_pid)

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "{}")
        except Exception:
            return

        user = self.scope.get("user")
        if not getattr(user, "is_authenticated", False):
            return

        typ = data.get("type") or "message"

        if typ == "typing":
            await self.channel_layer.group_send(
                self.group,
                {
                    "type": "chat.typing",
                    "user_id": user.id,
                    "state": bool(data.get("state", True)),
                },
            )
            return

        if typ == "message":
            content = (data.get("content") or "").strip()
            if not content:
                return
            if len(content) > 5000:
                return

            msg = await self._send(user.id, self.thread_pid, content)
            await self.channel_layer.group_send(self.group, {"type": "chat.message", "payload": msg})

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({"type": "message", **event["payload"]}))

    async def chat_typing(self, event):
        await self.send(text_data=json.dumps({"type": "typing", "user_id": event["user_id"], "state": event["state"]}))

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
    def _send(self, user_id: int, thread_pid: str, content: str) -> dict:
        from identity.models import User
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

        return {
            "public_id": str(msg.public_id),
            "content": msg.content,
            "sent_at": msg.sent_at.isoformat(),
            "sender_public_id": str(user.public_id),
            "sender_display_name": display_name,
            "sender_user_image": avatar,
        }


class InboxConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return

        self.group = f"chat.inbox.{user.public_id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def inbox_thread_updated(self, event):
        await self.send(text_data=json.dumps({"type": "inbox.thread_updated", **event["payload"]}))

    async def inbox_unread_counts(self, event):
        await self.send(text_data=json.dumps({"type": "inbox.unread_counts", **event["payload"]}))
