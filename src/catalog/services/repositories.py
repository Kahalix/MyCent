from __future__ import annotations
from typing import Optional, Iterable
from django.db.models import Count, Q
from django.utils.text import slugify
from catalog.models import ItemType, CatalogItem

# === ItemType ===
def get_type_by_path(path: str) -> Optional[ItemType]:
    return ItemType.objects.filter(path=path).first()

def get_type_by_public_id(public_id: str) -> Optional[ItemType]:
    return ItemType.objects.filter(public_id=public_id).first()

def roots_qs():
    return ItemType.objects.filter(parent__isnull=True).annotate(children_count=Count("children"))

def children_qs(parent: ItemType):
    return ItemType.objects.filter(parent=parent).annotate(children_count=Count("children"))

def tree_qs(depth: int = 2):
    # proste drzewo: korzenie + dzieci do zadanego poziomu
    roots = list(roots_qs().order_by("name"))
    return roots

def breadcrumbs_for(node: ItemType) -> list[ItemType]:
    out = []
    cur = node
    while cur:
        out.append(cur)
        cur = cur.parent
    return list(reversed(out))

def create_item_type(*, name: str, parent: ItemType | None) -> ItemType:
    it = ItemType(name=name, parent=parent)
    it.save()
    return it

def update_item_type(*, it: ItemType, name: str | None = None, parent: ItemType | None = None) -> ItemType:
    if name is not None:
        it.name = name
        it.slug = ""  # wymuś rekalkulację/unikalność przy save()
    if parent is not None or (parent is None and it.parent_id is not None):
        it.parent = parent
    it.save()
    return it

def delete_item_type(*, it: ItemType) -> None:
    it.delete()

# === CatalogItem ===
def items_for_type(type_obj: ItemType):
    return CatalogItem.objects.filter(type=type_obj).order_by("item_name")

def has_children(type_obj: ItemType) -> bool:
    return ItemType.objects.filter(parent=type_obj).exists()

def is_leaf(type_obj: ItemType) -> bool:
    return not has_children(type_obj)

def search_items(type_obj: ItemType | None, q: str | None):
    qs = CatalogItem.objects.all().order_by("item_name")
    if type_obj:
        # typ = dokładnie ta kategoria LUB jej potomkowie
        base = type_obj.path
        qs = qs.filter(Q(type__path=base) | Q(type__path__startswith=base + "/"))
    if q:
        qs = qs.filter(item_name__icontains=q)
    return qs

def delete_catalog_item(*, obj: CatalogItem) -> None:
    obj.delete()

def _unique_slug_for_type(type_obj: ItemType, base: str) -> str:
    base = (slugify(base) or "item").strip("-")
    exist = set(CatalogItem.objects.filter(type=type_obj).values_list("slug", flat=True))
    slug = base or "item"
    n = 2
    while slug in exist:
        slug = f"{base}-{n}"
        n += 1
    return slug

def create_catalog_item(*, type_obj: ItemType, item_name: str, image_path: str = "", attributes: dict | None = None) -> CatalogItem:
    # zabezpieczenie na wszelki wypadek: tylko liść
    if has_children(type_obj):
        raise ValueError("Catalog item must be assigned to a leaf category")
    return CatalogItem.objects.create(
        type=type_obj,
        item_name=item_name,
        image_path=image_path or "",
        attributes=attributes or {},
    )

def update_catalog_item(*, obj: CatalogItem, **fields) -> CatalogItem:
    fields.pop("slug", None)
    fields.pop("image_path", None)
    for k, v in fields.items():
        setattr(obj, k, v)
    obj.save()
    return obj