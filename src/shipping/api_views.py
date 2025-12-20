from __future__ import annotations
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from identity.permissions import IsAdmin
from .models import PackageType, ShippingAddress
from .serializers import (
    PackageTypePublicResponse, PackageTypeAdminResponse, PackageTypeCreateUpdateRequest,
    ShippingAddressResponse, ShippingAddressUpsertRequest
)
from .filters import PackageTypeFilter, ShippingAddressFilter
from .services import commands, queries
from .services.exceptions import InvalidPackageLimits, AddressAlreadyExists

User = get_user_model()


# ===== PUBLIC: package types =====

class PublicPackageTypeViewSet(mixins.ListModelMixin,
                               mixins.RetrieveModelMixin,
                               viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = PackageType.objects.all().order_by("provider","points")
    lookup_field = "public_id"
    serializer_class = PackageTypePublicResponse
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = PackageTypeFilter
    ordering_fields = ("price", "points", "provider")

    @action(detail=False, methods=["get"], url_path="suggest")
    def suggest(self, request):
        """
        /api/public/shipping/package-types/suggest?
          length_cm=&width_cm=&height_cm=&weight_kg=
        """
        def as_num(name):
            v = request.query_params.get(name)
            if v is None or v == "":
                return None
            try:
                return float(v) if name == "weight_kg" else int(v)
            except Exception:
                return None

        length = as_num("length_cm")
        width  = as_num("width_cm")
        height = as_num("height_cm")
        weight = as_num("weight_kg")

        suggestions = queries.suggest_packages_for_dims(
            length_cm=length, width_cm=width, height_cm=height, weight_kg=weight
        )
        # ten endpoint zwraca taką samą strukturę package_type jak public serializer
        payload = []
        for row in suggestions:
            payload.append({
                "package_type": PackageTypePublicResponse(row["package_type"]).data,
                "fits": row["fits"],
                "price": (
                    {"amount": str(row["price"].amount), "currency": str(row["price"].currency)}
                    if row["price"] is not None else None
                )
            })
        return Response(payload, status=200)


# ===== ADMIN: package types =====

class AdminPackageTypeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    queryset = PackageType.objects.all().order_by("provider","points")
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = PackageTypeFilter
    ordering_fields = ("price", "points", "provider")

    def get_serializer_class(self):
        if self.action in ("create","update","partial_update"):
            return PackageTypeCreateUpdateRequest
        return PackageTypeAdminResponse

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data); ser.is_valid(raise_exception=True)
        try:
            pkg = commands.create_package_type(data=ser.validated_data)
            return Response(PackageTypeAdminResponse(pkg).data, status=201)
        except InvalidPackageLimits as e:
            return Response({"detail": str(e)}, status=400)

    def update(self, request, *args, **kwargs):
        pkg = get_object_or_404(PackageType, public_id=kwargs.get("public_id"))
        ser = self.get_serializer(data=request.data, partial=True); ser.is_valid(raise_exception=True)
        try:
            pkg = commands.update_package_type(pkg=pkg, data=ser.validated_data)
            return Response(PackageTypeAdminResponse(pkg).data, status=200)
        except InvalidPackageLimits as e:
            return Response({"detail": str(e)}, status=400)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)


# ===== USER SELF: shipping address =====

class MyShippingAddressViewSet(viewsets.ViewSet):
    """
    /api/users/me/shipping-address  [GET, POST, PATCH, DELETE]
    POST = create jeśli brak; jeśli istnieje, zwraca 400 (żeby nie „duplikować” przez przypadek).
    PATCH = aktualizacja istniejącego; jeśli nie istnieje – stworzy („upsert”).
    DELETE = usuń.
    """
    permission_classes = [permissions.IsAuthenticated]

    def retrieve(self, request):
        addr = ShippingAddress.objects.filter(user=request.user).first()
        if not addr:
            return Response({"detail": "Not found"}, status=404)
        return Response(ShippingAddressResponse(addr).data, status=200)

    def create(self, request):
        ser = ShippingAddressUpsertRequest(data=request.data); ser.is_valid(raise_exception=True)
        try:
            addr = commands.create_address_for_user(user=request.user, data=ser.validated_data)
            return Response(ShippingAddressResponse(addr).data, status=201)
        except AddressAlreadyExists as e:
            return Response({"detail": str(e)}, status=400)

    def partial_update(self, request):
        ser = ShippingAddressUpsertRequest(data=request.data, partial=True); ser.is_valid(raise_exception=True)
        addr = commands.upsert_address_for_user(user=request.user, data=ser.validated_data)
        return Response(ShippingAddressResponse(addr).data, status=200)

    def destroy(self, request):
        addr = ShippingAddress.objects.filter(user=request.user).first()
        if not addr:
            return Response(status=204)
        commands.admin_delete_address(address=addr)
        return Response(status=204)


# ===== ADMIN: shipping addresses =====

class AdminShippingAddressViewSet(mixins.ListModelMixin,
                                  mixins.RetrieveModelMixin,
                                  mixins.UpdateModelMixin,
                                  mixins.DestroyModelMixin,
                                  viewsets.GenericViewSet):
    permission_classes = [IsAdmin]
    queryset = ShippingAddress.objects.select_related("user").all().order_by("-created_at")
    lookup_field = "public_id"
    serializer_class = ShippingAddressResponse
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ShippingAddressFilter
    ordering_fields = ("created_at","city","country")

    def update(self, request, *args, **kwargs):
        addr = get_object_or_404(ShippingAddress, public_id=kwargs.get("public_id"))
        ser = ShippingAddressUpsertRequest(data=request.data, partial=True); ser.is_valid(raise_exception=True)
        addr = commands.admin_update_address(address=addr, data=ser.validated_data)
        return Response(ShippingAddressResponse(addr).data, status=200)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)
