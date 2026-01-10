from __future__ import annotations
import django_filters
from django.db.models import Q
from django.utils import timezone
from coupons.models import Coupon, UserCoupon


class CouponFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_q")  # wyszukiwanie po code
    active = django_filters.BooleanFilter(field_name="active")
    discount_type = django_filters.CharFilter(field_name="discount_type", lookup_expr="exact")

    # dostępność do zakupu za punkty
    purchasable = django_filters.BooleanFilter(method="filter_purchasable")

    # daty ważności
    exp_from = django_filters.DateTimeFilter(field_name="expiration_date", lookup_expr="gte")
    exp_to   = django_filters.DateTimeFilter(field_name="expiration_date", lookup_expr="lte")

    # koszty punktowe zakres
    points_min = django_filters.NumberFilter(field_name="points_cost", lookup_expr="gte")
    points_max = django_filters.NumberFilter(field_name="points_cost", lookup_expr="lte")

    class Meta:
        model = Coupon
        fields = ["q","active","discount_type","purchasable","exp_from","exp_to","points_min","points_max"]

    def filter_q(self, qs, name, value):
        v = (value or "").strip()
        return qs if not v else qs.filter(Q(code__icontains=v))

    def filter_purchasable(self, qs, name, value: bool):
        now = timezone.now()
        base = qs.filter(points_cost__isnull=False, active=True)\
                 .filter(Q(expiration_date__isnull=True) | Q(expiration_date__gt=now))
        if value:
            return base.filter(Q(quantity__isnull=True) | Q(quantity__gt=0))
        # niekupowalne - odwrotność powyższego
        return qs.exclude(pk__in=base.filter(Q(quantity__isnull=True) | Q(quantity__gt=0)).values("pk"))

class UserCouponFilter(django_filters.FilterSet):
    redeemed = django_filters.BooleanFilter(field_name="redeemed")

    class Meta:
        model = UserCoupon
        fields = ["redeemed"]