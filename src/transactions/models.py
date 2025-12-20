from __future__ import annotations
from django.db import models
from django.db.models import Q
from common.models import PublicIdModel
from identity.models import User
from customers.models import Customer
from coupons.models import Coupon, UserCoupon


class Transaction(PublicIdModel):
    TYPE = [
        ("PURCHASE", "Purchase"),           # klient kupuje online/offline od sklepu
        ("PAWN_PURCHASE", "Pawn purchase"), # skup od klienta (przyjęcie towaru)
        ("PAWN_EXTENSION", "Pawn Extension"),
        ("PAWN_REDEEM", "Pawn Redeem"),
        ("PLEDGE", "Pledge"),
    ]
    STATUS = [
        ("PENDING", "Pending"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
        ("REFUNDED", "Refunded"),
    ]

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="transactions")

    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")
    customer_snapshot = models.JSONField(default=dict, blank=True)

    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")
    user_coupon = models.ForeignKey(UserCoupon, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions_used_in")

    type = models.CharField(max_length=16, choices=TYPE, default="PURCHASE")
    status = models.CharField(max_length=10, choices=STATUS, default="PENDING")

    expected_total_amount = models.DecimalField(max_digits=19, decimal_places=2, null=True, blank=True)
    expected_total_currency = models.CharField(max_length=3, default="PLN", blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "status"], name="ix_tx_user_status"),
            models.Index(fields=["type"], name="ix_tx_type"),
            models.Index(fields=["coupon"], name="ix_tx_coupon"),
            models.Index(fields=["user_coupon"], name="ix_tx_user_coupon"),
            models.Index(fields=["created_at"], name="ix_tx_created"),
        ]
        constraints = [
            models.CheckConstraint(
                name="ck_tx_expected_nonnegative",
                check=Q(expected_total_amount__isnull=True) | Q(expected_total_amount__gte=0),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type} {self.public_id}"


class TransactionStatusHistory(PublicIdModel):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=10, blank=True)
    to_status = models.CharField(max_length=10)
    reason = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.transaction.public_id}: {self.from_status} → {self.to_status}"
