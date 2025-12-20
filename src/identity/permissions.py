from __future__ import annotations
from rest_framework.permissions import BasePermission, SAFE_METHODS

from identity.models import SellerMembership

ADMIN_ROLES = {"OWNER", "MANAGER"}        # kto ma „pełną władzę”
MOD_ROLES   = {"MODERATOR", "MANAGER", "OWNER"}
SHOP_MOD_ROLES = {"MANAGER", "MODERATOR", "OWNER"}

def _has_membership(user, seller_public_id: str, roles: set[str] | None = None) -> bool:
    if not (user and user.is_authenticated and seller_public_id):
        return False
    qs = SellerMembership.objects.filter(
        user=user,
        seller_profile__public_id=seller_public_id,
        is_active=True
    )
    if roles:
        qs = qs.filter(role__in=list(roles))
    return qs.exists()

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.is_superuser)

class IsSellerMember(BasePermission):
    """Sprawdza członkostwo w profilu sprzedawcy przypiętym do obiektu."""
    def has_object_permission(self, request, view, obj):
        spid = getattr(getattr(obj, "seller_profile", None), "public_id", None)
        return _has_membership(request.user, spid)

class IsSellerManagerOrOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        spid = getattr(getattr(obj, "seller_profile", None), "public_id", None)
        return _has_membership(request.user, spid, ADMIN_ROLES)

class IsShopModeratorMember(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        seller_public_id = getattr(getattr(view, "kwargs", None), "get", lambda *_: None)("seller_public_id") or request.query_params.get("seller_public_id") or request.data.get("seller_public_id")
        if seller_public_id:
            return _has_membership(u, seller_public_id, SHOP_MOD_ROLES)
        return SellerMembership.objects.filter(user=u, is_active=True, role__in=list(SHOP_MOD_ROLES)).exists()

class IsModerator(BasePermission):
    """
    Moderator: Django is_staff OR rola w MOD_ROLES (MODERATOR/MANAGER/OWNER).
    """
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_staff or getattr(u, "role", None) in MOD_ROLES))

class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS

class IsSelf(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and obj.pk == request.user.pk

class IsSellerOwnerOrAdmin(BasePermission):
    """
    Dla obiektów SellerProfile – właściciel (owner) lub admin.
    """
    def has_object_permission(self, request, view, obj):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        if u.is_superuser:
            return True
        return getattr(obj, "owner_id", None) == u.id

    def has_permission(self, request, view):
        # przy tworzeniu pozwól zalogowanym; walidacja szczegółowa w command
        return request.user.is_authenticated

class IsBankAccountOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        if u.is_superuser:
            return True
        # własność konta = właściciel SellerProfile
        try:
            return obj.seller_profile.owner_id == u.id
        except Exception:
            return False

    def has_permission(self, request, view):
        return request.user.is_authenticated

class IsUserRoleOwner(BasePermission):
    """Wymaga, by request.user.role == OWNER (nie mylić z membership OWNER)."""
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and getattr(u, "role", None) == "OWNER")
