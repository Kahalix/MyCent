from __future__ import annotations

from typing import Optional

from django.db.models import Count
from catalog.models import ItemType, CatalogItem
from catalog.services import repositories as repo

def roots():
    return repo.roots_qs().order_by("name")

def children_of(path: str | None):
    if not path:
        return repo.roots_qs().order_by("name")
    parent = repo.get_type_by_path(path)
    if not parent:
        return ItemType.objects.none()
    return repo.children_qs(parent).order_by("name")

def category_detail_by_path(path: str):
    node = repo.get_type_by_path(path)
    if not node:
        return None
    bc = repo.breadcrumbs_for(node)
    kids = repo.children_qs(node).order_by("name")
    return {"node": node, "breadcrumbs": bc, "children": list(kids)}

def search_catalog_items(*, type_path: str | None, q: str | None):
    t = repo.get_type_by_path(type_path) if type_path else None
    return repo.search_items(t, q)

def get_catalog_item_by_path_and_slug(type_path: str, item_slug: str) -> Optional[CatalogItem]:
    t = repo.get_type_by_path(type_path)
    if not t:
        return None
    return CatalogItem.objects.filter(type=t, slug=item_slug).first()

def public_id_from_catalog_slug(slug: str) -> Optional[str]:
    # oczekujemy "...-<public_id>" — bierzemy część po OSTATNIM '-'
    parts = slug.rsplit("-", 1)
    return parts[1] if len(parts) == 2 and parts[1] else None

def get_catalog_item_by_slug(slug: str) -> Optional[CatalogItem]:
    pid = public_id_from_catalog_slug(slug)
    if not pid:
        return None
    return CatalogItem.objects.filter(public_id=pid).first()
