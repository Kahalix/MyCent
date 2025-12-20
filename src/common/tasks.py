from __future__ import annotations
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from common.models import IdempotencyKey

@shared_task(name="common.purge_old_idempotency_keys")
def purge_old_idempotency_keys(days: int = 30):
    cutoff = timezone.now() - timedelta(days=days)
    IdempotencyKey.objects.filter(created_at__lt=cutoff).delete()
