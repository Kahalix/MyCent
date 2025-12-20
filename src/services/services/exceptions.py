from __future__ import annotations
from typing import Any
from rest_framework.exceptions import APIException

class DomainError(APIException):
    status_code = 400
    default_detail = "Bad request"
    default_code = "bad_request"

    def __init__(self, detail: Any = None, code: str | None = None, *, errors: Any = None):
        msg = detail or self.default_detail
        code = code or self.default_code
        payload = {"detail": msg, "code": code}
        if errors is not None:
            payload["errors"] = errors
        super().__init__(detail=payload, code=code)


class BadRequest(DomainError):
    status_code = 400
    default_detail = "Bad request"
    default_code = "bad_request"


class Forbidden(DomainError):
    status_code = 403
    default_detail = "Forbidden"
    default_code = "forbidden"


class NotFound(DomainError):
    status_code = 404
    default_detail = "Not found"
    default_code = "not_found"


class Conflict(DomainError):
    status_code = 409
    default_detail = "Conflict"
    default_code = "conflict"


# —— domenowe —— #

class NoSlotsLeft(Conflict):
    default_detail = "Wyczerpałeś limit ogłoszeń w tej kategorii."
    default_code = "no_slots_left"


class PurchaseError(BadRequest):
    default_detail = "Błąd zakupu."
    default_code = "purchase_error"
