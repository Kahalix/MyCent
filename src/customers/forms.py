from __future__ import annotations
from django import forms
from django.core.exceptions import ValidationError

from customers.models import Customer


# ===== mixin: uruchom model.clean() w trakcie walidacji formularza =====
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
                        msgs_list = msgs if isinstance(msgs, (list, tuple)) else [msgs]
                        for msg in msgs_list:
                            self.add_error(field if field in self.fields else None, msg)
                else:
                    self.add_error(None, str(e))
        return cleaned


class CustomerAdminForm(CallModelCleanMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()

        email = (cleaned.get("email") or "").strip()
        phone = (cleaned.get("phone") or "").strip()
        if not email and not phone:
            self.add_error("email", "Podaj e-mail lub telefon (wystarczy jedno).")
            self.add_error("phone", "Podaj e-mail lub telefon (wystarczy jedno).")

        country = (cleaned.get("country") or "").strip()
        if country:
            if len(country) != 2:
                self.add_error("country", "Kod kraju powinien mieć 2 znaki (ISO 3166-1 alpha-2).")
            cleaned["country"] = country.upper()

        return cleaned
