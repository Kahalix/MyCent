from __future__ import annotations
import uuid

from django.contrib.auth import get_user_model

from identity.models import (
    SellerProfile,
    SellerBankAccount,
    SellerMembership,
    UserToken,
)

User = get_user_model()


def create_user(
    email: str | None = None,
    points: int = 0,
    password: str = "pass1234",
    **extra,
) -> User:
    if email is None:
        email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    return User.objects.create_user(
        email=email,
        password=password,
        points=points,
        **extra,
    )


def create_seller_profile(
    *,
    owner: User | None = None,
    company_name: str | None = None,
    slug: str | None = None,
    **extra,
) -> SellerProfile:
    if owner is None:
        owner = create_user()
    if company_name is None:
        company_name = f"Company {uuid.uuid4().hex[:6]}"
    if slug is None:
        slug = f"shop-{uuid.uuid4().hex[:6]}"
    return SellerProfile.objects.create(
        owner=owner,
        company_name=company_name,
        slug=slug,
        **extra,
    )


def create_seller_membership(
    *,
    seller_profile: SellerProfile | None = None,
    user: User | None = None,
    role: str = "EMPLOYEE",
    is_active: bool = True,
) -> SellerMembership:
    if seller_profile is None:
        seller_profile = create_seller_profile()
    if user is None:
        user = create_user()
    return SellerMembership.objects.create(
        seller_profile=seller_profile,
        user=user,
        role=role,
        is_active=is_active,
    )


def create_seller_bank_account(
    *,
    seller_profile: SellerProfile | None = None,
    iban: str | None = None,
    bank_name: str = "Test Bank",
    account_holder: str = "Test Holder",
    is_active: bool = True,
    is_default: bool = False,
) -> SellerBankAccount:
    if seller_profile is None:
        seller_profile = create_seller_profile()
    if iban is None:
        iban = f"PL00{uuid.uuid4().hex[:11].upper()}"
    return SellerBankAccount.objects.create(
        seller_profile=seller_profile,
        iban=iban,
        bank_name=bank_name,
        account_holder=account_holder,
        is_active=is_active,
        is_default=is_default,
    )


def issue_ephemeral_token(
    *,
    user: User | None = None,
    typ: str = "EMAIL_CONFIRMATION",
    minutes_valid: int = 10,
    data: dict | None = None,
) -> str:
    if user is None:
        user = create_user()
    return UserToken.issue_ephemeral(user, typ, minutes_valid=minutes_valid, data=data or {})
