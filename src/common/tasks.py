from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import timedelta

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from common.models import IdempotencyKey


@contextmanager
def task_lock(key: str, timeout: int = 14 * 60):
    token = str(uuid.uuid4())
    acquired = cache.add(key, token, timeout=timeout)
    try:
        yield acquired
    finally:
        if acquired and cache.get(key) == token:
            cache.delete(key)


@shared_task(name="common.purge_old_idempotency_keys")
def purge_old_idempotency_keys(days: int = 30):
    cutoff = timezone.now() - timedelta(days=days)
    IdempotencyKey.objects.filter(created_at__lt=cutoff).delete()
