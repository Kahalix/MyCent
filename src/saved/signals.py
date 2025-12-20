# src/saved/signals.py
from __future__ import annotations
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from saved.models import SavedListing

@receiver(post_save, sender=SavedListing)
def init_saved_listing_price(sender, instance: SavedListing, created: bool, **kwargs):
    if not created:
        return
    it = instance.item_set
    if getattr(it, "price", None):
        # ustaw snapshot tylko jeśli nie był ustawiony ręcznie
        if instance.saved_price_amount is None:
            instance.saved_price_amount = it.price.amount
            instance.saved_price_currency = str(it.price.currency)
            instance.price_drop_notification_sent = False
            instance.last_price_checked_at = timezone.now()
            instance.save(update_fields=[
                "saved_price_amount","saved_price_currency",
                "price_drop_notification_sent","last_price_checked_at"
            ])
