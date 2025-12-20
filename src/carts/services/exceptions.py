from rest_framework.exceptions import APIException

class DomainError(APIException):
    status_code = 400
    default_detail = "Bad request"

class NotFound(DomainError):
    status_code = 404
    default_detail = "Not found"

class Forbidden(DomainError):
    status_code = 403
    default_detail = "Forbidden"

class Conflict(DomainError):
    status_code = 409
    default_detail = "Conflict"