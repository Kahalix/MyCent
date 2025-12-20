from __future__ import annotations
from typing import Optional
from django.db import transaction as dbtx
from transactions.models import Transaction

# --- getters / querysets ---

def get_tx_by_public_id(public_id: str) -> Optional[Transaction]:
    return (Transaction.objects
            .select_related("user", "customer", "coupon")
            .prefetch_related("status_history", "orders")
            .filter(public_id=public_id).first())

def user_transactions_qs(user):
    return (Transaction.objects
            .filter(user=user)
            .order_by("-created_at"))

def seller_transactions_qs(user):
    # transakcje, w których są zamówienia sklepów usera
    return (Transaction.objects
            .filter(orders__seller_profile__memberships__user=user,
                    orders__seller_profile__memberships__is_active=True)
            .order_by("-created_at")
            .distinct())

def admin_transactions_qs():
    return Transaction.objects.all().order_by("-created_at")

# --- mutate ---

@dbtx.atomic
def save_transaction(tx: Transaction) -> Transaction:
    tx.save()
    return tx
