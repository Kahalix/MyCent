from __future__ import annotations
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from urllib.parse import unquote

from identity.permissions import IsAdmin
from catalog.models import ItemType, CatalogItem
from catalog.serializers import (
    ItemTypePublicResponse, ItemTypeCreateRequest, ItemTypeUpdateRequest, ItemTypeNodeResponse,
    CatalogItemPublicResponse, CatalogItemCreateUpdateRequest, CatalogItemImageUploadRequest, ItemTypeSchemaResponse
)
from catalog.filters import ItemTypeFilter, CatalogItemFilter
from catalog.services import commands, queries
from listings.serializers import PrefillFromCatalogResponse as ListingPrefillResponse
from listings.services.commands import prefill_from_catalog as listing_prefill

User = get_user_model()

# ===== PUBLIC: categories =====
class PublicCategoryViewSet(mixins.ListModelMixin,
                            viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = ItemTypePublicResponse
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ItemTypeFilter
    ordering_fields = ("name",)

    def get_queryset(self):
        parent_path = self.request.query_params.get("parent_path")
        parent_path = unquote(parent_path) if parent_path else None
        return queries.children_of(parent_path)

    @action(detail=False, methods=["get"], url_path=r"resolve")
    def resolve(self, request):
        path = request.query_params.get("path")
        public_id = request.query_params.get("public_id")
        obj = None
        if path:
            obj = ItemType.objects.filter(path=path).only("id").first()
        elif public_id:
            obj = ItemType.objects.filter(public_id=public_id).only("id").first()
        if not obj:
            return Response({"detail": "Not found"}, status=404)
        return Response({"type_id": str(obj.pk)}, status=200)

    @action(detail=False, methods=["get"], url_path=r"by-path/(?P<category_path>.+)")
    def by_path(self, request, category_path=None):
        category_path = unquote(category_path or "")
        data = queries.category_detail_by_path(category_path)
        if not data:
            return Response({"detail": "Not found"}, status=404)
        payload = {
            "category": ItemTypePublicResponse(data["node"]).data,
            "breadcrumbs": ItemTypeNodeResponse(data["breadcrumbs"], many=True).data,
            "children": ItemTypeNodeResponse(data["children"], many=True).data,
        }
        return Response(payload, status=200)

    @action(detail=False, methods=["get"], url_path=r"schema/by-id/(?P<type_id>[0-9a-f-]{36})")
    def schema_by_id(self, request, type_id=None):
        it = get_object_or_404(ItemType, pk=type_id)
        payload = {
            "path": it.path,
            "is_leaf": not it.children.exists(),
            "schema": it.schema_json if not it.children.exists() else {},
            "ui_schema": it.ui_schema_json if not it.children.exists() else {},
        }
        return Response(ItemTypeSchemaResponse(payload).data, status=200)

    @action(detail=False, methods=["get"], url_path=r"items/by-path/(?P<category_path>.+)")
    def items_in_category(self, request, category_path=None):
        category_path = unquote(category_path or "")
        base = CatalogItem.objects.select_related("type").all()
        params = request.query_params.copy()
        params["type_path"] = category_path
        fs = CatalogItemFilter(data=params, queryset=base, request=request)
        qs = fs.qs
        qs = OrderingFilter().filter_queryset(request, qs, self)
        page = self.paginate_queryset(qs)
        ser = CatalogItemPublicResponse(page or qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)

    @action(detail=False, methods=["get"], url_path=r"schema/by-path/(?P<category_path>.+)")
    def schema_by_path(self, request, category_path=None):
        category_path = unquote(category_path or "")
        it = ItemType.objects.filter(path=category_path).first()
        if not it:
            return Response({"detail": "Not found"}, status=404)
        payload = {
            "path": it.path,
            "is_leaf": not it.children.exists(),
            "schema": it.schema_json if not it.children.exists() else {},
            "ui_schema": it.ui_schema_json if not it.children.exists() else {},
        }
        from .serializers import ItemTypeSchemaResponse
        return Response(ItemTypeSchemaResponse(payload).data, status=200)


# ===== ADMIN: categories =====
class AdminCategoryViewSet(viewsets.ViewSet):
    permission_classes = [IsAdmin]

    def create(self, request):
        ser = ItemTypeCreateRequest(data=request.data); ser.is_valid(raise_exception=True)
        it = commands.admin_create_item_type(
            name=ser.validated_data["name"],
            parent_path=ser.validated_data.get("parent_path")
        )
        return Response(ItemTypePublicResponse(it).data, status=201)

    def partial_update(self, request, pk=None):
        ser = ItemTypeUpdateRequest(data=request.body if hasattr(request, "body") else request.data, partial=True)
        ser.is_valid(raise_exception=True)
        path = request.data.get("path")
        if not path:
            return Response({"detail":"path required"}, status=400)
        it = commands.admin_update_item_type(
            path=path,
            name=ser.validated_data.get("name"),
            parent_path=ser.validated_data.get("parent_path"),
        )
        return Response(ItemTypePublicResponse(it).data, status=200)

    def destroy(self, request, pk=None):
        path = request.data.get("path")
        if not path:
            return Response({"detail":"path required"}, status=400)
        try:
            commands.admin_delete_item_type(path=path)
            return Response(status=204)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)


# ===== PUBLIC: catalog items (sugestie do prefill) =====
class PublicCatalogItemViewSet(mixins.ListModelMixin,
                               mixins.RetrieveModelMixin,
                               viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = CatalogItemPublicResponse
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = CatalogItemFilter
    ordering_fields = ("item_name",)

    def get_queryset(self):
        return CatalogItem.objects.select_related("type").all()

    @action(detail=True, methods=["get"], url_path="prefill")
    def prefill(self, request, public_id=None):
        obj = get_object_or_404(CatalogItem, public_id=public_id)
        data = listing_prefill(catalog_item=obj)
        return Response(ListingPrefillResponse(data).data, status=200)

    @action(detail=False, methods=["get"], url_path=r"by-slug/(?P<item_slug>[^/]+)")
    def by_slug(self, request, item_slug=None):
        obj = queries.get_catalog_item_by_slug(item_slug)
        if not obj:
            return Response({"detail": "Not found"}, status=404)
        return Response(CatalogItemPublicResponse(obj).data, status=200)

    @action(detail=False, methods=["get"], url_path=r"items/by-path/(?P<category_path>.+)")
    def items_in_category(self, request, category_path=None):
        category_path = unquote(category_path or "")
        base = CatalogItem.objects.select_related("type").all()
        params = request.query_params.copy()
        params["type_path"] = category_path
        fs = CatalogItemFilter(data=params, queryset=base, request=request)
        qs = fs.qs
        qs = OrderingFilter().filter_queryset(request, qs, self)
        page = self.paginate_queryset(qs)
        ser = CatalogItemPublicResponse(page or qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)

    # endpoint po public_id (przyda się dla UI usera)
    @action(detail=True, methods=["get"], url_path="attrs")
    def attrs(self, request, public_id=None):
        obj = get_object_or_404(CatalogItem, public_id=public_id)
        return Response({
            "id": str(obj.pk),
            "type_id": str(obj.type_id),
            "type_path": obj.type.path if obj.type_id else "",
            "attributes": obj.attributes or {},
        }, status=200)

    @action(detail=False, methods=["get"], url_path=r"by-id/(?P<pk>[0-9a-f-]{36})/attrs")
    def attrs_by_pk(self, request, pk=None):
        obj = get_object_or_404(CatalogItem, pk=pk)
        return Response({
            "id": str(obj.pk),
            "type_id": str(obj.type_id),
            "type_path": obj.type.path if obj.type_id else "",
            "attributes": obj.attributes or {},
        }, status=200)


# ===== ADMIN: catalog items =====
class AdminCatalogItemViewSet(viewsets.ViewSet):
    permission_classes = [IsAdmin]

    def partial_update(self, request, pk=None):
        ser = CatalogItemCreateUpdateRequest(data=request.data, partial=True); ser.is_valid(raise_exception=True)
        obj = commands.admin_update_catalog_item(public_id=pk, **ser.validated_data)
        return Response(CatalogItemPublicResponse(obj).data, status=200)

    def destroy(self, request, pk=None):
        commands.admin_delete_catalog_item(public_id=pk)
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="image")
    def upload_image(self, request, pk=None):
        ser = CatalogItemImageUploadRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        url = commands.admin_upload_catalog_item_image(public_id=pk, image=ser.validated_data["image"])
        return Response({"image_url": request.build_absolute_uri(url)}, status=200)

    @upload_image.mapping.delete
    def delete_image(self, request, pk=None):
        commands.admin_delete_catalog_item_image(public_id=pk)
        return Response(status=204)
