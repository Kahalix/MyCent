from __future__ import annotations
from typing import Optional
from django.contrib.auth import get_user_model
from ..models import PackageType, ShippingAddress

User = get_user_model()

# ===== PackageType =====

def get_package_by_public_id(public_id: str) -> Optional[PackageType]:
    return PackageType.objects.filter(public_id=public_id).first()

def create_package_type(**data) -> PackageType:
    return PackageType.objects.create(**data)

def save_package_type(pkg: PackageType) -> PackageType:
    pkg.save()
    return pkg

def delete_package_type(pkg: PackageType) -> None:
    pkg.delete()

# ===== ShippingAddress (OneToOne do Usera) =====

def get_address_for_user(user: User) -> Optional[ShippingAddress]:
    return ShippingAddress.objects.filter(user=user).first()

def get_address_by_public_id(public_id: str) -> Optional[ShippingAddress]:
    return ShippingAddress.objects.filter(public_id=public_id).first()

def create_address_for_user(user: User, **data) -> ShippingAddress:
    return ShippingAddress.objects.create(user=user, **data)

def save_address(addr: ShippingAddress) -> ShippingAddress:
    addr.save()
    return addr

def delete_address(addr: ShippingAddress) -> None:
    addr.delete()
