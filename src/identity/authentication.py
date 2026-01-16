# from __future__ import annotations
#
# from django.conf import settings
# from rest_framework import exceptions
# from rest_framework.authentication import CSRFCheck
# from rest_framework_simplejwt.authentication import JWTAuthentication
# from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
#
#
# class CookieJWTAuthentication(JWTAuthentication):
#     def _enforce_csrf(self, request) -> None:
#         req = getattr(request, "_request", request)
#         check = CSRFCheck(lambda r: None)
#         check.process_request(req)
#         reason = check.process_view(req, None, (), {})
#         if reason:
#             raise exceptions.PermissionDenied("CSRF Failed")
#
#     def authenticate(self, request):
#         header = self.get_header(request)
#         if header is not None:
#             raw = self.get_raw_token(header)
#             if raw is not None:
#                 try:
#                     validated = self.get_validated_token(raw)
#                 except (InvalidToken, TokenError):
#                     raise exceptions.AuthenticationFailed("Invalid token", code="token_not_valid")
#                 return self.get_user(validated), validated
#
#         cookie_name = getattr(settings, "ACCESS_COOKIE_NAME", "access_token")
#         raw_cookie = request.COOKIES.get(cookie_name)
#         if not raw_cookie:
#             return None
#
#         if request.method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
#             self._enforce_csrf(request)
#
#         try:
#             validated = self.get_validated_token(raw_cookie)
#         except (InvalidToken, TokenError):
#             raise exceptions.AuthenticationFailed("Invalid token", code="token_not_valid")
#
#         return self.get_user(validated), validated


from __future__ import annotations

from django.conf import settings
from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class CookieJWTAuthentication(JWTAuthentication):
    def _enforce_csrf(self, request) -> None:
        req = getattr(request, "_request", request)
        check = CSRFCheck(lambda r: None)
        check.process_request(req)
        reason = check.process_view(req, None, (), {})
        if reason:
            raise exceptions.PermissionDenied("CSRF Failed")

    def authenticate(self, request):
        allow_bearer = bool(getattr(settings, "JWT_ALLOW_AUTH_HEADER_BEARER", False))

        if allow_bearer:
            header = self.get_header(request)
            if header is not None:
                raw = self.get_raw_token(header)
                if raw is not None:
                    try:
                        validated = self.get_validated_token(raw)
                    except (InvalidToken, TokenError):
                        raise exceptions.AuthenticationFailed("Invalid token", code="token_not_valid")
                    return self.get_user(validated), validated

        cookie_name = getattr(settings, "ACCESS_COOKIE_NAME", "access_token")
        raw_cookie = request.COOKIES.get(cookie_name)
        if not raw_cookie:
            return None

        if request.method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
            self._enforce_csrf(request)

        try:
            validated = self.get_validated_token(raw_cookie)
        except (InvalidToken, TokenError):
            raise exceptions.AuthenticationFailed("Invalid token", code="token_not_valid")

        return self.get_user(validated), validated
