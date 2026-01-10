from __future__ import annotations
from datetime import timedelta
from typing import Any
import uuid

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from common.widgets import SimpleJSONSchemaWidget, DEFAULT_EMPTY_SCHEMA

from catalog.models import ItemType, CatalogItem, _normalize_and_validate_attrs
from .models import ItemSet, ItemSetShipping, ItemSetImage

class CallModelCleanMixin:
    def clean(self):
        cleaned = super().clean()
        if hasattr(self, "instance") and self.instance is not None:
            for name, val in cleaned.items():
                setattr(self.instance, name, val)
            try:
                self.instance.clean()
            except ValidationError as e:
                if hasattr(e, "message_dict"):
                    for field, msgs in e.message_dict.items():
                        for msg in (msgs if isinstance(msgs, (list, tuple)) else [msgs]):
                            self.add_error(field if field in self.fields else None, msg)
                else:
                    self.add_error(None, str(e))
        return cleaned


class ItemSetAdminForm(forms.ModelForm):
    class Meta:
        model = ItemSet
        fields = (
            "set_name","slug","description",
            "price","stock_quantity",
            "condition","status",
            "listing_type","allow_online_checkout",
            "added_by","seller_profile","owner_user",
            "length_cm","width_cm","height_cm","weight_kg",
            "type","catalog_item",
            "attributes",
        )
        widgets = {
            # startowo pusty schemat – JS i tak go nadpisze po odczycie current type
            "attributes": SimpleJSONSchemaWidget(schema=DEFAULT_EMPTY_SCHEMA),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # tylko liście + fallback (type nie wymagamy, może przyjść z catalog_item)
        if "type" in self.fields:
            self.fields["type"].queryset = ItemType.objects.filter(children__isnull=True)
            self.fields["type"].required = False

        # jeśli znamy typ już na starcie - ustaw schemat widgetu,
        # żeby nie było pustej ramki przed pierwszym fetchem
        it = self.initial.get("type") or getattr(self.instance, "type", None)
        cat = self.initial.get("catalog_item") or getattr(self.instance, "catalog_item", None)
        if isinstance(cat, (uuid.UUID, str, int)):
            cat = CatalogItem.objects.filter(pk=cat).only("type_id").first()
        if not it and cat:
            it = cat.type
        if isinstance(it, (uuid.UUID, str, int)):
            it = ItemType.objects.filter(pk=it).only("schema_json").first()

        schema = it.schema_json if it and it.schema_json else DEFAULT_EMPTY_SCHEMA
        self.fields["attributes"].widget = SimpleJSONSchemaWidget(schema=schema)

    def clean_type(self):
        t = self.cleaned_data.get("type")
        if t is None:
            return t
        if ItemType.objects.filter(parent=t).exists():
            raise forms.ValidationError("Wybierz kategorię końcową (bez podkategorii).")
        return t

    def clean(self):
        cleaned = super().clean()

        # fallback z catalog_item
        cat = cleaned.get("catalog_item")
        if cat and not cleaned.get("type"):
            cleaned["type"] = cat.type

        # wymagane 'type' (z POST lub z instance)
        type_val = cleaned.get("type") or getattr(self.instance, "type", None)
        if not type_val:
            self.add_error("type" if "type" in self.fields else None, "To pole jest wymagane.")

        # walidacja/normalizacja atrybutów zgodnie z typem
        it = cleaned.get("type") or getattr(self.instance, "type", None)
        if it and getattr(it, "schema_json", None):
            attrs = cleaned.get("attributes") or getattr(self.instance, "attributes", {}) or {}
            cleaned["attributes"] = _normalize_and_validate_attrs(
                attrs, it.schema_json, where="attributes", require_same_fields=False
            )
        return cleaned

class ItemSetImageAdminForm(forms.ModelForm):
    class Meta:
        model = ItemSetImage
        fields = ("image", "image_path", "image_order")

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("image") and not cleaned.get("image_path"):
            raise ValidationError("Wymagane jest 'image' lub 'image_path'.")
        return cleaned


class ItemSetShippingAdminForm(CallModelCleanMixin, forms.ModelForm):
    class Meta:
        model = ItemSetShipping
        fields = (
            "package_type",
            "price_override",
            "packed_length_cm", "packed_width_cm", "packed_height_cm", "packed_weight_kg",
        )
