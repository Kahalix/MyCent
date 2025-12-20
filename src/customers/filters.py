from __future__ import annotations
import django_filters
from django.db.models import Q
from customers.models import Customer


def _digits_only(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


class CustomerFilter(django_filters.FilterSet):

    q = django_filters.CharFilter(method="filter_search", label="q")
    search = django_filters.CharFilter(method="filter_search", label="search")

    city = django_filters.CharFilter(field_name="city", lookup_expr="iexact")
    postal_code = django_filters.CharFilter(field_name="postal_code", lookup_expr="iexact")
    document_number = django_filters.CharFilter(field_name="document_number", lookup_expr="iexact")
    email = django_filters.CharFilter(field_name="email", lookup_expr="iexact")

    phone = django_filters.CharFilter(method="filter_phone")

    class Meta:
        model = Customer
        fields = ["q", "search", "city", "postal_code", "document_number", "email", "phone"]

    def filter_search(self, qs, name, value):
        v = (value or "").strip()
        if not v:
            return qs
        vd = _digits_only(v)
        q_obj = (
            Q(first_name__icontains=v) | Q(last_name__icontains=v)
            | Q(email__icontains=v) | Q(phone__icontains=v)
            | Q(address_line1__icontains=v) | Q(address_line2__icontains=v)
            | Q(city__icontains=v) | Q(postal_code__icontains=v)
            | Q(document_number__icontains=v)
        )
        if vd:
            q_obj = q_obj | Q(phone__icontains=vd)
        return qs.filter(q_obj)

    def filter_phone(self, qs, name, value):
        v = (value or "").strip()
        if not v:
            return qs
        vd = _digits_only(v)
        if vd:
            return qs.filter(Q(phone__iexact=v) | Q(phone__icontains=vd))
        return qs.filter(phone__iexact=v)
