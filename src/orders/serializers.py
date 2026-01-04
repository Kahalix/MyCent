from __future__ import annotations
from decimal import Decimal, InvalidOperation
import re

from rest_framework import serializers
from djmoney.contrib.django_rest_framework import MoneyField as DRFMoneyField
from djmoney.money import Money

from orders.models import Order, OrderLine, OrderShipping
from listings.serializers import ItemSetPublicResponse


class MoneyInputField(serializers.Field):
    def __init__(self, default_currency: str = "PLN", **kwargs):
        self.default_currency = default_currency
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if data is None:
            return None

        if isinstance(data, Money):
            if data.amount < 0:
                raise serializers.ValidationError("Cena za sztukę nie może być ujemna.")
            return data

        if isinstance(data, (int, float, Decimal, str)):
            try:
                amt = Decimal(str(data))
            except InvalidOperation:
                raise serializers.ValidationError("Podaj poprawną kwotę (liczbę).")
            if amt < 0:
                raise serializers.ValidationError("Cena za sztukę nie może być ujemna.")
            return Money(amt, self.default_currency)

        if isinstance(data, dict):
            amount = data.get("amount", None)
            currency = data.get("currency", None) or data.get("amount_currency", None) or self.default_currency
            if amount is None:
                raise serializers.ValidationError("Podaj kwotę ceny za sztukę.")
            try:
                amt = Decimal(str(amount))
            except InvalidOperation:
                raise serializers.ValidationError("Podaj poprawną kwotę (liczbę).")
            if amt < 0:
                raise serializers.ValidationError("Cena za sztukę nie może być ujemna.")
            cur = str(currency or self.default_currency).upper()
            return Money(amt, cur)

        raise serializers.ValidationError("Nieprawidłowy format ceny za sztukę.")

    def to_representation(self, value):
        if value is None:
            return None
        if isinstance(value, Money):
            return {"amount": str(value.amount), "currency": str(value.currency)}
        return value


class OrderLineResponse(serializers.ModelSerializer):
    item = ItemSetPublicResponse(source="item_set")
    unit_price = DRFMoneyField(max_digits=19, decimal_places=2, default_currency="PLN")
    line_total = DRFMoneyField(max_digits=19, decimal_places=2, default_currency="PLN")
    item_snapshot = serializers.JSONField()

    class Meta:
        model = OrderLine
        fields = ("public_id", "item", "quantity", "unit_price", "line_total", "item_snapshot")


class OrderShippingResponse(serializers.ModelSerializer):
    price = DRFMoneyField(max_digits=19, decimal_places=2, default_currency="PLN", allow_null=True)
    order_line_public_id = serializers.CharField(source="order_line.public_id", read_only=True)
    package_type_public_id = serializers.CharField(source="package_type.public_id", read_only=True, allow_null=True)
    mode = serializers.SerializerMethodField()

    def get_mode(self, obj):
        if obj.package_type_id is None:
            return "PICKUP"
        return "PACKAGE"

    class Meta:
        model = OrderShipping
        fields = (
            "public_id", "order_line_public_id", "package_type_public_id",
            "tracking_number", "shipping_status", "package_label", "price",
            "created_at", "updated_at", "mode"
        )


class OrderLineShippingCreateRequest(serializers.Serializer):
    order_line_public_id = serializers.CharField()
    tracking_number = serializers.CharField(max_length=120, required=False, allow_blank=True)
    package_label = serializers.CharField(max_length=120, required=False, allow_blank=True)
    package_type_public_id = serializers.CharField(required=False, allow_blank=True)
    price = DRFMoneyField(max_digits=19, decimal_places=2, required=False, allow_null=True, default_currency="PLN")


class OrderShippingStatusUpdateRequest(serializers.Serializer):
    shipping_status = serializers.ChoiceField(choices=("PENDING", "SHIPPED", "DELIVERED", "CANCELLED", "RETURNED"))


class OrderShippingPatchRequest(serializers.Serializer):
    shipping_status = serializers.ChoiceField(
        choices=("PENDING", "SHIPPED", "DELIVERED", "CANCELLED", "RETURNED"),
        required=False
    )
    tracking_number = serializers.CharField(max_length=120, required=False, allow_blank=True)


class BuyerShippingSelectRequest(serializers.Serializer):
    mode = serializers.ChoiceField(choices=("PICKUP", "PACKAGE"))
    package_type_public_id = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["mode"] == "PACKAGE" and not attrs.get("package_type_public_id"):
            raise serializers.ValidationError({"package_type_public_id": "Wymagane dla wysyłki."})
        return attrs


class OrderPublicResponse(serializers.ModelSerializer):
    items_total = DRFMoneyField(max_digits=19, decimal_places=2, default_currency="PLN", allow_null=True)
    shipping_total = DRFMoneyField(max_digits=19, decimal_places=2, default_currency="PLN", allow_null=True)
    customer_snapshot = serializers.JSONField()
    shipping_address = serializers.JSONField()
    purchase_cost = DRFMoneyField(max_digits=19, decimal_places=2, default_currency="PLN", allow_null=True)
    order_lines = OrderLineResponse(many=True)
    shippings = OrderShippingResponse(many=True)
    tx_type = serializers.CharField(source="transaction.type", read_only=True)
    customer_public_id = serializers.CharField(source="customer.public_id", read_only=True)
    transaction_public_id = serializers.SerializerMethodField()

    def get_transaction_public_id(self, obj):
        try:
            return obj.transaction.public_id
        except Exception:
            return None

    class Meta:
        model = Order
        fields = (
            "public_id", "order_name", "description", "purchase_date",
            "items_total", "shipping_total", "purchase_cost",
            "payment_method", "order_status",
            "seller_profile", "buyer", "transaction",
            "customer_snapshot", "customer_public_id", "shipping_address",
            "order_lines", "shippings", "created_at", "updated_at",
            "tx_type", "transaction_public_id"
        )
        read_only_fields = fields


class OrderShippingAddressRequest(serializers.Serializer):
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    street = serializers.CharField(required=False, allow_blank=True)
    house_number = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)
    state = serializers.CharField(required=False, allow_blank=True)
    postal_code = serializers.CharField(required=False, allow_blank=True)
    country = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        order = self.context.get("order")
        require_full = False

        if order is not None:
            for s in order.shippings.all():
                if s.package_type_id is not None:
                    require_full = True
                    break
                label = (s.package_label or "").strip().upper()
                if label and label != "PICKUP":
                    require_full = True
                    break

        if not require_full:
            return attrs

        errors = {}
        required = ["first_name", "last_name", "phone_number", "email", "street", "house_number", "city", "postal_code", "country"]

        for field in required:
            value = (attrs.get(field) or "").strip()
            if not value:
                errors[field] = "To pole jest wymagane."

        phone_raw = str(attrs.get("phone_number") or "")
        phone_digits = re.sub(r"\D+", "", phone_raw)
        if phone_digits and len(phone_digits) < 6:
            errors["phone_number"] = "Nieprawidłowy numer telefonu"

        postal = (attrs.get("postal_code") or "").strip()
        if postal and not re.match(r"^[0-9]{2}-[0-9]{3}$", postal):
            errors["postal_code"] = "Nieprawidłowy kod pocztowy"

        if errors:
            raise serializers.ValidationError(errors)

        return attrs


class CheckoutRequest(serializers.Serializer):
    item_public_id = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    payment_method = serializers.ChoiceField(
        choices=("CREDIT_CARD", "DEBIT_CARD", "PAYPAL", "BANK_TRANSFER"),
        default="CREDIT_CARD"
    )
    order_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)


class OfflineCustomerPayload(serializers.Serializer):
    customer_public_id = serializers.CharField(required=False, allow_blank=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    address = serializers.DictField(child=serializers.CharField(), required=False)
    document_type = serializers.CharField(required=False, allow_blank=True)
    document_number = serializers.CharField(required=False, allow_blank=True)
    birth_date = serializers.DateField(required=False)


class SellerOfflineCheckoutLineIn(serializers.Serializer):
    item_public_id = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    unit_price = MoneyInputField(required=False, allow_null=True, default_currency="PLN")


class SellerOfflineCheckoutRequest(serializers.Serializer):
    lines = serializers.ListField(child=SellerOfflineCheckoutLineIn(), required=False, allow_empty=False)

    item_public_id = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1, required=False, default=1)

    payment_method = serializers.ChoiceField(
        choices=("CASH", "CREDIT_CARD", "DEBIT_CARD", "PAYPAL", "BANK_TRANSFER", "CASH_ON_DELIVERY"),
        default="CASH"
    )
    customer = OfflineCustomerPayload(required=False)

    def validate(self, attrs):
        lines = attrs.get("lines") or []
        legacy_pid = (attrs.get("item_public_id") or "").strip()
        legacy_qty = int(attrs.get("quantity") or 1)

        if not lines:
            if not legacy_pid:
                raise serializers.ValidationError({"lines": "Dodaj co najmniej jedną pozycję."})
            attrs["lines"] = [{"item_public_id": legacy_pid, "quantity": legacy_qty}]
            return attrs

        norm = []
        for row in lines:
            pid = (row.get("item_public_id") or "").strip()
            if not pid:
                raise serializers.ValidationError({"lines": "Każda pozycja musi mieć item_public_id."})

            qty = int(row.get("quantity") or 1)
            if qty < 1:
                raise serializers.ValidationError({"lines": "Ilość w każdej pozycji musi wynosić co najmniej 1."})

            out = {"item_public_id": pid, "quantity": qty}

            if row.get("unit_price") is not None:
                up = row.get("unit_price")
                if isinstance(up, Money) and up.amount < 0:
                    raise serializers.ValidationError({"lines": "Cena za sztukę nie może być ujemna."})
                out["unit_price"] = up

            norm.append(out)

        attrs["lines"] = norm
        return attrs


class PawnPurchaseLineIn(serializers.Serializer):
    title = serializers.CharField(max_length=300)
    attributes = serializers.DictField(child=serializers.JSONField(), required=False)
    quantity = serializers.IntegerField(min_value=1, default=1)
    unit_price = DRFMoneyField(max_digits=19, decimal_places=2, default_currency="PLN")
    listing_price = DRFMoneyField(max_digits=19, decimal_places=2, required=False, allow_null=True, default_currency="PLN")
    notes = serializers.CharField(required=False, allow_blank=True)
    item_type_public_id = serializers.CharField(required=False, allow_blank=True)


class SellerPawnPurchaseRequest(serializers.Serializer):
    seller_public_id = serializers.CharField(required=False, allow_blank=True)
    lines = serializers.ListField(child=PawnPurchaseLineIn(), min_length=1)
    customer = OfflineCustomerPayload(required=False)
    note = serializers.CharField(required=False, allow_blank=True)
    purchase_date = serializers.DateField(required=False)
    payment_method = serializers.ChoiceField(
        choices=("CASH", "BANK_TRANSFER", "DEBIT_CARD", "CREDIT_CARD", "PAYPAL", "CASH_ON_DELIVERY"),
        default="CASH"
    )
    create_itemsets = serializers.BooleanField(required=False, default=True)
