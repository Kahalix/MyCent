from __future__ import annotations
from typing import Optional
from django.db.models import Q
from django.utils import timezone

from coupons.models import Coupon, UserCoupon
from identity.models import User


def get_coupon_by_public_id(public_id: str) -> Optional[Coupon]:
    return Coupon.objects.filter(public_id=public_id).first()


def get_coupon_by_code(code: str) -> Optional[Coupon]:
    c = (code or "").strip()
    if not c:
        return None
    return Coupon.objects.filter(code__iexact=c).first()


def list_active_for_purchase() -> list[Coupon]:
    now = timezone.now()
    qs = Coupon.objects.filter(
        active=True
    ).filter(
        Q(expiration_date__isnull=True) | Q(expiration_date__gt=now)
    ).filter(
        points_cost__isnull=False
    )
    # quantity==None => unlimited; gdy >0 => dostępne
    return [c for c in qs if (c.quantity is None or c.quantity > 0)]


def create_user_coupon(*, user: User, coupon: Coupon, points_paid: int | None) -> UserCoupon:
    return UserCoupon.objects.create(user=user, coupon=coupon, points_paid=points_paid)

def get_user_coupon_by_public_id(public_id: str) -> Optional[UserCoupon]:
    return UserCoupon.objects.select_related("coupon","user").filter(public_id=public_id).first()