from __future__ import annotations
import django_filters
from django.contrib.auth import get_user_model
from .models import SellerProfile, SellerBankAccount, SellerMembership
from django.db.models import Q

User = get_user_model()

class UserFilter(django_filters.FilterSet):
    email = django_filters.CharFilter(field_name="email", lookup_expr="icontains")
    role = django_filters.CharFilter(field_name="role", lookup_expr="exact")
    user_status = django_filters.CharFilter(field_name="user_status", lookup_expr="exact")
    is_active = django_filters.BooleanFilter(field_name="is_active")
    joined_after = django_filters.IsoDateTimeFilter(field_name="date_joined", lookup_expr="gte")
    joined_before = django_filters.IsoDateTimeFilter(field_name="date_joined", lookup_expr="lte")

    class Meta:
        model = User
        fields = ["email", "role", "user_status", "is_active"]

class SellerProfileFilter(django_filters.FilterSet):
    company = django_filters.CharFilter(field_name="company_name", lookup_expr="icontains")
    slug = django_filters.CharFilter(field_name="slug", lookup_expr="exact")
    rating_min = django_filters.NumberFilter(field_name="rating", lookup_expr="gte")

    class Meta:
        model = SellerProfile
        fields = ["company", "slug", "rating_min"]

class SellerBankAccountFilter(django_filters.FilterSet):
    iban = django_filters.CharFilter(field_name="iban", lookup_expr="icontains")
    is_active = django_filters.BooleanFilter(field_name="is_active")
    is_default = django_filters.BooleanFilter(field_name="is_default")
    seller_slug = django_filters.CharFilter(field_name="seller_profile__slug", lookup_expr="exact")
    seller_public_id = django_filters.CharFilter(field_name="seller_profile__public_id", lookup_expr="exact")

    class Meta:
        model = SellerBankAccount
        fields = ["iban", "is_active", "is_default", "seller_slug", "seller_public_id"]

class SellerMembershipFilter(django_filters.FilterSet):
    role = django_filters.CharFilter(field_name="role", lookup_expr="exact")
    is_active = django_filters.BooleanFilter(field_name="is_active")
    joined_after  = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    joined_before = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = SellerMembership
        fields = ["role", "is_active"]

class UserCandidateFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="by_search")
    role = django_filters.CharFilter(field_name="role", lookup_expr="exact")
    email = django_filters.CharFilter(field_name="email", lookup_expr="icontains")
    first_name = django_filters.CharFilter(field_name="first_name", lookup_expr="icontains")
    last_name = django_filters.CharFilter(field_name="last_name", lookup_expr="icontains")

    def by_search(self, qs, name, value):
        v = (value or "").strip()
        if not v:
            return qs
        return qs.filter(
            Q(email__icontains=v) |
            Q(first_name__icontains=v) |
            Q(last_name__icontains=v) |
            Q(public_id__iexact=v) |
            Q(phone_number__icontains=v)
        )

    class Meta:
        model = User
        fields = ["search", "role", "email", "first_name", "last_name"]