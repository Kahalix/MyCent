from __future__ import annotations
import django_filters
from django.db.models import Q
from orders.models import Order

class OrderFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="order_status", lookup_expr="exact")
    date_from = django_filters.DateFilter(field_name="purchase_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="purchase_date", lookup_expr="lte")
    search = django_filters.CharFilter(method="filter_search")
    tx = django_filters.CharFilter(field_name="transaction__public_id", lookup_expr="exact")

    tx_type = django_filters.CharFilter(field_name="transaction__type", lookup_expr="exact")
    kind = django_filters.CharFilter(method="filter_kind")  # 'pawn' | 'sale'

    class Meta:
        model = Order
        fields = ["status", "date_from", "date_to", "search", "tx_type", "kind", "tx"]

    def filter_search(self, qs, name, value):
        if not value: return qs
        return qs.filter(Q(order_name__icontains=value) | Q(description__icontains=value))

    def filter_kind(self, qs, name, value):
        v = (value or "").lower()
        if v == "pawn":
            return qs.filter(transaction__type="PAWN_PURCHASE")
        if v == "sale":
            return qs.exclude(transaction__type="PAWN_PURCHASE")
        return qs
