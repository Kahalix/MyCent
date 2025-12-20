from __future__ import annotations
from typing import Optional
from django.db import transaction

from carts.models import Cart, CartItem
from listings.models import ItemSet
from identity.models import User


def get_or_create_active_cart(user: User) -> Cart:
    cart, _ = Cart.objects.get_or_create(user=user, status="ACTIVE")
    return cart

def get_or_create_active_cart_prefetched(user: User) -> Cart:
    """
    Zwraca aktywny koszyk z dociągniętymi powiązaniami, żeby uniknąć N+1
    podczas serializacji (items -> item_set -> seller_profile, type).
    """
    cart = get_or_create_active_cart(user)
    return (
        Cart.objects
        .filter(pk=cart.pk)
        .prefetch_related(
            "items",
            "items__item_set",
            "items__item_set__seller_profile",
            "items__item_set__type",
        )
        .get()
    )

def get_cart(user: User) -> Optional[Cart]:
    return Cart.objects.filter(user=user, status="ACTIVE").first()

def add_or_inc_item(cart: Cart, item: ItemSet, qty: int) -> CartItem:
    obj, created = CartItem.objects.get_or_create(cart=cart, item_set=item, defaults={"quantity": qty})
    if not created:
        obj.quantity = max(1, obj.quantity + qty)
        obj.save(update_fields=["quantity","updated_at"])
    return obj

def set_item_qty(cart: Cart, item: ItemSet, qty: int) -> CartItem | None:
    obj = CartItem.objects.filter(cart=cart, item_set=item).first()
    if qty <= 0:
        if obj:
            obj.delete()
        return None
    if obj:
        obj.quantity = qty
        obj.save(update_fields=["quantity","updated_at"])
        return obj
    return CartItem.objects.create(cart=cart, item_set=item, quantity=qty)

def remove_item(cart: Cart, item: ItemSet) -> int:
    return CartItem.objects.filter(cart=cart, item_set=item).delete()[0]

def clear_cart(cart: Cart) -> int:
    return CartItem.objects.filter(cart=cart).delete()[0]

def current_qty(cart: Cart, item: ItemSet) -> int:
    return int(CartItem.objects.filter(cart=cart, item_set=item)
               .values_list("quantity", flat=True).first() or 0)
