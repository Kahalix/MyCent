from __future__ import annotations
import uuid
from contextlib import contextmanager
from celery import shared_task
from django.core.cache import cache
from saved.services.refresh import refresh_saved_searches, check_price_drops

@contextmanager
def task_lock(key: str, timeout: int = 14*60):
    """
    Prosta rozproszona blokada oparta o cache (np. Redis).
    """
    token = str(uuid.uuid4())
    acquired = cache.add(key, token, timeout=timeout)
    try:
        yield acquired
    finally:
        if acquired and cache.get(key) == token:
            cache.delete(key)

@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
def refresh_saved_searches_periodic(self, prune: bool = True, limit: int = 0):
    with task_lock("lock:saved:refresh_searches") as ok:
        if not ok:
            return {"skipped": "already running"}
        return refresh_saved_searches(prune=prune, limit=(limit or None))

@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
def check_price_drops_periodic(self, notify: bool = True, limit: int = 0):
    with task_lock("lock:saved:price_drops") as ok:
        if not ok:
            return {"skipped": "already running"}
        return check_price_drops(notify=notify, limit=(limit or None))