from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple
from django.utils import timezone
from djmoney.money import Money

from transactions.models import Transaction
from coupons.models import Coupon, UserCoupon


@dataclass
class DiscountResult:
    ok: bool
    reason: str | None
    discount: Money


def _count_redemptions(coupon: Coupon, user_id: int | None) -> Tuple[int, int]:
    from transactions.models import Transaction as _Tx
    base = _Tx.objects.filter(coupon=coupon, status="COMPLETED")
    total = base.count()
    per_user = base.filter(user_id=user_id).count() if user_id else 0
    return total, per_user

def _base_total_for(transaction: Transaction) -> Money:
    """
    Baza do rabatu: suma grand_total wszystkich orderów transakcji.
    """
    from orders.models import Order  # lazy import
    currency = transaction.expected_total_currency or "PLN"
    total = Money(0, currency)
    for o in transaction.orders.all():
        gt = o.grand_total
        if gt.currency != total.currency:
            gt = Money(gt.amount, total.currency)
        total += gt
    return total


def _apply_coupon_value(coupon: Coupon, base: Money) -> Money:
    if coupon.discount_type == "PERCENTAGE":
        pct = Decimal(coupon.discount_value.amount) if coupon.discount_value else Decimal("0")
        disc = Money((base.amount * pct / Decimal("100")), base.currency)
    else:  # AMOUNT
        amount = Decimal(coupon.discount_value.amount) if coupon.discount_value else Decimal("0")
        disc = Money(amount, base.currency)

    if coupon.max_discount_value:
        cap = Money(coupon.max_discount_value.amount, base.currency)
        if disc > cap:
            disc = cap
    if disc > base:
        disc = Money(base.amount, base.currency)
    return disc


def validate_and_compute_discount(
    *, transaction: Transaction, coupon: Coupon | None, user_coupon: UserCoupon | None
) -> DiscountResult:
    """
    Kupony stosujemy WYŁĄCZNIE dla PURCHASE.
    """
    currency = transaction.expected_total_currency or "PLN"

    if transaction.type != "PURCHASE":
        return DiscountResult(ok=False, reason="Coupons are not allowed for this transaction.", discount=Money(0, currency))

    if not coupon and not user_coupon:
        return DiscountResult(ok=True, reason=None, discount=Money(0, currency))

    now = timezone.now()
    if user_coupon:
        coupon = user_coupon.coupon

    if not coupon or not coupon.active:
        return DiscountResult(ok=False, reason="Coupon inactive", discount=Money(0, currency))
    if coupon.expiration_date and coupon.expiration_date <= now:
        return DiscountResult(ok=False, reason="Coupon expired", discount=Money(0, currency))

    total_red, per_user_red = _count_redemptions(coupon, transaction.user_id)
    if coupon.max_redemptions is not None and total_red >= coupon.max_redemptions:
        return DiscountResult(ok=False, reason="Coupon redemption limit reached", discount=Money(0, currency))
    if coupon.max_per_user is not None and per_user_red >= coupon.max_per_user:
        return DiscountResult(ok=False, reason="Per-user redemption limit reached", discount=Money(0, currency))

    if user_coupon:
        if user_coupon.user_id != transaction.user_id:
            return DiscountResult(ok=False, reason="This coupon does not belong to the user", discount=Money(0, currency))
        if user_coupon.redeemed:
            return DiscountResult(ok=False, reason="User coupon already redeemed", discount=Money(0, currency))

    base = _base_total_for(transaction)
    if coupon.min_purchase_value and base < coupon.min_purchase_value:
        return DiscountResult(ok=False, reason="Minimum purchase value not met", discount=Money(0, base.currency))

    discount = _apply_coupon_value(coupon, base)
    return DiscountResult(ok=True, reason=None, discount=discount)
