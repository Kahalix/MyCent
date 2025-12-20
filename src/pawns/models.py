from __future__ import annotations
from django.db import models
from django.db.models import Q, F
from djmoney.models.fields import MoneyField
from moneyed import Money

from common.models import PublicIdModel
from customers.models import Customer
from identity.models import User, SellerProfile
from listings.models import ItemSet
from transactions.models import Transaction


class Pawn(PublicIdModel):
    """
    Umowa zastawu.
    """
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, related_name="pawns")
    seller_profile = models.ForeignKey(SellerProfile, on_delete=models.PROTECT, related_name="pawns")
    operator = models.ForeignKey(User, on_delete=models.PROTECT, related_name="pawns_created")

    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="pawns")
    customer_snapshot = models.JSONField(default=dict, blank=True)

    # cache wyceny z linii
    appraisal_total = MoneyField(max_digits=19, decimal_places=2, default=Money(0, "PLN"), default_currency="PLN")
    # wypłacony kapitał
    principal = MoneyField(max_digits=19, decimal_places=2, default_currency="PLN")

    start_date = models.DateField()
    due_date   = models.DateField()  # termin wykupu
    redeemed_at  = models.DateTimeField(null=True, blank=True)
    forfeited_at = models.DateTimeField(null=True, blank=True)

    STATUS = [("ACTIVE","Active"),("REDEEMED","Redeemed"),("FORFEITED","Forfeited"),("CANCELLED","Cancelled")]
    status = models.CharField(max_length=10, choices=STATUS, default="ACTIVE")

    # po przepadku można utworzyć draft ogłoszenia
    forfeited_item = models.ForeignKey(ItemSet, null=True, blank=True, on_delete=models.SET_NULL, related_name="from_pawn")

    class Meta:
        indexes = [
            models.Index(fields=["seller_profile","status"], name="ix_pawn_seller_status"),
            models.Index(fields=["due_date"], name="ix_pawn_due"),
            models.Index(fields=["customer"], name="ix_pawn_customer"),
        ]
        constraints = [
            models.CheckConstraint(
                name="ck_pawn_due_after_start",
                check=Q(due_date__gte=F("start_date")),
            ),
        ]

    @property
    def is_active(self) -> bool:
        return self.status == "ACTIVE" and self.redeemed_at is None and self.forfeited_at is None

    def recalc_appraisal(self, save: bool = True):
        total = Money(0, self.principal.currency)
        for l in self.lines.all():
            if l.appraisal_value:
                if l.appraisal_value.currency != total.currency:
                    from djmoney.money import Money as M
                    val = M(l.appraisal_value.amount, total.currency)
                else:
                    val = l.appraisal_value
                qty = l.quantity or 1
                total += val * qty
        self.appraisal_total = total
        if save:
            self.save(update_fields=["appraisal_total", "updated_at"])

    def __str__(self):
        return f"Pawn {self.public_id} [{self.status}]"


class PawnLine(PublicIdModel):
    pawn = models.ForeignKey(Pawn, on_delete=models.CASCADE, related_name="lines")
    # powiązanie z ItemSet nie jest wymagane — zwykle snapshot
    item_set = models.ForeignKey(ItemSet, null=True, blank=True, on_delete=models.SET_NULL, related_name="pawn_lines")

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    quantity = models.PositiveIntegerField(default=1)

    appraisal_value = MoneyField(max_digits=19, decimal_places=2, default_currency="PLN", null=True, blank=True)
    item_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["pawn"], name="ix_pawn_lines_pawn"),
        ]

    def __str__(self):  # pragma: no cover
        return f"{self.title} x{self.quantity}"


class PawnExtension(PublicIdModel):
    pawn = models.ForeignKey(Pawn, on_delete=models.CASCADE, related_name="extensions")
    days = models.PositiveIntegerField(choices=((7, "7"), (14, "14"), (30, "30")))
    fee = MoneyField(max_digits=19, decimal_places=2, default_currency="PLN")
    previous_due = models.DateField()
    new_due = models.DateField()

    # transakcja księgująca opłatę (natychmiast finalizowana offline)
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, related_name="pawn_extensions")

    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="pawn_extensions_created")

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):  # pragma: no cover
        return f"Extension {self.days}d ({self.fee})"
