from __future__ import annotations

from celery import shared_task

from common.tasks import task_lock
from saved.services.refresh import refresh_saved_searches, check_price_drops


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
