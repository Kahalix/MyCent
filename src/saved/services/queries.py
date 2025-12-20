from __future__ import annotations
from typing import Iterable
from urllib.parse import parse_qs

from listings.models import ItemSet
from listings.filters import ItemSetFilter
from listings.services.queries import public_itemsets_qs
from saved.services.repositories import parse_query_string

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
