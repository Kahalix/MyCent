from __future__ import annotations
from typing import Optional, Iterable
from django.db import transaction
from django.db.models import Sum, Q, Count
from django.contrib.auth import get_user_model

from catalog.models import ItemType
from services.models import (
    ListingPackage, UserListingPackage, ListingUsageHistory, ServicePurchaseHistory
)
from listings.models import ItemSet

User = get_user_model()

# --------- LOOKUPS ---------

def get_package_by_public_id(public_id: str) -> Optional[ListingPackage]:
    return ListingPackage.objects.select_related("item_type").filter(public_id=public_id).first()

def get_or_create_user_pkg(user: User, package: ListingPackage) -> UserListingPackage:
    # blokujemy rząd dla pewności współbieżności
    up = (UserListingPackage.objects
          .select_for_update()
          .filter(user=user, listing_package=package)
          .first())
    if up:
        return up
    return UserListingPackage.objects.create(
        user=user, listing_package=package,
        free_total=0, paid_total=0
    )

def get_active_usage_for_itemset(itemset: ItemSet) -> Optional[ListingUsageHistory]:
    return ListingUsageHistory.objects.filter(item_set=itemset, released_at__isnull=True).first()

def get_any_paid_usage_for_itemset(itemset: ItemSet) -> Optional[ListingUsageHistory]:
    return (
        ListingUsageHistory.objects
        .filter(item_set=itemset, is_bought=True)
        .order_by("created_at")
        .first()
    )

# --------- LOCKING ---------

@transaction.atomic
def lock_user_packages_for_type(user: User, item_type: ItemType) -> None:
    list(UserListingPackage.objects
         .select_for_update()
         .filter(user=user, listing_package__item_type=item_type))

@transaction.atomic
def lock_active_usages_for_type(user: User, item_type: ItemType) -> None:
    list(ListingUsageHistory.objects
         .select_for_update()
         .filter(user=user, item_type=item_type, released_at__isnull=True))

@transaction.atomic
def lock_user_row(user: User) -> User:
    return User.objects.select_for_update().get(pk=user.pk)

# --------- TOTALS / COUNTS ---------

def totals_for_user_and_type(user: User, item_type: ItemType) -> tuple[int, int]:
    """
    Zwraca (free_total, paid_total) – SUMA z pakietów użytkownika dla danej kategorii.
    """
    agg = (UserListingPackage.objects
           .filter(user=user, listing_package__item_type=item_type)
           .aggregate(free=Sum("free_total"), paid=Sum("paid_total")))
    return (int(agg["free"] or 0), int(agg["paid"] or 0))

def active_free_used_count(user: User, item_type: ItemType) -> int:
    """
    Ile AKTYWNYCH (released_at is null) usage’ów FREE (is_bought=False) ma user w tej kategorii.
    """
    return (ListingUsageHistory.objects
            .filter(user=user, item_type=item_type, released_at__isnull=True, is_bought=False)
            .count())

def paid_consumed_count(user: User, item_type: ItemType) -> int:
    """
    Ile PAID zużył lifetime (is_bought=True) – nie zwracamy.
    """
    return (ListingUsageHistory.objects
            .filter(user=user, item_type=item_type, is_bought=True)
            .count())

def active_itemsets_count(user: User, item_type: ItemType) -> int:
    """
    Ile aktywnych ogłoszeń USER (AVAILABLE) ma user w tej kategorii.
    """
    return (ItemSet.objects
            .filter(owner_user=user, added_by="USER", status="AVAILABLE", type=item_type)
            .count())

# --------- MUTATIONS ---------

def add_free_capacity(up: UserListingPackage, count: int) -> UserListingPackage:
    up.free_total = (up.free_total or 0) + int(count)
    up.save(update_fields=["free_total", "updated_at"])
    return up

def add_paid_credits(up: UserListingPackage, count: int) -> UserListingPackage:
    up.paid_total = (up.paid_total or 0) + int(count)
    up.save(update_fields=["paid_total", "updated_at"])
    return up

def create_usage(user: User, item_type: ItemType, itemset: ItemSet, *, is_bought: bool) -> ListingUsageHistory:
    return ListingUsageHistory.objects.create(
        user=user, item_type=item_type, item_set=itemset, is_bought=is_bought
    )

def reopen_usage(usage: ListingUsageHistory) -> ListingUsageHistory:
    if usage.released_at is not None:
        from django.utils import timezone
        usage.released_at = None
        usage.updated_at = timezone.now()
        usage.save(update_fields=["released_at", "updated_at"])
    return usage

def release_usage(usage: ListingUsageHistory) -> None:
    if usage.released_at is None:
        from django.utils import timezone
        usage.released_at = timezone.now()
        usage.save(update_fields=["released_at", "updated_at"])

def create_purchase_history(*, user: User, package: ListingPackage,
                            cost_amount, cost_currency: str,
                            points_used: int | None,
                            description: str = "") -> ServicePurchaseHistory:
    return ServicePurchaseHistory.objects.create(
        user=user,
        listing_package=package,
        purchase_cost_amount=cost_amount,
        purchase_cost_currency=cost_currency,
        points_used=points_used,
        description=description,
    )

# --------- REPORTS ---------

def item_types_with_activity_for_user(user: User) -> Iterable[ItemType]:
    # wszystkie typy, w których user ma pakiety LUB aktywne/zużyte usage
    ids = set(ListingUsageHistory.objects
              .filter(user=user)
              .values_list("item_type_id", flat=True))
    ids |= set(UserListingPackage.objects
               .filter(user=user)
               .values_list("listing_package__item_type_id", flat=True))
    from catalog.models import ItemType
    return ItemType.objects.filter(id__in=list(ids))
