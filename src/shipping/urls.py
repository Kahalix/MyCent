from __future__ import annotations
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import (
    PublicPackageTypeViewSet, AdminPackageTypeViewSet,
    MyShippingAddressViewSet, AdminShippingAddressViewSet
)

app_name = "shipping"

router = DefaultRouter()
# Package types
router.register(r"api/public/shipping/package-types", PublicPackageTypeViewSet, basename="public-package-types")
router.register(r"api/admin/shipping/package-types", AdminPackageTypeViewSet, basename="admin-package-types")

# Self address (bez lookupu – pojedynczy zasób)
my_addr = MyShippingAddressViewSet.as_view({
    "get": "retrieve",
    "post": "create",
    "patch": "partial_update",
    "delete": "destroy",
})
# Admin addresses
router.register(r"api/admin/shipping-addresses", AdminShippingAddressViewSet, basename="admin-shipping-addresses")

urlpatterns = [
    path("", include(router.urls)),
    path("api/users/me/shipping-address", my_addr, name="users-me-shipping-address"),
]
