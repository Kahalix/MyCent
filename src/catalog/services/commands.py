from __future__ import annotations

import os

from django.db import transaction
from django.core.files.storage import default_storage
from catalog.services.exceptions import NotFound, BadRequest, Conflict, CannotDeleteNonEmpty
from catalog.services import repositories as repo
from catalog.models import ItemType, CatalogItem
from django.utils.text import slugify

# ===== ItemType =====
@transaction.atomic
def admin_create_item_type(*, name: str, parent_path: str | None = None) -> ItemType:
    parent = repo.get_type_by_path(parent_path) if parent_path else None
    return repo.create_item_type(name=name, parent=parent)

@transaction.atomic
def admin_update_item_type(*, path: str, name: str | None = None, parent_path: str | None = None) -> ItemType:
    it = repo.get_type_by_path(path)
    if not it:
        raise NotFound("Category not found")
    parent = repo.get_type_by_path(parent_path) if parent_path is not None and parent_path != "" else None
    # zabroń ustawienia rodzica na własnego potomka
    if parent and parent.path.startswith(it.path + "/"):
        raise BadRequest("Cannot set a descendant as parent.")
    return repo.update_item_type(it=it, name=name, parent=parent)

@transaction.atomic
def admin_delete_item_type(*, path: str) -> None:
    it = repo.get_type_by_path(path)
    if not it:
        return
    # nie kasujemy jeśli są dzieci lub catalog items
    if it.children.exists() or it.catalog_items.exists():
        raise CannotDeleteNonEmpty("Remove children/items first.")
    repo.delete_item_type(it=it)

# ===== CatalogItem =====
@transaction.atomic
def admin_create_catalog_item(*, type_path: str, item_name: str, image_path: str = "", attributes: dict | None = None) -> CatalogItem:
    t = repo.get_type_by_path(type_path)
    if not t:
        raise NotFound("Category not found")
    if repo.has_children(t):
        raise BadRequest("Catalog item must be assigned to a leaf category.")
    return repo.create_catalog_item(
        type_obj=t,
        item_name=item_name,
        image_path=image_path or "",
        attributes=attributes or {},
    )

@transaction.atomic
def admin_update_catalog_item(*, public_id: str, **fields) -> CatalogItem:
    obj = CatalogItem.objects.filter(public_id=public_id).first()
    if not obj:
        raise NotFound("Catalog item not found")
    if "type_path" in fields and fields["type_path"]:
        t = repo.get_type_by_path(fields.pop("type_path"))
        if not t:
            raise NotFound("Category not found")
        if repo.has_children(t):
            raise BadRequest("Catalog item must be assigned to a leaf category.")
        fields["type"] = t
    return repo.update_catalog_item(obj=obj, **fields)

@transaction.atomic
def admin_delete_catalog_item(*, public_id: str) -> None:
    obj = CatalogItem.objects.filter(public_id=public_id).first()
    if not obj:
        return
    repo.delete_catalog_item(obj=obj)

def _storage_url(path: str) -> str:
    try:
        return default_storage.url(path)
    except Exception:
        # fallback, gdy storage nie obsługuje .url()
        return f"/media/{path.lstrip('/')}"

def _save_catalog_image(public_id: str, image) -> str:
    base, ext = os.path.splitext(getattr(image, "name", "") or "")
    ext = ext or ".jpg"
    base = slugify(base) or "image"
    dest = f"catalog/{public_id}/{base}{ext}"
    saved_path = default_storage.save(dest, image)
    return saved_path

def _replace_file_and_return_url(obj, field_name: str, file) -> str:
    # tu zapisujemy ścieżkę w CatalogItem.image_path (CharField),
    # a URL zwracamy przez storage.url(saved_path)
    # usuwamy poprzedni plik, jeśli był
    old_path = getattr(obj, field_name)
    if old_path:
        try: default_storage.delete(old_path)
        except Exception: pass
    # zapisz nowy
    base_dir = f"catalog/{obj.public_id}/"
    safe_name = slugify(file.name) or "image"
    saved_path = default_storage.save(base_dir + safe_name, file)
    setattr(obj, field_name, saved_path)
    obj.save(update_fields=[field_name])
    try:
        return default_storage.url(saved_path)
    except Exception:
        return "/" + saved_path.lstrip("/")

@transaction.atomic
def admin_upload_catalog_item_image(*, public_id: str, image) -> str:
    obj = CatalogItem.objects.filter(public_id=public_id).first()
    if not obj:
        raise NotFound("Catalog item not found")
    return _replace_file_and_return_url(obj, "image_path", image)

@transaction.atomic
def admin_delete_catalog_item_image(*, public_id: str) -> None:
    obj = CatalogItem.objects.filter(public_id=public_id).first()
    if not obj:
        return
    if obj.image_path:
        try: default_storage.delete(obj.image_path)
        except Exception: pass
        obj.image_path = ""
        obj.save(update_fields=["image_path"])