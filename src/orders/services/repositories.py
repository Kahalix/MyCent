from __future__ import annotations
from typing import Optional, List
from django.db import transaction
from django.db.models import Prefetch, Sum
from django.utils import timezone

from catalog.models import ItemType
from identity.models import SellerProfile, User
from transactions.models import Transaction
from orders.models import Order, OrderLine, OrderShipping, ItemReservation
from listings.models import ItemSet

# === getters ===
def get_itemset_by_public_id(public_id: str) -> Optional[ItemSet]:
    return ItemSet.objects.select_related("seller_profile").filter(public_id=public_id).first()

def get_order_by_public_id(public_id: str) -> Optional[Order]:
    return (Order.objects
            .select_related("seller_profile","buyer","transaction")
            .prefetch_related("order_lines__item_set","shippings")
            .filter(public_id=public_id).first())

def buyer_orders_qs(user: User):
    return (Order.objects
            .select_related("seller_profile","transaction")
            .prefetch_related("order_lines__item_set","shippings")
            .filter(buyer=user).order_by("-created_at"))

def seller_orders_qs(seller: SellerProfile):
    return (Order.objects
            .select_related("buyer","transaction")
            .prefetch_related("order_lines__item_set","shippings")
            .filter(seller_profile=seller).order_by("-created_at"))

def admin_orders_qs():
    return (Order.objects
            .select_related("seller_profile","buyer","transaction")
            .prefetch_related("order_lines__item_set","shippings")
            .all().order_by("-created_at"))

# === rezerwacje / locki ===
def lock_itemsets_for_update(item_ids: List[int]) -> list[ItemSet]:
    return list(ItemSet.objects.select_for_update().filter(id__in=item_ids))

def active_reserved_qty(item: ItemSet, exclude_tx_id: int | None = None) -> int:
    qs = ItemReservation.objects.filter(
        item_set=item,
        released_at__isnull=True,
        expires_at__gt=timezone.now(),
    )
    if exclude_tx_id:
        qs = qs.exclude(transaction_id=exclude_tx_id)
    return int(qs.aggregate(s=Sum("quantity"))["s"] or 0)

def create_reservation(*, item: ItemSet, tx, line: OrderLine | None, user, quantity: int, ttl_seconds: int) -> ItemReservation:
    return ItemReservation.objects.create(
        item_set=item, transaction=tx, order_line=line, user=user,
        quantity=quantity, expires_at=timezone.now() + timezone.timedelta(seconds=ttl_seconds),
    )

def release_all_reservations_for_tx(tx) -> int:
    return ItemReservation.objects.filter(
        transaction=tx, released_at__isnull=True
    ).update(released_at=timezone.now())

# === mutate ===
@transaction.atomic
def create_order(*, tx: Transaction, seller: SellerProfile, buyer: Optional[User], fields: dict) -> Order:
    return Order.objects.create(transaction=tx, seller_profile=seller, buyer=buyer, **fields)

@transaction.atomic
def add_order_line(*, order: Order, item: ItemSet, quantity: int, unit_price) -> OrderLine:
    # snapshot w chwili zakupu
    snapshot = {
        "public_id": item.public_id,
        "set_name": item.set_name,
        "slug": item.slug,
        "description": item.description,
        "price": str(unit_price.amount),
        "currency": str(unit_price.currency),
        "condition": item.condition,
        "length_cm": item.length_cm, "width_cm": item.width_cm, "height_cm": item.height_cm, "weight_kg": str(item.weight_kg) if item.weight_kg is not None else None,
        "type_path": item.type.path if item.type_id else None,
        "catalog_item_public_id": item.catalog_item.public_id if item.catalog_item_id else None,
        "attributes": item.attributes or {},
        "seller_slug": item.seller_profile.slug if item.seller_profile_id else None,
    }
    return OrderLine.objects.create(
        order=order, item_set=item, quantity=quantity, unit_price=unit_price, item_snapshot=snapshot
    )

@transaction.atomic
def add_line_shipping(*, order: Order, line: OrderLine, tracking_number: str = "",
                      package_label: str = "", package_type=None, price=None) -> OrderShipping:
    # upsert na parze (order, order_line)
    ship, created = OrderShipping.objects.select_for_update().get_or_create(
        order=order, order_line=line,
        defaults={
            "tracking_number": tracking_number or "",
            "package_type": package_type,
            "price": price,
            "package_label": package_label or (getattr(package_type, "provider", "") if package_type else ""),
            "shipping_status": "PENDING",
        }
    )
    if not created:
        changed = False
        if tracking_number is not None and tracking_number != ship.tracking_number:
            ship.tracking_number = tracking_number; changed = True
        if package_type is not None and package_type != ship.package_type:
            ship.package_type = package_type; changed = True
        if price is not None and price != ship.price:
            ship.price = price; changed = True
        if package_label is not None and package_label != ship.package_label:
            ship.package_label = package_label; changed = True
        if changed:
            ship.save(update_fields=["tracking_number","package_type","price","package_label","updated_at"])
    # przeliczenie zamówienia
    order.recalc_totals(save=True)
    return ship

@transaction.atomic
def save_order(order: Order) -> Order:
    order.save()
    return order

@transaction.atomic
def add_order_line_from_payload(
    *, order: Order, title: str, quantity: int, unit_price, attributes: dict | None = None, notes: str = ""
) -> OrderLine:
    snapshot = {
        "title": title,
        "attributes": attributes or {},
        "notes": notes,
        "currency": str(unit_price.currency),
        "price": str(unit_price.amount),
    }
    return OrderLine.objects.create(
        order=order, item_set=None, quantity=quantity, unit_price=unit_price, item_snapshot=snapshot
    )

# Niepewne

def get_item_type_by_public_id(public_id: str) -> ItemType | None:
    return ItemType.objects.filter(public_id=public_id).first()

@transaction.atomic
def create_itemset_from_pawn_line(
    *, seller: SellerProfile, title: str, description: str = "", attributes: dict | None,
    listing_price, item_type: ItemType
) -> ItemSet:
    """
    Tworzy „draft” oferty z przyjęcia skupu:
      - added_by=STAFF, listing_type=BUY (do późniejszego włączenia checkoutu),
      - allow_online_checkout=False (niepubliczne do czasu akceptacji),
      - status=RESERVED (żeby nie weszło w publiczne listingi; później ręcznie ustawisz AVAILABLE).
    """
    it = ItemSet.objects.create(
        added_by="STAFF", seller_profile=seller,
        set_name=title, description=description,
        price=listing_price, stock_quantity=1,
        condition="USED", listing_type="BUY", allow_online_checkout=False,
        status="RESERVED",  # „draft”
        type=item_type,
        catalog_item=None,
        attributes=attributes or {},
    )
    return it