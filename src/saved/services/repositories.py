from __future__ import annotations
from typing import Optional, Iterable
from urllib.parse import parse_qs

from django.db import transaction
from django.db.models import Count
from django.contrib.auth import get_user_model
from django.utils import timezone

from listings.models import ItemSet
from saved.models import SavedListing, SavedSearch, SavedSearchItem

User = get_user_model()

# === helpers ===
def parse_query_string(qs: str) -> dict[str, list[str]]:
    try:
        return parse_qs(qs, keep_blank_values=False, strict_parsing=False)
    except Exception:
        return {}

# === SavedListing ===
def get_saved_listing(user: User, item: ItemSet) -> Optional[SavedListing]:
    return SavedListing.objects.filter(user=user, item_set=item).first()

def create_saved_listing(user: User, item: ItemSet) -> SavedListing:
    obj, _ = SavedListing.objects.get_or_create(user=user, item_set=item)
    return obj

def delete_saved_listing(user: User, item: ItemSet) -> None:
    SavedListing.objects.filter(user=user, item_set=item).delete()

def saved_listings_qs(user: User):
    return (SavedListing.objects
            .select_related("item_set","item_set__seller_profile","item_set__type")
            .filter(user=user)
            .order_by("-created_at"))

# === SavedSearch ===
def saved_searches_qs(user: User):
    # items_count = liczba NIEPRZECZYTANYCH wyników (SavedSearchItem)
    return (SavedSearch.objects
            .filter(user=user)
            .annotate(items_count=Count("items"))
            .order_by("-created_at"))

def mark_saved_search_seen(ss: SavedSearch) -> dict:
    """
    Ustaw znacznik since_at=now oraz usuń aktualne (nieprzeczytane) SavedSearchItem.
    Zwraca liczby: {"cleared": X, "since_at": "..."}.
    """
    now = timezone.now()
    cleared = SavedSearchItem.objects.filter(saved_search=ss).count()
    SavedSearchItem.objects.filter(saved_search=ss).delete()
    ss.since_at = now
    ss.save(update_fields=["since_at"])
    return {"cleared": cleared, "since_at": now}

def get_saved_search_by_public_id(user: User, public_id: str) -> Optional[SavedSearch]:
    return SavedSearch.objects.filter(user=user, public_id=public_id).first()

def create_saved_search(user: User, *, category_path: str, query_string: str, search_phrase: str = "") -> SavedSearch:
    return SavedSearch.objects.create(user=user, category_path=category_path, query_string=query_string, search_phrase=search_phrase)

def update_saved_search(ss: SavedSearch, **fields) -> SavedSearch:
    for k, v in fields.items():
        setattr(ss, k, v)
    ss.save()
    return ss

def delete_saved_search(ss: SavedSearch) -> None:
    ss.delete()

def saved_search_items_qs(ss: SavedSearch):
    return (SavedSearchItem.objects
            .select_related("item_set","item_set__seller_profile","item_set__type")
            .filter(saved_search=ss)
            .order_by("-created_at"))

def get_saved_search_unscoped_by_public_id(public_id: str) -> Optional[SavedSearch]:
    return SavedSearch.objects.filter(public_id=public_id).first()

@transaction.atomic
def upsert_saved_search_items(ss: SavedSearch, items: Iterable[ItemSet]) -> tuple[int,int]:
    """
    Dodaje brakujące ItemSet do snapshotu zapisanej wyszukiwarki.
    Zwraca (added_count, total_after).
    """
    existing = set(SavedSearchItem.objects.select_for_update()
                   .filter(saved_search=ss)
                   .values_list("item_set_id", flat=True))
    to_create = [SavedSearchItem(saved_search=ss, item_set=it) for it in items if it.id not in existing]
    if to_create:
        SavedSearchItem.objects.bulk_create(to_create, ignore_conflicts=True)
    total = SavedSearchItem.objects.filter(saved_search=ss).count()
    return (len(to_create), total)

