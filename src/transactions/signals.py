from __future__ import annotations
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from transactions.models import Transaction, TransactionStatusHistory

@receiver(pre_save, sender=Transaction)
def _capture_prev_status(sender, instance: Transaction, **kwargs):
    if instance.pk:
        try:
            old = Transaction.objects.get(pk=instance.pk)
            instance._prev_status = old.status
        except Transaction.DoesNotExist:
            instance._prev_status = ""

@receiver(post_save, sender=Transaction)
def _make_status_history(sender, instance: Transaction, created: bool, **kwargs):
    prev = getattr(instance, "_prev_status", "")
    if created:
        TransactionStatusHistory.objects.create(transaction=instance, from_status="", to_status=instance.status, reason="created")
    else:
        if prev and prev != instance.status:
            TransactionStatusHistory.objects.create(transaction=instance, from_status=prev, to_status=instance.status, reason="")
