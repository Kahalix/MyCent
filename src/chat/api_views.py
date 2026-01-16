from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from chat.filters import ChatThreadFilter
from chat.serializers import (
    ChatMessageResponse,
    ChatThreadResponse,
    ListMessagesRequest,
    SendMessageRequest,
    StartDMRequest,
)
from chat.services import commands as cmd
from chat.services import queries as q
from chat.services import repositories as repo
from identity.models import User
from listings.models import ItemSet


class UserChatThreadViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChatThreadResponse
    lookup_field = "public_id"
    filter_backends = [DjangoFilterBackend]
    filterset_class = ChatThreadFilter

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx.update({"request": self.request})
        return ctx

    def get_queryset(self):
        item_pid = self.request.query_params.get("item_public_id")
        item = ItemSet.objects.filter(public_id=item_pid).first() if item_pid else None
        qs = repo.list_user_threads(self.request.user, item=item)
        return (
            qs.select_related(
                "item_set",
                "item_set__type",
                "item_set__catalog_item",
            )
            .prefetch_related(
                "item_set__images",
                Prefetch("participants", queryset=repo.participants_qs()),
            )
        )

    def _send_inbox_counts(self, *, layer, user: User):
        async_to_sync(layer.group_send)(
            f"chat.inbox.{user.public_id}",
            {"type": "inbox.unread_counts", "payload": q.unread_counts_by_bucket(user)},
        )

    def _send_thread_updated(self, *, layer, user: User, payload: dict):
        async_to_sync(layer.group_send)(
            f"chat.inbox.{user.public_id}",
            {"type": "inbox.thread_updated", "payload": payload},
        )

    def _send_thread_message(self, *, layer, thread_public_id: str, payload: dict):
        async_to_sync(layer.group_send)(
            f"chat.thread.{thread_public_id}",
            {"type": "chat.message", "payload": payload},
        )

    def destroy(self, request, *args, **kwargs):
        thread = self.get_object()
        repo.mark_thread_deleted_for_user(thread=thread, user=request.user)
        layer = get_channel_layer()

        def _broadcast():
            self._send_inbox_counts(layer=layer, user=request.user)

        transaction.on_commit(_broadcast)
        return Response(status=204)

    @action(detail=False, methods=["get"], url_path="unread-counts")
    def unread_counts(self, request):
        data = q.unread_counts_by_bucket(request.user)
        return Response(data, status=200)

    @action(detail=False, methods=["post"], url_path="start")
    def start_dm(self, request):
        ser = StartDMRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        other = (
            get_object_or_404(User, public_id=ser.validated_data["other_user_public_id"])
            if ser.validated_data.get("other_user_public_id")
            else None
        )
        item = (
            get_object_or_404(ItemSet, public_id=ser.validated_data["item_public_id"])
            if ser.validated_data.get("item_public_id")
            else None
        )
        thread = cmd.start_dm(initiator=request.user, other_user=other, item=item)
        return Response(ChatThreadResponse(thread, context=self.get_serializer_context()).data, status=201)

    @action(detail=True, methods=["get"], url_path="messages")
    def messages(self, request, public_id=None):
        thread = self.get_object()
        qser = ListMessagesRequest(data=request.query_params)
        qser.is_valid(raise_exception=True)
        items = repo.list_messages(
            thread,
            limit=qser.validated_data["limit"],
            before=qser.validated_data.get("before") or None,
        )
        cmd.mark_read(thread=thread, user=request.user)
        layer = get_channel_layer()

        def _broadcast():
            self._send_inbox_counts(layer=layer, user=request.user)
            self._send_thread_updated(
                layer=layer,
                user=request.user,
                payload={
                    "thread_public_id": str(thread.public_id),
                    "last_message_preview": thread.last_message_preview,
                    "last_message_at": thread.last_message_at.isoformat() if thread.last_message_at else None,
                    "unread_count": 0,
                },
            )

        transaction.on_commit(_broadcast)
        return Response(ChatMessageResponse(items, many=True, context=self.get_serializer_context()).data, status=200)

    @action(detail=True, methods=["post"], url_path="messages/send")
    def send(self, request, public_id=None):
        thread = self.get_object()
        ser = SendMessageRequest(data=request.data)
        ser.is_valid(raise_exception=True)

        msg = cmd.send_message(thread=thread, sender=request.user, content=ser.validated_data["content"])

        if hasattr(thread, "_prefetched_objects_cache"):
            thread._prefetched_objects_cache = {}

        thread.refresh_from_db(fields=["last_message_preview", "last_message_at"])

        parts = list(thread.participants.select_related("user").all())

        sender = msg.sender
        if sender.first_name or sender.last_name:
            display_name = f"{(sender.first_name or '').strip()} {(sender.last_name or '').strip()}".strip()
        else:
            display_name = sender.email.split("@", 1)[0] if sender.email else "Użytkownik"

        sender_avatar = None
        if getattr(sender, "user_image", None):
            try:
                sender_avatar = sender.user_image.url
            except Exception:
                sender_avatar = None

        payload = {
            "public_id": str(msg.public_id),
            "content": msg.content,
            "sent_at": msg.sent_at.isoformat(),
            "sender_public_id": str(sender.public_id),
            "sender_display_name": display_name,
            "sender_user_image": sender_avatar,
        }

        layer = get_channel_layer()
        thread_pid = str(thread.public_id)

        def _broadcast():
            self._send_thread_message(layer=layer, thread_public_id=thread_pid, payload=payload)

            for p in parts:
                unread = int(p.unread_count)
                if p.user_id == request.user.id:
                    unread = 0

                self._send_thread_updated(
                    layer=layer,
                    user=p.user,
                    payload={
                        "thread_public_id": thread_pid,
                        "last_message_preview": thread.last_message_preview,
                        "last_message_at": thread.last_message_at.isoformat() if thread.last_message_at else None,
                        "unread_count": unread,
                    },
                )
                self._send_inbox_counts(layer=layer, user=p.user)

        transaction.on_commit(_broadcast)
        return Response(ChatMessageResponse(msg, context=self.get_serializer_context()).data, status=201)

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, public_id=None):
        thread = self.get_object()
        cmd.mark_read(thread=thread, user=request.user)

        if hasattr(thread, "_prefetched_objects_cache"):
            thread._prefetched_objects_cache = {}

        thread.refresh_from_db(fields=["last_message_preview", "last_message_at"])

        layer = get_channel_layer()

        def _broadcast():
            self._send_thread_updated(
                layer=layer,
                user=request.user,
                payload={
                    "thread_public_id": str(thread.public_id),
                    "last_message_preview": thread.last_message_preview,
                    "last_message_at": thread.last_message_at.isoformat() if thread.last_message_at else None,
                    "unread_count": 0,
                },
            )
            self._send_inbox_counts(layer=layer, user=request.user)

        transaction.on_commit(_broadcast)
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="mute")
    def mute(self, request, public_id=None):
        thread = self.get_object()
        raw = request.data.get("muted", None)
        if raw is None:
            muted = True
        elif isinstance(raw, bool):
            muted = raw
        else:
            muted = str(raw).lower() in ("1", "true", "yes", "on")

        repo.set_thread_mute_for_user(thread=thread, user=request.user, muted=muted)
        layer = get_channel_layer()

        def _broadcast():
            self._send_inbox_counts(layer=layer, user=request.user)

        transaction.on_commit(_broadcast)
        return Response(status=200)
