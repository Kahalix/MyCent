from __future__ import annotations
from typing import Optional, Dict
from django.db.models import QuerySet, Case, When, Value, CharField, Sum, Count, Q
from chat.models import ChatThread, ChatMessage, ChatParticipant


def threads_common_selects(qs: QuerySet[ChatThread]) -> QuerySet[ChatThread]:
    return qs.select_related(
        "item_set",
        "item_set__type",
        "item_set__catalog_item",
        "item_set__seller_profile",
    ).prefetch_related(
        "item_set__images",
    )


def messages_window_qs(thread: ChatThread, *, limit: int = 50, before: Optional[str] = None) -> QuerySet[ChatMessage]:
    qs = (
        ChatMessage.objects
        .filter(thread=thread)
        .select_related("sender")
        .order_by("-sent_at", "-id")
    )
    if before:
        prev = ChatMessage.objects.filter(public_id=before, thread=thread).only("id").first()
        if prev:
            qs = qs.filter(id__lt=prev.id)
    return qs[:limit]

def unread_total(user) -> int:
    row = (
        ChatParticipant.objects
        .filter(user=user, is_deleted=False, is_muted=False)
        .aggregate(total=Sum("unread_count"))
    )
    return int(row.get("total") or 0)

def unread_counts_by_bucket(user) -> Dict[str, dict]:
    base = (
        ChatParticipant.objects
        .select_related("thread", "thread__item_set", "thread__item_set__owner_user")
        .filter(user=user, is_deleted=False, is_muted=False)
    )

    bucket = Case(
        When(thread__item_set__isnull=True, then=Value("dm")),
        When(thread__item_set__added_by="STAFF", then=Value("sellers")),
        When(thread__item_set__added_by="USER", thread__item_set__owner_user=user, then=Value("my_user")),
        default=Value("users_other"),
        output_field=CharField(),
    )

    rows = (
        base
        .annotate(bucket=bucket)
        .values("bucket")
        .annotate(
            unread_threads=Count("id", filter=Q(unread_count__gt=0)),
            unread_messages=Sum("unread_count"),
        )
    )

    out = {
        "my_user": {"unread_threads": 0, "unread_messages": 0},
        "users_other": {"unread_threads": 0, "unread_messages": 0},
        "sellers": {"unread_threads": 0, "unread_messages": 0},
        "dm": {"unread_threads": 0, "unread_messages": 0},
    }
    for r in rows:
        b = r.get("bucket")
        if b in out:
            out[b]["unread_threads"] = int(r.get("unread_threads") or 0)
            out[b]["unread_messages"] = int(r.get("unread_messages") or 0)

    listings_threads = (
        out["my_user"]["unread_threads"]
        + out["users_other"]["unread_threads"]
        + out["sellers"]["unread_threads"]
    )
    listings_msgs = (
        out["my_user"]["unread_messages"]
        + out["users_other"]["unread_messages"]
        + out["sellers"]["unread_messages"]
    )
    total_threads = listings_threads + out["dm"]["unread_threads"]
    total_msgs = listings_msgs + out["dm"]["unread_messages"]

    out["all_listings"] = {"unread_threads": listings_threads, "unread_messages": listings_msgs}
    out["total"] = {"unread_threads": total_threads, "unread_messages": total_msgs}
    return out

