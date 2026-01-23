from __future__ import annotations
from typing import Optional
from django.db import transaction as dbtx

from customers.models import Customer
from identity.models import User


# ===== getters / listy =====

def get_by_public_id(public_id: str) -> Optional[Customer]:
    return Customer.objects.filter(public_id=public_id).first()

def admin_customers_qs():
    return Customer.objects.all().order_by("-created_at")

def seller_customers_qs(user: User):
    """
    Globalna baza klientów - dostęp jeśli user ma aktywne członkostwo w dowolnym sklepie.
    (Filtr po sprzedawcy można dorobić później, jeśli model się zmieni.)
    """
    from identity.models import SellerProfile
    has_membership = SellerProfile.objects.filter(memberships__user=user, memberships__is_active=True).exists()
    if not has_membership:
        return Customer.objects.none()
    return Customer.objects.all().order_by("-created_at")

def user_customers_qs(user: User):
    return Customer.objects.filter(user=user).order_by("-created_at")


# ===== mutacje =====

@dbtx.atomic
def create_customer(**fields) -> Customer:
    return Customer.objects.create(**fields)

@dbtx.atomic
def update_customer(obj: Customer, **fields) -> Customer:
    for k, v in fields.items():
        setattr(obj, k, v)
    obj.save()
    return obj

@dbtx.atomic
def delete_customer(obj: Customer) -> None:
    obj.delete()
