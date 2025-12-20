from django.utils.deprecation import MiddlewareMixin
from django.middleware.csrf import get_token

class EnsureCSRFCookieMiddleware(MiddlewareMixin):
    """
    Gwarantuje, że CsrfViewMiddleware ustawi cookie `csrftoken`.
    Działa przez wczesne wywołanie get_token(request).
    """
    def process_request(self, request):
        try:
            get_token(request)  # oznacza CSRF_COOKIE_USED => CsrfViewMiddleware wystawi cookie
        except Exception:
            pass
