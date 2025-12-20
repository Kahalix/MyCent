from __future__ import annotations
import django_filters
from django.db.models import Q
from transactions.models import Transaction

class CharInFilter(django_filters.BaseInFilter, django_filters.CharFilter):
    pass

_ACTIVE_PAYMENT_STATUSES = ("REQUIRES_CONFIRMATION","REQUIRES_ACTION","PROCESSING")

class TransactionFilter(django_filters.FilterSet):
    public_id = django_filters.CharFilter(field_name="public_id", lookup_expr="exact")
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    status_in = CharInFilter(field_name="status", lookup_expr="in")
    type = django_filters.CharFilter(field_name="type", lookup_expr="exact")
    created_from = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_to   = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")
    updated_from = django_filters.DateTimeFilter(field_name="updated_at", lookup_expr="gte")
    updated_to   = django_filters.DateTimeFilter(field_name="updated_at", lookup_expr="lte")
    # Czy transakcja ma aktywną płatność (pending/processing)
    has_active_payment = django_filters.BooleanFilter(method="filter_has_active_payment")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Transaction
        fields = ["public_id","status","status_in","type",
                  "created_from","created_to","updated_from","updated_to",
                  "has_active_payment","search"]

    def filter_search(self, qs, name, value):
        v = (value or "").strip()
        if not v: return qs
        return qs.filter(Q(public_id__icontains=v) | Q(notes__icontains=v))

    def filter_has_active_payment(self, qs, name, value: bool):
        expr = {"payments__status__in": _ACTIVE_PAYMENT_STATUSES}
        if value is True:
            return qs.filter(**expr).distinct()
        if value is False:
            return qs.exclude(**expr).distinct()
        return qs