from django.urls import re_path
from chat.consumers import ThreadConsumer, InboxConsumer

websocket_urlpatterns = [
    re_path(r"^ws/chat/threads/(?P<public_id>[^/]+)/$", ThreadConsumer.as_asgi()),
    re_path(r"^ws/chat/inbox/$", InboxConsumer.as_asgi()),
]
