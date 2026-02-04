from __future__ import annotations

from uuid import uuid4
from decimal import Decimal

from djmoney.money import Money

from identity.models import User, SellerProfile, SellerMembership
from transactions.models import Transaction
from orders.models import Order, OrderLine, OrderShipping
from shipping.models import PackageType
from coupons.models import Coupon, UserCoupon
from payments.models import Payment
from listings.models import ItemSet


def create_user(email: str | None = None, password: str = "pass1234", **extra) -> User:
    if email is None:
        email = f"user-{uuid4().hex[:8]}@example.com"
    return User.objects.create_user(email=email, password=password, **extra)

def create_itemset(
    seller_profile,
    item_type=None,
    set_name: str = "Item",
    price=None,
    stock_quantity: int = 10,
    status: str = "AVAILABLE",
    listing_type: str = "BUY",
    allow_online_checkout: bool = True,
):
    from djmoney.money import Money
    try:
        from catalog.models import ItemType
    except Exception:
        ItemType = None

    if price is None:
        cur = "PLN"
        price = Money(100, cur)

    if item_type is None and ItemType is not None:
        item_type = ItemType.objects.create(name="TestCategory")

    try:
        from listings.models import ItemSet as _ItemSet
    except Exception:
        _ItemSet = ItemSet

    return _ItemSet.objects.create(
        set_name=set_name,
        description="",
        price=price,
        stock_quantity=stock_quantity,
        condition="NEW",
        status=status,
        listing_type=listing_type,
        allow_online_checkout=allow_online_checkout,
        seller_profile=seller_profile,
        owner_user=None,
        type=item_type,
    )

def create_seller_profile(owner: User | None = None, slug: str | None = None, **extra) -> SellerProfile:
    owner = owner or create_user()
    if slug is None:
        slug = f"shop-{uuid4().hex[:6]}"
    data = {"company_name": f"Shop {slug}"}
    data.update(extra)
    return SellerProfile.objects.create(owner=owner, slug=slug, **data)


def create_seller_membership(
    seller_profile: SellerProfile,
    user: User,
    role: str = "EMPLOYEE",
    is_active: bool = True,
) -> SellerMembership:
    obj, created = SellerMembership.objects.get_or_create(
        seller_profile=seller_profile,
        user=user,
        defaults={"role": role, "is_active": is_active},
    )
    if not created:
        obj.role = role
        obj.is_active = is_active
        obj.save(update_fields=["role", "is_active", "updated_at"])
    return obj


def create_transaction(
    user: User | None = None,
    type: str = "PURCHASE",
    status: str = "PENDING",
    amount: Decimal = Decimal("100.00"),
    currency: str = "PLN",
    **extra,
) -> Transaction:
    user = user or create_user()
    data = {
        "expected_total_amount": amount,
        "expected_total_currency": currency,
    }
    data.update(extra)
    return Transaction.objects.create(
        user=user,
        type=type,
        status=status,
        **data,
    )


def create_order(
    tx: Transaction,
    seller_profile: SellerProfile | None = None,
    items_total: Money | None = None,
    shipping_total: Money | None = None,
    purchase_cost: Money | None = None,
    shipping_address: dict | None = None,
    **extra,
) -> Order:
    seller_profile = seller_profile or create_seller_profile(owner=tx.user)
    cur = tx.expected_total_currency or "PLN"
    if items_total is None:
        items_total = Money(tx.expected_total_amount or 0, cur)
    if shipping_total is None:
        shipping_total = Money(0, cur)
    if purchase_cost is None:
        base = items_total or Money(0, cur)
        purchase_cost = base + (shipping_total or Money(0, cur))
    if shipping_address is None:
        shipping_address = {}
    data = {
        "buyer": tx.user,
        "items_total": items_total,
        "shipping_total": shipping_total,
        "purchase_cost": purchase_cost,
        "shipping_address": shipping_address,
    }
    data.update(extra)
    return Order.objects.create(
        transaction=tx,
        seller_profile=seller_profile,
        **data,
    )


def create_order_line(
    order: Order,
    quantity: int = 1,
    unit_price: Money | None = None,
    **extra,
) -> OrderLine:
    cur = order.items_total.currency if order.items_total is not None else "PLN"
    if unit_price is None:
        unit_price = Money(Decimal("100.00"), cur)
    data = {
        "quantity": quantity,
        "unit_price": unit_price,
    }
    data.update(extra)
    return OrderLine.objects.create(
        order=order,
        **data,
    )


def create_package_type(provider: str = "OTHER", **extra) -> PackageType:
    data = {"provider": provider}
    data.update(extra)
    return PackageType.objects.create(**data)


def create_order_shipping(
    order: Order,
    order_line: OrderLine,
    price: Money | None = None,
    package_type: PackageType | None = None,
    **extra,
) -> OrderShipping:
    cur = order.items_total.currency if order.items_total is not None else "PLN"
    if price is None:
        price = Money(Decimal("10.00"), cur)
    if package_type is None:
        package_type = create_package_type()
    data = {
        "price": price,
        "package_type": package_type,
    }
    data.update(extra)
    return OrderShipping.objects.create(
        order=order,
        order_line=order_line,
        **data,
    )


def create_coupon(
    code: str | None = None,
    discount_type: str = "PERCENTAGE",
    discount_value: Money | None = None,
    **extra,
) -> Coupon:
    if code is None:
        code = f"COUPON-{uuid4().hex[:6]}".upper()
    if discount_value is None:
        discount_value = Money(Decimal("10.00"), "PLN")
    data = {
        "code": code,
        "discount_type": discount_type,
        "discount_value": discount_value,
    }
    data.update(extra)
    return Coupon.objects.create(**data)


def create_user_coupon(
    user: User,
    coupon: Coupon,
    points_paid: int | None = None,
    **extra,
) -> UserCoupon:
    data = {"points_paid": points_paid}
    data.update(extra)
    return UserCoupon.objects.create(
        user=user,
        coupon=coupon,
        **data,
    )


def create_payment(
    tx: Transaction,
    amount: Money | None = None,
    provider: str = "SIM",
    status: str = "REQUIRES_CONFIRMATION",
    **extra,
) -> Payment:
    cur = tx.expected_total_currency or "PLN"
    if amount is None:
        amount = Money(tx.expected_total_amount or 0, cur)
    data = {
        "provider": provider,
        "amount": amount,
        "status": status,
    }
    data.update(extra)
    return Payment.objects.create(
        transaction=tx,
        **data,
    )