from __future__ import annotations
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from .models import ListingPackage

User = get_user_model()


class ListingPackageForm(forms.ModelForm):
    """
    Walidacja biznesowa:
      - listings_free >= 0
      - points >= 0
      - dopuszczamy dowolną kombinację price/points (oba, jedno, żadne -> FREE grant)
      - listings_free == 0 oznacza „kredyt płatny” (paid credit) przy zakupie.
    """
    class Meta:
        model = ListingPackage
        fields = ("item_type", "listings_free", "price", "points")

    def clean(self):
        data = super().clean()
        lf = data.get("listings_free") or 0
        pts = data.get("points") or 0

        if lf < 0:
            self.add_error("listings_free", "Wartość musi być ≥ 0.")
        if pts < 0:
            self.add_error("points", "Wartość musi być ≥ 0.")

        # Nie wymuszamy price/points – pakiet może być darmowy (admin przyznaje).
        return data


class PurchasePackageForm(forms.Form):
    """
    Jeżeli budujesz stronę HTML (poza API), to tym formularzem
    użytkownik może wybrać pakiet i metodę płatności.
    """
    PAY_WITH = (
        ("auto", "Automatycznie"),
        ("points", "Punkty"),
        ("money", "Płatność pieniężna"),
    )
    listing_package = forms.ModelChoiceField(
        queryset=ListingPackage.objects.select_related("item_type").all(),
        required=True,
        label="Pakiet"
    )
    pay_with = forms.ChoiceField(choices=PAY_WITH, required=False, initial="auto", label="Metoda płatności")

    def clean(self):
        data = super().clean()
        # Dodatkowe walidacje typu: czy user ma punkty – robisz na etapie view/command,
        # bo tu nie mamy jeszcze użytkownika.
        return data
