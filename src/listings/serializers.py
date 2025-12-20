# src/listings/serializers.py
from __future__ import annotations
from rest_framework import serializers
from djmoney.contrib.django_rest_framework import MoneyField as DRFMoneyField
from django.contrib.auth import get_user_model

from saved.models import SavedListing
from .models import ItemSet, ItemSetImage, ItemSetShipping
from shipping.models import PackageType
from identity.serializers import PublicUserResponse
from identity.models import SellerProfile
from catalog.models import CatalogItem, ItemType
from django.core.files.storage import default_storage

User = get_user_model()

# ------- Helper: PackageType minimal -------
class PackageTypeResponse(serializers.ModelSerializer):
    class Meta:
        model = PackageType
        fields = ("public_id","provider","dimensions","max_length_cm","max_width_cm","max_height_cm","max_weight_kg","price","points")

# ------- Images -------
class ItemSetImageResponse(serializers.ModelSerializer):
    class Meta:
        model = ItemSetImage
        fields = ("public_id","image","image_path","image_order")

class ItemSetImageUploadRequest(serializers.Serializer):
    image = serializers.ImageField(required=False)
    image_path = serializers.CharField(required=False, allow_blank=True)
    image_order = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if not attrs.get("image") and not attrs.get("image_path"):
            raise serializers.ValidationError({"image": "Wymagane jest image lub image_path."})
        return attrs

class ItemSetImageReorderRequest(serializers.Serializer):
    order = serializers.ListField(
        child=serializers.CharField(min_length=3, max_length=80),
        allow_empty=False
    )

class ItemSetImageOrderUpdateRequest(serializers.Serializer):
    image_order = serializers.IntegerField(min_value=0)

# ------- Shipping (through) -------
class ItemSetShippingResponse(serializers.ModelSerializer):
    package_type = PackageTypeResponse()
    # -> dodajemy effective_price żeby UI miał jedną ścieżkę do ceny
    effective_price = serializers.SerializerMethodField()

    class Meta:
        model = ItemSetShipping
        fields = ("public_id","package_type","price_override","effective_price")

    def get_effective_price(self, obj):
        m = obj.price_override or (obj.package_type.price if obj.package_type else None)
        if m is None:
            return None
        return {"amount": str(m.amount), "currency": str(m.currency)}

class ItemSetShippingCreateRequest(serializers.Serializer):
    package_type_public_id = serializers.CharField()
    price_override = DRFMoneyField(max_digits=19, decimal_places=2, required=False, allow_null=True, default_currency="PLN")

    packed_length_cm = serializers.IntegerField(required=False, min_value=1)
    packed_width_cm  = serializers.IntegerField(required=False, min_value=1)
    packed_height_cm = serializers.IntegerField(required=False, min_value=1)
    packed_weight_kg = serializers.DecimalField(required=False, max_digits=10, decimal_places=3, min_value=0.001)

class SuggestPackageTypeItemResponse(serializers.Serializer):
    package_type = PackageTypeResponse()
    effective_price = DRFMoneyField(
        max_digits=19, decimal_places=2,
        required=False, allow_null=True, default_currency="PLN"
    )
    price_source = serializers.ChoiceField(choices=("override", "catalog", "unknown"))
    already_linked = serializers.BooleanField()

# ------- ItemSet – Responses -------
class ItemTypeMini(serializers.ModelSerializer):
    class Meta:
        model = ItemType
        fields = ("public_id","name","slug","path")

class CatalogItemMini(serializers.ModelSerializer):
    # można też dodać typ, żeby mieć ścieżkę kategorii na froncie
    type = ItemTypeMini(read_only=True)

    class Meta:
        model = CatalogItem
        fields = ("public_id","slug","item_name","image_path","type")

class UserMini(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("public_id","first_name","last_name","email","user_image")

class ItemSetPublicResponse(serializers.ModelSerializer):
    price = DRFMoneyField(max_digits=19, decimal_places=2, default_currency="PLN")
    images = ItemSetImageResponse(many=True)
    seller_slug = serializers.CharField(source="seller_profile.slug", allow_null=True)
    owner = UserMini(source="owner_user", allow_null=True)
    shipping_options = ItemSetShippingResponse(many=True)
    type = ItemTypeMini(read_only=True)
    catalog_item = CatalogItemMini(read_only=True)

    cover_image_url = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()

    class Meta:
        model = ItemSet
        fields = (
            "public_id", "set_name", "slug", "description", "price", "stock_quantity",
            "condition", "status", "listing_type", "added_by", "allow_online_checkout",
            "length_cm", "width_cm", "height_cm", "weight_kg",
            "seller_slug", "owner", "type",
            "catalog_item_id",
            "catalog_item",
            "attributes", "images", "shipping_options",
            "created_at", "updated_at",
            "cover_image_url", "is_saved",
        )

    def get_cover_image_url(self, obj):
        try:
            img = getattr(obj, "images", None)
            if hasattr(img, "order_by"):
                img = img.order_by("image_order", "id").first()
            else:
                img = None
        except Exception:
            img = None

        if not img:
            return None

        url = None
        try:
            if img.image:
                url = img.image.url
        except Exception:
            url = None

        if not url and img.image_path:
            try:
                url = default_storage.url(img.image_path)
            except Exception:
                url = img.image_path

        if not url:
            return None

        req = self.context.get("request")
        if req and url and not (url.startswith("http://") or url.startswith("https://")):
            return req.build_absolute_uri(url)
        return url

    def get_is_saved(self, obj):
        ann = getattr(obj, "is_saved", None)
        if ann is not None:
            return bool(ann)

        req = self.context.get("request")
        user = getattr(req, "user", None)
        if not (user and user.is_authenticated):
            return False
        return SavedListing.objects.filter(user=user, item_set=obj).exists()

class ItemSetOwnerResponse(ItemSetPublicResponse):
    """To samo + pola wew. mogą kiedyś dojść; zostawione na przyszłość."""
    pass

class ItemSetAdminResponse(ItemSetPublicResponse):
    """Admin też może zobaczyć to samo (albo rozszerzyć)."""
    pass

# ------- ItemSet – Requests -------
class ItemSetCreateRequest(serializers.ModelSerializer):
    class Meta:
        model = ItemSet
        fields = (
            "set_name","slug","description","price","stock_quantity",
            "condition","status","listing_type","type","catalog_item",
            "length_cm","width_cm","height_cm","weight_kg",
            "attributes","allow_online_checkout",
        )

    def validate(self, data):
        data = super().validate(data)
        if data.get("allow_online_checkout"):
            lt = data.get("listing_type")
            if lt != "BUY":
                raise serializers.ValidationError({
                    "allow_online_checkout": "Checkout online dozwolony tylko dla typu ogłoszenia BUY."
                })
        return data

    def validate_type(self, value):
        if value and ItemType.objects.filter(parent=value).exists():
            raise serializers.ValidationError("Wybierz kategorię końcową (bez podkategorii).")
        return value

class ItemSetUpdateRequest(serializers.ModelSerializer):
    class Meta:
        model = ItemSet
        fields = (
            "set_name","description","price","stock_quantity",
            "condition","status","listing_type",
            "length_cm","width_cm","height_cm","weight_kg",
            "attributes","catalog_item","type","allow_online_checkout",
        )

    def validate(self, data):
        data = super().validate(data)
        # dla PATCH odczytaj listing_type z instancji, jeśli nie przyszedł w payloadzie
        lt = data.get("listing_type") or (getattr(self.instance, "listing_type", None) if self.instance else None)
        if data.get("allow_online_checkout") and lt != "BUY":
            raise serializers.ValidationError({
                "allow_online_checkout": "Checkout online dozwolony tylko dla typu ogłoszenia BUY."
            })
        return data

    def validate_type(self, value):
        if value and ItemType.objects.filter(parent=value).exists():
            raise serializers.ValidationError("Wybierz kategorię końcową (bez podkategorii).")
        return value

class ItemSetStatusUpdateRequest(serializers.Serializer):
    status = serializers.ChoiceField(choices=[c[0] for c in ItemSet.STATUS])

class PrefillFromCatalogResponse(serializers.Serializer):
    catalog_item_id = serializers.UUIDField()
    attributes = serializers.DictField(child=serializers.JSONField())

