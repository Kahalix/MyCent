from __future__ import annotations
from rest_framework import serializers
from djmoney.contrib.django_rest_framework import MoneyField as DRFMoney
from decimal import Decimal

from coupons.models import Coupon, UserCoupon


class CouponResponse(serializers.ModelSerializer):
    discount_value = DRFMoney(max_digits=19, decimal_places=2, allow_null=True, default_currency="PLN")
    max_discount_value = DRFMoney(max_digits=19, decimal_places=2, allow_null=True, default_currency="PLN")
    min_purchase_value = DRFMoney(max_digits=19, decimal_places=2, allow_null=True, default_currency="PLN")

    class Meta:
        model = Coupon
        fields = (
            "public_id", "code", "discount_type",
            "discount_value", "max_discount_value", "min_purchase_value",
            "quantity", "points_cost",
            "max_redemptions", "max_per_user",
            "active", "expiration_date",
            "created_at", "updated_at",
        )
        read_only_fields = ("public_id", "created_at", "updated_at")


class CouponCreateUpdateRequest(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = (
            "code", "discount_type",
            "discount_value", "max_discount_value", "min_purchase_value",
            "quantity", "points_cost",
            "max_redemptions", "max_per_user",
            "active", "expiration_date",
        )

    def validate(self, attrs):
        code = attrs.get("code", None)
        if code is not None:
            code = code.strip().upper()
            attrs["code"] = code or None
        dtype = attrs.get("discount_type", getattr(self.instance, "discount_type", None))
        dval = attrs.get("discount_value", getattr(self.instance, "discount_value", None))
        if not dval:
            raise serializers.ValidationError({"discount_value": "Wymagane."})
        if dtype == "PERCENTAGE":
            pct = float(dval.amount)
            if pct < 0 or pct > 100:
                raise serializers.ValidationError({"discount_value": "Dla PERCENTAGE podaj wartość 0-100 (procent)."})
        elif dtype == "AMOUNT":
            if Decimal(str(dval.amount)) <= 0:
                raise serializers.ValidationError({"discount_value": "Dla AMOUNT podaj wartość > 0."})
        return attrs


class UserCouponResponse(serializers.ModelSerializer):
    coupon = CouponResponse()

    class Meta:
        model = UserCoupon
        fields = ("public_id", "coupon", "purchased_at", "redeemed", "redeemed_at", "points_paid", "created_at", "updated_at")


class PurchaseCouponRequest(serializers.Serializer):
    coupon_public_id = serializers.CharField()
