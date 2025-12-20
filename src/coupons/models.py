from __future__ import annotations
from decimal import Decimal

from django.db import models
from django.db.models import Q
from djmoney.models.fields import MoneyField
from django.db.models.functions import Lower

from common.models import PublicIdModel
from identity.models import User


class Coupon(PublicIdModel):
    """
    Definicja kuponu:
      - globalny (ma code) — użytkownik podaje kod w transakcji,
      - „sklepik punktowy” (bez code) — użytkownik kupuje egzemplarz UserCoupon za punkty.
    """
    code = models.CharField(max_length=50, unique=True, null=True, blank=True)

    DISCOUNT_TYPE = [("PERCENTAGE", "Percentage"), ("AMOUNT", "Amount")]
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE)

    # Uwaga: dla PERCENTAGE używamy discount_value.amount jako % (np. 10 => 10%)
    discount_value = MoneyField(max_digits=19, decimal_places=2, default_currency="PLN", null=True, blank=True)
    max_discount_value = MoneyField(max_digits=19, decimal_places=2, default_currency="PLN", null=True, blank=True)
    min_purchase_value = MoneyField(max_digits=19, decimal_places=2, default_currency="PLN", null=True, blank=True)

    # Dla „sklepiku punktowego”: stok kuponów i koszt punktowy
    quantity = models.PositiveIntegerField(null=True, blank=True)       # None = bez limitu
    points_cost = models.PositiveIntegerField(null=True, blank=True)    # None = nie do kupienia za punkty

    # Limity użyć (dla GLOBAL – przez code) i per user (dla GLOBAL i USER)
    max_redemptions = models.PositiveIntegerField(null=True, blank=True)   # None = bez limitu
    max_per_user = models.PositiveIntegerField(null=True, blank=True)      # None = bez limitu

    active = models.BooleanField(default=True)
    expiration_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["code"], name="ix_coupon_code"),
            models.Index(fields=["active"], name="ix_coupon_active"),
            models.Index(fields=["expiration_date"], name="ix_coupon_exp"),
        ]
        constraints = [
            models.UniqueConstraint(Lower("code"), name="uq_coupon_code_ci", condition=Q(code__isnull=False)),
        ]

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper() or None
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.code or f"coupon-{self.public_id}"


class UserCoupon(PublicIdModel):
    """
    Kupon „należący” do użytkownika – powstaje po zakupie za punkty, a potem może być
    użyty w transakcji (doklejamy go do Transaction.user_coupon i po COMPLETED oznaczamy redeemed).
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_coupons")
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="user_coupons")

    purchased_at = models.DateTimeField(null=True, blank=True)
    redeemed = models.BooleanField(default=False)
    redeemed_at = models.DateTimeField(null=True, blank=True)

    points_paid = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "redeemed"], name="ix_uc_user_redeemed"),
            models.Index(fields=["coupon"], name="ix_uc_coupon"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.coupon_id}:{'USED' if self.redeemed else 'NEW'}"
