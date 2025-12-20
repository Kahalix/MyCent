from __future__ import annotations
from typing import Optional, Tuple, Dict, Any
from djmoney.money import Money
from django.http import HttpRequest

class ProviderClient:
    """
    Interfejs klienta providera płatności.
    Implementacje powinny zapewnić metody opisane niżej.
    """

    provider_code: str = "UNKNOWN"

    def create_intent(self, *, tx_public_id: str, amount: Money) -> Tuple[str, str]:
        """
        Tworzy intent i zwraca (provider_payment_id, client_secret).
        """
        raise NotImplementedError

    def confirm(self, *, provider_payment_id: str) -> str:
        """
        Potwierdza płatność po stronie providera (jeśli flow jest 2-etapowy).
        Zwraca status: 'succeeded' | 'processing' | 'failed' | 'cancelled'.
        """
        raise NotImplementedError

    def cancel(self, *, provider_payment_id: str) -> str:
        """
        Anuluje intent po stronie providera.
        Zwraca status po anulacji ('cancelled' zwykle).
        """
        raise NotImplementedError

    def parse_webhook(self, request: HttpRequest) -> Dict[str, Any]:
        """
        Parsuje webhook i zwraca dict:
          {
            "provider_payment_id": str,
            "status": "succeeded"|"processing"|"failed"|"cancelled"
          }
        """
        raise NotImplementedError
