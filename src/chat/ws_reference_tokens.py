from __future__ import annotations

import json
import secrets
from typing import Optional

from django.conf import settings
from django_redis import get_redis_connection


def issue_ws_reference_token(*, user_id: int, ua_hash: str, ip: str | None) -> tuple[str, int]:
    ttl = int(getattr(settings, "WS_REFERENCE_TOKEN_TTL", 30))
    enforce_ip = bool(getattr(settings, "WS_REFERENCE_TOKEN_ENFORCE_IP", True))
    enforce_ua = bool(getattr(settings, "WS_REFERENCE_TOKEN_ENFORCE_UA", True))

    token = secrets.token_urlsafe(32)

    payload: dict[str, object] = {"uid": int(user_id)}
    if enforce_ua:
        payload["ua"] = ua_hash
    if enforce_ip and ip:
        payload["ip"] = ip

    conn = get_redis_connection("default")
    conn.setex(
        f"wsrt:{token}",
        ttl,
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
    )
    conn.setex(f"wsrt:{token}:u", ttl, b"0")
    return token, ttl


def consume_ws_reference_token(*, raw: str, ua_hash: str, ip: str | None) -> Optional[int]:
    if not raw:
        return None

    conn = get_redis_connection("default")
    val = conn.get(f"wsrt:{raw}")
    if not val:
        return None

    try:
        payload = json.loads(val.decode("utf-8"))
    except Exception:
        return None

    uid = payload.get("uid")
    if not isinstance(uid, int):
        return None

    enforce_ip = bool(getattr(settings, "WS_REFERENCE_TOKEN_ENFORCE_IP", True))
    enforce_ua = bool(getattr(settings, "WS_REFERENCE_TOKEN_ENFORCE_UA", True))

    if enforce_ua:
        pua = payload.get("ua")
        if not isinstance(pua, str) or pua != ua_hash:
            return None

    if enforce_ip:
        pip = payload.get("ip")
        if isinstance(pip, str) and pip:
            if not ip or pip != ip:
                return None

    max_uses = int(getattr(settings, "WS_REFERENCE_TOKEN_MAX_USES", 25))
    uses = int(conn.incr(f"wsrt:{raw}:u"))
    if uses > max_uses:
        conn.delete(f"wsrt:{raw}")
        conn.delete(f"wsrt:{raw}:u")
        return None

    single_use = bool(getattr(settings, "WS_REFERENCE_TOKEN_SINGLE_USE", False))
    if single_use:
        conn.delete(f"wsrt:{raw}")
        conn.delete(f"wsrt:{raw}:u")

    return uid
