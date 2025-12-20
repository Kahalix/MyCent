# chat/services/repositories.py
from __future__ import annotations

import hashlib
from typing import Optional
from django.db import transaction
from django.db.models import Q, F
from django.utils import timezone

from identity.models import User
from listings.models import ItemSet
from chat.models import ChatThread, ChatParticipant, ChatMessage
from chat.services import notifications


# ---------- helpers / identyfikatory ----------

def _dm_key_for(u1_id, u2_id) -> str:
    """
    Stabilny klucz DM dla pary użytkowników.
    - sortujemy po stringach (działa dla int/UUID)
    - jeżeli za długie (>60), skracamy do sha1 z prefiksem 'h:'
    """
    a, b = sorted([str(u1_id), str(u2_id)])
    raw = f"{a}:{b}"
    if len(raw) > 60:
        return "h:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return raw


# ---------- podstawowe lookupi ----------

def get_thread_by_public_id(pid: str) -> Optional[ChatThread]:
    return (ChatThread.objects
            .select_related("item_set__seller_profile")
            .prefetch_related("participants__user")
            .filter(public_id=pid).first())


def user_has_access_to_thread(user: User, thread: ChatThread | None) -> bool:
    if not thread:
        return False
    # uczestnik
    if thread.participants.filter(user=user, is_deleted=False).exists():
        return True
    # członek sklepu (jeśli wątek dotyczy ogłoszenia sklepu)
    if thread.item_set_id and thread.item_set.seller_profile_id:
        return thread.item_set.seller_profile.memberships.filter(user=user, is_active=True).exists()
    return False


def ensure_participant(thread: ChatThread, user: User) -> ChatParticipant:
    obj, _ = ChatParticipant.objects.get_or_create(thread=thread, user=user, defaults={})
    return obj


# ---------- DM threading ----------

def get_or_create_dm_thread(u1: User, u2: User, *, item: ItemSet | None) -> ChatThread:
    if u1.id == u2.id:
        raise ValueError("Cannot start a DM with yourself.")
    key = _dm_key_for(u1.id, u2.id)
    with transaction.atomic():
        thread, _ = ChatThread.objects.get_or_create(
            dm_key=key,
            item_set=item,
            defaults={"is_group": False},
        )
        # gwarantujemy obecność dwóch uczestników (DM = 1:1)
        for u in (u1, u2):
            ChatParticipant.objects.get_or_create(thread=thread, user=u, defaults={})
        return thread


# ---------- listy / okna ----------

def list_user_threads(user: User, *, item: ItemSet | None = None):
    base = (ChatThread.objects
            .select_related("item_set__seller_profile"))
    cond_part = Q(participants__user=user, participants__is_deleted=False)
    cond_staff = Q(item_set__seller_profile__memberships__user=user,
                   item_set__seller_profile__memberships__is_active=True)
    qs = base.filter(cond_part | cond_staff)
    if item:
        qs = qs.filter(item_set=item)
    return qs.order_by(F("last_message_at").desc(nulls_last=True), "-updated_at").distinct()


def participants_qs():
    # Prefetch-ready queryset na uczestników z podstawowymi polami usera.
    return (ChatParticipant.objects
            .select_related("user")
            .only(
                "id", "public_id", "thread_id", "is_deleted", "is_muted", "last_read_at", "unread_count",
                "user__public_id", "user__first_name", "user__last_name", "user__user_image", "user__email"
            ))


def list_messages(thread: ChatThread, *, limit: int = 50, before: Optional[str] = None):
    qs = (ChatMessage.objects
          .filter(thread=thread)
          .select_related("sender")
          .order_by("-sent_at", "-id"))
    if before:
        prev = ChatMessage.objects.filter(public_id=before, thread=thread).only("id").first()
        if prev:
            qs = qs.filter(id__lt=prev.id)
    return list(qs[:limit])


# ---------- mutacje (zapisy) ----------

def create_message(*, thread: ChatThread, sender: User, content: str) -> ChatMessage:
    msg = ChatMessage.objects.create(thread=thread, sender=sender, content=content.strip())
    thread.last_message_at = msg.sent_at
    thread.last_message_preview = (msg.content[:300] or "").strip()
    thread.save(update_fields=["last_message_at", "last_message_preview", "updated_at"])

    (ChatParticipant.objects
     .filter(thread=thread)
     .exclude(user=sender)
     .update(unread_count=F("unread_count") + 1))

    # webhook po commicie (bez blokowania transakcji)
    transaction.on_commit(lambda: notifications.notify_new_message(msg))
    return msg


def mark_read_up_to_now(*, thread: ChatThread, user: User) -> ChatParticipant | None:
    part = ChatParticipant.objects.filter(thread=thread, user=user).first()
    if not part:
        return None
    part.last_read_at = timezone.now()
    if part.unread_count:
        part.unread_count = 0
    part.save(update_fields=["last_read_at", "unread_count", "updated_at"])
    return part
