from __future__ import annotations
from django.contrib.auth import get_user_model
from rest_framework import serializers
from djmoney.contrib.django_rest_framework.fields import MoneyField as DRFMoneyField
from .models import PackageType, ShippingAddress

User = get_user_model()


# ===== PackageType =====

class PackageTypePublicResponse(serializers.ModelSerializer):
    price = DRFMoneyField(max_digits=19, decimal_places=2, required=False, allow_null=True)

    class Meta:
        model = PackageType
        fields = (
            "public_id", "provider", "dimensions",
            "max_length_cm", "max_width_cm", "max_height_cm", "max_weight_kg",
            "price", "points"
        )


class PackageTypeAdminResponse(PackageTypePublicResponse):
    pass


class PackageTypeCreateUpdateRequest(serializers.ModelSerializer):
    price = DRFMoneyField(max_digits=19, decimal_places=2, required=False, allow_null=True)

    class Meta:
        model = PackageType
        fields = (
            "provider", "dimensions",
            "max_length_cm", "max_width_cm", "max_height_cm", "max_weight_kg",
            "price", "points"
        )

    def validate(self, data):
        for k in ("max_length_cm","max_width_cm","max_height_cm"):
            if data.get(k) is not None and data[k] == 0:
                raise serializers.ValidationError({k: "Musi być > 0 lub null"})
        if data.get("max_weight_kg") is not None and data["max_weight_kg"] <= 0:
            raise serializers.ValidationError({"max_weight_kg": "Musi byc > 0 lub null"})
        return data


# ===== ShippingAddress =====

class ShippingAddressResponse(serializers.ModelSerializer):
    user_public_id = serializers.CharField(source="user.public_id", read_only=True)

    class Meta:
        model = ShippingAddress
        fields = (
            "public_id", "user_public_id",
            "first_name", "last_name", "phone_number", "email",
            "street", "house_number", "city", "state", "postal_code", "country"
        )


class ShippingAddressUpsertRequest(serializers.ModelSerializer):
    class Meta:
        model = ShippingAddress
        fields = (
            "first_name", "last_name", "phone_number", "email",
            "street", "house_number", "city", "state", "postal_code", "country"
        )
