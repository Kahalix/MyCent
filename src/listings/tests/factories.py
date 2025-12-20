from django.contrib.auth import get_user_model
from moneyed import Money

from identity.models import SellerProfile
from catalog.models import ItemType
from shipping.models import PackageType
from listings.models import ItemSet

User = get_user_model()


def make_user(email: str, **extra):
    data = {"password": "testpass123"}
    data.update(extra)
    return User.objects.create_user(email=email, **data)


def make_leaf_item_type(name="Phones", slug="phones", path="phones"):
    return ItemType.objects.create(name=name, slug=slug, path=path)


def make_seller(owner, slug="shop-1", **extra):
    data = {"owner": owner, "slug": slug, "company_name": "Test Shop"}
    data.update(extra)
    return SellerProfile.objects.create(**data)


def make_package_type(
    provider="P1",
    dimensions="S",
    max_length_cm=50,
    max_width_cm=50,
    max_height_cm=50,
    max_weight_kg=5,
    price_amount=10,
):
    return PackageType.objects.create(
        provider=provider,
        dimensions=dimensions,
        max_length_cm=max_length_cm,
        max_width_cm=max_width_cm,
        max_height_cm=max_height_cm,
        max_weight_kg=max_weight_kg,
        price=Money(price_amount, "PLN"),
        points=0,
    )


def make_staff_itemset(
    seller,
    item_type,
    set_name="Item",
    status="AVAILABLE",
    listing_type="BUY",
    allow_online_checkout=False,
    **extra,
):
    data = {
        "set_name": set_name,
        "description": "",
        "price": Money(100, "PLN"),
        "stock_quantity": 1,
        "condition": "USED",
        "status": status,
        "listing_type": listing_type,
        "allow_online_checkout": allow_online_checkout,
        "added_by": "STAFF",
        "seller_profile": seller,
        "owner_user": None,
        "type": item_type,
        "catalog_item": None,
        "length_cm": 10,
        "width_cm": 10,
        "height_cm": 10,
        "weight_kg": 1,
        "attributes": {},
    }
    data.update(extra)
    return ItemSet.objects.create(**data)


def make_user_itemset(
    owner,
    item_type,
    set_name="User item",
    status="AVAILABLE",
    listing_type="LISTING",
    **extra,
):
    data = {
        "set_name": set_name,
        "description": "",
        "price": Money(50, "PLN"),
        "stock_quantity": 1,
        "condition": "USED",
        "status": status,
        "listing_type": listing_type,
        "allow_online_checkout": False,
        "added_by": "USER",
        "seller_profile": None,
        "owner_user": owner,
        "type": item_type,
        "catalog_item": None,
        "length_cm": 10,
        "width_cm": 10,
        "height_cm": 10,
        "weight_kg": 1,
        "attributes": {},
    }
    data.update(extra)
    return ItemSet.objects.create(**data)
