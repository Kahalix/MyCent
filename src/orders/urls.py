from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import BuyerOrderViewSet, SellerOrderViewSet, AdminOrderViewSet

app_name = "orders"

router = DefaultRouter()
router.register(r"api/users/me/orders", BuyerOrderViewSet, basename="buyer-orders")
router.register(r"api/sellers/mine/orders", SellerOrderViewSet, basename="seller-orders")
router.register(r"api/admin/orders", AdminOrderViewSet, basename="admin-orders")

urlpatterns = [ path("", include(router.urls)) ]
