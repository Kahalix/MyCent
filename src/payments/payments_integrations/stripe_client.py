from __future__ import annotations
from typing import Tuple, Dict, Any
from decimal import Decimal
import json
import stripe
from djmoney.money import Money
from django.conf import settings
from django.http import HttpRequest
from .base import ProviderClient

ZERO_DECIMAL = {"BIF","CLP","DJF","GNF","JPY","KMF","KRW","MGA","PYG","RWF","UGX","VND","VUV","XAF","XOF","XPF"}

def to_minor_units(amount: Money) -> int:
    cur = str(amount.currency).upper()
    if cur in ZERO_DECIMAL:
        return int(Decimal(amount.amount).quantize(Decimal("1")))
    return int((Decimal(amount.amount) * Decimal("100")).quantize(Decimal("1")))

class StripeClient(ProviderClient):
    provider_code: str = "STRIPE"

    def __init__(self) -> None:
        api_key = getattr(settings, "STRIPE_SECRET_KEY", "")
        if api_key:
            stripe.api_key = api_key

    def _require_api_key(self) -> None:
        if not getattr(settings, "STRIPE_SECRET_KEY", ""):
            raise RuntimeError("STRIPE_SECRET_KEY is empty")

    def create_intent(self, *, tx_public_id: str, amount: Money) -> Tuple[str, str]:
        self._require_api_key()
        minor = to_minor_units(amount)
        intent = stripe.PaymentIntent.create(
            amount=minor,
            currency=str(amount.currency).lower(),
            automatic_payment_methods={"enabled": True},
            metadata={"tx_public_id": tx_public_id},
        )
        return intent.id, intent.client_secret

    def confirm(self, *, provider_payment_id: str) -> str:
        return "processing"

    def cancel(self, *, provider_payment_id: str) -> str:
        self._require_api_key()
        pi = stripe.PaymentIntent.cancel(provider_payment_id)
        return pi.status

    def parse_webhook(self, request: HttpRequest) -> Dict[str, Any]:
        raw = request.body or b""
        payload = raw.decode("utf-8")
        sig = (getattr(request, "headers", {}) or {}).get("Stripe-Signature") or request.META.get("HTTP_STRIPE_SIGNATURE", "")
        secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "") or ""

        def _construct_from_payload():
            try:
                data = request.data if isinstance(request.data, dict) else json.loads(payload or "{}")
            except Exception:
                data = {}
            return stripe.Event.construct_from(data, stripe.api_key)

        if secret:
            try:
                evt = stripe.Webhook.construct_event(payload, sig, secret)
            except Exception:
                if getattr(settings, "DEBUG", False):
                    evt = _construct_from_payload()
                else:
                    raise
        else:
            evt = _construct_from_payload()

        typ = evt["type"]
        obj = evt["data"]["object"]
        provider_payment_id = obj.get("id") if isinstance(obj, dict) else getattr(obj, "id", None)

        status_map = {
            "payment_intent.succeeded": "succeeded",
            "payment_intent.processing": "processing",
            "payment_intent.payment_failed": "failed",
            "payment_intent.canceled": "cancelled",
            "payment_intent.requires_action": "requires_action",
        }
        status = status_map.get(typ, "processing")
        return {"provider_payment_id": provider_payment_id, "status": status}
