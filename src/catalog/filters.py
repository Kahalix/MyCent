from __future__ import annotations
import django_filters
from django.db.models import Q
from .models import ItemType, CatalogItem

class ItemTypeFilter(django_filters.FilterSet):
    parent_path = django_filters.CharFilter(method="filter_parent_path")
    q = django_filters.CharFilter(method="filter_q")

    class Meta:
        model = ItemType
        fields = ["parent_path", "q"]

    def filter_parent_path(self, qs, name, value):
        if not value:
            return qs.filter(parent__isnull=True)
        parent = ItemType.objects.filter(path=value).first()
        if not parent:
            return qs.none()
        return qs.filter(parent=parent)

    def filter_q(self, qs, name, value):
        if not value:
            return qs
        return qs.filter(Q(name__icontains=value) | Q(slug__icontains=value))


class CatalogItemFilter(django_filters.FilterSet):
    type_path = django_filters.CharFilter(method="filter_type_path")
    search = django_filters.CharFilter(field_name="item_name", lookup_expr="icontains")

    class Meta:
        model = CatalogItem
        fields = ["type_path", "search"]

    def filter_type_path(self, qs, name, value):
        if not value:
            return qs
        t = ItemType.objects.filter(path=value).first()
        if not t:
            return qs.none()
        base = t.path
        return qs.filter(Q(type__path=base) | Q(type__path__startswith=base + "/"))
