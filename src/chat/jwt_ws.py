# src/chat/jwt_ws.py
from urllib.parse import parse_qs
from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


@database_sync_to_async
def _get_user_for_token(raw: str):
    jwt_auth = JWTAuthentication()
    try:
        validated = jwt_auth.get_validated_token(raw)
        user = jwt_auth.get_user(validated)
        return user
    except InvalidToken:
        return AnonymousUser()


class JWTAuthMiddleware:
    """
    WS: ws://.../ws/.../?token=<ACCESS_JWT>
    Jeśli brak/niepoprawny token, spadamy do cookie/session auth.
    Zgodne z ASGI: __call__(scope, receive, send)
    """
    def __init__(self, app):
        # owijamy "inner" standardowym AuthMiddlewareStack, żeby działały też sesje
        self.app = AuthMiddlewareStack(app)

    async def __call__(self, scope, receive, send):
        # kopiujemy scope, żeby nie modyfikować obiektu współdzielonego
        scope = dict(scope)
        try:
            query = parse_qs((scope.get("query_string") or b"").decode())
            token = (query.get("token") or [None])[0]
            if token:
                user = await _get_user_for_token(token)
                scope["user"] = user
        except Exception:
            # w razie czegokolwiek – po prostu kontynuuj bez JWT
            pass

        return await self.app(scope, receive, send)
