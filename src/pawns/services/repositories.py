from __future__ import annotations
from typing import Optional, Iterable
from django.db import transaction as dbtx
from djmoney.money import Money

from pawns.models import Pawn, PawnLine, PawnExtension
from identity.models import User, SellerProfile
from customers.models import Customer
from transactions.models import Transaction


# ==== getters / qs ====

def get_pawn_by_public_id(public_id: str) -> Optional[Pawn]:
    return (Pawn.objects
            .select_related("seller_profile","operator","customer","transaction")
            .prefetch_related("lines","extensions")
            .filter(public_id=public_id).first())

def seller_pawns_qs(user: User):
    return (Pawn.objects
            .select_related("seller_profile","operator","customer","transaction")
            .prefetch_related("lines","extensions")
            .filter(seller_profile__memberships__user=user, seller_profile__memberships__is_active=True)
            .order_by("-created_at").distinct())

def admin_pawns_qs():
    return (Pawn.objects
            .select_related("seller_profile","operator","customer","transaction")
            .prefetch_related("lines","extensions")
            .order_by("-created_at"))

def user_pawns_qs(user: User):
    return (Pawn.objects
            .select_related("seller_profile","operator","customer","transaction")
            .prefetch_related("lines","extensions")
            .filter(customer__user=user)
            .order_by("-created_at"))

# ==== mutate ====

@dbtx.atomic
def create_transaction(*, user: Optional[User], type: str, status: str,
                       expected_total_amount, expected_total_currency: str) -> Transaction:
    return Transaction.objects.create(
        user=user, type=type, status=status,
        expected_total_amount=expected_total_amount,
        expected_total_currency=expected_total_currency
    )

@dbtx.atomic
def create_pawn(*, tx: Transaction, seller: SellerProfile, operator: User,
                customer: Optional[Customer], customer_snapshot: dict,
                principal: Money, start_date, due_date) -> Pawn:
    return Pawn.objects.create(
        transaction=tx, seller_profile=seller, operator=operator,
        customer=customer, customer_snapshot=customer_snapshot,
        principal=principal, appraisal_total=Money(0, principal.currency),
        start_date=start_date, due_date=due_date, status="ACTIVE",
    )

@dbtx.atomic
def add_pawn_line(*, pawn: Pawn, title: str, description: str, quantity: int,
                  appraisal_value: Optional[Money], item_set, item_snapshot: dict) -> PawnLine:
    return PawnLine.objects.create(
        pawn=pawn, item_set=item_set, title=title,
        description=description, quantity=quantity,
        appraisal_value=appraisal_value, item_snapshot=item_snapshot
    )

@dbtx.atomic
def create_extension(*, pawn: Pawn, days: int, fee: Money, previous_due, new_due,
                     tx: Transaction, operator: User) -> PawnExtension:
    return PawnExtension.objects.create(
        pawn=pawn, days=days, fee=fee,
        previous_due=previous_due, new_due=new_due,
        transaction=tx, created_by=operator
    )
