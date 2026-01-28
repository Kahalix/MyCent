from django.contrib.auth import logout
from django.http import HttpResponseRedirect
from django.urls import reverse

# class BlockAdminForSuspendedUsersMiddleware:
#     def __init__(self, get_response):
#         self.get_response = get_response
#
#     def __call__(self, request):
#         u = getattr(request, "user", None)
#         if request.path.startswith("/admin") and u and u.is_authenticated:
#             if getattr(u, "user_status", "ACTIVE") in {"SUSPENDED", "DELETED"}:
#                 logout(request)
#                 return HttpResponseRedirect(reverse("admin:login"))
#         return self.get_response(request)
#

# Ignorujemy status dla superuser
class BlockAdminForSuspendedUsersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        u = getattr(request, "user", None)
        if request.path.startswith("/admin") and u and u.is_authenticated:
            if u.is_superuser:
                return self.get_response(request)
            if getattr(u, "user_status", "ACTIVE") in {"SUSPENDED", "DELETED"}:
                logout(request)
                return HttpResponseRedirect(reverse("admin:login"))
        return self.get_response(request)