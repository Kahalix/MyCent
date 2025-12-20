from __future__ import annotations
import django_filters
from djmoney.money import Money
from django.db.models import Q, Exists, OuterRef

from catalog.models import ItemType
from .models import ItemSet, ItemSetShipping
from shipping.models import PackageType


class ItemSetFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search")

    added_by = django_filters.CharFilter(field_name="added_by", lookup_expr="exact")
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    statuses = django_filters.CharFilter(method="filter_statuses")
    listing_type = django_filters.CharFilter(field_name="listing_type", lookup_expr="exact")
    type_id = django_filters.UUIDFilter(field_name="type_id")
    type_public_id = django_filters.CharFilter(field_name="type__public_id", lookup_expr="exact")
    seller_slug = django_filters.CharFilter(field_name="seller_profile__slug", lookup_expr="exact")
    price_min = django_filters.NumberFilter(method="filter_price_min")
    price_max = django_filters.NumberFilter(method="filter_price_max")
    condition = django_filters.CharFilter(field_name="condition", lookup_expr="exact")
    has_shipping_for = django_filters.CharFilter(method="filter_has_shipping_for")  # package_type public_id
    allow_online_checkout = django_filters.BooleanFilter(field_name="allow_online_checkout")
    type_path = django_filters.CharFilter(method="filter_type_path")
    owner_public_id = django_filters.CharFilter(field_name="owner_user__public_id", lookup_expr="exact")

    class Meta:
        model = ItemSet
        fields = [
            "added_by", "status", "listing_type", "type_id", "seller_slug",
            "condition", "allow_online_checkout", "type_path",
            "owner_public_id",
        ]

    def filter_type_path(self, qs, name, value):
        if not value:
            return qs
        t = ItemType.objects.filter(path=value).only("path").first()
        if not t:
            return qs.none()
        base = t.path
        # równa kategoria LUB potomek (prefix z '/'), żeby nie brać np. 'electronics-old'
        return qs.filter(Q(type__path=base) | Q(type__path__startswith=base + "/")).distinct()

    def filter_search(self, qs, name, value):
        if not value:
            return qs
        return qs.filter(Q(set_name__icontains=value) | Q(description__icontains=value))

    def filter_price_min(self, qs, name, value):
        return qs.filter(price__gte=Money(value, "PLN"))

    def filter_price_max(self, qs, name, value):
        return qs.filter(price__lte=Money(value, "PLN"))

    def filter_owner_public_id(self, qs, name, value):
        if not value:
            return qs

    def filter_statuses(self, qs, name, value):
        """
        Obsługuje ?statuses=CLOSED,RESERVED albo wiele ?statuses=CLOSED&statuses=RESERVED
        """
        raw = []
        if value:
            raw.extend([v.strip() for v in str(value).split(",") if v.strip()])
        try:
            params = self.data.getlist("statuses")
            for p in params:
                raw.extend([v.strip() for v in str(p).split(",") if v.strip()])
        except Exception:
            pass

        vals = sorted({v.upper() for v in raw if v})
        if not vals:
            return qs
        return qs.filter(status__in=vals)

    def filter_has_shipping_for(self, qs, name, value):
        """
        Zwraca oferty, które:
          - mieszczą się w gabarytach/wadze,
          - oraz (mają link do wskazanego PackageType) LUB (nie mają w ogóle żadnych shipping_options).
        Implementacja używa Exists + annotate, zamiast ~Exists w wyrażeniu OR.
        """
        if not value:
            return qs
        pkg = PackageType.objects.filter(public_id=value).first()
        if not pkg:
            return qs.none()

        # warunek na gabaryty/wagę (None = brak limitu)
        def leq(field: str, limit):
            return Q(**{f"{field}__lte": limit}) if limit is not None else Q()

        dims_q = (
            leq("length_cm", pkg.max_length_cm)
            & leq("width_cm",  pkg.max_width_cm)
            & leq("height_cm", pkg.max_height_cm)
        )
        if pkg.max_weight_kg is not None:
            dims_q &= Q(weight_kg__lte=pkg.max_weight_kg)

        # czy oferta ma jakiekolwiek shipping options
        shipping_exists = ItemSetShipping.objects.filter(item_set=OuterRef("pk"))
        qs = qs.filter(dims_q).annotate(has_ship=Exists(shipping_exists))

        # jeśli ma shippingi -> wymagamy relacji do danego pkg; jeśli nie ma -> przepuszczamy
        return qs.filter(Q(has_ship=False) | Q(shipping_options__package_type=pkg)).distinct()
