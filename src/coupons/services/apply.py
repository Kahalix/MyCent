from __future__ import annotations
from decimal import Decimal
from django.utils import timezone
from djmoney.money import Money

from coupons.models import Coupon, UserCoupon
from coupons.services.exceptions import Conflict, NotFound
from coupons.services import repositories as repo

def _ensure_active_not_expired(c: Coupon):
    if not c.active:
        raise Conflict("Kupon nieaktywny.")
    if c.expiration_date and c.expiration_date <= timezone.now():
        raise Conflict("Kupon wygasł.")

def _ensure_min_purchase(c: Coupon, subtotal: Money):
    mpv = c.min_purchase_value
    if mpv and subtotal.amount < mpv.amount:
        raise Conflict(f"Minimalna wartość zamówienia dla tego kuponu to {mpv}.")

def _discount_for_coupon(c: Coupon, subtotal: Money) -> Money:
    """
    Zwraca Money (zniżka), ograniczoną max_discount_value.
    Dla PERCENTAGE używamy discount_value.amount jako procentu (np. 10 => 10%).
    """
    if subtotal.amount <= 0:
        return Money(0, subtotal.currency)

    if c.discount_type == "PERCENTAGE":
        pct = Decimal(c.discount_value.amount) / Decimal("100")
        disc = Money((Decimal(subtotal.amount) * pct).quantize(Decimal("0.01")), subtotal.currency)
        if c.max_discount_value:
            cap = Money(c.max_discount_value.amount, subtotal.currency)
            if disc > cap:
                disc = cap
        return disc

    # AMOUNT
    want = Money(c.discount_value.amount, subtotal.currency)
    return want if want <= subtotal else subtotal

def compute_discount_by_code(*, code: str, subtotal: Money) -> tuple[Coupon, Money]:
    code = (code or "").strip().upper()
    c = repo.get_coupon_by_code(code)
    if not c:
        raise NotFound("Nieprawidłowy kod kuponu.")
    _ensure_active_not_expired(c)
    _ensure_min_purchase(c, subtotal)
    return c, _discount_for_coupon(c, subtotal)

def compute_discount_by_user_coupon(*, user, user_coupon_public_id: str, subtotal: Money) -> tuple[UserCoupon, Coupon, Money]:
    uc = repo.get_user_coupon_by_public_id(user_coupon_public_id or "")
    if not uc or uc.user_id != user.id:
        raise NotFound("Kupon użytkownika nie istnieje.")
    if uc.redeemed:
        raise Conflict("Kupon został już wykorzystany.")
    c = uc.coupon
    _ensure_active_not_expired(c)
    _ensure_min_purchase(c, subtotal)
    return uc, c, _discount_for_coupon(c, subtotal)
