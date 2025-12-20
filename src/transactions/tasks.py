from __future__ import annotations
from celery import shared_task
from django.conf import settings
from transactions.services.commands import cancel_stale_pending_transactions


@shared_task(name="transactions.cancel_stale_pending")
def cancel_stale_pending() -> int:
    minutes = int(getattr(settings, "TRANSACTIONS_PENDING_TTL_MINUTES", 60))
    return cancel_stale_pending_transactions(minutes=minutes)
