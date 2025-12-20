from __future__ import annotations
from rest_framework import serializers
from .models import SavedListing, SavedSearch, SavedSearchItem
from listings.serializers import ItemSetPublicResponse

# === Saved Listing ===
class SavedListingCreateRequest(serializers.Serializer):
    item_public_id = serializers.CharField(max_length=64)

class SavedListingResponse(serializers.ModelSerializer):
    item = serializers.SerializerMethodField()

    class Meta:
        model = SavedListing
        fields = ("public_id","created_at","price_drop_notification_sent","item")

    def get_item(self, obj):
        req = self.context.get("request")
        return ItemSetPublicResponse(obj.item_set, context={"request": req}).data


# === Saved Search ===
class SavedSearchCreateRequest(serializers.ModelSerializer):
    class Meta:
        model = SavedSearch
        fields = ("category_path","query_string","search_phrase")

class SavedSearchUpdateRequest(serializers.ModelSerializer):
    class Meta:
        model = SavedSearch
        fields = ("category_path","query_string","search_phrase")
        extra_kwargs = {
            "category_path": {"required": False, "allow_blank": True, "default": ""},
            "query_string": {"required": False},
            "search_phrase": {"required": False},
        }

class SavedSearchResponse(serializers.ModelSerializer):
    items_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = SavedSearch
        fields = ("public_id","created_at","category_path","query_string","search_phrase","items_count")


class SavedSearchItemResponse(serializers.ModelSerializer):
    item = serializers.SerializerMethodField()

    class Meta:
        model = SavedSearchItem
        fields = ("public_id","created_at","item")

    def get_item(self, obj):
        return ItemSetPublicResponse(obj.item_set, context=self.context).data
