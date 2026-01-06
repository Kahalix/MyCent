from __future__ import annotations

from uuid import uuid4
from typing import Any

from django.core.files.storage import default_storage
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError

from identity.models import SellerProfile, User
from listings.models import ItemSet, ItemSetImage
from services.services.commands import ensure_slot_matches_state, release_slot_for_itemset
from shipping.models import PackageType
from catalog.models import CatalogItem

from .exceptions import BadRequest, Forbidden
from .repositories import (
    is_member_of_seller,
    create_itemset_staff, create_itemset_user,
    create_image as repo_create_image, delete_image as repo_delete_image, bulk_update_image_orders,
    upsert_shipping_link, delete_shipping_link as repo_delete_shipping_link,
)

from listings.services.cache_utils import invalidate_public_itemsets_cache

SOFT_DELETED = "DELETED"
SUSPENDED = "SUSPENDED"

# ---------- helpers ----------

def _clean_and_save(obj: Any):
    try:
        obj.full_clean()
    except DjangoValidationError as e:
        raise BadRequest("Validation error", errors=e.message_dict)
    obj.save()
    return obj

# ---------- CREATE / UPDATE ----------

@transaction.atomic
def seller_create_itemset(*, seller: SellerProfile, data: dict) -> ItemSet:
    it = create_itemset_staff(seller=seller, data=data)
    it = _clean_and_save(it)
    # invalidate cache
    try:
        invalidate_public_itemsets_cache()
    except Exception:
        pass
    return it

@transaction.atomic
def user_create_itemset(*, owner: User, data: dict) -> ItemSet:
    data = dict(data)
    data["allow_online_checkout"] = False
    if data.get("listing_type") == "BUY":
        data["listing_type"] = "LISTING"
    it = create_itemset_user(owner=owner, data=data)
    it = _clean_and_save(it)
    ensure_slot_matches_state(user=owner, itemset=it)
    try:
        invalidate_public_itemsets_cache()
    except Exception:
        pass
    return it

@transaction.atomic
def update_itemset(*, itemset: ItemSet, data: dict) -> ItemSet:
    from django.utils import timezone
    data = dict(data)

    if itemset.status == SOFT_DELETED:
        raise Forbidden("Ogłoszenie zostało usunięte. Edycja niedostępna.")

    if itemset.status == SUSPENDED:
        raise Forbidden("Ogłoszenie jest zawieszone. Edycja niedostępna.")

    if itemset.added_by == "USER":
        if "type" in data:
            new_type = data["type"]
            if new_type and getattr(new_type, "id", getattr(new_type, "pk", None)) != itemset.type_id:
                if (timezone.now() - itemset.created_at).total_seconds() > 24 * 3600:
                    raise Forbidden("Zmiana kategorii możliwa wyłącznie w ciągu 24 godzin od utworzenia ogłoszenia.")
        if "catalog_item" in data:
            new_cat = data["catalog_item"]
            new_cat_id = getattr(new_cat, "id", getattr(new_cat, "pk", None)) if new_cat else None
            if new_cat_id != itemset.catalog_item_id:
                if (timezone.now() - itemset.created_at).total_seconds() > 24 * 3600:
                    raise Forbidden("Zmiana pozycji katalogowej możliwa wyłącznie w ciągu 24 godzin od utworzenia ogłoszenia.")
        data["allow_online_checkout"] = False
        if data.get("listing_type") == "BUY":
            data["listing_type"] = "LISTING"

    for k, v in data.items():
        setattr(itemset, k, v)
    it = _clean_and_save(itemset)
    ensure_slot_matches_state(user=it.owner_user, itemset=it)
    return it

@transaction.atomic
def set_status(*, itemset: ItemSet, status: str) -> ItemSet:
    """
    - SELLER (STAFF): AVAILABLE/CLOSED/RESERVED/SOLD/SUSPENDED/DELETED
    - USER (USER):    AVAILABLE/CLOSED/RESERVED/DELETED
    - EXPIRED tylko systemowo.
    - Jeżeli już DELETED | SUSPENDED -> blokujemy każdą inną zmianę.
    """
    if itemset.status == SOFT_DELETED and status != SOFT_DELETED:
        raise Forbidden("Ogłoszenie zostało usunięte. Zmiana statusu niedostępna.")

    if itemset.status == SUSPENDED and itemset.added_by == "USER" and status != SUSPENDED:
        raise Forbidden("Ogłoszenie jest zawieszone. Zmiana statusu niedostępna.")

    allowed_staff = {"AVAILABLE", "CLOSED", "RESERVED", "SOLD", "SUSPENDED", SOFT_DELETED}
    allowed_user = {"AVAILABLE", "CLOSED", "RESERVED", SOFT_DELETED}

    if itemset.added_by == "STAFF":
        if status not in allowed_staff:
            raise BadRequest("Nieobsługiwany status dla sprzedawcy.")
    else:
        if status not in allowed_user:
            raise Forbidden("Tego statusu nie można ustawić dla ogłoszenia użytkownika.")

    if status == "AVAILABLE":
        sq = getattr(itemset, "stock_quantity", None)
        try:
            sq_i = int(sq) if sq is not None else 0
        except Exception:
            sq_i = 0
        if sq_i <= 0:
            raise BadRequest("Brak dostępnego stanu magazynowego.", errors={
                "stock_quantity": "Ustaw wartość > 0 aby aktywować ogłoszenie."
            })

    itemset.status = status

    it = _clean_and_save(itemset)

    try:
        invalidate_public_itemsets_cache()
    except Exception:
        pass

    ensure_slot_matches_state(user=it.owner_user, itemset=it)
    return it

@transaction.atomic
def moderator_set_status(*, itemset: ItemSet, status: str) -> ItemSet:
    if itemset.added_by != "USER":
        raise Forbidden("Moderator operuje wyłącznie na ogłoszeniach użytkowników.")
    if itemset.status == SOFT_DELETED or status == SOFT_DELETED:
        raise Forbidden("Moderator nie operuje na ogłoszeniach usuniętych.")
    if status not in {"AVAILABLE", SUSPENDED}:
        raise Forbidden("Moderator może wyłącznie zawieszać lub aktywować ogłoszenia.")
    itemset.status = status
    it = _clean_and_save(itemset)
    try:
        invalidate_public_itemsets_cache()
    except Exception:
        pass
    ensure_slot_matches_state(user=it.owner_user, itemset=it)
    return it


@transaction.atomic
def soft_delete_itemset(*, itemset: ItemSet) -> ItemSet:
    if itemset.status != SOFT_DELETED:
        itemset.status = SOFT_DELETED
        _clean_and_save(itemset)
    if itemset.added_by == "USER":
        release_slot_for_itemset(itemset=itemset)
    try:
        invalidate_public_itemsets_cache()
    except Exception:
        pass
    return itemset

@transaction.atomic
def hard_delete_itemset(*, itemset: ItemSet) -> None:
    if itemset.added_by == "USER":
        release_slot_for_itemset(itemset=itemset)
    # before delete
    try:
        invalidate_public_itemsets_cache()
    except Exception:
        pass
    itemset.delete()

@transaction.atomic
def seller_member_create_itemset(*, user: User, seller: SellerProfile, data: dict) -> ItemSet:
    if not is_member_of_seller(user, seller, roles=None):
        raise Forbidden("Nie jesteś członkiem tego sklepu.")
    it = create_itemset_staff(seller=seller, data=data)
    return _clean_and_save(it)

# ---------- IMAGES ----------

def add_image(*, itemset: ItemSet, image=None, image_path: str | None = None, image_order: int | None = None) -> ItemSetImage:
    if itemset.status == SOFT_DELETED:
        raise Forbidden("Ogłoszenie zostało usunięte. Zarządzanie zdjęciami niedostępne.")
    if itemset.status == SUSPENDED:
        raise Forbidden("Ogłoszenie jest zawieszone. Zarządzanie zdjęciami niedostępne.")

    fields: dict[str, Any] = {}
    if image is not None:
        name = f"listings/{itemset.public_id}/{uuid4()}_{getattr(image, 'name', 'image.bin')}"
        saved_path = default_storage.save(name, image)
        fields["image_path"] = saved_path
    elif image_path:
        fields["image_path"] = image_path

    if image_order is not None:
        fields["image_order"] = image_order

    img = repo_create_image(itemset=itemset, **fields)
    try:
        invalidate_public_itemsets_cache()
    except Exception:
        pass
    return img

def delete_image(*, image: ItemSetImage) -> None:
    itemset = image.item_set
    if itemset.status == SOFT_DELETED:
        raise Forbidden("Ogłoszenie zostało usunięte. Zarządzanie zdjęciami niedostępne.")
    path = getattr(image, "image_path", None)
    if path:
        try:
            default_storage.delete(path)
        except Exception:
            pass
    repo_delete_image(image)
    try:
        invalidate_public_itemsets_cache()
    except Exception:
        pass

@transaction.atomic
def reorder_images(*, itemset: ItemSet, ordered_public_ids: list[str]) -> list[ItemSetImage]:
    if itemset.status == SOFT_DELETED:
        raise Forbidden("Ogłoszenie zostało usunięte. Zarządzanie zdjęciami niedostępne.")
    if itemset.status == SUSPENDED:
        raise Forbidden("Ogłoszenie jest zawieszone. Zarządzanie zdjęciami niedostępne.")
    imgs = list(itemset.images.select_for_update().all())
    by_id = {img.public_id: img for img in imgs}
    if set(by_id.keys()) != set(ordered_public_ids):
        raise BadRequest("Lista 'order' musi zawierać dokładnie public_id aktualnych zdjęć.")
    for idx, pid in enumerate(ordered_public_ids):
        by_id[pid].image_order = idx
    bulk_update_image_orders(imgs)
    return sorted(imgs, key=lambda x: x.image_order)

@transaction.atomic
def update_image_order(*, image: ItemSetImage, image_order: int) -> ItemSetImage:
    itemset = image.item_set
    if itemset.status == SOFT_DELETED:
        raise Forbidden("Ogłoszenie zostało usunięte. Zarządzanie zdjęciami niedostępne.")
    if itemset.status == SUSPENDED:
        raise Forbidden("Ogłoszenie jest zawieszone. Zarządzanie zdjęciami niedostępne.")
    imgs = list(itemset.images.select_for_update().order_by("image_order", "id"))
    imgs.remove(image)
    image.image_order = max(0, image_order)
    imgs.insert(min(image.image_order, len(imgs)), image)
    for idx, img in enumerate(imgs):
        img.image_order = idx
    bulk_update_image_orders(imgs)
    return image

# ---------- SHIPPING OPTIONS ----------

@transaction.atomic
def add_shipping_option(*, itemset: ItemSet, package_type: PackageType, **kwargs):
    if itemset.status == SOFT_DELETED:
        raise Forbidden("Ogłoszenie zostało usunięte. Opcje wysyłki niedostępne.")
    if itemset.status == SUSPENDED:
        raise Forbidden("Ogłoszenie jest zawieszone. Opcje wysyłki niedostępne.")
    if not (itemset.added_by == "STAFF" and itemset.listing_type == "BUY" and itemset.allow_online_checkout):
        raise Forbidden("Opcje wysyłki tylko dla SELLER + BUY + checkout online.")
    link = upsert_shipping_link(itemset=itemset, package_type=package_type)
    for k in ("price_override", "packed_length_cm", "packed_width_cm", "packed_height_cm", "packed_weight_kg"):
        if k in kwargs and kwargs[k] is not None:
            setattr(link, k, kwargs[k])
    return _clean_and_save(link)

@transaction.atomic
def remove_shipping_option(*, itemset: ItemSet, package_type: PackageType) -> None:
    if itemset.status == SOFT_DELETED:
        raise Forbidden("Ogłoszenie zostało usunięte. Opcje wysyłki niedostępne.")
    if itemset.status == SUSPENDED:
        raise Forbidden("Ogłoszenie jest zawieszone. Opcje wysyłki niedostępne.")
    repo_delete_shipping_link(itemset=itemset, package_type=package_type)

# ---------- PREFILL FROM CATALOG ----------

def prefill_from_catalog(*, catalog_item: CatalogItem) -> dict:
    return {"catalog_item_id": catalog_item.id, "attributes": catalog_item.attributes or {}}
