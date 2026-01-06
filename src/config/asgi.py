import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from django.conf import settings
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator, OriginValidator

from chat.jwt_ws import JWTAuthMiddleware
from chat.routing import websocket_urlpatterns


ws_app = AuthMiddlewareStack(
    JWTAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    )
)

allowed = getattr(settings, "WS_ALLOWED_ORIGINS", None)
if allowed:
    ws_app = OriginValidator(ws_app, allowed)
else:
    ws_app = AllowedHostsOriginValidator(ws_app)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": ws_app,
    }
)
