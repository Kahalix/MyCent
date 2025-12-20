from __future__ import annotations
from rest_framework import serializers
from transactions.models import Transaction


class TransactionResponse(serializers.ModelSerializer):
    coupon_id = serializers.UUIDField(read_only=True, allow_null=True)
    customer_id = serializers.UUIDField(read_only=True, allow_null=True)
    user_coupon_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Transaction
        fields = (
            "public_id", "type", "status",
            "expected_total_amount", "expected_total_currency",
            "coupon_id", "user_coupon_id", "customer_id", "customer_snapshot",
            "created_at", "updated_at",
        )
        read_only_fields = fields


class AttachCouponRequest(serializers.Serializer):
    coupon_code = serializers.CharField(required=False, allow_blank=True)
    user_coupon_public_id = serializers.CharField(required=False, allow_blank=True)


class TransactionStatusUpdateRequest(serializers.Serializer):
    status = serializers.ChoiceField(choices=("PENDING", "COMPLETED", "CANCELLED", "REFUNDED"))
    reason = serializers.CharField(required=False, allow_blank=True)
