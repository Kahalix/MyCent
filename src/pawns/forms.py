from __future__ import annotations
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from pawns.services.fees import calc_extension_fee

from pawns.models import Pawn, PawnLine, PawnExtension

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


class PawnAdminForm(CallModelCleanMixin, forms.ModelForm):
    """
    Spójność dat i statusów oraz dodatnia kwota principal.
    """
    class Meta:
        model = Pawn
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()

        principal = cleaned.get("principal")
        if principal is not None and principal.amount is not None and principal.amount <= 0:
            self.add_error("principal", "Kwota pożyczki (principal) musi być dodatnia.")

        start_date = cleaned.get("start_date")
        due_date   = cleaned.get("due_date")
        if start_date and due_date and due_date < start_date:
            self.add_error("due_date", "Termin wykupu musi być ≥ data startu.")

        status = cleaned.get("status")
        redeemed_at  = cleaned.get("redeemed_at")
        forfeited_at = cleaned.get("forfeited_at")
        forfeited_item = cleaned.get("forfeited_item")

        # status <> znaczniki czasu
        if status == "REDEEMED":
            if not redeemed_at:
                # ustaw automatycznie, jeżeli admin zmienia sam status
                cleaned["redeemed_at"] = timezone.now()
        else:
            if redeemed_at:
                cleaned["redeemed_at"] = None

        if status == "FORFEITED":
            if not forfeited_at:
                cleaned["forfeited_at"] = timezone.now()
            if forfeited_item is None:
                # sam status bez itemu jest ok (listing może powstać później),
                # ale jeżeli item jest ustawiony, status MUSI być FORFEITED
                pass
        else:
            if forfeited_at:
                cleaned["forfeited_at"] = None
            if forfeited_item is not None:
                self.add_error("forfeited_item", "Pole „forfeited_item” dozwolone tylko dla statusu FORFEITED.")

        if cleaned.get("redeemed_at") and cleaned.get("forfeited_at"):
            self.add_error(None, "Zastaw nie może być jednocześnie wykupiony i niewykupiony.")

        return cleaned


class PawnLineAdminForm(CallModelCleanMixin, forms.ModelForm):
    """
    Gdy podano ItemSet - musi należeć do tego samego sprzedawcy co Pawn.
    Dodatkowo automatyczna nazwa tytułu z ItemSet gdy tytuł pusty.
    """
    class Meta:
        model = PawnLine
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()

        pawn = cleaned.get("pawn") or getattr(self.instance, "pawn", None)
        iset = cleaned.get("item_set")

        if iset and pawn and iset.seller_profile_id != pawn.seller_profile_id:
            self.add_error("item_set", "Wybrany przedmiot nie należy do tego sprzedawcy.")

        # uzupełnij tytuł z ItemSet (jeśli pusty)
        title = (cleaned.get("title") or "").strip()
        if not title and iset:
            cleaned["title"] = iset.set_name

        return cleaned

class PawnExtensionAdminForm(forms.ModelForm):
    """
    Tworzenie przedłużeń:
      - automatycznie liczy fee, poprzedni i nowy termin (previous_due/new_due),
      - blokuje przedłużenie nieaktywnego lub przeterminowanego zastawu.
    Pola fee/previous_due/new_due są prezentowane jako tylko-do-odczytu (disabled),
    ale ich wartości są zapisywane na instancji w clean().
    """
    class Meta:
        model = PawnExtension
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("fee", "previous_due", "new_due"):
            if name in self.fields:
                self.fields[name].disabled = True

    def clean(self):
        cleaned = super().clean()

        pawn: Pawn | None = cleaned.get("pawn") or getattr(self.instance, "pawn", None)
        days: int | None = cleaned.get("days")

        if not pawn:
            raise ValidationError("Wymagany obiekt zastawu (pawn).")

        if pawn.status != "ACTIVE":
            raise ValidationError("Nie można przedłużyć nieaktywnego zastawu.")
        if timezone.now().date() > pawn.due_date:
            raise ValidationError("Zastaw jest już po terminie - przedłużenie niedozwolone.")

        if days not in (7, 14, 30):
            raise ValidationError("Dozwolone wartości days: 7, 14 lub 30.")

        # automatyczne wyliczenia
        fee = calc_extension_fee(principal=pawn.principal, days=days)
        prev = pawn.due_date
        new = pawn.due_date + timedelta(days=days)

        # zapisz zarówno w cleaned_data (dla admina), jak i na instancji (dla save)
        cleaned["fee"] = fee
        cleaned["previous_due"] = prev
        cleaned["new_due"] = new

        self.instance.fee = fee
        self.instance.previous_due = prev
        self.instance.new_due = new

        return cleaned
