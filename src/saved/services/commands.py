from __future__ import annotations
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth import get_user_model

from listings.models import ItemSet
from listings.services.queries import public_itemsets_qs
from saved.models import SavedListing, SavedSearch
from saved.services.exceptions import AlreadySaved, NotOwner, InvalidQuery, NotFound
from saved.services.repositories import (
    get_saved_listing, create_saved_listing, delete_saved_listing, saved_listings_qs,
    get_saved_search_by_public_id, create_saved_search, update_saved_search, delete_saved_search,
    saved_search_items_qs, upsert_saved_search_items, saved_searches_qs, mark_saved_search_seen,
)
from saved.services.refresh import _query_for_search
from saved.services.queries import run_saved_query

User = get_user_model()

# === Saved Listing ===
@transaction.atomic
def add_saved_listing(*, user: User, item_public_id: str) -> SavedListing:
    item = get_object_or_404(ItemSet, public_id=item_public_id)
    obj = get_saved_listing(user, item)
    if obj:
        # nie traktujemy jako błąd, po prostu zwracamy istniejący
        return obj
    return create_saved_listing(user, item)

@transaction.atomic
def remove_saved_listing(*, user: User, item_public_id: str) -> None:
    item = get_object_or_404(ItemSet, public_id=item_public_id)
    delete_saved_listing(user, item)

def list_saved_listings(*, user: User):
    return saved_listings_qs(user)

# === Saved Search ===
@transaction.atomic
def create_saved_search_cmd(*, user: User, category_path: str, query_string: str, search_phrase: str="") -> SavedSearch:
    if not (query_string and query_string.strip()):
        raise InvalidQuery("query_string cannot be empty")
    return create_saved_search(user, category_path=category_path, query_string=query_string, search_phrase=search_phrase)

@transaction.atomic
def update_saved_search_cmd(*, user: User, public_id: str, **fields) -> SavedSearch:
    ss = get_saved_search_by_public_id(user, public_id)
    if not ss:
        raise NotFound("Saved search not found")
    return update_saved_search(ss, **fields)

@transaction.atomic
def delete_saved_search_cmd(*, user: User, public_id: str) -> None:
    ss = get_saved_search_by_public_id(user, public_id)
    if not ss:
        return
    delete_saved_search(ss)

def list_saved_searches(*, user: User):
    return saved_searches_qs(user)

def list_saved_search_items(*, user: User, public_id: str):
    ss = get_saved_search_by_public_id(user, public_id)
    if not ss:
        raise NotFound("Saved search not found")
    return saved_search_items_qs(ss)

@transaction.atomic
def refresh_saved_search_items(*, user: User, public_id: str, limit: int = 200) -> dict:
    ss = get_saved_search_by_public_id(user, public_id)
    if not ss:
        raise NotFound("Saved search not found")

    qs = _query_for_search(ss).order_by("-created_at")
    if limit is not None:
        qs = qs[:limit]

    added, total = upsert_saved_search_items(ss, list(qs))
    return {"added": added, "total": total}

@transaction.atomic
def mark_saved_search_seen_cmd(*, user: User, public_id: str) -> dict:
    ss = get_saved_search_by_public_id(user, public_id)
    if not ss:
        raise NotFound("Saved search not found")
    return mark_saved_search_seen(ss)
