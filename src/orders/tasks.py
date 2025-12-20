from __future__ import annotations
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from orders.models import ItemReservation

@shared_task(name="orders.purge_expired_reservations")
def purge_expired_reservations(days: int = 3):
    cutoff = timezone.now() - timedelta(days=days)
    ItemReservation.objects.filter(expires_at__lt=cutoff, released_at__isnull=True).delete()
