from __future__ import annotations
from rest_framework import serializers
from djmoney.contrib.django_rest_framework import MoneyField as DRFMoney
from payments.models import Payment

class PaymentResponse(serializers.ModelSerializer):
    amount = DRFMoney(max_digits=19, decimal_places=2, default_currency="PLN")
    transaction_public_id = serializers.CharField(source="transaction.public_id", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "public_id", "transaction_public_id", "provider", "status",
            "amount", "client_secret", "provider_payment_id", "metadata",
            "created_at", "updated_at",
        )
        read_only_fields = fields

class PaymentSellerResponse(serializers.ModelSerializer):
    amount = DRFMoney(max_digits=19, decimal_places=2, default_currency="PLN")
    transaction_public_id = serializers.CharField(source="transaction.public_id", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "public_id", "transaction_public_id", "provider", "status",
            "amount", "metadata", "created_at", "updated_at",
        )
        read_only_fields = fields

class CreatePaymentRequest(serializers.Serializer):
    transaction_public_id = serializers.CharField()
    provider = serializers.ChoiceField(choices=("SIM", "STRIPE"), required=False, allow_blank=True)
    coupon_code = serializers.CharField(required=False, allow_blank=True)
    user_coupon_public_id = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        code = (attrs.get("coupon_code") or "").strip()
        ucid = (attrs.get("user_coupon_public_id") or "").strip()
        if code and ucid:
            raise serializers.ValidationError("Podaj tylko coupon_code albo user_coupon_public_id (nie oba).")
        attrs["coupon_code"] = code
        attrs["user_coupon_public_id"] = ucid
        return attrs

class ConfirmPaymentRequest(serializers.Serializer):
    result = serializers.ChoiceField(choices=("success", "fail"))

class CancelPaymentRequest(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)
