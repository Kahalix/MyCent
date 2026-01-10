from __future__ import annotations
from decimal import Decimal
from typing import Optional

from django import forms
from django.core.exceptions import ValidationError

from djmoney.money import Money

from .models import PackageType, ShippingAddress


# =========================
# Helpers
# =========================

def _strip(v: Optional[str]) -> Optional[str]:
    return v.strip() if isinstance(v, str) else v

def _lower(v: Optional[str]) -> Optional[str]:
    return v.lower().strip() if isinstance(v, str) else v


# =========================
# PACKAGE TYPES
# =========================

def _provider_choices():
    return PackageType.PROVIDER  # [(value, label), ...]

class PackageTypeCreateUpdateForm(forms.Form):
    provider = forms.ChoiceField(choices=_provider_choices())

    dimensions = forms.CharField(max_length=120, required=False)

    max_length_cm = forms.IntegerField(required=False, min_value=1)
    max_width_cm  = forms.IntegerField(required=False, min_value=1)
    max_height_cm = forms.IntegerField(required=False, min_value=1)
    max_weight_kg = forms.DecimalField(required=False, min_value=Decimal("0.001"), max_digits=10, decimal_places=3)

    price_amount   = forms.DecimalField(required=False, min_value=Decimal("0"), max_digits=19, decimal_places=2)
    price_currency = forms.CharField(required=False, max_length=3, initial="PLN")

    points = forms.IntegerField(required=False, min_value=0, initial=0)

    def clean_dimensions(self): return _strip(self.cleaned_data.get("dimensions"))

    def clean_price_currency(self):
        cur = self.cleaned_data.get("price_currency") or "PLN"
        return cur.upper()

    def clean(self):
        cleaned = super().clean()

        # Jeżeli podano price_amount bez price_currency -> domyślnie PLN
        amount = cleaned.get("price_amount")
        if amount is not None and cleaned.get("price_currency") in (None, ""):
            cleaned["price_currency"] = "PLN"

        return cleaned

    def to_data(self) -> dict:
        """
        Zwraca dict zgodny z oczekiwaniami warstwy:
        {
          provider, dimensions, max_length_cm, ..., price(Money|None), points
        }
        """
        cd = self.cleaned_data
        price = None
        if cd.get("price_amount") is not None:
            price = Money(cd["price_amount"], cd["price_currency"] or "PLN")
        return {
            "provider": cd["provider"],
            "dimensions": cd.get("dimensions") or "",
            "max_length_cm": cd.get("max_length_cm"),
            "max_width_cm": cd.get("max_width_cm"),
            "max_height_cm": cd.get("max_height_cm"),
            "max_weight_kg": cd.get("max_weight_kg"),
            "price": price,
            "points": cd.get("points", 0),
        }


class PackageSuggestForm(forms.Form):
    length_cm = forms.IntegerField(required=False, min_value=1)
    width_cm  = forms.IntegerField(required=False, min_value=1)
    height_cm = forms.IntegerField(required=False, min_value=1)
    weight_kg = forms.DecimalField(required=False, min_value=Decimal("0.001"), max_digits=10, decimal_places=3)


# =========================
# SHIPPING ADDRESS (SELF/ADMIN)
# =========================

class BaseShippingAddressForm(forms.Form):
    first_name = forms.CharField(max_length=120, required=False)
    last_name = forms.CharField(max_length=120, required=False)
    phone_number = forms.CharField(max_length=32, required=False)
    email = forms.EmailField(required=False)

    street = forms.CharField(max_length=120, required=False)
    house_number = forms.CharField(max_length=20, required=False)
    city = forms.CharField(max_length=120, required=False)
    state = forms.CharField(max_length=120, required=False)
    postal_code = forms.CharField(max_length=20, required=False)
    country = forms.CharField(max_length=60, required=False)

    def clean_first_name(self): return _strip(self.cleaned_data.get("first_name"))
    def clean_last_name(self):  return _strip(self.cleaned_data.get("last_name"))
    def clean_phone_number(self): return _strip(self.cleaned_data.get("phone_number"))
    def clean_email(self): return _lower(self.cleaned_data.get("email"))
    def clean_street(self): return _strip(self.cleaned_data.get("street"))
    def clean_house_number(self): return _strip(self.cleaned_data.get("house_number"))
    def clean_city(self): return _strip(self.cleaned_data.get("city"))
    def clean_state(self): return _strip(self.cleaned_data.get("state"))
    def clean_postal_code(self): return _strip(self.cleaned_data.get("postal_code"))
    def clean_country(self): return _strip(self.cleaned_data.get("country"))

    def to_data(self) -> dict:
        cd = self.cleaned_data
        return {
            "first_name": cd.get("first_name") or "",
            "last_name": cd.get("last_name") or "",
            "phone_number": cd.get("phone_number") or "",
            "email": cd.get("email") or "",
            "street": cd.get("street") or "",
            "house_number": cd.get("house_number") or "",
            "city": cd.get("city") or "",
            "state": cd.get("state") or "",
            "postal_code": cd.get("postal_code") or "",
            "country": cd.get("country") or "",
        }

class ShippingAddressCreateForm(BaseShippingAddressForm):
    pass

class ShippingAddressUpsertForm(BaseShippingAddressForm):
    pass

class AdminShippingAddressUpdateForm(BaseShippingAddressForm):
    pass
