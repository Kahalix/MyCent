from __future__ import annotations

from rest_framework import serializers
from djmoney.contrib.django_rest_framework import MoneyField as DRFMoneyField

from carts.models import Cart, CartItem


class ItemTypeMiniResponse(serializers.Serializer):
    path = serializers.CharField()


class CatalogItemMiniResponse(serializers.Serializer):
    image_path = serializers.CharField(allow_blank=True, required=False)


class ItemImageMiniResponse(serializers.Serializer):
    image_path = serializers.CharField(allow_blank=True, required=False)
    image = serializers.CharField(allow_blank=True, required=False)


class ItemSetCartResponse(serializers.Serializer):
    public_id = serializers.CharField()
    slug = serializers.CharField(allow_blank=True, required=False)
    set_name = serializers.CharField(allow_blank=True, required=False)
    price = DRFMoneyField(max_digits=19, decimal_places=2, default_currency="PLN")
    cover_image_url = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    catalog_item = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()

    def get_cover_image_url(self, obj):
        return getattr(obj, "cover_image_url", None)

    def get_type(self, obj):
        t = getattr(obj, "type", None)
        if not t:
            return None
        return {"path": getattr(t, "path", None)}

    def get_catalog_item(self, obj):
        ci = getattr(obj, "catalog_item", None)
        if not ci:
            return None
        return {"image_path": getattr(ci, "image_path", "")}

    def get_images(self, obj):
        imgs = getattr(obj, "_cart_images", None)
        if imgs is None:
            rel = getattr(obj, "images", None)
            if rel is None:
                return []
            imgs = list(rel.all()[:1])
        out = []
        for im in imgs[:1]:
            out.append({
                "image_path": getattr(im, "image_path", "") or "",
                "image": getattr(im, "image", "") or "",
            })
        return out


class CartItemResponse(serializers.ModelSerializer):
    item = ItemSetCartResponse(source="item_set")

    class Meta:
        model = CartItem
        fields = ("public_id", "item", "quantity")


class CartResponse(serializers.ModelSerializer):
    items = CartItemResponse(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = ("public_id", "status", "items", "created_at", "updated_at")


class AddToCartRequest(serializers.Serializer):
    item_public_id = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class SetQtyRequest(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0)


class CheckoutCartRequest(serializers.Serializer):
    payment_method = serializers.ChoiceField(
        choices=("CREDIT_CARD", "DEBIT_CARD", "PAYPAL", "BANK_TRANSFER", "ONLINE_PAYMENT"),
        default="CREDIT_CARD",
    )
