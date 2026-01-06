from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


@database_sync_to_async
def _get_user_for_token(raw: str):
    jwt_auth = JWTAuthentication()
    try:
        validated = jwt_auth.get_validated_token(raw)
        user = jwt_auth.get_user(validated)
        if not getattr(user, "is_active", False):
            return None
        return user
    except (InvalidToken, TokenError):
        return None
    except Exception:
        return None


def _extract_token_from_scope(scope) -> str | None:
    try:
        query = parse_qs((scope.get("query_string") or b"").decode("utf-8"))
        token = (query.get("token") or [None])[0]
        if token:
            return token
    except Exception:
        pass

    try:
        headers = dict(scope.get("headers") or [])
        raw = headers.get(b"authorization")
        if raw:
            value = raw.decode("latin1").strip()
            if value.lower().startswith("bearer "):
                token = value.split(" ", 1)[1].strip()
                return token or None
    except Exception:
        pass

    return None


class JWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope = dict(scope)

        token = _extract_token_from_scope(scope)
        if token:
            user = await _get_user_for_token(token)
            if user is not None:
                scope["user"] = user

        return await self.app(scope, receive, send)
