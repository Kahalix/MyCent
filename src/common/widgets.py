from __future__ import annotations
import json
from django import forms

DEFAULT_EMPTY_SCHEMA = {"type": "object", "properties": {}}

class SimpleJSONSchemaWidget(forms.Textarea):
    """
    Ukryty <textarea> + atrybuty data-*, a UI buduje JS (static/catalog/simple_schema_form.js).
    """
    def __init__(self, schema: dict | None = None, attrs=None):
        schema = schema or DEFAULT_EMPTY_SCHEMA
        attrs = attrs or {}
        attrs.setdefault("data-ssf", "1")  # znacznik dla naszego JS
        attrs.setdefault("data-ssf-schema", json.dumps(schema))
        # textarea chowamy – UI jest w osobnym kontenerze
        style = attrs.get("style", "")
        if "display:" not in style:
            style = (style + ";display:none;").lstrip(";")
        attrs["style"] = style
        super().__init__(attrs=attrs)

    class Media:
        js = ("catalog/simple_schema_form.js",)
        css = {"all": ("catalog/simple_schema_form.css",)}
