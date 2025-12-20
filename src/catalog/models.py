from __future__ import annotations
from typing import Optional, Dict, Any
from django.db import models, transaction
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from django.db.models.functions import Length
from common.models import PublicIdModel
from typing import Any, Tuple, Dict

def _default_for(spec: dict) -> Any:
    if "default" in spec: return spec["default"]
    t = spec.get("type")
    if t == "string":  return ""
    if t == "integer": return None
    if t == "number":  return None
    if t == "boolean": return False
    return None

def _coerce_type(val: Any, typ: str):
    if val is None: return None
    try:
        if typ == "string":  return str(val)
        if typ == "integer": return int(val)
        if typ == "number":  return float(val)
        if typ == "boolean":
            if isinstance(val, bool): return val
            s = str(val).strip().lower()
            if s in ("1","true","yes","y","t"): return True
            if s in ("0","false","no","n","f"): return False
            return bool(val)
    except Exception:
        return val
    return val

def _manual_validate_and_fill(attrs: Dict[str,Any], schema: dict, *, require_same_fields: bool) -> Tuple[Dict[str,list], Dict[str,Any]]:
    props = (schema or {}).get("properties", {}) or {}
    required = set((schema or {}).get("required", []) or [])
    errors: Dict[str, list] = {}
    out: Dict[str, Any] = {}

    # znane pola
    for key, spec in props.items():
        val = _coerce_type(attrs.get(key, None), spec.get("type"))
        # enum
        if "enum" in spec and val is not None and val not in spec["enum"]:
            errors.setdefault(key, []).append(f"musi być jednym z: {', '.join(map(str, spec['enum']))}")
        # min/max
        if val is not None and isinstance(val, (int, float)):
            if "minimum" in spec and val < spec["minimum"]:
                errors.setdefault(key, []).append(f"min {spec['minimum']}")
            if "maximum" in spec and val > spec["maximum"]:
                errors.setdefault(key, []).append(f"max {spec['maximum']}")
        # required
        if key in required and (val is None or val == "" or (isinstance(val, (list, dict)) and not val)):
            errors.setdefault(key, []).append("wymagane")

        # default gdy brak
        if (val is None or val == "") and key not in required:
            val = _default_for(spec)
        out[key] = val

    # nieznane pola
    if require_same_fields:
        unknown = set(attrs.keys()) - set(props.keys())
        for u in unknown:
            errors.setdefault(u, []).append("nieznane pole (nie w schemacie)")

    return errors, out

class ItemType(PublicIdModel):
    name   = models.CharField(max_length=120)
    slug   = models.SlugField(max_length=140, blank=True)
    path   = models.CharField(max_length=1024, db_index=True, unique=True, editable=False)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")

    # JSON Schema (tylko liście) + opcjonalny UI-schema
    schema_json    = models.JSONField(default=dict, blank=True)
    ui_schema_json = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = (("parent","name"), ("parent","slug"))
        indexes = [
            models.Index(fields=["parent","slug"], name="ix_itemtype_parent_slug"),
            models.Index(fields=["parent","name"], name="ix_itemtype_parent_name"),
            models.Index(fields=["path"], name="ix_itemtype_path"),
        ]

    def __str__(self) -> str:
        return self.path or self.name

    @property
    def is_leaf(self) -> bool:
        return not self.children.exists()

    # --- helpers (slug/path) ---
    def _make_base_slug(self) -> str:
        base = slugify(self.name or "").strip("-")
        return base or "kategoria"

    def _ensure_unique_slug_within_parent(self, base: str) -> str:
        slug = base
        n = 2
        exist = set(ItemType.objects.filter(parent=self.parent).values_list("slug", flat=True))
        while slug in exist:
            slug = f"{base}-{n}"; n += 1
        return slug

    def compute_path(self, slug: Optional[str] = None) -> str:
        s = slug or self.slug or self._make_base_slug()
        return f"{self.parent.path}/{s}" if self.parent and self.parent.path else s

    def clean(self):
        # schemat wyłącznie na liściach
        if self.schema_json and self.children.exists():
            raise ValidationError({"schema_json": "Schemat dozwolony wyłącznie dla kategorii końcowych (liści)."})
        super().clean()

    @transaction.atomic
    def save(self, *args, **kwargs):
        old = None
        if self.pk:
            old = ItemType.objects.filter(pk=self.pk).values("slug", "parent_id", "path").first()
        old_path = old["path"] if old else None
        parent_changed = (old and old["parent_id"] != self.parent_id) if old else False

        if not self.slug:
            self.slug = self._make_base_slug()
        if not self.pk or (old and (old["slug"] != self.slug or parent_changed)):
            self.slug = self._ensure_unique_slug_within_parent(self.slug)

        self.path = self.compute_path(self.slug)
        super().save(*args, **kwargs)

        # przepchnij nowy path w dół drzewa
        if old_path and old_path != self.path:
            descendants = ItemType.objects.filter(path__startswith=old_path + "/").annotate(pl=Length("path"))
            for child in descendants.select_related("parent").order_by("pl"):
                child.path = child.compute_path(child.slug)
                super(ItemType, child).save(update_fields=["path"])


def _normalize_and_validate_attrs(attrs: dict, schema: dict, *, where: str,
                                  require_same_fields: bool = True) -> dict:
    """
    Wspieramy wyłącznie pełny JSON Schema:
      {"type":"object","properties":{...},"required":[...]}
    Zasady:
      - wypełniamy brakujące pola defaultami (jeśli są w properties[*].default),
      - jeśli require_same_fields=True: wszystkie keys z `properties` MUSZĄ wystąpić,
        a dodatkowe pola są zabronione,
      - walidujemy jsonschema (typy, min/max, enum, minLength...).
    """
    if not schema:
        return attrs or {}

    # twarde oczekiwanie na pełny format
    if not isinstance(schema, dict) or schema.get("type") != "object" or "properties" not in schema or not isinstance(schema["properties"], dict):
        raise ValidationError({where: "Nieprawidłowy format schematu (wymagane: {type:'object', properties:{...}})."})

    props = schema["properties"]
    keys_schema = set(props.keys())
    out = dict(attrs or {})

    # uzupełnij defaulty
    for k, spec in props.items():
        if k not in out and isinstance(spec, dict) and "default" in spec:
            out[k] = spec["default"]

    # pilnuj zestawu pól (wszyscy mają jednakowy kształt)
    if require_same_fields:
        extras = [k for k in out.keys() if k not in keys_schema]
        if extras:
            raise ValidationError({where: f"Nieznane pola: {', '.join(sorted(extras))}. Dozwolone: {', '.join(sorted(keys_schema))}."})
        missing = [k for k in props.keys() if k not in out]
        if missing:
            raise ValidationError({where: f"Brak pól wymaganych przez schemat: {', '.join(missing)}."})

    # walidacja jsonschema
    try:
        from jsonschema import Draft7Validator, ValidationError as JSONSchemaError
    except Exception:
        # jeśli pakietu nie ma, jasno powiedz
        raise ValidationError({where: "Walidacja atrybutów wymaga pakietu 'jsonschema'."})

    effective = dict(schema)  # kopia
    if require_same_fields:
        # wymagamy WSZYSTKICH properties (nie tylko schema.required)
        effective["required"] = list(keys_schema)
        effective.setdefault("additionalProperties", False)

    try:
        Draft7Validator(effective).validate(out)
    except JSONSchemaError as e:
        path = ".".join(str(p) for p in list(e.path))
        msg = f"{path}: {e.message}" if path else e.message
        raise ValidationError({where: f"Niepoprawne atrybuty: {msg}"})

    return out


def _validate_against_schema(attrs: dict, schema_or_itemtype, *, where: str = "attributes",
                             require_same_fields: bool = True) -> dict:
    schema = (getattr(schema_or_itemtype, "schema_json", None) or
              (schema_or_itemtype or {}))
    return _normalize_and_validate_attrs(attrs or {}, schema, where=where, require_same_fields=require_same_fields)

# alias „czytelny”
validate_against_schema = _validate_against_schema


class CatalogItem(PublicIdModel):
    item_name   = models.CharField(max_length=255)
    slug        = models.SlugField(max_length=220, blank=True)
    type        = models.ForeignKey(ItemType, on_delete=models.PROTECT, related_name="catalog_items")
    image_path  = models.CharField(max_length=1024, blank=True)
    attributes  = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["type","item_name"], name="ix_catalogitem_type_name"),
            models.Index(fields=["slug"], name="ix_catalogitem_slug"),
        ]

    def __str__(self) -> str:
        return self.item_name

    def _slug_base(self) -> str:
        return (slugify(self.item_name) or "item").strip("-")

    def _ensure_seo_slug(self) -> str:
        return f"{self._slug_base()}-{self.public_id}"

    def clean(self):
        super().clean()
        # liść
        if self.type_id and ItemType.objects.filter(parent_id=self.type_id).exists():
            raise ValidationError({"type": "Przedmiot musi być przypisany do kategorii końcowej (bez podkategorii)."})

        if self.type_id:
            t = ItemType.objects.filter(id=self.type_id).only("id", "schema_json").first()
            if t and t.schema_json:
                # dla katalogu wymagamy dokładnie tych samych pól co w schemacie
                self.attributes = _normalize_and_validate_attrs(self.attributes or {}, t.schema_json,
                                                                where="attributes", require_same_fields=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # potrzebujemy public_id
        desired = self._ensure_seo_slug()
        if not self.slug or not self.slug.endswith(f"-{self.public_id}"):
            self.slug = desired
            super(CatalogItem, self).save(update_fields=["slug"])
