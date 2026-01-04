from __future__ import annotations

from typing import Optional

from django.db import IntegrityError
from django.db.models import Prefetch, F
from django.utils import timezone

from carts.models import Cart, CartItem
from identity.models import User
from listings.models import ItemSet


def get_or_create_active_cart(user: User) -> Cart:
    cart = Cart.objects.filter(user=user, status="ACTIVE").first()
    if cart:
        return cart
    try:
        return Cart.objects.create(user=user, status="ACTIVE")
    except IntegrityError:
        return Cart.objects.get(user=user, status="ACTIVE")


def get_or_create_active_cart_prefetched(user: User) -> Cart:
    images_prefetch = None
    try:
        from listings.models import ItemSetImage
        images_prefetch = Prefetch(
            "item_set__images",
            queryset=ItemSetImage.objects.only("id", "item_set_id", "image_path", "image").order_by("created_at"),
            to_attr="_cart_images",
        )
    except Exception:
        images_prefetch = None

    items_qs = (
        CartItem.objects
        .select_related(
            "item_set",
            "item_set__type",
            "item_set__catalog_item",
        )
        .only(
            "public_id", "quantity", "cart_id", "item_set_id",
            "item_set__public_id", "item_set__slug", "item_set__set_name",
            "item_set__price", "item_set__price_currency",
            "item_set__type_id", "item_set__catalog_item_id",
            "item_set__type__path",
            "item_set__catalog_item__image_path",
        )
    )

    if images_prefetch is not None:
        items_qs = items_qs.prefetch_related(images_prefetch)

    cart = (
        Cart.objects
        .filter(user=user, status="ACTIVE")
        .only("id", "public_id", "status", "created_at", "updated_at")
        .prefetch_related(Prefetch("items", queryset=items_qs))
        .first()
    )
    if cart:
        return cart

    try:
        Cart.objects.create(user=user, status="ACTIVE")
    except IntegrityError:
        pass

    return (
        Cart.objects
        .filter(user=user, status="ACTIVE")
        .only("id", "public_id", "status", "created_at", "updated_at")
        .prefetch_related(Prefetch("items", queryset=items_qs))
        .get()
    )


def get_cart(user: User) -> Optional[Cart]:
    return Cart.objects.filter(user=user, status="ACTIVE").first()


def set_item_qty(cart: Cart, item: ItemSet, qty: int) -> CartItem | None:
    if qty <= 0:
        CartItem.objects.filter(cart=cart, item_set=item).delete()
        return None

    now = timezone.now()
    updated = (
        CartItem.objects
        .filter(cart=cart, item_set=item)
        .update(quantity=qty, updated_at=now)
    )
    if not updated:
        try:
            CartItem.objects.create(cart=cart, item_set=item, quantity=qty)
        except IntegrityError:
            CartItem.objects.filter(cart=cart, item_set=item).update(quantity=qty, updated_at=now)

    return (
        CartItem.objects
        .select_related("item_set", "item_set__type", "item_set__catalog_item")
        .get(cart=cart, item_set=item)
    )


def remove_item(cart: Cart, item: ItemSet) -> int:
    return CartItem.objects.filter(cart=cart, item_set=item).delete()[0]


def clear_cart(cart: Cart) -> int:
    return CartItem.objects.filter(cart=cart).delete()[0]


def current_qty(cart: Cart, item: ItemSet) -> int:
    return int(
        CartItem.objects.filter(cart=cart, item_set=item)
        .values_list("quantity", flat=True)
        .first() or 0
    )


def inc_item_qty(cart: Cart, item: ItemSet, qty: int) -> CartItem:
    now = timezone.now()
    updated = (
        CartItem.objects
        .filter(cart=cart, item_set=item)
        .update(quantity=F("quantity") + qty, updated_at=now)
    )
    if not updated:
        try:
            CartItem.objects.create(cart=cart, item_set=item, quantity=qty)
        except IntegrityError:
            CartItem.objects.filter(cart=cart, item_set=item).update(
                quantity=F("quantity") + qty,
                updated_at=now,
            )

    return (
        CartItem.objects
        .select_related("item_set", "item_set__type", "item_set__catalog_item")
        .get(cart=cart, item_set=item)
    )
