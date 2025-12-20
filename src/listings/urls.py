# src/listings/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api_views import (
    PublicItemSetViewSet, SellerItemSetViewSet, UserItemSetViewSet, AdminItemSetViewSet, ModeratorItemSetViewSet
)

app_name = "listings"

router = DefaultRouter()
router.register(r"api/public/item-sets", PublicItemSetViewSet, basename="public-itemsets")
router.register(r"api/sellers/mine/item-sets", SellerItemSetViewSet, basename="seller-itemsets")
router.register(r"api/users/me/item-sets", UserItemSetViewSet, basename="user-itemsets")
router.register(r"api/admin/item-sets", AdminItemSetViewSet, basename="admin-itemsets")
router.register(r"api/moderation/item-sets", ModeratorItemSetViewSet, basename="moderation-item-sets")

urlpatterns = [ path("", include(router.urls)) ]
