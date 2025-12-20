from __future__ import annotations
from decimal import Decimal
from django import forms
from django.db.models import Q
from payments.models import Payment
from transactions.models import Transaction

_ALLOWED = {
    "REQUIRES_CONFIRMATION": {"REQUIRES_ACTION","PROCESSING","SUCCEEDED","FAILED","CANCELLED"},
    "REQUIRES_ACTION":       {"PROCESSING","SUCCEEDED","FAILED","CANCELLED"},
    "PROCESSING":            {"SUCCEEDED","FAILED","CANCELLED"},
    "SUCCEEDED":             set(),
    "FAILED":                set(),
    "CANCELLED":             set(),
}
_ACTIVE = {"REQUIRES_CONFIRMATION","REQUIRES_ACTION","PROCESSING"}

class PaymentAdminForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        inst: Payment = self.instance
        tx: Transaction | None = cleaned.get("transaction") or getattr(inst, "transaction", None)
        amount = cleaned.get("amount")
        if tx:
            exp_amt = Decimal(str(tx.expected_total_amount or 0))
            exp_cur = (tx.expected_total_currency or "PLN").upper()
            if amount:
                if str(amount.currency).upper() != exp_cur:
                    self.add_error("amount", f"Waluta płatności powinna być {exp_cur}.")
                amt_dec = Decimal(str(amount.amount or 0)).quantize(Decimal("0.01"))
                exp_dec = exp_amt.quantize(Decimal("0.01"))
                if amt_dec != exp_dec:
                    self.add_error("amount", f"Kwota płatności powinna wynosić {exp_dec} {exp_cur}.")
        new_status = cleaned.get("status") or inst.status
        old_status = inst.status
        if inst.pk and new_status != old_status:
            allowed = _ALLOWED.get(old_status, set())
            if new_status not in allowed:
                self.add_error("status", f"Niedozwolona zmiana statusu z {old_status} na {new_status}.")
        if tx and new_status in _ACTIVE:
            exists = (Payment.objects
                      .filter(transaction=tx)
                      .filter(Q(status="REQUIRES_CONFIRMATION") | Q(status="REQUIRES_ACTION") | Q(status="PROCESSING"))
                      .exclude(pk=inst.pk if inst.pk else None)
                      .exists())
            if exists:
                self.add_error(None, "Dla tej transakcji istnieje już aktywna płatność.")
        return cleaned
