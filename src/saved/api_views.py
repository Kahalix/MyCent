from __future__ import annotations
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from saved.serializers import (
    SavedListingCreateRequest, SavedListingResponse,
    SavedSearchCreateRequest, SavedSearchUpdateRequest, SavedSearchResponse, SavedSearchItemResponse
)
from saved.filters import SavedListingFilter, SavedSearchFilter
from saved.services import commands
from saved.services import queries
from saved.services.exceptions import InvalidQuery, NotFound
from listings.serializers import ItemSetPublicResponse
from saved.services.repositories import get_saved_search_by_public_id

User = get_user_model()

class DefaultPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200

# ===== USER: Saved Listings =====
class MySavedListingsViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = DefaultPagination
    lookup_url_kwarg = "item_public_id"

    def list(self, request):
        qs = queries.list_saved_listings(user=request.user)
        page = self.paginate_queryset(qs)
        if page is not None:
            ser = SavedListingResponse(page, many=True, context={"request": request})
            return self.get_paginated_response(ser.data)
        return Response(SavedListingResponse(qs, many=True, context={"request": request}).data, status=200)

    def create(self, request):
        ser = SavedListingCreateRequest(data=request.data); ser.is_valid(raise_exception=True)
        obj = commands.add_saved_listing(user=request.user, item_public_id=ser.validated_data["item_public_id"])
        return Response(SavedListingResponse(obj, context={"request": request}).data, status=201)

    def destroy(self, request, item_public_id=None):
        commands.remove_saved_listing(user=request.user, item_public_id=item_public_id)
        return Response(status=204)


# ===== USER: Saved Searches =====
class MySavedSearchesViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = DefaultPagination
    lookup_field = "public_id"
    lookup_url_kwarg = "public_id"

    def list(self, request):
        qs = queries.list_saved_searches(user=request.user)
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(SavedSearchResponse(page, many=True).data)
        return Response(SavedSearchResponse(qs, many=True).data, status=200)

    def retrieve(self, request, public_id=None):
        try:
            ss = queries.get_saved_search_meta(user=request.user, public_id=public_id)
            return Response(SavedSearchResponse(ss).data, status=200)
        except NotFound as e:
            return Response({"detail": str(e)}, status=404)

    def create(self, request):
        ser = SavedSearchCreateRequest(data=request.data); ser.is_valid(raise_exception=True)
        try:
            ss = commands.create_saved_search_cmd(user=request.user, **ser.validated_data)
            return Response(SavedSearchResponse(ss).data, status=201)
        except InvalidQuery as e:
            return Response({"detail": str(e)}, status=400)

    def partial_update(self, request, public_id=None):
        ser = SavedSearchUpdateRequest(data=request.data, partial=True);
        ser.is_valid(raise_exception=True)
        try:
            ss = commands.update_saved_search_cmd(user=request.user, public_id=public_id, **ser.validated_data)
            return Response(SavedSearchResponse(ss).data, status=200)
        except NotFound as e:
            return Response({"detail": str(e)}, status=404)

    def destroy(self, request, public_id=None):
        commands.delete_saved_search_cmd(user=request.user, public_id=public_id)
        return Response(status=204)

    @action(detail=True, methods=["get"], url_path="items")
    def items(self, request, public_id=None):
        """
        Zwraca snapshot NIEPRZECZYTANYCH wyników (SavedSearchItem).
        """
        try:
            qs = queries.list_saved_search_items(user=request.user, public_id=public_id)
            page = self.paginate_queryset(qs)
            ser = SavedSearchItemResponse(page or qs, many=True, context={"request": request})
            return self.get_paginated_response(ser.data) if page is not None else Response(ser.data, status=200)
        except NotFound as e:
            return Response({"detail": str(e)}, status=404)

    @action(detail=True, methods=["post"], url_path="refresh")
    def refresh(self, request, public_id=None):
        """
        Dociąga do snapshotu tylko NOWE ogłoszenia (created_at > since_at/created_at).
        """
        limit = request.data.get("limit")
        try:
            result = commands.refresh_saved_search_items(user=request.user, public_id=public_id, limit=limit or 200)
            return Response(result, status=200)
        except NotFound as e:
            return Response({"detail": str(e)}, status=404)

    @action(detail=True, methods=["post"], url_path="mark-seen")
    def mark_seen(self, request, public_id=None):
        """
        Oznacz wyniki jako obejrzane: czyści snapshot i ustawia since_at=now.
        """
        try:
            result = commands.mark_saved_search_seen_cmd(user=request.user, public_id=public_id)
            return Response(result, status=200)
        except NotFound as e:
            return Response({"detail": str(e)}, status=404)

    @action(detail=True, methods=["get"], url_path="results")
    def results(self, request, public_id=None):
        """
        Podgląd NOWYCH wyników (bez modyfikacji stanu).
        """
        ss = get_saved_search_by_public_id(request.user, public_id)
        if not ss:
            return Response({"detail": "Not found"}, status=404)
        from saved.services.refresh import _since
        from saved.services.queries import run_saved_query
        base = run_saved_query(ss.query_string)
        qs = base.filter(created_at__gt=_since(ss)).select_related("seller_profile", "type").order_by("-created_at")
        page = self.paginate_queryset(qs)
        ser = ItemSetPublicResponse(page or qs, many=True, context={"request": request})
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data, status=200)
