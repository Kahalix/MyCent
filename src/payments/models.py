from __future__ import annotations
from django.db import models
from django.db.models import Q
from djmoney.models.fields import MoneyField
from moneyed import Money

from common.models import PublicIdModel
from transactions.models import Transaction


class Payment(PublicIdModel):
    PROVIDER = [("SIM", "Simulator"), ("STRIPE", "Stripe")]
    STATUS = [
        ("REQUIRES_CONFIRMATION", "REQUIRES_CONFIRMATION"),
        ("REQUIRES_ACTION",       "REQUIRES_ACTION"),
        ("PROCESSING",            "PROCESSING"),
        ("SUCCEEDED",             "SUCCEEDED"),
        ("FAILED",                "FAILED"),
        ("CANCELLED",             "CANCELLED"),
    ]

    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, related_name="payments")
    provider    = models.CharField(max_length=16, choices=PROVIDER, default="SIM")
    amount      = MoneyField(max_digits=19, decimal_places=2, default=Money(0, "PLN"), default_currency="PLN")
    status      = models.CharField(max_length=32, choices=STATUS, default="REQUIRES_CONFIRMATION")

    provider_payment_id = models.CharField(max_length=120, blank=True)
    client_secret       = models.CharField(max_length=120, blank=True)
    metadata            = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["transaction", "status"], name="ix_payment_tx_status"),
            models.Index(fields=["provider"], name="ix_payment_provider"),
            models.Index(fields=["created_at"], name="ix_payment_created"),
            models.Index(fields=["provider", "provider_payment_id"], name="ix_payment_provider_pid"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["transaction"],
                condition=(Q(status="REQUIRES_CONFIRMATION") | Q(status="PROCESSING") | Q(status="REQUIRES_ACTION")),
                name="uq_active_payment_per_tx",
            ),
            models.UniqueConstraint(
                fields=["provider", "provider_payment_id"],
                condition=~Q(provider_payment_id=""),
                name="uq_provider_pid_not_empty",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.public_id}"
