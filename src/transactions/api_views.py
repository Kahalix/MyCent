from __future__ import annotations
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from transactions.filters import TransactionFilter

from identity.permissions import IsAdmin
from transactions.models import Transaction
from transactions.serializers import (
    TransactionResponse, AttachCouponRequest, TransactionStatusUpdateRequest
)
from transactions.services.commands import attach_coupon_and_recalculate, set_transaction_status, \
    preview_coupon_discount


# ====== USER ======
class UserTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    /api/users/me/transactions/...
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TransactionResponse
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = TransactionFilter
    ordering_fields = ("created_at", "updated_at")

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)\
            .select_related("user","coupon","user_coupon")\
            .order_by("-created_at")

    @action(detail=True, methods=["post"], url_path="attach-coupon")
    def attach_coupon(self, request, public_id=None):
        tx = self.get_object()
        ser = AttachCouponRequest(data=request.data); ser.is_valid(raise_exception=True)
        tx = attach_coupon_and_recalculate(
            transaction=tx,
            coupon_code=ser.validated_data.get("coupon_code") or None,
            user_coupon_public_id=ser.validated_data.get("user_coupon_public_id") or None,
        )
        return Response(TransactionResponse(tx).data, status=200)

    @action(detail=True, methods=["post"], url_path="preview-discount")
    def preview_discount(self, request, public_id=None):
        """
        Podgląd rabatu bez zapisywania na transakcji.
        Payload (jeden z pól): {"coupon_code": "..."} lub {"user_coupon_public_id": "..."}
        """
        tx = self.get_object()
        ser = AttachCouponRequest(data=request.data); ser.is_valid(raise_exception=True)
        result = preview_coupon_discount(
            tx=tx,
            coupon_code=ser.validated_data.get("coupon_code") or None,
            user_coupon_public_id=ser.validated_data.get("user_coupon_public_id") or None,
        )
        return Response(result, status=200)


# ====== SELLER ======
class SellerTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    /api/sellers/mine/transactions/...
    Pokazuje transakcje, w których są zamówienia sprzedawcy (dowolnego jego profilu).
    Pozwala zmienić status (symulacja płatności/offline rozliczenie).
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TransactionResponse
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = TransactionFilter
    ordering_fields = ("created_at", "updated_at")

    def get_queryset(self):
        return (
            Transaction.objects
            .filter(orders__seller_profile__memberships__user=self.request.user,
                    orders__seller_profile__memberships__is_active=True)
            .order_by("-created_at")
            .distinct()
        )

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, public_id=None):
        tx = self.get_object()
        ser = TransactionStatusUpdateRequest(data=request.data); ser.is_valid(raise_exception=True)
        tx = set_transaction_status(tx=tx, to_status=ser.validated_data["status"], reason=ser.validated_data.get("reason", ""))
        return Response(TransactionResponse(tx).data, status=200)


# ====== ADMIN ======
class AdminTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    /api/admin/transactions/...
    """
    permission_classes = [IsAdmin]
    serializer_class = TransactionResponse
    lookup_field = "public_id"

    def get_queryset(self):
        return Transaction.objects.all().order_by("-created_at")

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, public_id=None):
        tx = self.get_object()
        ser = TransactionStatusUpdateRequest(data=request.data); ser.is_valid(raise_exception=True)
        tx = set_transaction_status(tx=tx, to_status=ser.validated_data["status"], reason=ser.validated_data.get("reason", ""))
        return Response(TransactionResponse(tx).data, status=200)
