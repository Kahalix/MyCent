from __future__ import annotations
from rest_framework import serializers
from djmoney.contrib.django_rest_framework import MoneyField as DRFMoneyField

from pawns.models import Pawn, PawnLine, PawnExtension


class PawnLineResponse(serializers.ModelSerializer):
    appraisal_value = DRFMoneyField(max_digits=19, decimal_places=2, allow_null=True, default_currency="PLN")

    class Meta:
        model = PawnLine
        fields = ("public_id","title","description","quantity","appraisal_value","item_snapshot","created_at","updated_at")
        read_only_fields = fields


class PawnExtensionResponse(serializers.ModelSerializer):
    fee = DRFMoneyField(max_digits=19, decimal_places=2, default_currency="PLN")

    class Meta:
        model = PawnExtension
        fields = ("public_id","days","fee","previous_due","new_due","created_at","updated_at")
        read_only_fields = fields


class PawnResponse(serializers.ModelSerializer):
    principal = DRFMoneyField(max_digits=19, decimal_places=2, default_currency="PLN")
    appraisal_total = DRFMoneyField(max_digits=19, decimal_places=2, default_currency="PLN")
    lines = PawnLineResponse(many=True, read_only=True)
    extensions = PawnExtensionResponse(many=True, read_only=True)
    is_active = serializers.SerializerMethodField()
    customer_public_id = serializers.CharField(source="customer.public_id", read_only=True)

    class Meta:
        model = Pawn
        fields = (
            "public_id","seller_profile","operator","customer", "customer_public_id", "customer_snapshot",
            "principal","appraisal_total",
            "start_date","due_date","redeemed_at","forfeited_at",
            "status","is_active","forfeited_item",
            "lines","extensions","created_at","updated_at",
        )
        read_only_fields = fields

    def get_is_active(self, obj: Pawn) -> bool:
        return obj.is_active


# ==== input ====

class PawnLineIn(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1, default=1)
    appraisal_value = DRFMoneyField(max_digits=19, decimal_places=2, required=False, allow_null=True, default_currency="PLN")
    item_set_public_id = serializers.CharField(required=False, allow_blank=True)
    item_snapshot = serializers.DictField(required=False)

class PawnCreateRequest(serializers.Serializer):
    seller_public_id = serializers.CharField()
    customer_public_id = serializers.CharField(required=False, allow_blank=True)
    customer_snapshot = serializers.DictField(required=False)
    principal = DRFMoneyField(max_digits=19, decimal_places=2, default_currency="PLN")
    due_in_days = serializers.IntegerField(min_value=1, default=30)
    lines = serializers.ListField(child=PawnLineIn(), min_length=1)

class PawnExtendRequest(serializers.Serializer):
    days = serializers.ChoiceField(choices=(7,14,30))
