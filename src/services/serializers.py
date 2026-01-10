from __future__ import annotations
from rest_framework import serializers
from djmoney.contrib.django_rest_framework import MoneyField as DRFMoneyField

from catalog.models import ItemType
from services.models import ListingPackage, UserListingPackage, ServicePurchaseHistory

# ----- PACKAGES -----

class ItemTypeShort(serializers.ModelSerializer):
    class Meta:
        model = ItemType
        fields = ("public_id","name")

class ListingPackagePublicResponse(serializers.ModelSerializer):
    item_type = ItemTypeShort()
    price = DRFMoneyField(max_digits=19, decimal_places=2, required=False, allow_null=True)
    class Meta:
        model = ListingPackage
        fields = ("public_id", "listings_free", "price", "points", "item_type")

class ListingPackageAdminResponse(ListingPackagePublicResponse):
    class Meta(ListingPackagePublicResponse.Meta):
        fields = ("public_id", "listings_free", "price", "points", "item_type", "created_at", "updated_at")

class ListingPackageCreateUpdateRequest(serializers.ModelSerializer):
    class Meta:
        model = ListingPackage
        fields = ("listings_free", "price", "points", "item_type")

# ---- USER PACKAGES -----

class UserListingPackageResponse(serializers.ModelSerializer):
    listing_package = ListingPackagePublicResponse()
    class Meta:
        model = UserListingPackage
        fields = ("public_id","free_total","paid_total","listing_package","created_at","updated_at")

# ---- PURCHASE -----

class PurchasePackageRequest(serializers.Serializer):
    listing_package_public_id = serializers.CharField()
    pay_with = serializers.ChoiceField(choices=[("points","points"),("money","money"),("auto","auto")], required=False)

# ---- REPORTS ----

class SlotSummaryRow(serializers.Serializer):
    item_type = serializers.DictField()
    free_total = serializers.IntegerField()
    free_used_active = serializers.IntegerField()
    free_left = serializers.IntegerField()
    paid_total = serializers.IntegerField()
    paid_used_lifetime = serializers.IntegerField()
    paid_left = serializers.IntegerField()
    active_itemsets = serializers.IntegerField()
