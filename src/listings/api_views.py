from __future__ import annotations
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef
from django.conf import settings
from django.core.cache import cache
from rest_framework import viewsets, mixins, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from identity.permissions import IsAdmin, IsModerator, IsShopModeratorMember
from identity.models import SellerProfile
from saved.models import SavedListing
from .models import ItemSet, ItemSetImage
from shipping.models import PackageType

from .serializers import (
    ItemSetPublicResponse, ItemSetOwnerResponse, ItemSetAdminResponse,
    ItemSetCreateRequest, ItemSetUpdateRequest,
    ItemSetImageResponse, ItemSetImageUploadRequest,
    ItemSetShippingResponse, ItemSetShippingCreateRequest,
    PrefillFromCatalogResponse, SuggestPackageTypeItemResponse,
    ItemSetImageReorderRequest, ItemSetImageOrderUpdateRequest, ItemSetStatusUpdateRequest,
)
from .filters import ItemSetFilter
from .services import commands, queries
from catalog.models import CatalogItem
from chat.serializers import ChatThreadResponse
from chat.services import commands as chat_cmd

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from .services.queries import itemset_by_slug

import copy
from listings.services.cache_utils import get_cache_key, invalidate_public_itemsets_cache, get_public_itemsets_cache_version

User = get_user_model()


# ===== PUBLIC =====
class PublicItemSetViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = ItemSetPublicResponse
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ItemSetFilter
    ordering_fields = ("created_at", "price")

    # ---------- queryset ----------
    def get_queryset(self):
        qs = queries.public_itemsets_qs()
        user = getattr(self.request, "user", None)
        # Dla zalogowanych można annotate'ować (optymalizacja), ale i tak nie cache'ujemy user-specific
        if user and user.is_authenticated:
            qs = qs.annotate(is_saved=Exists(
                SavedListing.objects.filter(user=user, item_set=OuterRef("pk"))
            ))
        return qs

    # ---------- helpers ----------
    def _cache_key(self, prefix: str, request) -> str:
        return get_cache_key(prefix, request.get_full_path())

    def _cache_ttl_list(self) -> int:
        return getattr(settings, "PUBLIC_ITEMSETS_LIST_CACHE_TTL", 20)

    def _cache_ttl_detail(self) -> int:
        return getattr(settings, "PUBLIC_ITEMSETS_DETAIL_CACHE_TTL", 5)

    def _strip_user_fields_from_payload(self, data):
        """
        Usuń pola user-specific (ostrzeżenie: defensywnie)
        """
        # paginacja DRF zwykle zwraca dict z 'results'
        if isinstance(data, dict) and isinstance(data.get("results"), list):
            for row in data["results"]:
                if isinstance(row, dict):
                    row.pop("is_saved", None)
        elif isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    row.pop("is_saved", None)
        elif isinstance(data, dict):
            # single object response
            data.pop("is_saved", None)
        return data

    def _inject_is_saved(self, data, user):
        """
        Dograj per-user flagę is_saved. Wywołuje tylko jedno zapytanie do SavedListing (IN).
        Modyfikuje lokalną kopię.
        """
        if not (user and getattr(user, "is_authenticated", False)):
            # jeśli nie auth -> dla paginacji i list zwróć False
            if isinstance(data, dict) and isinstance(data.get("results"), list):
                for row in data["results"]:
                    if isinstance(row, dict):
                        row["is_saved"] = False
            elif isinstance(data, list):
                for row in data:
                    if isinstance(row, dict):
                        row["is_saved"] = False
            elif isinstance(data, dict):
                data["is_saved"] = False
            return data

        # collect ids
        if isinstance(data, dict) and isinstance(data.get("results"), list):
            rows = data["results"]
        elif isinstance(data, list):
            rows = data
        else:
            # single object
            rows = [data] if isinstance(data, dict) else []

        ids = [r.get("public_id") for r in rows if isinstance(r, dict) and r.get("public_id")]
        if not ids:
            for r in rows:
                if isinstance(r, dict):
                    r["is_saved"] = False
            return data

        saved_ids = set(
            SavedListing.objects
            .filter(user=user, item_set__public_id__in=ids)
            .values_list("item_set__public_id", flat=True)
        )

        for r in rows:
            if not isinstance(r, dict):
                continue
            r["is_saved"] = r.get("public_id") in saved_ids

        # if single object and rows was list form, map back
        if isinstance(data, dict) and not isinstance(data.get("results"), list) and rows:
            # data was single-object dict
            # nothing else to do
            pass

        return data

    # ---------- LIST ----------
    def list(self, request, *args, **kwargs):
        cache_key = self._cache_key("public_itemsets:list", request)
        cached = cache.get(cache_key)

        if cached is not None:
            # deepcopy to avoid mutating cached object
            data = copy.deepcopy(cached)
        else:
            response = super().list(request, *args, **kwargs)
            data = response.data

            safe_data = copy.deepcopy(data)
            safe_data = self._strip_user_fields_from_payload(safe_data)

            # zapisujemy tylko anonymized payload
            cache.set(cache_key, safe_data, self._cache_ttl_list())

            data = safe_data

        # dograj user-specific flagi na kopii
        data = self._inject_is_saved(data, request.user)
        return Response(data)

    # ---------- RETRIEVE ----------
    def retrieve(self, request, *args, **kwargs):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            return super().retrieve(request, *args, **kwargs)

        cache_key = self._cache_key("public_itemsets:detail", request)
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        response = super().retrieve(request, *args, **kwargs)
        data = response.data

        safe = copy.deepcopy(data)
        if isinstance(safe, dict):
            safe.pop("is_saved", None)
        cache.set(cache_key, safe, self._cache_ttl_detail())
        return Response(data)

    # ---------- BY SLUG ----------
    @action(detail=False, methods=["get"], url_path=r"by-slug/(?P<slug>[^/]+)")
    def by_slug(self, request, slug=None):
        cache_key = self._cache_key("public_itemsets:detail_slug", request)
        cached = cache.get(cache_key)
        if cached is not None:
            data = copy.deepcopy(cached)
            data = self._inject_is_saved(data, request.user)
            return Response(data, status=200)

        obj = itemset_by_slug(slug or "")
        if not obj:
            return Response({"detail": "Not found"}, status=404)

        data = ItemSetPublicResponse(obj, context={"request": request}).data

        safe = copy.deepcopy(data)
        if isinstance(safe, dict):
            safe.pop("is_saved", None)
        cache.set(cache_key, safe, self._cache_ttl_detail())

        data = self._inject_is_saved(data, request.user)
        return Response(data, status=200)

    # ---------- ITEMS IN CATEGORY ----------
    @action(detail=False, methods=["get"], url_path=r"categories/by-path/(?P<category_path>.+)/items")
    def items_in_category(self, request, category_path=None):
        cache_key = self._cache_key("public_itemsets:category", request)
        cached = cache.get(cache_key)
        if cached is not None:
            data = copy.deepcopy(cached)
            data = self._inject_is_saved(data, request.user)
            return Response(data)

        base = queries.public_itemsets_qs()
        params = request.query_params.copy()
        params["type_path"] = category_path
        fs = self.filterset_class(data=params, queryset=base, request=request)
        qs = fs.qs
        qs = OrderingFilter().filter_queryset(request, qs, self)

        page = self.paginate_queryset(qs)
        ser = ItemSetPublicResponse(page or qs, many=True, context={"request": request})
        if page is not None:
            response = self.get_paginated_response(ser.data)
            data = response.data
        else:
            data = ser.data if isinstance(ser.data, list) else ser.data

        safe_data = copy.deepcopy(data)
        safe_data = self._strip_user_fields_from_payload(safe_data)
        cache.set(cache_key, safe_data, self._cache_ttl_list())

        data = self._inject_is_saved(safe_data, request.user)
        return Response(data)

    # ---------- START CHAT ----------
    @action(detail=True, methods=["post"], url_path="start-chat", permission_classes=[permissions.IsAuthenticated])
    def start_chat(self, request, public_id=None):
        item = get_object_or_404(ItemSet, public_id=public_id, status="AVAILABLE")
        thread = chat_cmd.start_dm(initiator=request.user, other_user=None, item=item)
        return Response(ChatThreadResponse(thread).data, status=201)

# ===== SELLER (OWNER of SellerProfile) =====
class SellerItemSetViewSet(viewsets.ModelViewSet):
    """
    /api/sellers/mine/item-sets/...
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ItemSetOwnerResponse
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ItemSetFilter
    ordering_fields = ("created_at", "price")

    def get_queryset(self):
        return (
            ItemSet.objects
            .select_related("seller_profile", "type", "catalog_item")
            .prefetch_related("images", "shipping_options__package_type")
            .filter(seller_profile__memberships__user=self.request.user, seller_profile__memberships__is_active=True)
            .exclude(status="DELETED")
            .order_by("-created_at")
            .distinct()
        )

    def get_serializer_class(self):
        if self.action in ("create",): return ItemSetCreateRequest
        if self.action in ("update", "partial_update"): return ItemSetUpdateRequest
        return ItemSetOwnerResponse

    def create(self, request, *args, **kwargs):
        seller_public_id = request.data.get("seller_public_id")
        if not seller_public_id:
            return Response({"detail": "seller_public_id required"}, status=400)
        seller = get_object_or_404(SellerProfile, public_id=seller_public_id)
        ser = self.get_serializer(data=request.data);
        ser.is_valid(raise_exception=True)
        it = commands.seller_member_create_itemset(user=request.user, seller=seller, data=ser.validated_data)
        return Response(ItemSetOwnerResponse(it).data, status=201)

    def update(self, request, *args, **kwargs):
        # obiekt i tak przejdzie przez get_queryset() => wymusza membership
        it = self.get_object()
        ser = self.get_serializer(data=request.data, partial=True);
        ser.is_valid(raise_exception=True)
        it = commands.update_itemset(itemset=it, data=ser.validated_data)
        return Response(ItemSetOwnerResponse(it).data, status=200)

    def destroy(self, request, *args, **kwargs):
        it = self.get_object()
        commands.soft_delete_itemset(itemset=it)
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, public_id=None):
        it = self.get_object()
        ser = ItemSetStatusUpdateRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        it = commands.set_status(itemset=it, status=ser.validated_data["status"])
        return Response(ItemSetOwnerResponse(it).data, status=200)

    @action(detail=True, methods=["get"], url_path="images")
    def list_images(self, request, public_id=None):
        it = self.get_object()
        return Response(ItemSetImageResponse(it.images.all(), many=True).data, status=200)

    @action(detail=True, methods=["post"], url_path="images/upload")
    def upload_image(self, request, public_id=None):
        it = self.get_object()
        ser = ItemSetImageUploadRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        img = commands.add_image(itemset=it, **ser.validated_data)
        return Response(ItemSetImageResponse(img).data, status=201)

    @action(detail=True, methods=["delete"], url_path=r"images/(?P<image_public_id>[a-z0-9]{12,})")
    def delete_image(self, request, public_id=None, image_public_id=None):
        it = self.get_object()
        img = get_object_or_404(ItemSetImage, item_set=it, public_id=image_public_id)
        commands.delete_image(image=img)
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="images/reorder")
    def reorder_images(self, request, public_id=None):
        it = self.get_object()
        ser = ItemSetImageReorderRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        imgs = commands.reorder_images(itemset=it, ordered_public_ids=ser.validated_data["order"])
        return Response(ItemSetImageResponse(imgs, many=True).data, status=200)

    @action(detail=True, methods=["patch"], url_path="images/(?P<image_public_id>[a-z0-9]{12,})/order")
    def update_image_order(self, request, public_id=None, image_public_id=None):
        it = self.get_object()
        img = get_object_or_404(ItemSetImage, item_set=it, public_id=image_public_id)
        ser = ItemSetImageOrderUpdateRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        img = commands.update_image_order(image=img, image_order=ser.validated_data["image_order"])
        return Response(ItemSetImageResponse(img).data, status=200)

    @action(detail=True, methods=["get"], url_path="shipping-options")
    def list_shipping(self, request, public_id=None):
        it = self.get_object()
        return Response(
            ItemSetShippingResponse(it.shipping_options.select_related("package_type"), many=True).data,
            status=200,
        )

    @action(detail=True, methods=["post"], url_path="shipping-options/add")
    def add_shipping(self, request, public_id=None):
        it = self.get_object()
        ser = ItemSetShippingCreateRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        pkg = get_object_or_404(PackageType, public_id=ser.validated_data["package_type_public_id"])
        link = commands.add_shipping_option(
            itemset=it,
            package_type=pkg,
            price_override=ser.validated_data.get("price_override"),
            packed_length_cm=ser.validated_data.get("packed_length_cm"),
            packed_width_cm=ser.validated_data.get("packed_width_cm"),
            packed_height_cm=ser.validated_data.get("packed_height_cm"),
            packed_weight_kg=ser.validated_data.get("packed_weight_kg"),
        )
        return Response(ItemSetShippingResponse(link).data, status=201)

    @action(detail=True, methods=["delete"], url_path=r"shipping-options/(?P<pkg_public_id>[a-z0-9]{12,})")
    def remove_shipping(self, request, public_id=None, pkg_public_id=None):
        it = self.get_object()
        pkg = get_object_or_404(PackageType, public_id=pkg_public_id)
        commands.remove_shipping_option(itemset=it, package_type=pkg)
        return Response(status=204)

    # PREFILL FROM CATALOG
    @action(detail=False, methods=["get"], url_path="prefill")
    def prefill(self, request):
        catalog_public_id = request.query_params.get("catalog_public_id")
        if not catalog_public_id:
            return Response({"detail": "catalog_public_id required"}, status=400)
        cat = get_object_or_404(CatalogItem, public_id=catalog_public_id)
        data = commands.prefill_from_catalog(catalog_item=cat)
        return Response(PrefillFromCatalogResponse(data).data, status=200)

    @action(detail=True, methods=["get"], url_path="suggest-package-types")
    def suggest_package_types(self, request, public_id=None):
        it = self.get_object()
        suggestions = queries.suggest_package_types(it)
        return Response(SuggestPackageTypeItemResponse(suggestions, many=True).data, status=200)

# ===== USER (propozycje) =====
class UserItemSetViewSet(viewsets.ModelViewSet):
    """
    /api/users/me/item-sets/...
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ItemSetOwnerResponse
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ItemSetFilter
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return (
            ItemSet.objects
            .select_related("owner_user", "type", "catalog_item")
            .prefetch_related("images")
            .filter(owner_user=self.request.user, added_by="USER")
            .exclude(status="DELETED")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action in ("create",):
            return ItemSetCreateRequest
        if self.action in ("update", "partial_update"):
            return ItemSetUpdateRequest
        return ItemSetOwnerResponse

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        it = commands.user_create_itemset(owner=request.user, data=ser.validated_data)
        return Response(ItemSetOwnerResponse(it).data, status=201)

    def update(self, request, *args, **kwargs):
        it = self.get_object()
        ser = self.get_serializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        it = commands.update_itemset(itemset=it, data=ser.validated_data)
        return Response(ItemSetOwnerResponse(it).data, status=200)

    def destroy(self, request, *args, **kwargs):
        it = self.get_object()
        commands.soft_delete_itemset(itemset=it)
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, public_id=None):
        it = self.get_object()  # added_by=USER + owner = request.user
        ser = ItemSetStatusUpdateRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        it = commands.set_status(itemset=it, status=ser.validated_data["status"])
        return Response(ItemSetOwnerResponse(it).data, status=200)

    # IMAGES
    @action(detail=True, methods=["get"], url_path="images")
    def list_images(self, request, public_id=None):
        it = self.get_object()
        return Response(ItemSetImageResponse(it.images.all(), many=True).data, status=200)

    @action(detail=True, methods=["post"], url_path="images/upload")
    def upload_image(self, request, public_id=None):
        it = self.get_object()
        ser = ItemSetImageUploadRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        img = commands.add_image(itemset=it, **ser.validated_data)
        return Response(ItemSetImageResponse(img).data, status=201)

    @action(detail=True, methods=["delete"], url_path="images/(?P<image_public_id>[a-z0-9]{12,})")
    def delete_image(self, request, public_id=None, image_public_id=None):
        it = self.get_object()
        img = get_object_or_404(ItemSetImage, item_set=it, public_id=image_public_id)
        commands.delete_image(image=img)
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="images/reorder")
    def reorder_images(self, request, public_id=None):
        it = self.get_object()
        ser = ItemSetImageReorderRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        imgs = commands.reorder_images(itemset=it, ordered_public_ids=ser.validated_data["order"])
        return Response(ItemSetImageResponse(imgs, many=True).data, status=200)

    @action(detail=True, methods=["patch"], url_path="images/(?P<image_public_id>[a-z0-9]{12,})/order")
    def update_image_order(self, request, public_id=None, image_public_id=None):
        it = self.get_object()
        img = get_object_or_404(ItemSetImage, item_set=it, public_id=image_public_id)
        ser = ItemSetImageOrderUpdateRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        img = commands.update_image_order(image=img, image_order=ser.validated_data["image_order"])
        return Response(ItemSetImageResponse(img).data, status=200)


# ===== ADMIN =====
class AdminItemSetViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    serializer_class = ItemSetAdminResponse
    lookup_field = "public_id"
    queryset = (
        ItemSet.objects
        .select_related("seller_profile", "owner_user", "type", "catalog_item")
        .prefetch_related("images", "shipping_options__package_type")
        .all()
        .order_by("-created_at")
    )
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ItemSetFilter
    ordering_fields = ("created_at", "price")

    def get_serializer_class(self):
        if self.action in ("create",):
            return ItemSetCreateRequest
        if self.action in ("update", "partial_update"):
            return ItemSetUpdateRequest
        return ItemSetAdminResponse

    def create(self, request, *args, **kwargs):
        seller_public_id = request.data.get("seller_public_id")
        ser = self.get_serializer(data=request.data); ser.is_valid(raise_exception=True)
        if seller_public_id:
            seller = get_object_or_404(SellerProfile, public_id=seller_public_id)
            it = commands.seller_create_itemset(seller=seller, data=ser.validated_data)
        else:
            owner_public_id = request.data.get("owner_public_id")
            if not owner_public_id:
                return Response({"detail": "owner_public_id or seller_public_id required"}, status=400)
            user = get_object_or_404(User, public_id=owner_public_id)
            it = commands.user_create_itemset(owner=user, data=ser.validated_data)
        return Response(ItemSetAdminResponse(it).data, status=201)

    def destroy(self, request, *args, **kwargs):
            it = self.get_object()
            commands.hard_delete_itemset(itemset=it)
            return Response(status=204)

    @action(detail=True, methods=["get"], url_path="suggest-package-types")
    def suggest_package_types(self, request, public_id=None):
        it = self.get_object()
        suggestions = queries.suggest_package_types(it)
        return Response(SuggestPackageTypeItemResponse(suggestions, many=True).data, status=200)

    @action(detail=True, methods=["post"], url_path="images/reorder")
    def reorder_images(self, request, public_id=None):
        it = self.get_object()
        ser = ItemSetImageReorderRequest(data=request.data);
        ser.is_valid(raise_exception=True)
        imgs = commands.reorder_images(itemset=it, ordered_public_ids=ser.validated_data["order"])
        return Response(ItemSetImageResponse(imgs, many=True).data, status=200)

    @action(detail=True, methods=["patch"], url_path="images/(?P<image_public_id>[a-z0-9]{12,})/order")
    def update_image_order(self, request, public_id=None, image_public_id=None):
        it = self.get_object()
        img = get_object_or_404(ItemSetImage, item_set=it, public_id=image_public_id)
        ser = ItemSetImageOrderUpdateRequest(data=request.data);
        ser.is_valid(raise_exception=True)
        img = commands.update_image_order(image=img, image_order=ser.validated_data["image_order"])
        return Response(ItemSetImageResponse(img).data, status=200)

# ===== MODERATOR =====

class ModeratorItemSetViewSet(viewsets.ModelViewSet):
    permission_classes = [IsShopModeratorMember]
    serializer_class = ItemSetAdminResponse
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ItemSetFilter
    ordering_fields = ("created_at", "price")

    def get_queryset(self):
        return (
            ItemSet.objects
            .select_related("owner_user", "type", "catalog_item")
            .prefetch_related("images")
            .filter(added_by="USER")
            .exclude(status="DELETED")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action in ("create",):
            return ItemSetCreateRequest
        if self.action in ("update", "partial_update"):
            return ItemSetUpdateRequest
        return ItemSetAdminResponse

    # def create(self, request, *args, **kwargs):
    #     owner_public_id = request.data.get("owner_public_id")
    #     if not owner_public_id:
    #         return Response({"detail": "owner_public_id required"}, status=400)
    #     user = get_object_or_404(User, public_id=owner_public_id)
    #     ser = self.get_serializer(data=request.data)
    #     ser.is_valid(raise_exception=True)
    #     it = commands.user_create_itemset(owner=user, data=ser.validated_data)
    #     return Response(ItemSetAdminResponse(it).data, status=201)
    #
    # def update(self, request, *args, **kwargs):
    #     it = get_object_or_404(ItemSet, public_id=kwargs.get("public_id"), added_by="USER")
    #     ser = self.get_serializer(data=request.data, partial=True)
    #     ser.is_valid(raise_exception=True)
    #     it = commands.update_itemset(itemset=it, data=ser.validated_data)
    #     return Response(ItemSetAdminResponse(it).data, status=200)
    #
    # def destroy(self, request, *args, **kwargs):
    #     return Response({"detail": "Forbidden"}, status=403)

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, public_id=None):
        it = get_object_or_404(ItemSet, public_id=public_id, added_by="USER")
        ser = ItemSetStatusUpdateRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        new_status = ser.validated_data["status"]
        it = commands.moderator_set_status(itemset=it, status=new_status)
        return Response(ItemSetAdminResponse(it).data, status=200)

    @action(detail=True, methods=["get"], url_path="images")
    def list_images(self, request, public_id=None):
        it = self.get_object()
        return Response(ItemSetImageResponse(it.images.all(), many=True).data, status=200)

    # @action(detail=True, methods=["delete"], url_path=r"images/(?P<image_public_id>[a-z0-9]{12,})")
    # def delete_image(self, request, public_id=None, image_public_id=None):
    #     it = self.get_object()
    #     img = get_object_or_404(ItemSetImage, item_set=it, public_id=image_public_id)
    #     commands.delete_image(image=img)
    #     return Response(status=204)
    #
    # @action(detail=True, methods=["post"], url_path="images/reorder")
    # def reorder_images(self, request, public_id=None):
    #     it = self.get_object()
    #     ser = ItemSetImageReorderRequest(data=request.data)
    #     ser.is_valid(raise_exception=True)
    #     imgs = commands.reorder_images(itemset=it, ordered_public_ids=ser.validated_data["order"])
    #     return Response(ItemSetImageResponse(imgs, many=True).data, status=200)
    #
    # @action(detail=True, methods=["patch"], url_path="images/(?P<image_public_id>[a-z0-9]{12,})/order")
    # def update_image_order(self, request, public_id=None, image_public_id=None):
    #     it = self.get_object()
    #     img = get_object_or_404(ItemSetImage, item_set=it, public_id=image_public_id)
    #     ser = ItemSetImageOrderUpdateRequest(data=request.data)
    #     ser.is_valid(raise_exception=True)
    #     img = commands.update_image_order(image=img, image_order=ser.validated_data["image_order"])
    #     return Response(ItemSetImageResponse(img).data, status=200)