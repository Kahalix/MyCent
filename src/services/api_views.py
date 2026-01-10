from __future__ import annotations
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from identity.permissions import IsAdmin
from catalog.models import ItemType
from services.models import ListingPackage, UserListingPackage
from .serializers import (
    ListingPackagePublicResponse, ListingPackageAdminResponse, ListingPackageCreateUpdateRequest,
    UserListingPackageResponse, PurchasePackageRequest, SlotSummaryRow
)
from .filters import ListingPackageFilter
from .services import commands
from .services.exceptions import PurchaseError, BadRequest

User = get_user_model()

# ===== PUBLIC: packages =====

class PublicListingPackageViewSet(mixins.ListModelMixin,
                                  mixins.RetrieveModelMixin,
                                  viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = ListingPackage.objects.select_related("item_type").all().order_by("price","points")
    lookup_field = "public_id"
    serializer_class = ListingPackagePublicResponse
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ListingPackageFilter
    ordering_fields = ("price", "points")

# ===== ADMIN: packages =====

class AdminListingPackageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    queryset = ListingPackage.objects.select_related("item_type").all().order_by("-created_at")
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ListingPackageFilter
    ordering_fields = ("price", "points", "created_at")

    def get_serializer_class(self):
        if self.action in ("create","update","partial_update"):
            return ListingPackageCreateUpdateRequest
        return ListingPackageAdminResponse

# ===== USER SELF: purchases & reports =====

class MyServicesViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    # @action(methods=["post"], detail=False, url_path="purchase-package")
    # def purchase_package(self, request):
    #     ser = PurchasePackageRequest(data=request.data)
    #     ser.is_valid(raise_exception=True)
    #     pkg = get_object_or_404(ListingPackage, public_id=ser.validated_data["listing_package_public_id"])
    #     pay_with = ser.validated_data.get("pay_with") or "auto"
    #     pay_with = None if pay_with == "auto" else pay_with
    #
    #     up = commands.purchase_package(user=request.user, package=pkg, pay_with=pay_with)
    #     return Response(UserListingPackageResponse(up).data, status=201)

    @action(methods=["get"], detail=False, url_path="slot-summary")
    def slot_summary(self, request):
        rows = commands.slot_summary_for_user(request.user)
        return Response(SlotSummaryRow(rows, many=True).data, status=200)

    @action(methods=["get"], detail=False, url_path="packages")
    def my_packages(self, request):
        ups = (UserListingPackage.objects
               .select_related("listing_package","listing_package__item_type")
               .filter(user=request.user)
               .order_by("-updated_at"))
        return Response(UserListingPackageResponse(ups, many=True).data, status=200)
