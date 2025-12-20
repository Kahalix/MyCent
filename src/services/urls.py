from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import (
    PublicListingPackageViewSet, AdminListingPackageViewSet, MyServicesViewSet
)

app_name = "services"

router = DefaultRouter()
router.register(r"api/public/services/listing-packages", PublicListingPackageViewSet, basename="public-listing-packages")
router.register(r"api/admin/services/listing-packages", AdminListingPackageViewSet, basename="admin-listing-packages")
router.register(r"api/users/me/services", MyServicesViewSet, basename="my-services")

urlpatterns = [ path("", include(router.urls)) ]
