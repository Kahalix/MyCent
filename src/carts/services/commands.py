from __future__ import annotations
from django.db import transaction

from carts.services import repositories as repo
from carts.services.exceptions import DomainError, NotFound, Conflict
from listings.models import ItemSet
from orders.services.commands import checkout_cart as orders_checkout_cart
from orders.services.commands import _assert_item_buyable, _available_qty

def _get_item_by_public_id(public_id: str) -> ItemSet | None:
    from listings.models import ItemSet
    return ItemSet.objects.filter(public_id=public_id).first()

@transaction.atomic
def add_to_cart(*, user, item_public_id: str, quantity: int = 1):
    if quantity <= 0:
        raise DomainError("Ilość musi być dodatnia.")
    item = _get_item_by_public_id(item_public_id)
    if not item:
        raise NotFound("Ogłoszenie nie istnieje.")
    _assert_item_buyable(item)
    if quantity > _available_qty(item):
        raise Conflict("Brak dostępnej ilości.")
    cart = repo.get_or_create_active_cart(user)
    current = repo.current_qty(cart, item)
    if current + quantity > _available_qty(item):
        raise Conflict("Brak dostępnej ilości.")
    return repo.add_or_inc_item(cart=cart, item=item, qty=quantity)

@transaction.atomic
def set_quantity(*, user, item_public_id: str, quantity: int):
    item = _get_item_by_public_id(item_public_id)
    if not item:
        raise NotFound("Ogłoszenie nie istnieje.")

    cart = repo.get_or_create_active_cart(user)

    # Usunięcie / wyzerowanie - pozwól nawet, jeśli item przestał być kupowalny
    if quantity <= 0:
        return repo.set_item_qty(cart=cart, item=item, qty=0)

    # Dla dodatniej ilości weryfikuj kupowalność i dostępność
    _assert_item_buyable(item)
    current = repo.current_qty(cart, item)
    available_plus_current = _available_qty(item) + current
    if quantity > available_plus_current:
        raise Conflict("Brak dostępnej ilości.")

    return repo.set_item_qty(cart=cart, item=item, qty=quantity)

@transaction.atomic
def remove_from_cart(*, user, item_public_id: str):
    item = _get_item_by_public_id(item_public_id)
    if not item:
        return 0
    cart = repo.get_or_create_active_cart(user)
    return repo.remove_item(cart=cart, item=item)

@transaction.atomic
def clear(*, user):
    cart = repo.get_or_create_active_cart(user)
    return repo.clear_cart(cart)

@transaction.atomic
def checkout_active_cart(*, user, payment_method: str = "ONLINE_PAYMENT"):
    cart = repo.get_cart(user)
    if not cart:
        raise DomainError("Koszyk jest pusty.")
    rows = list(cart.items.select_related("item_set__seller_profile"))
    if not rows:
        raise DomainError("Koszyk jest pusty.")
    cart_items = [(r.item_set, int(r.quantity)) for r in rows]
    orders = orders_checkout_cart(buyer=user, cart_items=cart_items, payment_method="ONLINE_PAYMENT")
    cart.status = "CHECKED_OUT"
    cart.save(update_fields=["status","updated_at"])
    return orders
