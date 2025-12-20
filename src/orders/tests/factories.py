from django.utils import timezone
from djmoney.money import Money

from identity.models import User, SellerProfile, SellerMembership
from catalog.models import ItemType
from listings.models import ItemSet
from shipping.models import PackageType
from customers.models import Customer
from transactions.models import Transaction
from orders.models import Order, OrderLine, OrderShipping, ItemReservation


def create_user(email: str = "user@example.com", password: str = "pass", is_staff: bool = False, is_superuser: bool = False, **extra):
    if is_superuser:
        return User.objects.create_superuser(email=email, password=password, **extra)
    if is_staff:
        return User.objects.create_user(email=email, password=password, is_staff=True, **extra)
    return User.objects.create_user(email=email, password=password, **extra)


def create_seller_profile(owner: User, slug: str = "shop", company_name: str = "Shop"):
    return SellerProfile.objects.create(
        owner=owner,
        company_name=company_name,
        slug=slug,
    )


def create_seller_member(seller: SellerProfile, user: User, role: str = "EMPLOYEE", is_active: bool = True):
    return SellerMembership.objects.create(
        seller_profile=seller,
        user=user,
        role=role,
        is_active=is_active,
    )


def create_item_type(name: str = "Category"):
    return ItemType.objects.create(name=name)


def create_itemset(
    seller: SellerProfile,
    item_type: ItemType,
    set_name: str = "Item",
    price: Money = Money(100, "PLN"),
    stock_quantity: int = 10,
    status: str = "AVAILABLE",
    listing_type: str = "BUY",
    allow_online_checkout: bool = True,
):
    return ItemSet.objects.create(
        set_name=set_name,
        description="",
        price=price,
        stock_quantity=stock_quantity,
        condition="NEW",
        status=status,
        listing_type=listing_type,
        allow_online_checkout=allow_online_checkout,
        seller_profile=seller,
        owner_user=None,
        type=item_type,
    )


def create_package_type(
    provider: str = "INPOST",
    dimensions: str = "A",
    price: Money | None = Money(10, "PLN"),
    max_length_cm: int | None = None,
    max_width_cm: int | None = None,
    max_height_cm: int | None = None,
    max_weight_kg: float | None = None,
):
    return PackageType.objects.create(
        provider=provider,
        dimensions=dimensions,
        price=price,
        max_length_cm=max_length_cm,
        max_width_cm=max_width_cm,
        max_height_cm=max_height_cm,
        max_weight_kg=max_weight_kg,
    )


def create_customer(
    first_name: str = "Jan",
    last_name: str = "Kowalski",
    email: str = "customer@example.com",
    phone: str = "123456789",
):
    return Customer.objects.create(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
    )


def create_transaction(user: User | None = None, type_: str = "PURCHASE", status: str = "PENDING"):
    return Transaction.objects.create(
        user=user,
        type=type_,
        status=status,
    )


def create_order(
    tx: Transaction,
    seller: SellerProfile,
    buyer: User | None = None,
    order_name: str = "Order",
    status: str = "PENDING",
    payment_method: str = "CASH",
    purchase_date=None,
):
    if purchase_date is None:
        purchase_date = timezone.now().date()
    return Order.objects.create(
        transaction=tx,
        seller_profile=seller,
        buyer=buyer,
        order_name=order_name,
        purchase_date=purchase_date,
        order_status=status,
        payment_method=payment_method,
    )


def create_order_line(
    order: Order,
    item: ItemSet | None,
    quantity: int = 1,
    unit_price: Money | None = None,
    snapshot: dict | None = None,
):
    if unit_price is None and item is not None:
        unit_price = item.price
    if unit_price is None:
        unit_price = Money(0, "PLN")
    if snapshot is None:
        if item is not None:
            snapshot = {"set_name": item.set_name}
        else:
            snapshot = {"title": "Pozycja"}
    return OrderLine.objects.create(
        order=order,
        item_set=item,
        quantity=quantity,
        unit_price=unit_price,
        item_snapshot=snapshot,
    )


def create_order_shipping(
    order: Order,
    line: OrderLine,
    package_type: PackageType | None = None,
    price: Money | None = None,
    tracking_number: str = "",
    shipping_status: str = "PENDING",
    package_label: str = "PICKUP",
):
    return OrderShipping.objects.create(
        order=order,
        order_line=line,
        tracking_number=tracking_number,
        package_type=package_type,
        price=price,
        shipping_status=shipping_status,
        package_label=package_label,
    )


def create_item_reservation(
    item: ItemSet,
    tx: Transaction,
    line: OrderLine | None,
    user: User | None,
    quantity: int = 1,
    expires_at=None,
    released_at=None,
):
    if expires_at is None:
        expires_at = timezone.now() + timezone.timedelta(hours=1)
    return ItemReservation.objects.create(
        item_set=item,
        transaction=tx,
        order_line=line,
        user=user,
        quantity=quantity,
        expires_at=expires_at,
        released_at=released_at,
    )
