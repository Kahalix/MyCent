from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import SellerCustomerViewSet, AdminCustomerViewSet

app_name = "customers"

router = DefaultRouter()
router.register(r"api/sellers/mine/customers", SellerCustomerViewSet, basename="seller-customers")
router.register(r"api/admin/customers", AdminCustomerViewSet, basename="admin-customers")

urlpatterns = [ path("", include(router.urls)) ]
