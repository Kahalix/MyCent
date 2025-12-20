from __future__ import annotations
import json, hmac, hashlib, logging
from typing import Any, Dict
import requests
from django.conf import settings
from chat.models import ChatMessage

logger = logging.getLogger(__name__)

def _sign(payload: Dict[str, Any]) -> str:
    secret = (getattr(settings, "CHAT_NEW_MESSAGE_WEBHOOK_SECRET", "") or "").encode("utf-8")
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hmac.new(secret, body, hashlib.sha256).hexdigest()

def notify_new_message(msg: ChatMessage) -> None:
    url = getattr(settings, "CHAT_NEW_MESSAGE_WEBHOOK_URL", None)
    if not url:
        return
    th = msg.thread
    item = th.item_set
    participants = [
        {"public_id": p.user.public_id, "email": p.user.email}
        for p in th.participants.select_related("user").all()
    ]
    payload = {
        "event": "chat.message.created",
        "thread_public_id": th.public_id,
        "item_public_id": item.public_id if item else None,
        "seller_slug": (item.seller_profile.slug if (item and item.seller_profile_id) else None),
        "message": {
            "public_id": msg.public_id,
            "content": msg.content,
            "sent_at": msg.sent_at.isoformat(),
            "sender_public_id": msg.sender.public_id,
            "sender_email": msg.sender.email,
        },
        "participants": participants,
    }
    headers = {"Content-Type": "application/json", "X-Chat-Signature": _sign(payload)}
    try:
        requests.post(url, json=payload, headers=headers, timeout=2.0)
    except Exception:
        logger.warning("chat webhook delivery failed", exc_info=True)
