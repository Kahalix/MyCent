from __future__ import annotations
from typing import Optional
from django.db import transaction as dbtx
from djmoney.money import Money
from decimal import Decimal

from transactions.models import Transaction
from coupons.models import Coupon, UserCoupon
from transactions.services.repositories import save_transaction
from transactions.services.discounts import validate_and_compute_discount, _base_total_for
from transactions.services.exceptions import DomainError, Conflict


_VALID_TX_TRANSITIONS = {
    "PENDING": {"COMPLETED", "CANCELLED"},
    "COMPLETED": {"REFUNDED"},
    "CANCELLED": set(),
    "REFUNDED": set(),
}

def _format_amount_2(amount) -> str:
    if isinstance(amount, Decimal):
        d = amount
    else:
        d = Decimal(str(amount))
    return str(d.quantize(Decimal("0.01")))


def _map_discount_reason_to_message(reason: str | None) -> str:
    mapping = {
        "Coupon inactive": "Kupon nieaktywny.",
        "Coupon expired": "Kupon wygasł.",
        "Coupon redemption limit reached": "Przekroczono maksymalną liczbę użyć tego kuponu.",
        "Per-user redemption limit reached": "Przekroczono maksymalną liczbę użyć kuponu przez tego użytkownika.",
        "This coupon does not belong to the user": "Ten kupon nie należy do użytkownika.",
        "User coupon already redeemed": "Ten kupon użytkownika został już wykorzystany.",
        "Minimum purchase value not met": "Minimalna wartość zamówienia dla tego kuponu nie została osiągnięta.",
        "Coupons are not allowed for this transaction.": "Kupony nie są dostępne dla tej transakcji.",
    }
    if not reason:
        return "Nie udało się zastosować kuponu."
    return mapping.get(reason, "Nie udało się zastosować kuponu.")


@dbtx.atomic
def attach_coupon_and_recalculate(
    *, transaction: Transaction,
    coupon_code: Optional[str] = None,
    user_coupon_public_id: Optional[str] = None
) -> Transaction:
    if transaction.type != "PURCHASE":
        raise DomainError("Kupony nie są dostępne dla tej transakcji.")

    coupon: Optional[Coupon] = None
    user_coupon: Optional[UserCoupon] = None

    coupon_code = (coupon_code or "").strip()
    user_coupon_public_id = (user_coupon_public_id or "").strip()

    if coupon_code and user_coupon_public_id:
        raise Conflict("Podaj kod kuponu albo kupon użytkownika, nie oba naraz.")

    if coupon_code:
        coupon = Coupon.objects.filter(code__iexact=coupon_code).first()
        if not coupon:
            raise DomainError("Nieprawidłowy kod kuponu.")

    if user_coupon_public_id:
        user_coupon = (
            UserCoupon.objects
            .select_related("coupon", "user")
            .filter(public_id=user_coupon_public_id)
            .first()
        )
        if not user_coupon:
            raise DomainError("Kupon użytkownika nie istnieje.")

    if not coupon and not user_coupon:
        transaction.coupon = None
        transaction.user_coupon = None
        _recompute_expected_total(transaction, user_coupon=None)
        transaction.save(update_fields=["coupon", "user_coupon", "expected_total_amount", "expected_total_currency", "updated_at"])
        return transaction

    if user_coupon and user_coupon.user_id != transaction.user_id:
        raise Conflict("Ten kupon użytkownika nie należy do tego klienta.")

    if coupon is None and user_coupon is not None:
        coupon = user_coupon.coupon

    dr = validate_and_compute_discount(transaction=transaction, coupon=coupon, user_coupon=user_coupon)

    if not dr.ok:
        msg = _map_discount_reason_to_message(dr.reason)
        raise Conflict(msg)

    transaction.coupon = coupon
    transaction.user_coupon = user_coupon
    _recompute_expected_total(transaction, user_coupon=user_coupon)
    transaction.save(update_fields=["coupon", "user_coupon", "expected_total_amount", "expected_total_currency", "updated_at"])
    return transaction

def _recompute_expected_total(transaction: Transaction, user_coupon: Optional[UserCoupon] = None) -> None:
    """
    expected_total = (suma grand_total orderów) - rabat (>= 0).
    Dla typów innych niż PURCHASE nic nie przeliczamy (kwota jest np. opłatą za przedłużenie).
    """
    if transaction.type != "PURCHASE":
        # ZACHOWAJ kwotę ustawioną wcześniej (np. fee przy PAWN_EXTENSION)
        if not transaction.expected_total_currency:
            transaction.expected_total_currency = "PLN"
        return

    if user_coupon is None:
        user_coupon = getattr(transaction, "user_coupon", None)

    currency = transaction.expected_total_currency or "PLN"

    gross = Money(0, currency)
    for o in transaction.orders.all():
        gt = o.grand_total
        if gt.currency != gross.currency:
            gt = Money(gt.amount, gross.currency)
        gross += gt

    dr = validate_and_compute_discount(transaction=transaction, coupon=transaction.coupon, user_coupon=user_coupon)
    discount = dr.discount if dr.ok else Money(0, gross.currency)

    total = gross - discount
    if total.amount < 0:
        total = Money(0, gross.currency)

    transaction.expected_total_amount = total.amount
    transaction.expected_total_currency = total.currency.code


@dbtx.atomic
def set_transaction_status(*, tx: Transaction, to_status: str, reason: str = "") -> Transaction:
    allowed_statuses = {"PENDING", "COMPLETED", "CANCELLED", "REFUNDED"}
    if to_status not in allowed_statuses:
        raise DomainError("Invalid status")
    allowed = _VALID_TX_TRANSITIONS.get(tx.status, set())
    if to_status not in allowed and to_status != tx.status:
        raise Conflict(f"Transition {tx.status} → {to_status} not allowed")

    tx.status = to_status
    tx.save(update_fields=["status", "updated_at"])

    if to_status == "COMPLETED" and tx.user_coupon_id and tx.type == "PURCHASE":
        uc = tx.user_coupon
        if uc and not uc.redeemed:
            from django.utils import timezone
            uc.redeemed = True
            uc.redeemed_at = timezone.now()
            uc.save(update_fields=["redeemed", "redeemed_at", "updated_at"])

    if to_status == "REFUNDED" and tx.user_coupon_id and tx.type == "PURCHASE":
        uc = tx.user_coupon
        if uc and uc.redeemed:
            uc.redeemed = False
            uc.redeemed_at = None
            uc.save(update_fields=["redeemed", "redeemed_at", "updated_at"])

    return tx

@dbtx.atomic
def preview_coupon_discount(
    *, tx: Transaction, coupon_code: Optional[str] = None, user_coupon_public_id: Optional[str] = None
) -> dict:
    """
    Podgląd rabatu bez zapisywania na transakcji.
    Dla typów =/= PURCHASE zwracamy info, że kupony są niedostępne.
    """
    if tx.type != "PURCHASE":
        cur = tx.expected_total_currency or "PLN"
        from djmoney.money import Money as _M
        base = _M(tx.expected_total_amount or 0, cur)
        gross_str = _format_amount_2(base.amount)
        return {
            "ok": False,
            "reason": "Coupons are not available for this transaction.",
            "currency": str(base.currency),
            "gross_amount": gross_str,
            "discount_amount": "0.00",
            "net_amount": gross_str,
            "coupon_public_id": None,
            "user_coupon_public_id": None,
        }

    coupon = None
    user_coupon = None
    if coupon_code:
        coupon = Coupon.objects.filter(code__iexact=coupon_code.strip()).first()
    elif user_coupon_public_id:
        user_coupon = UserCoupon.objects.select_related("coupon").filter(public_id=user_coupon_public_id.strip()).first()
        coupon = user_coupon.coupon if user_coupon else None

    base = _base_total_for(tx)  # suma grand_total orderów
    dr = validate_and_compute_discount(transaction=tx, coupon=coupon, user_coupon=user_coupon)

    discount = dr.discount if dr.ok else Money(0, base.currency)
    net = base - discount
    if net.amount < 0:
        net = Money(0, base.currency)

    gross_str = _format_amount_2(base.amount)
    discount_str = _format_amount_2(discount.amount)
    net_str = _format_amount_2(net.amount)

    return {
        "ok": dr.ok,
        "reason": dr.reason,
        "currency": str(base.currency),
        "gross_amount": gross_str,
        "discount_amount": discount_str,
        "net_amount": net_str,
        "coupon_public_id": getattr(coupon, "public_id", None),
        "user_coupon_public_id": getattr(user_coupon, "public_id", None),
    }


@dbtx.atomic
def cancel_stale_pending_transactions(*, minutes: int = 60) -> int:
    from django.utils import timezone
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(minutes=minutes)
    qs = Transaction.objects.select_for_update().filter(status="PENDING", updated_at__lt=cutoff)
    count = 0
    for tx in qs:
        set_transaction_status(tx=tx, to_status="CANCELLED", reason="Auto-cancelled: pending too long")
        count += 1
    return count
