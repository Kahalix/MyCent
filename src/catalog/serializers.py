from __future__ import annotations
from rest_framework import serializers
from .models import ItemType, CatalogItem

# ===== ItemType =====
class ItemTypePublicResponse(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    parent = serializers.SerializerMethodField()
    children_count = serializers.IntegerField(read_only=True)
    is_leaf = serializers.SerializerMethodField()
    schema = serializers.SerializerMethodField()
    ui_schema = serializers.SerializerMethodField()

    class Meta:
        model = ItemType
        fields = (
            "id", "public_id", "name", "slug", "path", "parent", "children_count",
            "is_leaf", "schema", "ui_schema", "created_at"
        )

    def get_parent(self, obj):
        if not obj.parent_id:
          return None
        p = obj.parent
        return {
            "id": p.id,
            "public_id": p.public_id,
            "name": p.name,
            "slug": p.slug,
            "path": p.path,
        }

    def get_is_leaf(self, obj):
        try:
            return obj.children_count == 0
        except Exception:
            return not obj.children.exists()

    def get_schema(self, obj):
        return obj.schema_json if self.get_is_leaf(obj) else None

    def get_ui_schema(self, obj):
        return obj.ui_schema_json if self.get_is_leaf(obj) else None


class ItemTypeSchemaResponse(serializers.Serializer):
    path = serializers.CharField()
    is_leaf = serializers.BooleanField()
    schema = serializers.JSONField()
    ui_schema = serializers.JSONField()

class ItemTypeNodeResponse(serializers.ModelSerializer):
    """Węzeł drzewa: dzieci w płaskiej liście """
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ItemType
        fields = ("id", "public_id", "name", "slug", "path")

class ItemTypeCreateRequest(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    parent_path = serializers.CharField(max_length=1024, required=False, allow_blank=True)

class ItemTypeUpdateRequest(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    parent_path = serializers.CharField(max_length=1024, required=False, allow_blank=True)

# ===== CatalogItem =====
class CatalogItemPublicResponse(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    type = serializers.SerializerMethodField()

    class Meta:
        model = CatalogItem
        fields = ("id", "public_id","item_name","slug","image_path","attributes","type","created_at")
        read_only_fields = ("slug","public_id","created_at")

    def get_type(self, obj):
        t = obj.type
        return {
            "id": t.id,
            "public_id": t.public_id,
            "name": t.name,
            "slug": t.slug,
            "path": t.path
        }

class CatalogItemCreateUpdateRequest(serializers.Serializer):
    item_name = serializers.CharField(max_length=255, required=False)
    type_path = serializers.CharField(max_length=1024, required=False)
    attributes = serializers.JSONField(required=False)

class CatalogItemImageUploadRequest(serializers.Serializer):
    image = serializers.ImageField()

