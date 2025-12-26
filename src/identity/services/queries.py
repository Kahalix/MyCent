from __future__ import annotations
from typing import Optional, Any

from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet, Case, When, Value, IntegerField

from ..models import SellerProfile, SellerBankAccount, SellerMembership
from ..serializers import PublicUserResponse

User = get_user_model()


# === DTO dla /me itp. ===
def me_payload(user: User) -> dict[str, Any]:
    return PublicUserResponse(user).data


# === helpery user/seller (cienkie wrapy dla widoków) ===
def get_user_by_public_id(public_id: str) -> Optional[User]:
    return User.objects.filter(public_id=public_id).first()

def find_user_by_email_ci(email: str) -> Optional[User]:
    return User.objects.filter(email__iexact=email).first()


# === zapytania o sklepy i konta bankowe dla usera ===
def sellers_for_user(user: User) -> QuerySet[SellerProfile]:
    """
    Wszystkie sklepy, w których user ma aktywne członkostwo.
    """
    return (
        SellerProfile.objects
        .select_related("owner")
        .filter(memberships__user=user, memberships__is_active=True)
        .distinct()
        .order_by("company_name")
    )

def bank_accounts_for_user(user: User):
    """
    Wszystkie konta bankowe w sklepach, gdzie user ma aktywne membership.
    """
    return (
        SellerBankAccount.objects
        .select_related("seller_profile")
        .filter(
            seller_profile__memberships__user=user,
            seller_profile__memberships__is_active=True
        )
        .order_by("-created_at")
        .distinct()
    )


# === membership listy ===
def memberships_for_seller(seller: SellerProfile) -> QuerySet[SellerMembership]:
    return (
        SellerMembership.objects
        .select_related("user", "seller_profile")
        .filter(seller_profile=seller, is_active=True)
        .order_by("-created_at")
    )

def memberships_for_user(user: User):
    return (
        SellerMembership.objects
        .select_related("seller_profile", "user")
        .filter(user=user, is_active=True)
        .order_by("-created_at")
    )

def members_for_seller(seller: SellerProfile):
    return (
        SellerMembership.objects
        .select_related("seller_profile", "user")
        .filter(seller_profile=seller, is_active=True)
        .order_by(
            Case(
                When(role="OWNER", then=Value(1)),
                When(role="MANAGER", then=Value(2)),
                When(role="MODERATOR", then=Value(3)),
                default=Value(4),
                output_field=IntegerField(),
            ),
            "-created_at",
        )
    )

def get_membership_by_public_id(public_id: str) -> Optional[SellerMembership]:
    return (
        SellerMembership.objects
        .select_related("seller_profile", "user")
        .filter(public_id=public_id)
        .first()
    )

def get_seller_by_public_id(public_id: str) -> Optional[SellerProfile]:
    return SellerProfile.objects.select_related("owner").filter(public_id=public_id).first()


# === uprawnienia (read-layer) ===
def user_role_in_seller(user: User, seller: SellerProfile) -> Optional[str]:
    if not user or not seller:
        return None
    if user.id == seller.owner_id:
        return "OWNER"
    m = SellerMembership.objects.filter(
        seller_profile=seller, user=user, is_active=True
    ).first()
    return m.role if m else None

def can_manage_members(user: User, seller: SellerProfile) -> bool:
    # superuser zawsze może
    if user.is_superuser:
        return True
    # tylko właściciel lub manager sklepu
    role = user_role_in_seller(user, seller)
    return role in ("OWNER", "MANAGER")

def get_membership_by_public_id_for_seller(public_id: str, seller: SellerProfile) -> Optional[SellerMembership]:
    return (
        SellerMembership.objects
        .select_related("seller_profile", "user")
        .filter(public_id=public_id, seller_profile=seller)
        .first()
    )

def best_membership_for_user(user: User) -> Optional[SellerMembership]:
    """
    Zwraca „najsilniejsze” aktywne członkostwo usera wg priorytetu:
    OWNER > MANAGER > MODERATOR > EMPLOYEE (a w ramach roli – najnowsze).
    """
    return (
        SellerMembership.objects
        .select_related("seller_profile")
        .filter(user=user, is_active=True)
        .annotate(role_rank=Case(
            When(role="OWNER", then=Value(1)),
            When(role="MANAGER", then=Value(2)),
            When(role="MODERATOR", then=Value(3)),
            When(role="EMPLOYEE", then=Value(4)),
            default=Value(9),
            output_field=IntegerField(),
        ))
        .order_by("role_rank", "-created_at")
        .first()
    )
