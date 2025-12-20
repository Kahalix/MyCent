from __future__ import annotations
import secrets
from typing import Tuple, Dict, Any
from djmoney.money import Money
from django.http import HttpRequest, JsonResponse
from .base import ProviderClient

class DummyClient(ProviderClient):
    """
    Minimalny „provider” do lokalnej symulacji – bez zewnętrznego API.
    """
    provider_code: str = "SIM"

    def create_intent(self, *, tx_public_id: str, amount: Money) -> Tuple[str, str]:
        provider_payment_id = f"sim_{secrets.token_urlsafe(8)}"
        client_secret = secrets.token_urlsafe(16)
        return provider_payment_id, client_secret

    def confirm(self, *, provider_payment_id: str) -> str:
        # w dummy nie dzwonimy do zewnętrza – status zwróci webhook/endpoint testowy
        # ale dla zgodności oddamy 'processing'
        return "processing"

    def cancel(self, *, provider_payment_id: str) -> str:
        return "cancelled"

    def parse_webhook(self, request: HttpRequest) -> Dict[str, Any]:
        # oczekujemy JSONa: {"event": "...", "provider_payment_id": "..."}
        # event: payment_intent.succeeded / payment_intent.failed / payment_intent.cancelled / payment_intent.processing
        body = request.body.decode("utf-8") if request.body else "{}"
        import json
        try:
            data = json.loads(body)
        except Exception:
            data = {}
        event = (data.get("event") or "").strip()
        pid = data.get("provider_payment_id")
        map_status = {
            "payment_intent.succeeded": "succeeded",
            "payment_intent.failed": "failed",
            "payment_intent.cancelled": "cancelled",
            "payment_intent.processing": "processing",
        }
        return {"provider_payment_id": pid, "status": map_status.get(event, "processing")}
