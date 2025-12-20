from __future__ import annotations
from celery import shared_task
from payments.services.commands import expire_stale_payments

@shared_task(name="payments.expire_stale")
def expire_stale(minutes: int = 30) -> int:
    return expire_stale_payments(minutes=minutes)
