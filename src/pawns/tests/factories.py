from datetime import timedelta
from djmoney.money import Money
from django.utils import timezone

from identity.models import User, SellerProfile, SellerMembership
from customers.models import Customer
from catalog.models import ItemType
from listings.models import ItemSet
from transactions.models import Transaction
from pawns.models import Pawn, PawnLine, PawnExtension

_user_seq = 0
_seller_seq = 0
_itemtype_seq = 0
_itemset_seq = 0
_customer_seq = 0


def create_user(email=None, role="EMPLOYEE", **extra):
    global _user_seq
    if email is None:
        _user_seq += 1
        email = f"user{_user_seq}@example.com"
    return User.objects.create_user(email=email, password="pwd", role=role, **extra)


def create_seller_profile(owner=None, slug=None, **extra):
    global _seller_seq
    if owner is None:
        owner = create_user(role="OWNER")
    if slug is None:
        _seller_seq += 1
        slug = f"shop-{_seller_seq}"

    seller = SellerProfile.objects.create(
        owner=owner,
        company_name=f"Shop {slug}",
        slug=slug,
        **extra,
    )

    membership, created = SellerMembership.objects.get_or_create(
        seller_profile=seller,
        user=owner,
        defaults={"role": "OWNER", "is_active": True},
    )
    if not created:
        dirty = False
        if membership.role != "OWNER":
            membership.role = "OWNER"
            dirty = True
        if not membership.is_active:
            membership.is_active = True
            dirty = True
        if dirty:
            membership.save(update_fields=["role", "is_active"])

    return seller

def create_customer(email=None, user=None, **extra):
    global _customer_seq
    if email is None:
        _customer_seq += 1
        email = f"customer{_customer_seq}@example.com"
    return Customer.objects.create(email=email, user=user, **extra)


def create_item_type(name=None, parent=None, **extra):
    global _itemtype_seq
    if name is None:
        _itemtype_seq += 1
        name = f"Category {_itemtype_seq}"
    return ItemType.objects.create(name=name, parent=parent, **extra)


def create_itemset(seller_profile, item_type=None, price=None, stock_quantity=1, **extra):
    global _itemset_seq
    if item_type is None:
        item_type = create_item_type()
    if price is None:
        price = Money(100, "PLN")
    _itemset_seq += 1
    return ItemSet.objects.create(
        seller_profile=seller_profile,
        owner_user=None,
        set_name=f"Item {_itemset_seq}",
        description="",
        price=price,
        stock_quantity=stock_quantity,
        condition="USED",
        status="AVAILABLE",
        listing_type="BUY",
        allow_online_checkout=False,
        added_by="STAFF",
        type=item_type,
        attributes={},
        **extra,
    )


def create_transaction(user=None, type="PLEDGE", status="PENDING", expected_total_amount=None, currency="PLN", **extra):
    if expected_total_amount is None:
        expected_total_amount = 0
    return Transaction.objects.create(
        user=user,
        type=type,
        status=status,
        expected_total_amount=expected_total_amount,
        expected_total_currency=currency,
        **extra,
    )


def create_pawn(transaction=None, seller_profile=None, operator=None, customer=None, principal=None, start_date=None, due_date=None, status="ACTIVE", **extra):
    if operator is None:
        operator = create_user()
    if seller_profile is None:
        seller_profile = create_seller_profile(owner=operator)
    if transaction is None:
        transaction = create_transaction(user=operator, type="PLEDGE", status="COMPLETED", expected_total_amount=0)
    if principal is None:
        principal = Money(100, "PLN")
    if start_date is None:
        start_date = timezone.now().date()
    if due_date is None:
        due_date = start_date + timedelta(days=30)
    return Pawn.objects.create(
        transaction=transaction,
        seller_profile=seller_profile,
        operator=operator,
        customer=customer,
        customer_snapshot={},
        principal=principal,
        appraisal_total=Money(0, principal.currency),
        start_date=start_date,
        due_date=due_date,
        status=status,
        **extra,
    )


def create_pawn_line(pawn, title="Pozycja", description="", quantity=1, appraisal_value=None, item_set=None, item_snapshot=None, **extra):
    if appraisal_value is None:
        appraisal_value = Money(50, "PLN")
    if item_snapshot is None:
        item_snapshot = {}
    return PawnLine.objects.create(
        pawn=pawn,
        item_set=item_set,
        title=title,
        description=description,
        quantity=quantity,
        appraisal_value=appraisal_value,
        item_snapshot=item_snapshot,
        **extra,
    )


def create_pawn_extension(pawn, days=7, fee=None, previous_due=None, new_due=None, transaction=None, created_by=None, **extra):
    if fee is None:
        fee = Money(10, "PLN")
    if previous_due is None:
        previous_due = pawn.due_date
    if new_due is None:
        new_due = pawn.due_date + timedelta(days=days)
    if created_by is None:
        created_by = pawn.operator
    if transaction is None:
        transaction = create_transaction(user=created_by, type="PAWN_EXTENSION", status="COMPLETED", expected_total_amount=fee.amount, currency=str(fee.currency))
    return PawnExtension.objects.create(
        pawn=pawn,
        days=days,
        fee=fee,
        previous_due=previous_due,
        new_due=new_due,
        transaction=transaction,
        created_by=created_by,
        **extra,
    )
