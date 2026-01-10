from __future__ import annotations
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from orders.models import OrderLine, OrderShipping
from orders.services.commands import sync_orders_with_transaction, _update_tx_expected_total
from transactions.models import Transaction


@receiver(pre_save, sender=Transaction)
def _tx_store_prev_status(sender, instance: Transaction, **kwargs):
    if not instance.pk:
        instance._prev_status = None
        return
    instance._prev_status = sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()


@receiver([post_save, post_delete], sender=OrderLine)
def _recalc_order_total_on_line_change(sender, instance: OrderLine, **kwargs):
    order = instance.order
    order.recalc_totals(save=True)
    _update_tx_expected_total(order.transaction)


@receiver([post_save, post_delete], sender=OrderShipping)
def _recalc_order_total_on_shipping_change(sender, instance: OrderShipping, **kwargs):
    order = instance.order
    order.recalc_totals(save=True)
    _update_tx_expected_total(order.transaction)


@receiver(post_save, sender=Transaction)
def _sync_orders_when_transaction_changes(sender, instance: Transaction, created: bool, **kwargs):
    if created:
        return
    prev = getattr(instance, "_prev_status", None)
    if prev == instance.status:
        return
    sync_orders_with_transaction(tx=instance)
