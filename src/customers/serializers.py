from __future__ import annotations
from rest_framework import serializers
from customers.models import Customer


class CustomerResponse(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = (
            "public_id",
            "first_name","last_name","email","phone",
            "address_line1","address_line2","postal_code","city","country",
            "document_type","document_number","birth_date",
            "created_at","updated_at",
        )
        read_only_fields = ("public_id","created_at","updated_at")


class CustomerCreateUpdateRequest(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = (
            "first_name","last_name","email","phone",
            "address_line1","address_line2","postal_code","city","country",
            "document_type","document_number","birth_date",
        )

    def validate(self, attrs):
        email = (attrs.get("email") or "").strip()
        phone = (attrs.get("phone") or "").strip()
        if not email and not phone:
            raise serializers.ValidationError({"email": "Podaj e-mail lub telefon.", "phone": "Podaj e-mail lub telefon."})
        attrs["email"] = email or None
        attrs["phone"] = phone
        country = (attrs.get("country") or "").strip().upper()
        if country:
            if len(country) != 2:
                raise serializers.ValidationError({"country": "Kod kraju powinien mieć 2 znaki (ISO 3166-1 alpha-2)."})
            attrs["country"] = country
        return attrs