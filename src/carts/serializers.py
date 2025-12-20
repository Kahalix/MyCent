from __future__ import annotations
from rest_framework import serializers
from carts.models import Cart, CartItem
from listings.serializers import ItemSetPublicResponse

class CartItemResponse(serializers.ModelSerializer):
    item = ItemSetPublicResponse(source="item_set")
    class Meta:
        model = CartItem
        fields = ("public_id","item","quantity")

class CartResponse(serializers.ModelSerializer):
    items = CartItemResponse(many=True)
    class Meta:
        model = Cart
        fields = ("public_id","status","items","created_at","updated_at")

class AddToCartRequest(serializers.Serializer):
    item_public_id = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1, default=1)

class SetQtyRequest(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0)

class CheckoutCartRequest(serializers.Serializer):
    # Kupujący online: tylko metody online
    payment_method = serializers.ChoiceField(
        choices = ("CREDIT_CARD", "DEBIT_CARD", "PAYPAL", "BANK_TRANSFER", "ONLINE_PAYMENT"),
        default = "CREDIT_CARD"
    )
