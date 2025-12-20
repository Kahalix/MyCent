from __future__ import annotations
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from djmoney.money import Money

from catalog.models import ItemType
from listings.models import ItemSet
from services.models import (
    ListingPackage,
    UserListingPackage,
    ListingUsageHistory,
    ServicePurchaseHistory,
)

User = get_user_model()


def create_user(email: str | None = None, points: int = 0, **extra) -> User:
    if email is None:
        email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    return User.objects.create_user(email=email, password="pass1234", points=points, **extra)


def create_item_type(name: str | None = None, parent: ItemType | None = None) -> ItemType:
    if name is None:
        name = f"Type {uuid.uuid4().hex[:6]}"
    return ItemType.objects.create(name=name, parent=parent)


def create_listing_package(
    *,
    item_type: ItemType | None = None,
    listings_free: int = 0,
    price_amount: Decimal | None = None,
    price_currency: str = "PLN",
    points: int = 0,
) -> ListingPackage:
    if item_type is None:
        item_type = create_item_type()
    price = Money(price_amount, price_currency) if price_amount is not None else None
    pkg = ListingPackage.objects.create(
        item_type=item_type,
        listings_free=listings_free,
        price=price,
        points=points,
    )
    return pkg


def create_user_listing_package(
    *,
    user: User | None = None,
    listing_package: ListingPackage | None = None,
    free_total: int = 0,
    paid_total: int = 0,
) -> UserListingPackage:
    if user is None:
        user = create_user()
    if listing_package is None:
        listing_package = create_listing_package()
    return UserListingPackage.objects.create(
        user=user,
        listing_package=listing_package,
        free_total=free_total,
        paid_total=paid_total,
    )


def create_item_set(
    *,
    owner_user: User | None = None,
    item_type: ItemType | None = None,
    added_by: str = "USER",
    status: str = "AVAILABLE",
    price_amount: Decimal = Decimal("10.00"),
    price_currency: str = "PLN",
) -> ItemSet:
    from moneyed import Money as M

    if owner_user is None:
        owner_user = create_user()
    if item_type is None:
        item_type = create_item_type()
    itemset = ItemSet.objects.create(
        set_name=f"Item {uuid.uuid4().hex[:6]}",
        description="",
        price=M(price_amount, price_currency),
        stock_quantity=1,
        condition="USED",
        status=status,
        listing_type="LISTING",
        allow_online_checkout=False,
        added_by=added_by,
        seller_profile=None,
        owner_user=owner_user,
        type=item_type,
        catalog_item=None,
        attributes={},
    )
    return itemset


def create_listing_usage_history(
    *,
    user: User,
    item_type: ItemType,
    itemset: ItemSet | None = None,
    is_bought: bool = False,
    released_at=None,
) -> ListingUsageHistory:
    return ListingUsageHistory.objects.create(
        user=user,
        item_type=item_type,
        item_set=itemset,
        is_bought=is_bought,
        released_at=released_at,
    )


def create_service_purchase_history(
    *,
    user: User,
    listing_package: ListingPackage | None = None,
    cost_amount: Decimal | None = None,
    cost_currency: str = "PLN",
    points_used: int | None = None,
    description: str = "",
) -> ServicePurchaseHistory:
    return ServicePurchaseHistory.objects.create(
        user=user,
        listing_package=listing_package,
        purchase_cost_amount=cost_amount,
        purchase_cost_currency=cost_currency,
        points_used=points_used,
        description=description,
    )
