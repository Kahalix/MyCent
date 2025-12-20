from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import UserCartViewSet

app_name = "carts"
router = DefaultRouter()
router.register(r"api/users/me/cart", UserCartViewSet, basename="user-carts")
urlpatterns = [path("", include(router.urls))]