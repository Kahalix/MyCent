from __future__ import annotations
from django import forms

class ItemTypeCreateForm(forms.Form):
    name = forms.CharField(max_length=120)
    parent_path = forms.CharField(max_length=1024, required=False)

class ItemTypeUpdateForm(forms.Form):
    path = forms.CharField(max_length=1024)  # obowiązkowe — identyfikuje kategorię
    name = forms.CharField(max_length=120, required=False)
    parent_path = forms.CharField(max_length=1024, required=False)

class CatalogItemForm(forms.Form):
    item_name = forms.CharField(max_length=255)
    type_path = forms.CharField(max_length=1024)
    image_path = forms.CharField(max_length=1024, required=False)
    attributes = forms.JSONField(required=False)
