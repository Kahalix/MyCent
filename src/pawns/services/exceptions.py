from __future__ import annotations
from rest_framework.exceptions import APIException

class DomainError(APIException):
    status_code = 400
    default_detail = "Bad request"
    default_code = "bad_request"

class NotFound(DomainError):
    status_code = 404
    default_detail = "Not found"
    default_code = "not_found"

class Forbidden(DomainError):
    status_code = 403
    default_detail = "Forbidden"
    default_code = "forbidden"

class Conflict(DomainError):
    status_code = 409
    default_detail = "Conflict"
    default_code = "conflict"
