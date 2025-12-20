from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import UserTransactionViewSet, SellerTransactionViewSet, AdminTransactionViewSet

app_name = "transactions"

router = DefaultRouter()
router.register(r"api/users/me/transactions", UserTransactionViewSet, basename="user-transactions")
router.register(r"api/sellers/mine/transactions", SellerTransactionViewSet, basename="seller-transactions")
router.register(r"api/admin/transactions", AdminTransactionViewSet, basename="admin-transactions")

urlpatterns = [ path("", include(router.urls)) ]
