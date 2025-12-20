from __future__ import annotations
from django import forms

class SavedListingToggleForm(forms.Form):
    item_public_id = forms.CharField(max_length=64)

class SavedSearchCreateForm(forms.Form):
    category_path = forms.CharField(max_length=500)
    query_string = forms.CharField(max_length=2000)
    search_phrase = forms.CharField(max_length=255, required=False)

class SavedSearchUpdateForm(forms.Form):
    category_path = forms.CharField(max_length=500, required=False)
    query_string = forms.CharField(max_length=2000, required=False)
    search_phrase = forms.CharField(max_length=255, required=False)
