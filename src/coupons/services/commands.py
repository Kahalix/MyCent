from __future__ import annotations
from django.db import transaction as dbtx
from django.utils import timezone
from django.db.models import F

from coupons.models import Coupon, UserCoupon
from coupons.services import repositories as repo
from coupons.services.exceptions import DomainError, NotFound, Conflict, Forbidden
from coupons.services.points_backend import spend_points


def _assert_coupon_buyable(c: Coupon):
    if not c.active:
        raise Conflict("Kupon nieaktywny.")
    if c.expiration_date and c.expiration_date <= timezone.now():
        raise Conflict("Kupon wygasł.")
    if c.points_cost is None:
        raise Conflict("Tego kuponu nie można kupić za punkty.")
    if c.quantity is not None and c.quantity <= 0:
        raise Conflict("Brak kuponów w puli.")


@dbtx.atomic
def purchase_coupon_for_user(*, user, coupon_public_id: str) -> UserCoupon:
    c = Coupon.objects.select_for_update().filter(public_id=coupon_public_id).first()
    if not c:
        raise NotFound("Kupon nie istnieje.")
    _assert_coupon_buyable(c)
    try:
        spend_points(user, int(c.points_cost or 0), reason=f"Zakup kuponu {c.public_id}")
    except Exception as e:
        raise Conflict(str(e))
    uc = repo.create_user_coupon(user=user, coupon=c, points_paid=int(c.points_cost or 0))
    uc.purchased_at = timezone.now()
    uc.save(update_fields=["purchased_at", "updated_at"])
    if c.quantity is not None:
        if c.quantity <= 0:
            raise Conflict("Brak kuponów w puli.")
        c.quantity = F("quantity") - 1
        c.save(update_fields=["quantity", "updated_at"])
    return uc
