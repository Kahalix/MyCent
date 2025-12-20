from __future__ import annotations
import django_filters
from django.db.models import Q
from payments.models import Payment

class CharInFilter(django_filters.BaseInFilter, django_filters.CharFilter):
    pass

class PaymentFilter(django_filters.FilterSet):
    status       = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    provider     = django_filters.CharFilter(field_name="provider", lookup_expr="exact")
    public_id    = django_filters.CharFilter(field_name="public_id", lookup_expr="exact")
    tx           = django_filters.CharFilter(field_name="transaction__public_id", lookup_expr="exact")
    date_from    = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    date_to      = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")
    updated_from = django_filters.DateTimeFilter(field_name="updated_at", lookup_expr="gte")
    updated_to   = django_filters.DateTimeFilter(field_name="updated_at", lookup_expr="lte")
    status_in    = CharInFilter(field_name="status", lookup_expr="in")
    search       = django_filters.CharFilter(method="filter_search")
    active       = django_filters.BooleanFilter(method="filter_active", label="Aktywna płatność")

    class Meta:
        model = Payment
        fields = [
            "status","provider","public_id","tx",
            "date_from","date_to","updated_from","updated_to",
            "status_in","search","active",
        ]

    def filter_search(self, qs, name, value):
        v = (value or "").strip()
        if not v:
            return qs
        return qs.filter(Q(public_id__icontains=v) | Q(transaction__public_id__icontains=v)).distinct()

    def filter_active(self, qs, name, value: bool):
        if value is None:
            return qs
        active_statuses = ["REQUIRES_CONFIRMATION","REQUIRES_ACTION","PROCESSING"]
        return qs.filter(status__in=active_statuses) if value else qs.exclude(status__in=active_statuses)
