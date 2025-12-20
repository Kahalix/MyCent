from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import UserChatThreadViewSet

app_name = "chat"

router = DefaultRouter()
router.register(r"api/users/me/chats/threads", UserChatThreadViewSet, basename="user-chat-threads")

urlpatterns = [path("", include(router.urls))]
