from __future__ import annotations
from typing import Optional
from django.contrib.auth import get_user_model
from django.db import transaction
from ..models import UserToken, SellerProfile, SellerBankAccount, SellerMembership

User = get_user_model()

# ===== Users =====

def find_user_by_email_ci(email: str) -> Optional[User]:
    return User.objects.filter(email__iexact=email).first()

def is_email_taken_ci(email: str, exclude_user_id: Optional[int] = None) -> bool:
    qs = User.objects.filter(email__iexact=email)
    if exclude_user_id:
        qs = qs.exclude(id=exclude_user_id)
    return qs.exists()

def create_user(email: str, password: str, first_name: str, last_name: str, *, active: bool) -> User:
    return User.objects.create_user(
        email=email, password=password, first_name=first_name, last_name=last_name, is_active=active
    )

def get_user_by_id(user_id: int) -> Optional[User]:
    return User.objects.filter(id=user_id).first()

def get_user_by_public_id(public_id: str) -> Optional[User]:
    return User.objects.filter(public_id=public_id).first()

# ===== Tokens =====

def issue_ephemeral(user: User, typ: str, minutes: int, data: Optional[dict] = None) -> str:
    return UserToken.issue_ephemeral(user, typ, minutes_valid=minutes, data=data)

def consume_ephemeral(token_raw: str, typ: str) -> Optional[UserToken]:
    return UserToken.consume_ephemeral(token_raw, typ)

def save_refresh(user: User, refresh_jwt: str, data: Optional[dict] = None) -> UserToken:
    return UserToken.save_refresh(user, refresh_jwt, data=data)

def exists_refresh(user: User, refresh_jwt: str) -> bool:
    return UserToken.exists_refresh(user, refresh_jwt)

def delete_refresh(user: User, refresh_jwt: str) -> int:
    return UserToken.delete_refresh(user, refresh_jwt)

def delete_all_refreshes(user: User) -> int:
    return UserToken.delete_all_refreshes(user)

# ===== SellerProfile =====

def get_seller_by_public_id(public_id: str) -> Optional[SellerProfile]:
    return SellerProfile.objects.select_related("owner").filter(public_id=public_id).first()

def get_seller_by_slug(slug: str) -> Optional[SellerProfile]:
    return SellerProfile.objects.select_related("owner").filter(slug=slug).first()

def get_seller_for_owner(owner: User) -> Optional[SellerProfile]:
    return SellerProfile.objects.filter(owner=owner).first()

# ===== SellerBankAccount =====

def get_bank_account_by_public_id(public_id: str) -> SellerBankAccount | None:
    return SellerBankAccount.objects.select_related("seller_profile__owner").filter(public_id=public_id).first()

def list_bank_accounts_for_owner(owner) -> "QuerySet[SellerBankAccount]":
    return SellerBankAccount.objects.select_related("seller_profile").filter(seller_profile__owner=owner).order_by("-created_at")

@transaction.atomic
def set_default_for_seller(seller_profile: SellerProfile, bank_account: SellerBankAccount):
    SellerBankAccount.objects.filter(seller_profile=seller_profile, is_default=True).update(is_default=False)
    bank_account.is_default = True
    bank_account.save(update_fields=["is_default"])

# ===== SellerMembership =====

def is_member(user: User, seller_public_id: str, roles: set[str] | None = None) -> bool:
    if not user or not seller_public_id: return False
    qs = SellerMembership.objects.filter(user=user, seller_profile__public_id=seller_public_id, is_active=True)
    if roles:
        qs = qs.filter(role__in=list(roles))
    return qs.exists()

def list_sellers_for_user(user: User):
    return SellerProfile.objects.filter(memberships__user=user, memberships__is_active=True).distinct()

def list_bank_accounts_for_user(user: User):
    return SellerBankAccount.objects.select_related("seller_profile").filter(
        seller_profile__memberships__user=user,
        seller_profile__memberships__is_active=True
    ).order_by("-created_at")

