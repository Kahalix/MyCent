from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from common.tasks import task_lock
from listings.models import ItemSet
from listings.services.cache_utils import invalidate_public_itemsets_cache
from services.services.commands import ensure_slot_matches_state


@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
def expire_stale_user_itemsets_periodic(self, days: int = 30, limit: int = 0):
    with task_lock("lock:listings:expire_stale_user_itemsets") as ok:
        if not ok:
            return {"skipped": "already running"}

        now = timezone.now()
        threshold = now - timedelta(days=int(days))

        with transaction.atomic():
            qs = (
                ItemSet.objects.select_for_update(skip_locked=True)
                .filter(added_by="USER", status="AVAILABLE", updated_at__lt=threshold)
                .order_by("updated_at")
            )

            if limit and int(limit) > 0:
                qs = qs[: int(limit)]

            ids = list(qs.values_list("id", flat=True))
            if not ids:
                return {"expired": 0, "days": int(days)}

            ItemSet.objects.filter(id__in=ids).update(status="EXPIRED", updated_at=now)

        items = ItemSet.objects.filter(id__in=ids).select_related("owner_user")
        for it in items:
            ensure_slot_matches_state(user=it.owner_user, itemset=it)

        try:
            invalidate_public_itemsets_cache()
        except Exception:
            pass

        return {"expired": len(ids), "days": int(days)}
