from __future__ import annotations
from django.db import models
from django.db.models import Q
from common.models import PublicIdModel
from identity.models import User
from listings.models import ItemSet


class ChatThread(PublicIdModel):
    """
    Wątek rozmowy (DM 1:1, powiązany opcjonalnie z ogłoszeniem).
    dm_key = "<min_user_id>:<max_user_id>" zapewnia 1 DM na parę.
    """
    is_group = models.BooleanField(default=False)
    item_set = models.ForeignKey(ItemSet, null=True, blank=True, on_delete=models.PROTECT, related_name="chat_threads")
    dm_key = models.CharField(max_length=64, null=True, blank=True)

    last_message_preview = models.CharField(max_length=300, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["last_message_at"], name="ix_chatthread_lastmsg"),
            models.Index(fields=["item_set", "last_message_at"], name="ix_chatthread_item_lastmsg"),
        ]
        constraints = [
            # Unikalny DM dla pary, gdy thread bez itemu
            models.UniqueConstraint(
                fields=["dm_key"],
                condition=Q(item_set__isnull=True) & Q(dm_key__isnull=False),
                name="uq_dmkey_global_when_no_item",
            ),
            # Unikalny DM dla pary w obrębie danego itemu
            models.UniqueConstraint(
                fields=["item_set", "dm_key"],
                condition=Q(dm_key__isnull=False),
                name="uq_dmkey_per_item",
            ),
        ]

    def __str__(self) -> str:
        return f"Thread {self.public_id} ({'item' if self.item_set_id else 'global'})"


class ChatParticipant(PublicIdModel):
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_participations")

    is_deleted = models.BooleanField(default=False)
    is_muted = models.BooleanField(default=False)

    last_read_at = models.DateTimeField(null=True, blank=True)
    unread_count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = (("thread", "user"),)
        indexes = [
            models.Index(fields=["thread"], name="ix_part_thread"),
            models.Index(fields=["user", "is_deleted"], name="ix_part_user_deleted"),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} in {self.thread.public_id}"


class ChatMessage(PublicIdModel):
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.PROTECT, related_name="sent_messages")
    content = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["thread", "sent_at"], name="ix_msg_thread_sent"),
            models.Index(fields=["sender", "sent_at"], name="ix_msg_sender_sent"),
        ]

    def __str__(self) -> str:
        return f"Msg {self.public_id} by {self.sender_id}"
