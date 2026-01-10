from __future__ import annotations
from typing import Optional
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from ..models import PackageType, ShippingAddress
from ..services import repositories as repo
from ..services.exceptions import (
    AddressAlreadyExists, InvalidPackageLimits, NotFound, NotAllowed, DomainError
)

User = get_user_model()

# ===== ShippingAddress - self/admin =====

@transaction.atomic
def create_address_for_user(*, user: User, data: dict) -> ShippingAddress:
    if repo.get_address_for_user(user):
        raise AddressAlreadyExists("Address already exists. Use PATCH to update.")
    addr = repo.create_address_for_user(user, **data)
    return addr

@transaction.atomic
def upsert_address_for_user(*, user: User, data: dict) -> ShippingAddress:
    addr = repo.get_address_for_user(user)
    if not addr:
        return repo.create_address_for_user(user, **data)
    changed = False
    for k, v in data.items():
        if v is not None:
            setattr(addr, k, v); changed = True
    if changed:
        repo.save_address(addr)
    return addr

@transaction.atomic
def admin_update_address(*, address: ShippingAddress, data: dict) -> ShippingAddress:
    for k, v in data.items():
        if v is not None:
            setattr(address, k, v)
    repo.save_address(address)
    return address

@transaction.atomic
def admin_delete_address(*, address: ShippingAddress) -> None:
    repo.delete_address(address)

# ===== PackageType - admin =====

@transaction.atomic
def create_package_type(*, data: dict) -> PackageType:
    pkg = PackageType(**data)
    try:
        pkg.full_clean()
    except DjangoValidationError as e:
        raise InvalidPackageLimits(e.message_dict if hasattr(e, "message_dict") else str(e))
    repo.save_package_type(pkg)
    return pkg

@transaction.atomic
def update_package_type(*, pkg: PackageType, data: dict) -> PackageType:
    for k, v in data.items():
        setattr(pkg, k, v)
    try:
        pkg.full_clean()
    except DjangoValidationError as e:
        raise InvalidPackageLimits(e.message_dict if hasattr(e, "message_dict") else str(e))
    repo.save_package_type(pkg)
    return pkg

@transaction.atomic
def delete_package_type(*, pkg: PackageType) -> None:
    repo.delete_package_type(pkg)
