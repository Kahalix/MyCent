from __future__ import annotations
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from coupons.filters import CouponFilter, UserCouponFilter
from coupons.models import Coupon, UserCoupon
from coupons.serializers import (
    CouponResponse, CouponCreateUpdateRequest,
    UserCouponResponse, PurchaseCouponRequest,
)
from coupons.services import commands, queries
from identity.permissions import IsAdmin
from transactions.services.discounts import validate_and_compute_discount
from transactions.services.repositories import get_tx_by_public_id


# ===== USER =====
class UserCouponViewSet(mixins.ListModelMixin,
                        mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserCouponResponse
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = UserCouponFilter
    ordering_fields = ("created_at", "purchased_at", "redeemed_at")

    def get_queryset(self):
        return queries.list_user_coupons(self.request.user)

    def list(self, request, *args, **kwargs):
        usable_for_tx = request.query_params.get("usable_for_tx", "").strip()
        if not usable_for_tx:
            return super().list(request, *args, **kwargs)

        tx = get_tx_by_public_id(usable_for_tx)
        if not tx or tx.user_id != request.user.id:
            return Response([], status=200)

        if tx.type != "PURCHASE":
            return Response([], status=200)

        base_qs = self.get_queryset().filter(redeemed=False)
        usable = []
        for uc in base_qs.select_related("coupon"):
            dr = validate_and_compute_discount(transaction=tx, coupon=uc.coupon, user_coupon=uc)
            if dr.ok:
                usable.append(uc)
        return Response(UserCouponResponse(usable, many=True).data, status=200)

    @action(detail=False, methods=["get"], url_path="catalog")
    def catalog(self, request):
        items = queries.list_catalog_for_user_purchase()
        return Response(CouponResponse(items, many=True).data, status=200)

    @action(detail=False, methods=["post"], url_path="purchase")
    def purchase(self, request):
        ser = PurchaseCouponRequest(data=request.data); ser.is_valid(raise_exception=True)
        uc = commands.purchase_coupon_for_user(user=request.user, coupon_public_id=ser.validated_data["coupon_public_id"])
        return Response(UserCouponResponse(uc).data, status=201)


# ===== ADMIN =====
class AdminCouponViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    serializer_class = CouponResponse
    lookup_field = "public_id"
    queryset = Coupon.objects.all().order_by("-created_at")

    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = CouponFilter
    ordering_fields = ("created_at", "expiration_date", "points_cost")

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CouponCreateUpdateRequest
        return CouponResponse
