from __future__ import annotations

import django_filters
from django.db.models import Q
from pawns.models import Pawn


class PawnFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    due_from = django_filters.DateFilter(field_name="due_date", lookup_expr="gte")
    due_to   = django_filters.DateFilter(field_name="due_date", lookup_expr="lte")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Pawn
        fields = ["status","due_from","due_to","search"]

    def filter_search(self, qs, name, value):
        v = (value or "").strip()
        if not v:
            return qs
        return qs.filter(
            Q(customer__email__icontains=v) |
            Q(customer__phone__icontains=v) |
            Q(customer__first_name__icontains=v) |
            Q(customer__last_name__icontains=v) |
            Q(customer_snapshot__email__icontains=v) |
            Q(customer_snapshot__phone__icontains=v) |
            Q(customer_snapshot__first_name__icontains=v) |
            Q(customer_snapshot__last_name__icontains=v)
        )
