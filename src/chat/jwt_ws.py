from __future__ import annotations

import hashlib

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from chat.ws_reference_tokens import consume_ws_reference_token

User = get_user_model()


@database_sync_to_async
def _get_user_by_id(user_id):
    try:
        user = User.objects.filter(id=user_id).first()
        if not user or not getattr(user, "is_active", False):
            return None
        return user
    except Exception:
        return None


def _headers_dict(scope) -> dict[bytes, bytes]:
    try:
        return dict(scope.get("headers") or [])
    except Exception:
        return {}


def _get_header(scope, name: bytes) -> str | None:
    headers = _headers_dict(scope)
    raw = headers.get(name)
    if not raw:
        return None
    try:
        return raw.decode("latin1").strip()
    except Exception:
        return None


def _ua_hash(ua: str | None) -> str:
    return hashlib.sha256((ua or "").encode("utf-8")).hexdigest()


def _extract_subprotocol_rt(scope) -> str | None:
    subs = scope.get("subprotocols") or []
    for it in subs:
        if isinstance(it, str) and it.startswith("rt."):
            token = it[3:].strip()
            return token or None

    value = _get_header(scope, b"sec-websocket-protocol")
    if not value:
        return None
    items = [x.strip() for x in value.split(",") if x.strip()]
    for it in items:
        if it.startswith("rt."):
            token = it[3:].strip()
            return token or None
    return None


def _client_ip_from_scope(scope) -> str | None:
    xff = _get_header(scope, b"x-forwarded-for")
    if xff:
        ip = xff.split(",", 1)[0].strip()
        if ip:
            return ip

    xri = _get_header(scope, b"x-real-ip")
    if xri:
        ip = xri.strip()
        if ip:
            return ip

    client = scope.get("client")
    if client and isinstance(client, (list, tuple)) and len(client) >= 1:
        ip = client[0]
        if isinstance(ip, str) and ip.strip():
            return ip.strip()

    return None


class JWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope = dict(scope)

        rt = _extract_subprotocol_rt(scope)
        ua = _get_header(scope, b"user-agent")
        ua_h = _ua_hash(ua)
        ip = _client_ip_from_scope(scope)

        user = AnonymousUser()

        if not rt:
            scope["ws_auth"] = "missing_rt"
            scope["user"] = user
            return await self.app(scope, receive, send)

        try:
            user_id = await sync_to_async(consume_ws_reference_token, thread_sensitive=True)(
                raw=rt,
                ua_hash=ua_h,
                ip=ip,
            )
        except Exception:
            user_id = None

        if not user_id:
            scope["ws_auth"] = "rt_rejected"
            scope["user"] = user
            return await self.app(scope, receive, send)

        u = await _get_user_by_id(user_id)
        if u is None:
            scope["ws_auth"] = "user_missing_or_inactive"
            scope["user"] = user
            return await self.app(scope, receive, send)

        scope["ws_auth"] = "ok"
        scope["user"] = u
        return await self.app(scope, receive, send)
