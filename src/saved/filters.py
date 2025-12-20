from __future__ import annotations
import django_filters
from django.db.models import Q
from .models import SavedListing, SavedSearch

class SavedListingFilter(django_filters.FilterSet):
    class Meta:
        model = SavedListing
        fields = []

class SavedSearchFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_q")

    class Meta:
        model = SavedSearch
        fields = ["q"]

    def filter_q(self, qs, name, value):
        v = (value or "").strip()
        if not v:
            return qs
        return qs.filter(Q(search_phrase__icontains=v) | Q(category_path__icontains=v))
