from __future__ import annotations
from typing import Optional

from django.db import transaction
from django.contrib.auth import get_user_model

from identity.models import SellerProfile, SellerMembership
from listings.models import ItemSet, ItemSetImage, ItemSetShipping
from shipping.models import PackageType

User = get_user_model()

# ---------- helpers: memberships ----------

def is_member_of_seller(user: User, seller: SellerProfile, roles: set[str] | None = None) -> bool:
    qs = SellerMembership.objects.filter(seller_profile=seller, user=user, is_active=True)
    if roles:
        qs = qs.filter(role__in=list(roles))
    return qs.exists()

# ---------- ItemSet ----------

def get_itemset_by_public_id(public_id: str) -> Optional[ItemSet]:
    return (ItemSet.objects
            .select_related("seller_profile", "owner_user", "type", "catalog_item")
            .filter(public_id=public_id).first())

def create_itemset_staff(*, seller: SellerProfile, data: dict) -> ItemSet:
    return ItemSet(added_by="STAFF", seller_profile=seller, **data)

def create_itemset_user(*, owner: User, data: dict) -> ItemSet:
    return ItemSet(added_by="USER", owner_user=owner, seller_profile=None, **data)

def save_itemset(itemset: ItemSet) -> ItemSet:
    itemset.save()
    return itemset

def delete_itemset(itemset: ItemSet) -> None:
    itemset.delete()

# ---------- ItemSetImage ----------

def get_image_for_itemset(itemset: ItemSet, public_id: str) -> Optional[ItemSetImage]:
    return ItemSetImage.objects.filter(item_set=itemset, public_id=public_id).first()

@transaction.atomic
def create_image(*, itemset: ItemSet, **fields) -> ItemSetImage:
    # wyznacz docelową pozycję
    want_order = fields.pop("image_order", None)
    siblings = list(
        ItemSetImage.objects.select_for_update()
        .filter(item_set=itemset)
        .order_by("image_order", "id")
    )
    if want_order is None or want_order < 0:
        want_order = len(siblings)
    else:
        want_order = min(want_order, len(siblings))

    # zrób miejsce: shift od want_order w górę
    for idx in range(want_order, len(siblings)):
        sib = siblings[idx]
        sib.image_order = idx + 1
    if siblings:
        ItemSetImage.objects.bulk_update(siblings, ["image_order"])

    # utwórz nowy w „dziurze”
    img = ItemSetImage.objects.create(item_set=itemset, image_order=want_order, **fields)
    return img

def delete_image(image: ItemSetImage) -> None:
    image.delete()

@transaction.atomic
def bulk_update_image_orders(images: list[ItemSetImage]) -> None:
    ItemSetImage.objects.bulk_update(images, ["image_order"])

# ---------- PackageType / Shipping link ----------

def get_package_type_by_public_id(public_id: str) -> Optional[PackageType]:
    return PackageType.objects.filter(public_id=public_id).first()

def get_shipping_link(*, itemset: ItemSet, package_type: PackageType) -> Optional[ItemSetShipping]:
    return ItemSetShipping.objects.filter(item_set=itemset, package_type=package_type).first()

def upsert_shipping_link(*, itemset: ItemSet, package_type: PackageType) -> ItemSetShipping:
    link, _ = ItemSetShipping.objects.get_or_create(item_set=itemset, package_type=package_type)
    return link

def delete_shipping_link(*, itemset: ItemSet, package_type: PackageType) -> None:
    ItemSetShipping.objects.filter(item_set=itemset, package_type=package_type).delete()
