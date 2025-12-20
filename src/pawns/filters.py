from __future__ import annotations
import django_filters
from django.db.models import TextField
from django.db.models.functions import Cast
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
        qs = qs.annotate(_snapshot_txt=Cast("customer_snapshot", output_field=TextField()))
        return qs.filter(_snapshot_txt__icontains=v)
