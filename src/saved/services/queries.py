from __future__ import annotations

from listings.filters import ItemSetFilter
from listings.services.queries import public_itemsets_qs
from saved.services.exceptions import NotFound
from saved.services.repositories import (
    parse_query_string,
    saved_listings_qs,
    saved_searches_qs,
    saved_search_items_qs,
    get_saved_search_by_public_id,
)

def list_saved_listings(*, user):
    return saved_listings_qs(user)

def list_saved_searches(*, user):
    return saved_searches_qs(user)

def get_saved_search_meta(*, user, public_id: str):
    ss = saved_searches_qs(user).filter(public_id=public_id).first()
    if not ss:
        raise NotFound("Saved search not found")
    return ss

def list_saved_search_items(*, user, public_id: str):
    ss = get_saved_search_by_public_id(user, public_id)
    if not ss:
        raise NotFound("Saved search not found")
    return saved_search_items_qs(ss)

def run_saved_query(query_string: str):
    """
    Parsuje query_string i stosuje ItemSetFilter do publicznego querysetu ogłoszeń.
    """
    params = parse_query_string(query_string)
    # parse_qs zwraca listy; DRF filterset zaakceptuje pojedyncze wartości (weź pierwszy)
    flat = {k: v[0] for k, v in params.items() if v}
    base = public_itemsets_qs()
    fs = ItemSetFilter(flat, queryset=base)
    return fs.qs
