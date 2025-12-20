from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import SellerPawnViewSet, UserPawnViewSet, AdminPawnViewSet

app_name = "pawns"

router = DefaultRouter()
router.register(r"api/sellers/mine/pawns", SellerPawnViewSet, basename="seller-pawns")
router.register(r"api/users/me/pawns",   UserPawnViewSet,   basename="user-pawns")
router.register(r"api/admin/pawns",      AdminPawnViewSet,  basename="admin-pawns")

urlpatterns = [ path("", include(router.urls)) ]
