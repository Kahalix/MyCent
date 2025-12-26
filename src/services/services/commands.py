from __future__ import annotations
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth import get_user_model
from django.db.models import F

from catalog.models import ItemType
from listings.models import ItemSet
from services.models import ListingPackage, UserListingPackage, ListingUsageHistory, ServicePurchaseHistory
from .exceptions import BadRequest, Forbidden, NoSlotsLeft, PurchaseError
from . import repositories as repo

User = get_user_model()

# ------------- helpers -------------

def _clean_and_save(obj: Any):
    try:
        obj.full_clean()
    except DjangoValidationError as e:
        raise BadRequest("Validation error", errors=e.message_dict)
    obj.save()
    return obj

# ------------- PURCHASE -------------

@transaction.atomic
def purchase_package(*, user: User, package: ListingPackage,
                     pay_with: str | None = None) -> UserListingPackage:
    """
    pay_with: "points" | "money" | None
      - "points": wymagane package.points > 0 i user.points >= package.points
      - "money" : wymagane package.price != None (tu nie integrujemy bramek; tylko zapis historii)
      - None    : jeśli package.points>0 -> "points"; elif package.price -> "money"; else "free"
    Efekt:
      - jeśli package.listings_free > 0 -> zwiększa free_total o listings_free
      - jeśli == 0 -> dodaje 1 paid credit (paid_total += 1)
    """
    # Lock user row (punkty) + user_package row
    user = repo.lock_user_row(user)
    if pay_with is None:
        if package.points and package.points > 0:
            pay_with = "points"
        elif package.price:
            pay_with = "money"
        else:
            pay_with = "free"

    # Płatność punktami
    if pay_with == "points":
        if not package.points or package.points <= 0:
            raise PurchaseError("Ten pakiet nie może być opłacony punktami.")
        if (user.points or 0) < package.points:
            raise PurchaseError("Niewystarczająca liczba punktów.")
        # zdejmij punkty
        user.points = int(user.points) - int(package.points)
        user.save(update_fields=["points", "updated_at"])
        repo.create_purchase_history(
            user=user, package=package,
            cost_amount=None, cost_currency="PLN",
            points_used=int(package.points),
            description=f"Zakup pakietu {package.public_id} za punkty"
        )

    # Płatność pieniędzmi
    elif pay_with == "money":
        if not package.price:
            raise PurchaseError("Ten pakiet nie ma ceny pieniężnej.")
        repo.create_purchase_history(
            user=user, package=package,
            cost_amount=Decimal(str(package.price.amount)),
            cost_currency=str(package.price.currency),
            points_used=None,
            description=f"Zakup pakietu {package.public_id} za środki pieniężne"
        )

    # Bezpłatny (np. przyznany przez admina / „0”)
    elif pay_with == "free":
        repo.create_purchase_history(
            user=user, package=package,
            cost_amount=None, cost_currency="PLN",
            points_used=None,
            description=f"Przyznanie pakietu {package.public_id}"
        )
    else:
        raise PurchaseError("Nieprawidłowa metoda płatności.")

    # Zwiększ user-package totals (z blokadą)
    repo.lock_user_packages_for_type(user, package.item_type)
    up = repo.get_or_create_user_pkg(user, package)
    if package.listings_free and package.listings_free > 0:
        up = repo.add_free_capacity(up, package.listings_free)
    else:
        up = repo.add_paid_credits(up, 1)

    return up

# ------------- SLOTS (consume/release) -------------

@transaction.atomic
def consume_slot_for_itemset(*, user: User, itemset: ItemSet) -> ListingUsageHistory:
    """
    Zajmuje FREE (jeśli dostępny), w przeciwnym razie PAID.
    Jeśli istnieje aktywny usage dla itemset -> idempotentnie zwraca go.
    """
    existing = repo.get_active_usage_for_itemset(itemset)
    if existing:
        return existing

    if getattr(itemset, "owner_user_id", None) != getattr(user, "id", None):
        raise Forbidden("Możesz zarządzać slotami tylko dla własnych ogłoszeń.")

    item_type = itemset.type

    prev_paid = repo.get_any_paid_usage_for_itemset(itemset)
    if (
            prev_paid
            and getattr(prev_paid, "user_id", None) == getattr(user, "id", None)
            and getattr(prev_paid, "item_type_id", None) == getattr(item_type, "id", None)
    ):
        repo.reopen_usage(prev_paid)
        return prev_paid

    repo.lock_user_packages_for_type(user, item_type)
    repo.lock_active_usages_for_type(user, item_type)

    free_total, paid_total = repo.totals_for_user_and_type(user, item_type)
    free_used = repo.active_free_used_count(user, item_type)
    paid_used = repo.paid_consumed_count(user, item_type)

    free_left = max(0, free_total - free_used)
    paid_left = max(0, paid_total - paid_used)

    if free_left > 0:
        return repo.create_usage(user, item_type, itemset, is_bought=False)
    if paid_left > 0:
        return repo.create_usage(user, item_type, itemset, is_bought=True)

    raise NoSlotsLeft("Wyczerpałeś limit ogłoszeń w tej kategorii.")

@transaction.atomic
def release_slot_for_itemset(*, itemset: ItemSet) -> None:
    """
    Zwalnia aktywny FREE/PAID dla ogłoszenia (ustawia released_at) – totals NIE zmieniamy.
    """
    usage = repo.get_active_usage_for_itemset(itemset)
    if usage:
        repo.release_usage(usage)

@transaction.atomic
def ensure_slot_matches_state(*, user: User, itemset: ItemSet) -> None:
    """
    Centralne miejsce spójności:
      - jeśli ogłoszenie USER + AVAILABLE - musi istnieć aktywny usage
      - jeśli nie-AVAILABLE - usage musi być zwolniony
      - jeśli zmienił się item_type - zwalniamy stary usage i konsumujemy w nowej kategorii
    """
    # sloty liczymy tylko dla ogłoszeń USER
    if itemset.added_by != "USER":
        return

    # bezpieczeństwo: tylko właściciel
    if getattr(itemset, "owner_user_id", None) != getattr(user, "id", None):
        raise Forbidden("Możesz zarządzać slotami tylko dla własnych ogłoszeń.")

    active = repo.get_active_usage_for_itemset(itemset)

    if itemset.status == "AVAILABLE":
        if active:
            if getattr(active, "item_type_id", None) == getattr(itemset, "type_id", None):
                # już spójnie
                return
            # zmiana kategorii: zwolnij stary usage i skonsumuj w nowej
            repo.release_usage(active)
        consume_slot_for_itemset(user=user, itemset=itemset)
    else:
        if active:
            repo.release_usage(active)

@transaction.atomic
def grant_signup_freebies(user) -> None:
    from django.conf import settings
    public_ids = getattr(settings, "SERVICES_SIGNUP_FREE_PACKAGE_PUBLIC_IDS", [])
    if not public_ids:
        return

    # idempotentnie – nie duplikuj grantów jeśli już były nadane
    for pkg in ListingPackage.objects.select_for_update().filter(public_id__in=public_ids):
        up = (UserListingPackage.objects
              .select_for_update()
              .filter(user=user, listing_package=pkg)
              .first())
        if not up:
            up = UserListingPackage(user=user, listing_package=pkg, free_total=0, paid_total=0)
            up.save()

        # jeśli chcesz grant „tylko raz”, sprawdź historię z opisem SIGNUP_FREE
        already = ServicePurchaseHistory.objects.filter(
            user=user, listing_package=pkg, description="SIGNUP_FREE"
        ).exists()
        if already:
            continue

        UserListingPackage.objects.filter(pk=up.pk).update(
            free_total=F("free_total") + pkg.listings_free
        )
        ServicePurchaseHistory.objects.create(
            user=user,
            listing_package=pkg,
            purchase_cost_amount=0,
            purchase_cost_currency="PLN",
            points_used=0,
            description="SIGNUP_FREE",
        )

# ------------- REPORTS -------------

def slot_summary_for_user(user: User) -> list[dict]:
    """
    Zwraca listę wpisów per ItemType:
      {
        "item_type": { "id": ..., "name": ... },
        "free_total": int,
        "free_used_active": int,
        "free_left": int,
        "paid_total": int,
        "paid_used_lifetime": int,
        "paid_left": int,
        "active_itemsets": int
      }
    """
    out: list[dict] = []
    for itype in repo.item_types_with_activity_for_user(user):
        free_total, paid_total = repo.totals_for_user_and_type(user, itype)
        free_used  = repo.active_free_used_count(user, itype)
        paid_used  = repo.paid_consumed_count(user, itype)
        act_cnt    = repo.active_itemsets_count(user, itype)
        out.append({
            "item_type": {"id": itype.id, "public_id": itype.public_id, "name": itype.name},
            "free_total": free_total,
            "free_used_active": free_used,
            "free_left": max(0, free_total - free_used),
            "paid_total": paid_total,
            "paid_used_lifetime": paid_used,
            "paid_left": max(0, paid_total - paid_used),
            "active_itemsets": act_cnt
        })
    out.sort(key=lambda r: r["item_type"]["name"])
    return out
