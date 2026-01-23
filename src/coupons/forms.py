from __future__ import annotations
from django import forms
from django.core.exceptions import ValidationError

from coupons.models import Coupon


class CouponAdminForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        code = cleaned.get("code")
        if code:
            cleaned["code"] = code.strip().upper()
            self.instance.code = cleaned["code"]

        dtype = cleaned.get("discount_type")
        dval = cleaned.get("discount_value")

        if not dval:
            raise ValidationError({"discount_value": "Wymagane."})

        if dtype == "PERCENTAGE":
            pct = float(dval.amount)
            if pct < 0 or pct > 100:
                raise ValidationError({"discount_value": "Dla procentu podaj wartość 0-100."})

        return cleaned
