from __future__ import annotations
from rest_framework import viewsets, permissions
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from identity.permissions import IsAdmin
from customers.models import Customer
from customers.serializers import CustomerResponse, CustomerCreateUpdateRequest
from customers.filters import CustomerFilter
from customers.services import queries


def _ensure_staff_membership(request) -> bool:
    from identity.models import SellerProfile
    return SellerProfile.objects.filter(memberships__user=request.user, memberships__is_active=True).exists()


# ===== SELLER =====
class SellerCustomerViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CustomerResponse
    lookup_field = "public_id"

    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = CustomerFilter
    ordering_fields = ("created_at","last_name","first_name","city")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not _ensure_staff_membership(request):
            self.permission_denied(request, message="Brak uprawnień (wymagana aktywna rola w sklepie).")

    def get_queryset(self):
        return queries.seller_customers_qs(self.request.user)

    def get_serializer_class(self):
        if self.action in ("create","update","partial_update"):
            return CustomerCreateUpdateRequest
        return CustomerResponse


# ===== ADMIN =====
class AdminCustomerViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    serializer_class = CustomerResponse
    lookup_field = "public_id"

    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = CustomerFilter
    ordering_fields = ("created_at","last_name","first_name","city")

    def get_queryset(self):
        return queries.admin_customers_qs()

    def get_serializer_class(self):
        if self.action in ("create","update","partial_update"):
            return CustomerCreateUpdateRequest
        return CustomerResponse
