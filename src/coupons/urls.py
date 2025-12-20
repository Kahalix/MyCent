from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api_views import UserCouponViewSet, AdminCouponViewSet

app_name = "coupons"

router = DefaultRouter()
router.register(r"api/users/me/coupons", UserCouponViewSet, basename="user-coupons")
router.register(r"api/admin/coupons",     AdminCouponViewSet, basename="admin-coupons")

urlpatterns = [path("", include(router.urls))]
