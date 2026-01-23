from __future__ import annotations
import django_filters
from django.db.models import Q
from services.models import ListingPackage


class ListingPackageFilter(django_filters.FilterSet):
    item_type = django_filters.CharFilter(field_name="item_type__public_id", lookup_expr="exact")
    item_type_path = django_filters.CharFilter(field_name="item_type__path", lookup_expr="exact")
    search = django_filters.CharFilter(method="filter_search")
    price_min = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    price_max = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    points_min = django_filters.NumberFilter(field_name="points", lookup_expr="gte")
    points_max = django_filters.NumberFilter(field_name="points", lookup_expr="lte")

    class Meta:
        model = ListingPackage
        fields = ["item_type", "item_type_path", "search", "price_min", "price_max", "points_min", "points_max"]

    def filter_search(self, qs, name, value):
        v = (value or "").strip()
        return qs if not v else qs.filter(Q(item_type__name__icontains=v))
