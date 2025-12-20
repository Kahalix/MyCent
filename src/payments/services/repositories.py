from __future__ import annotations
from typing import Optional
from django.db import transaction as dbtx
from django.db.models import QuerySet

from payments.models import Payment
from transactions.models import Transaction

def get_by_public_id(public_id: str) -> Optional[Payment]:
    return Payment.objects.select_related("transaction").filter(public_id=public_id).first()

def list_for_user(user) -> QuerySet[Payment]:
    return (Payment.objects
            .select_related("transaction")
            .filter(transaction__user=user)
            .order_by("-created_at"))

def list_for_seller(user) -> QuerySet[Payment]:
    # płatności transakcji, które mają zamówienia sprzedawcy (podobnie jak SellerTransactionViewSet)
    return (Payment.objects.select_related("transaction")
            .filter(transaction__orders__seller_profile__memberships__user=user,
                    transaction__orders__seller_profile__memberships__is_active=True)
            .order_by("-created_at").distinct())

def list_for_admin() -> QuerySet[Payment]:
    return Payment.objects.select_related("transaction").order_by("-created_at")

@dbtx.atomic
def create_payment(*, tx: Transaction, **fields) -> Payment:
    return Payment.objects.create(transaction=tx, **fields)

@dbtx.atomic
def save_payment(p: Payment) -> Payment:
    p.save()
    return p
