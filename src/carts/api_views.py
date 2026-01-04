from __future__ import annotations

from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from carts.services import commands
from carts.services.repositories import get_or_create_active_cart_prefetched, get_cart
from carts.serializers import CartResponse, CartItemResponse, AddToCartRequest, SetQtyRequest, CheckoutCartRequest
from orders.serializers import OrderPublicResponse
from orders.models import Order

from common.services.idempotency import get_existing, save_result


class UserCartViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        cart = get_or_create_active_cart_prefetched(request.user)
        return Response(CartResponse(cart).data, status=200)

    @action(detail=False, methods=["post"], url_path="items")
    def add_item(self, request):
        ser = AddToCartRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        item = commands.add_to_cart(user=request.user, **ser.validated_data)
        return Response(CartItemResponse(item).data, status=201)

    @action(detail=False, methods=["patch"], url_path=r"items/(?P<item_public_id>[^/]+)")
    def set_quantity(self, request, item_public_id=None):
        ser = SetQtyRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        item = commands.set_quantity(
            user=request.user,
            item_public_id=item_public_id,
            quantity=ser.validated_data["quantity"],
        )
        if item is None:
            return Response(status=204)
        return Response(CartItemResponse(item).data, status=200)

    @action(detail=False, methods=["delete"], url_path=r"items/(?P<item_public_id>[^/]+)/remove")
    def remove_item(self, request, item_public_id=None):
        commands.remove_from_cart(user=request.user, item_public_id=item_public_id)
        return Response(status=204)

    @action(detail=False, methods=["delete"], url_path="clear")
    def clear(self, request):
        commands.clear(user=request.user)
        return Response(status=204)

    @action(detail=False, methods=["post"], url_path="checkout")
    def checkout(self, request):
        ser = CheckoutCartRequest(data=request.data)
        ser.is_valid(raise_exception=True)

        idem_key = request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key")
        cart = get_cart(request.user)
        cart_pid = cart.public_id if cart else "no_cart"

        if idem_key:
            existing = get_existing(user=request.user, scope="carts:checkout", fingerprint=cart_pid, key=idem_key)
            if existing and existing.target_ids:
                qs = Order.objects.filter(public_id__in=existing.target_ids).order_by("created_at")
                return Response(OrderPublicResponse(qs, many=True).data, status=200)

        orders = commands.checkout_active_cart(user=request.user, **ser.validated_data)

        if idem_key:
            save_result(
                user=request.user,
                scope="carts:checkout",
                fingerprint=cart_pid,
                key=idem_key,
                target_type="ORDER",
                target_ids=[o.public_id for o in orders],
            )

        return Response(OrderPublicResponse(orders, many=True).data, status=201)
