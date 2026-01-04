from __future__ import annotations

from typing import Optional
from django.db import transaction as dbtx
from django.db.models import IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.db.models import Count

from djmoney.money import Money

from pawns.models import Pawn, PawnLine, PawnExtension
from identity.models import User, SellerProfile, SellerMembership
from customers.models import Customer
from transactions.models import Transaction


def _annotate_counts(qs):
    lines_sq = (
        PawnLine.objects.filter(pawn_id=OuterRef("pk"))
        .order_by()
        .values("pawn_id")
        .annotate(c=Count("*"))
        .values("c")[:1]
    )
    ext_sq = (
        PawnExtension.objects.filter(pawn_id=OuterRef("pk"))
        .order_by()
        .values("pawn_id")
        .annotate(c=Count("*"))
        .values("c")[:1]
    )
    return qs.annotate(
        lines_count=Coalesce(Subquery(lines_sq, output_field=IntegerField()), Value(0)),
        extensions_count=Coalesce(Subquery(ext_sq, output_field=IntegerField()), Value(0)),
    )


def get_pawn_by_public_id(public_id: str) -> Optional[Pawn]:
    return (
        Pawn.objects.select_related("seller_profile","operator","customer","transaction")
        .prefetch_related("lines","extensions")
        .filter(public_id=public_id)
        .first()
    )


def seller_pawns_qs(user: User, *, with_related: bool = False):
    seller_ids = SellerMembership.objects.filter(user=user, is_active=True).values("seller_profile_id")
    qs = (
        Pawn.objects.select_related("seller_profile","operator","customer","transaction")
        .filter(seller_profile_id__in=Subquery(seller_ids))
        .order_by("-created_at")
    )
    if with_related:
        return qs.prefetch_related("lines","extensions")
    qs = qs.defer("customer_snapshot")
    return _annotate_counts(qs)


def admin_pawns_qs(*, with_related: bool = False):
    qs = Pawn.objects.select_related("seller_profile","operator","customer","transaction").order_by("-created_at")
    if with_related:
        return qs.prefetch_related("lines","extensions")
    qs = qs.defer("customer_snapshot")
    return _annotate_counts(qs)


def user_pawns_qs(user: User, *, with_related: bool = False):
    cust_id_sq = Customer.objects.filter(user=user).values("id")[:1]
    qs = (
        Pawn.objects.select_related("seller_profile","operator","customer","transaction")
        .filter(customer_id__in=Subquery(cust_id_sq))
        .order_by("-created_at")
    )
    if with_related:
        return qs.prefetch_related("lines","extensions")
    qs = qs.defer("customer_snapshot")
    return _annotate_counts(qs)


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
