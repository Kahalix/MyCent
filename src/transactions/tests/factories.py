from __future__ import annotations
from decimal import Decimal

from django.utils import timezone
from djmoney.money import Money

from identity.models import User, SellerProfile, SellerMembership
from customers.models import Customer
from coupons.models import Coupon, UserCoupon
from transactions.models import Transaction
from orders.models import Order


def create_user(email: str = "user@example.com", is_staff: bool = False, is_superuser: bool = False) -> User:
    user = User.objects.create_user(email=email, password="password123")
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    return user


def create_customer(user: User | None = None, email: str = "cust@example.com") -> Customer:
    return Customer.objects.create(
        user=user,
        first_name="John",
        last_name="Doe",
        email=email,
        phone="123456789",
    )


def create_transaction(
    user: User | None = None,
    type: str = "PURCHASE",
    status: str = "PENDING",
    expected_total_amount: Decimal | None = None,
    expected_total_currency: str = "PLN",
    coupon: Coupon | None = None,
    user_coupon: UserCoupon | None = None,
    customer: Customer | None = None,
    notes: str = "test",
) -> Transaction:
    return Transaction.objects.create(
        user=user,
        customer=customer,
        coupon=coupon,
        user_coupon=user_coupon,
        type=type,
        status=status,
        expected_total_amount=expected_total_amount,
        expected_total_currency=expected_total_currency,
        notes=notes,
    )


def create_coupon(
    code: str | None = None,
    discount_type: str = "PERCENTAGE",
    discount_value: Money | None = Money(10, "PLN"),
    max_discount_value: Money | None = None,
    min_purchase_value: Money | None = None,
    active: bool = True,
    max_redemptions: int | None = None,
    max_per_user: int | None = None,
) -> Coupon:
    if code is None:
        code = f"CODE{Coupon.objects.count() + 1}"
    return Coupon.objects.create(
        code=code,
        discount_type=discount_type,
        discount_value=discount_value,
        max_discount_value=max_discount_value,
        min_purchase_value=min_purchase_value,
        quantity=None,
        points_cost=None,
        max_redemptions=max_redemptions,
        max_per_user=max_per_user,
        active=active,
        expiration_date=None,
    )


def create_user_coupon(
    user: User,
    coupon: Coupon,
    redeemed: bool = False,
) -> UserCoupon:
    redeemed_at = timezone.now() if redeemed else None
    return UserCoupon.objects.create(
        user=user,
        coupon=coupon,
        redeemed=redeemed,
        redeemed_at=redeemed_at,
    )


def create_seller_profile(owner: User, slug: str | None = None) -> SellerProfile:
    if slug is None:
        slug = f"seller-{SellerProfile.objects.count() + 1}"
    return SellerProfile.objects.create(
        owner=owner,
        company_name="Test Seller",
        legal_name="Test Seller Sp. z o.o.",
        slug=slug,
        description="",
        contact_email=owner.email,
    )


def create_seller_membership(
    seller_profile: SellerProfile,
    user: User,
    role: str = "OWNER",
    is_active: bool = True,
) -> SellerMembership:
    obj, _ = SellerMembership.objects.get_or_create(
        seller_profile=seller_profile,
        user=user,
        defaults={"role": role, "is_active": is_active},
    )
    return obj


def create_order_for_transaction(
    tx: Transaction,
    seller_profile: SellerProfile,
    buyer: User | None = None,
    grand_total: Money = Money(100, "PLN"),
) -> Order:
    return Order.objects.create(
        transaction=tx,
        seller_profile=seller_profile,
        buyer=buyer or tx.user,
        purchase_cost=grand_total,
    )
