from __future__ import annotations
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework import viewsets, mixins, permissions
from rest_framework.decorators import action

from customers.models import Customer
from .services import commands as cmd
from rest_framework.response import Response

from identity.permissions import IsAdmin, IsSellerMember, IsAnyActiveSellerMember
from identity.models import SellerProfile, SellerMembership
from orders.models import Order, OrderShipping, OrderLine
from orders.serializers import (
    OrderPublicResponse, CheckoutRequest,
    OrderLineShippingCreateRequest, OrderShippingResponse, OrderShippingStatusUpdateRequest,
    SellerOfflineCheckoutRequest, SellerPawnPurchaseRequest, BuyerShippingSelectRequest, OrderShippingAddressRequest,
    OrderShippingPatchRequest
)
from orders.filters import OrderFilter
from orders.services import commands, queries
from shipping.models import PackageType

from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from .services.commands import seller_pawn_purchase, build_receipt_pdf, build_receipt_csv, ensure_customer_for_order, \
    detach_customer_from_order, attach_customer_to_order
from .services.printing_csv import export_orders_csv, export_orders_summary_csv

ADMIN_ROLES = {"OWNER", "MANAGER"}

def can_full_export_for_queryset(*, user, qs) -> bool:
    seller_ids = list(qs.values_list("seller_profile_id", flat=True).distinct())
    if not seller_ids:
        return False
    admin_ids = set(
        SellerMembership.objects.filter(
            user=user,
            is_active=True,
            role__in=list(ADMIN_ROLES),
            seller_profile_id__in=seller_ids
        ).values_list("seller_profile_id", flat=True)
    )
    return admin_ids.issuperset(set(seller_ids))

User = get_user_model()

# ===== BUYER =====
class BuyerOrderViewSet(mixins.ListModelMixin,
                        mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderPublicResponse
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = OrderFilter
    ordering_fields = ("created_at","purchase_date")

    def get_queryset(self):
        return queries.list_buyer_orders(self.request.user)

    @action(detail=False, methods=["post"], url_path="checkout")
    def checkout(self, request):
        ser = CheckoutRequest(data=request.data); ser.is_valid(raise_exception=True)
        o = commands.checkout_single_item(buyer=request.user, **ser.validated_data)
        return Response(OrderPublicResponse(o).data, status=201)

    @action(detail=True, methods=["post"], url_path="lines/(?P<line_public_id>[^/]+)/select-shipping")
    def select_line_shipping(self, request, public_id=None, line_public_id=None):
        order = self.get_object()
        line = get_object_or_404(OrderLine, order=order, public_id=line_public_id)
        ser = BuyerShippingSelectRequest(data=request.data);
        ser.is_valid(raise_exception=True)

        mode = ser.validated_data["mode"]
        pkg = None
        if mode == "PACKAGE":
            pkg_pid = ser.validated_data.get("package_type_public_id")
            pkg = get_object_or_404(PackageType, public_id=pkg_pid)

        shipping, cancelled = cmd.buyer_set_line_shipping(order=order, line=line, mode=mode, package_type=pkg)
        resp = Response(OrderShippingResponse(shipping).data, status=200)
        if cancelled:
            resp["X-Active-Payment-Cancelled"] = "1"
        return resp

    @action(detail=True, methods=["post"], url_path="shipping-address")
    def set_shipping_address(self, request, public_id=None):
        order = self.get_object()
        ser = OrderShippingAddressRequest(
            data=request.data,
            context={"request": request, "order": order}
        )
        ser.is_valid(raise_exception=True)
        from orders.services.commands import set_order_shipping_address
        set_order_shipping_address(order=order, address=ser.validated_data)
        from orders.serializers import OrderPublicResponse
        return Response(OrderPublicResponse(order).data, status=200)


# ===== SELLER
from identity.permissions import IsSellerMember, IsAnyActiveSellerMember, IsAnyActiveSellerManagerOrOwner

class SellerOrderViewSet(mixins.ListModelMixin,
                         mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderPublicResponse
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = OrderFilter
    ordering_fields = ("created_at", "purchase_date")

    def get_permissions(self):
        if self.action == "list":
            return [permissions.IsAuthenticated(), IsAnyActiveSellerMember()]
        if self.action == "export_csv":
            return [permissions.IsAuthenticated(), IsAnyActiveSellerManagerOrOwner()]
        return [permissions.IsAuthenticated(), IsSellerMember()]

    def get_queryset(self):
        qs = (
            Order.objects.filter(
                seller_profile__memberships__user=self.request.user,
                seller_profile__memberships__is_active=True
            )
            .select_related("buyer", "transaction", "seller_profile")
            .order_by("-created_at")
            .distinct()
        )

        if self.action == "export_csv":
            admin_seller_ids = SellerMembership.objects.filter(
                user=self.request.user,
                is_active=True,
                role__in=list(ADMIN_ROLES),
            ).values_list("seller_profile_id", flat=True)
            qs = qs.filter(seller_profile_id__in=admin_seller_ids)
            return qs

        return qs.prefetch_related("order_lines__item_set", "shippings")

    @action(detail=True, methods=["post"], url_path="lines/(?P<line_public_id>[^/]+)/shipping")
    def add_line_shipping(self, request, public_id=None, line_public_id=None):
        order = self.get_object()
        line = get_object_or_404(OrderLine, order=order, public_id=line_public_id)
        had = getattr(line, "shipping", None)

        ser = OrderLineShippingCreateRequest(data={**request.data, "order_line_public_id": line_public_id})
        ser.is_valid(raise_exception=True)

        pkg = None
        price = ser.validated_data.get("price")
        pkg_pid = ser.validated_data.get("package_type_public_id")
        if pkg_pid:
            pkg = get_object_or_404(PackageType, public_id=pkg_pid)

        s = commands.seller_add_line_shipping(
            order=order, line=line,
            tracking_number=ser.validated_data.get("tracking_number", ""),
            package_type=pkg,
            price=price,
        )
        return Response(OrderShippingResponse(s).data, status=200 if had else 201)

    @action(detail=True, methods=["patch"],
            url_path="lines/(?P<line_public_id>[^/]+)/shipping/(?P<shipping_public_id>[^/]+)")
    def update_line_shipping_status(self, request, public_id=None, line_public_id=None, shipping_public_id=None):
        order = self.get_object()
        line = get_object_or_404(OrderLine, order=order, public_id=line_public_id)
        shipping = get_object_or_404(OrderShipping, order=order, order_line=line, public_id=shipping_public_id)
        ser = OrderShippingPatchRequest(data=request.data)
        ser.is_valid(raise_exception=True)

        data = ser.validated_data
        if "shipping_status" in data:
            commands.set_shipping_status(shipping=shipping, status=data["shipping_status"])
        if "tracking_number" in data:
            shipping.tracking_number = data["tracking_number"]
            shipping.save(update_fields=["tracking_number", "updated_at"])

        return Response(OrderShippingResponse(shipping).data, status=200)

    @action(detail=False, methods=["post"], url_path="offline-checkout")
    def offline_checkout(self, request):
        ser = SellerOfflineCheckoutRequest(data=request.data)
        ser.is_valid(raise_exception=True)

        seller = SellerProfile.objects.filter(
            memberships__user=request.user, memberships__is_active=True
        ).first()
        if not seller:
            return Response({"detail": "Brak przypisanego profilu sprzedawcy."}, status=403)

        order = cmd.seller_offline_checkout_many(
            seller=seller,
            employee=request.user,
            lines=ser.validated_data["lines"],
            payment_method=ser.validated_data["payment_method"],
            customer_payload=ser.validated_data.get("customer"),
            status="COMPLETED",
        )
        return Response(OrderPublicResponse(order).data, status=201)

    @action(detail=False, methods=["post"], url_path="pawn-purchase")
    def pawn_purchase(self, request):
        ser = SellerPawnPurchaseRequest(data=request.data)
        ser.is_valid(raise_exception=True)

        seller = None
        pid = ser.validated_data.get("seller_public_id")
        if pid:
            seller = get_object_or_404(SellerProfile, public_id=pid,
                                       memberships__user=request.user,
                                       memberships__is_active=True)
        else:
            seller = (SellerProfile.objects
                      .filter(memberships__user=request.user, memberships__is_active=True)
                      .first())
        if not seller:
            return Response({"detail": "Brak przypisanego profilu sprzedawcy."}, status=403)

        order = seller_pawn_purchase(
            seller=seller,
            employee=request.user,
            lines=ser.validated_data["lines"],
            customer_payload=ser.validated_data.get("customer"),
            note=ser.validated_data.get("note", ""),
            purchase_date=ser.validated_data.get("purchase_date"),
            payment_method=ser.validated_data.get("payment_method", "CASH"),
            create_itemsets=ser.validated_data.get("create_itemsets", True),
        )
        return Response(OrderPublicResponse(order).data, status=201)

    @action(detail=True, methods=["get"], url_path="receipt.csv")
    def receipt_csv(self, request, public_id=None):
        order = self.get_object()
        data = build_receipt_csv(order)
        filename = f"receipt_{order.public_id}.csv"
        resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @action(detail=True, methods=["get"], url_path="receipt.pdf")
    def receipt_pdf(self, request, public_id=None):
        order = self.get_object()
        try:
            data = build_receipt_pdf(order)
        except RuntimeError as e:
            return Response({"detail": str(e)}, status=500)

        filename = f"receipt_{order.public_id}.pdf"
        resp = HttpResponse(data, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp["Content-Length"] = str(len(data))
        return resp

    @action(detail=False, methods=["get"], url_path="export.csv")
    def export_csv(self, request):
        qs = self.filter_queryset(self.get_queryset())
        data = export_orders_csv(qs)
        filename = "orders_export.csv"
        resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @action(detail=True, methods=["post"], url_path="attach-customer")
    def attach_customer(self, request, public_id=None):
        order = self.get_object()
        pid = (request.data or {}).get("customer_public_id", "")
        if not pid:
            return Response({"detail": "Brak customer_public_id."}, status=400)
        try:
            c = Customer.objects.get(public_id=pid)
        except Customer.DoesNotExist:
            return Response({"detail": "Nie znaleziono klienta."}, status=404)
        attach_customer_to_order(order=order, customer=c, update_snapshot=True)
        return Response(OrderPublicResponse(order).data, status=200)

    @action(detail=True, methods=["post"], url_path="detach-customer")
    def detach_customer(self, request, public_id=None):
        order = self.get_object()
        detach_customer_from_order(order=order)
        return Response(OrderPublicResponse(order).data, status=200)

    @action(detail=True, methods=["post"], url_path="ensure-customer")
    def ensure_customer(self, request, public_id=None):
        order = self.get_object()
        data = request.data or {}
        res = ensure_customer_for_order(
            order=order,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            address=data.get("address") or {},
            document_type=data.get("document_type", ""),
            document_number=data.get("document_number", ""),
            birth_date=data.get("birth_date"),
            allow_update_email=bool(data.get("allow_update_email", False)),
            allow_update_phone=bool(data.get("allow_update_phone", False)),
        )
        if res.get("result") == "conflict":
            return Response(
                {"detail": "Znaleziono wielu kandydatów — wybierz ręcznie.", "candidates": res["candidates"]},
                status=409
            )
        return Response({
            "result": res["result"],
            "customer_public_id": res.get("customer_public_id"),
            "order": OrderPublicResponse(order).data
        }, status=200 if res["result"] == "attached" else 201)

# ===== ADMIN =====
class AdminOrderViewSet(mixins.ListModelMixin,
                        mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    permission_classes = [IsAdmin]
    serializer_class = OrderPublicResponse
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = OrderFilter
    ordering_fields = ("created_at","purchase_date")

    def get_queryset(self):
        return queries.list_admin_orders()
