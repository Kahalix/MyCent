from __future__ import annotations
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils.text import slugify
from djmoney.money import Money

from identity.models import SellerProfile, SellerMembership
from listings.models import ItemSet, ItemSetImage, ItemSetShipping
from catalog.models import ItemType, CatalogItem
from shipping.models import PackageType
from saved.models import SavedListing

User = get_user_model()


def create_user(email: str | None = None, password: str = "pass1234", **extra) -> User:
    if email is None:
        email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    return User.objects.create_user(email=email, password=password, **extra)


def create_item_type(name: str | None = None, parent: ItemType | None = None, path: str | None = None, **extra) -> ItemType:
    if name is None:
        name = f"Category {uuid.uuid4().hex[:6]}"
    if path is None:
        base = slugify(name) or "cat"
        if parent and getattr(parent, "path", None):
            path = f"{parent.path}/{base}-{uuid.uuid4().hex[:4]}"
        else:
            path = f"{base}-{uuid.uuid4().hex[:4]}"
    return ItemType.objects.create(name=name, parent=parent, path=path, **extra)


def create_catalog_item(
    *,
    item_type: ItemType | None = None,
    item_name: str | None = None,
    attributes: dict | None = None,
    slug: str | None = None,
    image_path: str | str | None = "",
    **extra,
) -> CatalogItem:
    if item_type is None:
        item_type = create_item_type()
    if item_name is None:
        item_name = f"Item {uuid.uuid4().hex[:6]}"
    if slug is None:
        slug = slugify(item_name)[:50] or f"item-{uuid.uuid4().hex[:6]}"
    if attributes is None:
        attributes = {"field": "value"}
    return CatalogItem.objects.create(
        type=item_type,
        item_name=item_name,
        slug=slug,
        image_path=image_path or "",
        attributes=attributes,
        **extra,
    )


def create_seller_profile(
    *,
    owner: User | None = None,
    company_name: str | None = None,
    slug: str | None = None,
    **extra,
) -> SellerProfile:
    if owner is None:
        owner = create_user()
    if company_name is None:
        company_name = f"Shop {uuid.uuid4().hex[:6]}"
    if slug is None:
        slug = slugify(company_name)[:50] or f"shop-{uuid.uuid4().hex[:6]}"
    defaults = {
        "legal_name": "",
        "description": "",
        "contact_email": "",
        "contact_phone": "",
        "website_url": "",
    }
    defaults.update(extra)
    return SellerProfile.objects.create(
        owner=owner,
        company_name=company_name,
        slug=slug,
        **defaults,
    )


def create_seller_membership(
    *,
    seller_profile: SellerProfile,
    user: User | None = None,
    role: str = "OWNER",
    is_active: bool = True,
) -> SellerMembership:
    if user is None:
        user = create_user()
    return SellerMembership.objects.create(
        seller_profile=seller_profile,
        user=user,
        role=role,
        is_active=is_active,
    )


def create_package_type(
    *,
    provider: str = "P",
    dimensions: str = "S",
    max_length_cm: int | None = 100,
    max_width_cm: int | None = 100,
    max_height_cm: int | None = 100,
    max_weight_kg: Decimal | None = Decimal("10.0"),
    price_amount: Decimal | None = Decimal("10.00"),
    price_currency: str = "PLN",
    points: int = 0,
    **extra,
) -> PackageType:
    price = Money(price_amount, price_currency) if price_amount is not None else None
    return PackageType.objects.create(
        provider=provider,
        dimensions=dimensions,
        max_length_cm=max_length_cm,
        max_width_cm=max_width_cm,
        max_height_cm=max_height_cm,
        max_weight_kg=max_weight_kg,
        price=price,
        points=points,
        **extra,
    )


def create_item_set(
    *,
    set_name: str | None = None,
    seller_profile: SellerProfile | None = None,
    owner_user: User | None = None,
    item_type: ItemType | None = None,
    added_by: str | None = None,
    listing_type: str = "LISTING",
    status: str = "AVAILABLE",
    allow_online_checkout: bool = False,
    price_amount: Decimal = Decimal("10.00"),
    price_currency: str = "PLN",
    stock_quantity: int = 1,
    condition: str = "USED",
    length_cm: int | None = None,
    width_cm: int | None = None,
    height_cm: int | None = None,
    weight_kg: Decimal | None = None,
    catalog_item: CatalogItem | None = None,
    attributes: dict | None = None,
) -> ItemSet:
    from moneyed import Money as M

    if set_name is None:
        set_name = f"Listing {uuid.uuid4().hex[:6]}"
    if owner_user is None and seller_profile is None:
        owner_user = create_user()
    if item_type is None:
        item_type = create_item_type()
    if added_by is None:
        added_by = "STAFF" if seller_profile is not None else "USER"
    if attributes is None:
        attributes = {}

    return ItemSet.objects.create(
        set_name=set_name,
        description="",
        price=M(price_amount, price_currency),
        stock_quantity=stock_quantity,
        condition=condition,
        status=status,
        listing_type=listing_type,
        allow_online_checkout=allow_online_checkout,
        added_by=added_by,
        seller_profile=seller_profile,
        owner_user=owner_user,
        length_cm=length_cm,
        width_cm=width_cm,
        height_cm=height_cm,
        weight_kg=weight_kg,
        type=item_type,
        catalog_item=catalog_item,
        attributes=attributes,
    )


def create_item_image(
    *,
    item_set: ItemSet,
    image_path: str | None = "images/example.jpg",
    image_order: int = 0,
) -> ItemSetImage:
    return ItemSetImage.objects.create(
        item_set=item_set,
        image_path=image_path or "",
        image_order=image_order,
    )


def create_item_shipping(
    *,
    item_set: ItemSet,
    package_type: PackageType,
    price_override_amount: Decimal | None = None,
    price_override_currency: str = "PLN",
    packed_length_cm: int | None = None,
    packed_width_cm: int | None = None,
    packed_height_cm: int | None = None,
    packed_weight_kg: Decimal | None = None,
) -> ItemSetShipping:
    price_override = (
        Money(price_override_amount, price_override_currency)
        if price_override_amount is not None
        else None
    )
    return ItemSetShipping.objects.create(
        item_set=item_set,
        package_type=package_type,
        price_override=price_override,
        packed_length_cm=packed_length_cm,
        packed_width_cm=packed_width_cm,
        packed_height_cm=packed_height_cm,
        packed_weight_kg=packed_weight_kg,
    )


def create_saved_listing(*, user: User, item_set: ItemSet) -> SavedListing:
    return SavedListing.objects.create(user=user, item_set=item_set)
