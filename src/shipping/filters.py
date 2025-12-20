from __future__ import annotations
import django_filters
from djmoney.money import Money
from django.db.models import Q
from .models import PackageType, ShippingAddress


class PackageTypeFilter(django_filters.FilterSet):
    provider = django_filters.CharFilter(field_name="provider", lookup_expr="exact")
    currency = django_filters.CharFilter(field_name="price_currency", lookup_expr="iexact")
    price_min = django_filters.NumberFilter(method="filter_price_min")
    price_max = django_filters.NumberFilter(method="filter_price_max")
    points_min = django_filters.NumberFilter(field_name="points", lookup_expr="gte")
    points_max = django_filters.NumberFilter(field_name="points", lookup_expr="lte")

    # Dopasowanie po wymiarach/wadze: <= limitów (NULL = brak limitu, więc zawsze przechodzi)
    length_cm = django_filters.NumberFilter(method="filter_fits")
    width_cm  = django_filters.NumberFilter(method="filter_fits")
    height_cm = django_filters.NumberFilter(method="filter_fits")
    weight_kg = django_filters.NumberFilter(method="filter_fits")

    class Meta:
        model = PackageType
        fields = ("provider", "currency", "points_min", "points_max")

    def filter_price_min(self, qs, name, value):
        cur = (self.data.get("currency") or "PLN").upper()
        return qs.filter(price__gte=Money(value, cur))

    def filter_price_max(self, qs, name, value):
        cur = (self.data.get("currency") or "PLN").upper()
        return qs.filter(price__lte=Money(value, cur))

    def filter_fits(self, qs, name, value):
        def _num(val, caster):
            if val in (None, "", []):
                return None
            try:
                return caster(val)
            except Exception:
                return None
        length = _num(self.data.get("length_cm"), int)
        width = _num(self.data.get("width_cm"), int)
        height = _num(self.data.get("height_cm"), int)
        weight = _num(self.data.get("weight_kg"), float)

        def cmp(field, v):
            return Q(**{f"{field}__gte": v}) | Q(**{f"{field}__isnull": True})

        q = Q()
        if length is not None: q &= cmp("max_length_cm", length)
        if width is not None: q &= cmp("max_width_cm", width)
        if height is not None: q &= cmp("max_height_cm", height)
        if weight is not None: q &= cmp("max_weight_kg", weight)
        return qs.filter(q)


class ShippingAddressFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_q")
    user_email = django_filters.CharFilter(field_name="user__email", lookup_expr="icontains")
    city = django_filters.CharFilter(field_name="city", lookup_expr="icontains")
    country = django_filters.CharFilter(field_name="country", lookup_expr="icontains")

    class Meta:
        model = ShippingAddress
        fields = ("q", "user_email", "city", "country")

    def filter_q(self, qs, name, value):
        v = (value or "").strip()
        if not v:
            return qs
        return qs.filter(
            Q(user__email__icontains=v) |
            Q(city__icontains=v) |
            Q(country__icontains=v) |
            Q(first_name__icontains=v) |
            Q(last_name__icontains=v)
        )
