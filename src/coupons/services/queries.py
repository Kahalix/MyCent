from __future__ import annotations

from django.utils import timezone
from django.db.models import Q

from coupons.models import Coupon, UserCoupon


def list_catalog_for_user_purchase():
    """
    Katalog kuponów do zakupu za punkty:
    - aktywne,
    - nieprzeterminowane,
    - mają ustawiony points_cost,
    - mają dostępność (quantity IS NULL lub > 0).
    Zwraca QuerySet, żeby można było dalej filtrować / paginować.
    """
    now = timezone.now()
    return (
        Coupon.objects
        .filter(active=True, points_cost__isnull=False)
        .filter(Q(expiration_date__isnull=True) | Q(expiration_date__gt=now))
        .filter(Q(quantity__isnull=True) | Q(quantity__gt=0))
        .order_by("-created_at")
    )


def list_user_coupons(user, *, redeemed: bool | None = None):
    """
    Kupony użytkownika (przypisane), opcjonalnie filtrowanie po statusie wykorzystania.
    """
    qs = (
        UserCoupon.objects
        .select_related("coupon")
        .filter(user=user)
        .order_by("-created_at")
    )
    if redeemed is not None:
        qs = qs.filter(redeemed=redeemed)
    return qs
