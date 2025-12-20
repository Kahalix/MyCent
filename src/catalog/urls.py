from django.urls import path, include
from rest_framework.routers import DefaultRouter
from catalog.api_views import (
    PublicCategoryViewSet, AdminCategoryViewSet,
    PublicCatalogItemViewSet, AdminCatalogItemViewSet,
)

app_name = "catalog"

router = DefaultRouter()
# PUBLIC
router.register(r"api/public/catalog/categories", PublicCategoryViewSet, basename="public-categories")
router.register(r"api/public/catalog/items", PublicCatalogItemViewSet, basename="public-catalog-items")

# ADMIN
router.register(r"api/admin/catalog/categories", AdminCategoryViewSet, basename="admin-categories")
router.register(r"api/admin/catalog/items", AdminCatalogItemViewSet, basename="admin-catalog-items")

urlpatterns = [
    path("", include(router.urls)),
]
