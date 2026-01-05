from __future__ import annotations
from typing import Optional
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from djmoney.money import Money
from django.conf import settings
from moneyed import Money as M

from customers.models import Customer
from orders.models import Order, OrderLine, OrderShipping
from orders.services import repositories as repo
from orders.services.exceptions import NotFound, Forbidden, Conflict, DomainError
from identity.models import User, SellerProfile
from payments.services.commands import cancel_active_payments_for_tx
from transactions.models import Transaction
from listings.models import ItemSet
from collections import defaultdict
from shipping.models import PackageType
from coupons.models import Coupon
from .printing import render_receipt_csv, render_receipt_pdf
from orders.services._party import make_customer_snapshot, snapshot_from_user, snapshot_from_customer

ONLINE_PAYMENT_METHODS = {"CREDIT_CARD","DEBIT_CARD","PAYPAL","BANK_TRANSFER","ONLINE_PAYMENT"}
OFFLINE_PAYMENT_METHODS = {"CASH","CASH_ON_DELIVERY"}


def _normalize_buyer_payment(method: str) -> str:
    if method in OFFLINE_PAYMENT_METHODS:
        raise Forbidden("Ta metoda płatności jest niedostępna w zakupie online. Wybierz płatność online.")
    if method not in ONLINE_PAYMENT_METHODS:
        raise DomainError("Nieprawidłowa metoda płatności.")
    return method


def _assert_item_buyable(item: ItemSet):
    if item.status != "AVAILABLE":
        raise Conflict("Ogłoszenie nie jest dostępne.")
    if item.listing_type != "BUY" or not item.allow_online_checkout:
        raise Forbidden("To ogłoszenie nie obsługuje zakupu online.")
    if not item.seller_profile_id:
        raise Conflict("Oferta nie ma przypisanego sprzedawcy.")


def _unit_price_for(item: ItemSet) -> Money:
    return item.price


def _label_for_package(pkg: PackageType | None) -> str:
    if not pkg:
        return "PICKUP"
    prov = getattr(pkg, "get_provider_display", None)
    provider = prov() if callable(prov) else (pkg.provider or "PACZKA")
    dim = (pkg.dimensions or "").strip()
    return f"{provider} {dim}".strip()


def _apply_coupon_to_amount(*, coupon: Optional[Coupon], amount: Decimal, currency: str) -> Decimal:
    if not coupon or not coupon.active:
        return amount
    from django.utils import timezone
    if coupon.expiration_date and coupon.expiration_date <= timezone.now():
        return amount
    if coupon.min_purchase_value and Decimal(str(amount)) < Decimal(str(coupon.min_purchase_value.amount)):
        return amount

    discount = Decimal("0")
    if coupon.discount_type == "PERCENTAGE":
        pct = Decimal(str(coupon.discount_value.amount if coupon.discount_value else 0))
        discount = (amount * pct / Decimal("100")).quantize(Decimal("0.01"))
    else:
        discount = Decimal(str(coupon.discount_value.amount if coupon.discount_value else 0))

    if coupon.max_discount_value:
        cap = Decimal(str(coupon.max_discount_value.amount))
        if discount > cap:
            discount = cap

    new_amount = amount - discount
    if new_amount < Decimal("0"):
        new_amount = Decimal("0")
    return new_amount


def _update_tx_expected_total(tx: Transaction):
    total = Decimal("0")
    currency = "PLN"
    for o in tx.orders.all():
        if o.purchase_cost:
            total += Decimal(str(o.purchase_cost.amount))
            currency = str(o.purchase_cost.currency)
    total_after = _apply_coupon_to_amount(coupon=tx.coupon, amount=total, currency=currency)

    type(tx).objects.filter(pk=tx.pk).update(
        expected_total_amount=total_after,
        expected_total_currency=currency,
        updated_at=timezone.now(),
    )
    tx.expected_total_amount = total_after
    tx.expected_total_currency = currency


@transaction.atomic
def checkout_single_item(*, buyer: Optional[User], item_public_id: str, quantity: int = 1,
                         payment_method: str = "ONLINE_PAYMENT", order_name: str = "", description: str = "") -> Order:
    item = repo.get_itemset_by_public_id(item_public_id)
    if not item:
        raise NotFound("Ogłoszenie nie istnieje.")
    if buyer:
        payment_method = _normalize_buyer_payment(payment_method)
    orders = checkout_cart(buyer=buyer, cart_items=[(item, quantity)], payment_method=payment_method)
    o = orders[0]
    if order_name:
        o.order_name = order_name
    if description:
        o.description = description
    o.save(update_fields=["order_name","description","updated_at"])
    return o


@transaction.atomic
def seller_add_line_shipping(
    *, order: Order, line: OrderLine, tracking_number: str,
    package_label: str = "", package_type: Optional[PackageType] = None,
    price: Optional[Money] = None
) -> OrderShipping:
    if order.order_status not in ("PENDING","COMPLETED"):
        raise Conflict("Nie można dodać wysyłki dla zamówienia w tym statusie.")

    if package_type is None:
        from djmoney.money import Money as _Money
        label = "PICKUP"
        eff_price = _Money(0, str(line.unit_price.currency))
    else:
        label = _label_for_package(package_type)
        eff_price = price if price is not None else package_type.price
        if eff_price is None:
            from djmoney.money import Money as _Money
            eff_price = _Money(0, str(line.unit_price.currency))

    ship = repo.add_line_shipping(
        order=order,
        line=line,
        tracking_number=tracking_number,
        package_label=label,
        package_type=package_type,
        price=eff_price,
    )

    order.recalc_totals(save=True)
    _update_tx_expected_total(order.transaction)
    return ship


@transaction.atomic
def set_shipping_status(*, shipping: OrderShipping, status: str) -> OrderShipping:
    allowed = {"PENDING","SHIPPED","DELIVERED","CANCELLED","RETURNED"}
    if status not in allowed:
        raise DomainError("Nieznany status wysyłki.")

    prev = shipping.shipping_status
    if prev == status:
        return shipping

    shipping.shipping_status = status
    shipping.save(update_fields=["shipping_status", "updated_at"])

    if status == "SHIPPED":
        order = shipping.order
        pkg_qs = order.shippings.exclude(package_label="PICKUP")
        if pkg_qs.exists():
            still_open = pkg_qs.exclude(shipping_status__in=["SHIPPED", "DELIVERED"]).exists()
            if not still_open:
                user = getattr(order, "buyer", None)
                if user and getattr(user, "email", ""):
                    try:
                        from orders.services.notifications import notify_order_shipped
                        notify_order_shipped(user=user, order=order)
                    except Exception:
                        pass

    return shipping


_VALID_ORDER_TRANSITIONS = {
    "PENDING": {"COMPLETED","CANCELLED","REFUNDED"},
    "COMPLETED": {"REFUNDED"},
    "CANCELLED": set(),
    "REFUNDED": set(),
}


@transaction.atomic
def set_order_status(*, order: Order, to_status: str) -> Order:
    if to_status not in {"PENDING","COMPLETED","CANCELLED","REFUNDED"}:
        raise DomainError("Nieprawidłowy status zamówienia.")
    allowed = _VALID_ORDER_TRANSITIONS.get(order.order_status, set())
    if to_status not in allowed and to_status != order.order_status:
        raise Conflict(f"Niedozwolona zmiana statusu z {order.order_status} na {to_status}.")
    order.order_status = to_status
    repo.save_order(order)
    return order


@transaction.atomic
def sync_orders_with_transaction(*, tx: Transaction) -> None:
    orders = list(tx.orders.select_related().prefetch_related("order_lines__item_set"))
    if not orders:
        return
    if tx.status == "PENDING":
        return

    to_status = {"COMPLETED": "COMPLETED", "CANCELLED": "CANCELLED", "REFUNDED": "REFUNDED"}.get(tx.status)
    if not to_status:
        return

    for order in orders:
        set_order_status(order=order, to_status=to_status)
        if to_status == "COMPLETED" and tx.type == "PURCHASE":
            for line in order.order_lines.select_related("item_set"):
                if not line.item_set_id:
                    continue
                item = line.item_set
                if item.stock_quantity is not None:
                    new_qty = max(0, int(item.stock_quantity) - int(line.quantity))
                    if new_qty != item.stock_quantity:
                        item.stock_quantity = new_qty
                        if new_qty == 0 and item.status == "AVAILABLE":
                            item.status = "SOLD"
                        item.save(update_fields=["stock_quantity","status","updated_at"])

    repo.release_all_reservations_for_tx(tx)
    _update_tx_expected_total(tx)


def _available_qty(item: ItemSet, *, exclude_tx_id: int | None = None) -> int:
    stock = int(item.stock_quantity or 0)
    reserved = repo.active_reserved_qty(item, exclude_tx_id=exclude_tx_id)
    return max(0, stock - reserved)

@transaction.atomic
def checkout_cart(*, buyer: User | None, cart_items: list[tuple[ItemSet, int]], payment_method: str = "CREDIT_CARD") -> list[Order]:
    if not cart_items:
        raise DomainError("Koszyk jest pusty.")

    if buyer:
        payment_method = _normalize_buyer_payment(payment_method)

    uniq_ids = []
    seen = set()
    for item, _qty in cart_items:
        if item.id not in seen:
            seen.add(item.id)
            uniq_ids.append(item.id)

    locked_list = repo.lock_itemsets_for_update(uniq_ids)
    locked_by_id = {it.id: it for it in locked_list}

    reserved_map = repo.active_reserved_qty_by_item_ids(uniq_ids)

    for item, qty in cart_items:
        it = locked_by_id.get(item.id)
        if it is None:
            raise NotFound("Ogłoszenie nie istnieje.")

        _assert_item_buyable(it)

        if qty <= 0:
            raise DomainError("Ilość musi być dodatnia.")

        stock = int(it.stock_quantity or 0)
        reserved = int(reserved_map.get(it.id, 0))
        available = max(0, stock - reserved)

        if qty > available:
            raise Conflict(f"Brak dostępnej ilości dla: {it.set_name}.")

    tx = Transaction.objects.create(user=buyer, type="PURCHASE", status="PENDING")

    cust_obj = None
    cust_snapshot = {}
    if buyer:
        cust_snapshot = snapshot_from_user(buyer)

    tx.customer = cust_obj
    tx.customer_snapshot = cust_snapshot
    tx.save(update_fields=["customer", "customer_snapshot", "updated_at"])

    by_seller: dict[int, list[tuple[ItemSet, int]]] = defaultdict(list)
    for item, qty in cart_items:
        it = locked_by_id[item.id]
        by_seller[it.seller_profile_id].append((it, qty))

    seller_ids = list(by_seller.keys())
    sellers = SellerProfile.objects.in_bulk(seller_ids)

    orders: list[Order] = []
    ttl = int(getattr(settings, "ORDERS_RESERVATION_TTL_MINUTES", 30)) * 60

    tx_total = Decimal("0")
    tx_currency = "PLN"

    for seller_id, rows in by_seller.items():
        seller = sellers.get(seller_id)
        if seller is None:
            raise Conflict("Oferta nie ma przypisanego sprzedawcy.")

        order = repo.create_order(
            tx=tx,
            seller=seller,
            buyer=buyer,
            fields={
                "order_name": f"Zamówienie u {seller.company_name}",
                "payment_method": payment_method,
                "purchase_date": timezone.now().date(),
                "order_status": "PENDING",
                "customer": cust_obj,
                "customer_snapshot": cust_snapshot,
            },
        )

        items_total = None
        from djmoney.money import Money as _Money

        for item, qty in rows:
            unit_price = _unit_price_for(item)
            line = repo.add_order_line(order=order, item=item, quantity=qty, unit_price=unit_price)
            repo.create_reservation(item=item, tx=tx, line=line, user=buyer, quantity=qty, ttl_seconds=ttl)

            OrderShipping.objects.create(
                order=order,
                order_line=line,
                tracking_number="",
                package_type=None,
                price=_Money(0, str(unit_price.currency)),
                package_label="PICKUP",
                shipping_status="PENDING",
            )

            lt = unit_price * int(qty)
            items_total = lt if items_total is None else (items_total + lt)

        cur = str(items_total.currency) if items_total is not None else "PLN"
        ship_total = _Money(0, cur)
        purchase_cost = (items_total or _Money(0, cur)) + ship_total

        order.items_total = items_total
        order.shipping_total = ship_total
        order.purchase_cost = purchase_cost
        order.save(update_fields=["items_total", "shipping_total", "purchase_cost", "updated_at"])

        orders.append(order)

        tx_total += Decimal(str(purchase_cost.amount))
        tx_currency = str(purchase_cost.currency)

    total_after = _apply_coupon_to_amount(coupon=tx.coupon, amount=tx_total, currency=tx_currency)
    type(tx).objects.filter(pk=tx.pk).update(
        expected_total_amount=total_after,
        expected_total_currency=tx_currency,
        updated_at=timezone.now(),
    )
    tx.expected_total_amount = total_after
    tx.expected_total_currency = tx_currency

    return orders

@transaction.atomic
def seller_offline_checkout_many(
    *,
    seller: SellerProfile,
    employee: User,
    lines: list[dict],
    payment_method: str = "CASH",
    customer_payload: dict | None = None,
    status: str = "COMPLETED",
) -> "Order":
    if not lines:
        raise DomainError("Dodaj co najmniej jedną pozycję.")

    req_rows: list[dict] = []
    pids: list[str] = []

    for row in lines:
        pid = str(row.get("item_public_id") or "").strip()
        if not pid:
            raise DomainError("Każda pozycja musi mieć item_public_id.")
        qty = int(row.get("quantity") or 1)
        if qty <= 0:
            raise DomainError("Ilość w pozycji musi wynosić co najmniej 1.")

        up = row.get("unit_price", None)
        if up is not None:
            if not isinstance(up, Money):
                raise DomainError("Nieprawidłowy format ceny za sztukę.")
            if up.amount < 0:
                raise DomainError("Cena za sztukę nie może być ujemna.")

        req_rows.append({"item_public_id": pid, "quantity": qty, "unit_price": up})
        pids.append(pid)

    items = list(
        ItemSet.objects.select_related("seller_profile")
        .filter(public_id__in=list(set(pids)))
    )
    found = {it.public_id for it in items}
    missing = [pid for pid in set(pids) if pid not in found]
    if missing:
        raise NotFound("Ogłoszenie nie istnieje.")

    locked = repo.lock_itemsets_for_update([it.id for it in items])
    by_pid = {it.public_id: it for it in locked}

    qty_total_by_pid: dict[str, int] = {}
    amount_total_by_pid: dict[str, Decimal] = {}
    currency_by_pid: dict[str, str] = {}

    for row in req_rows:
        pid = row["item_public_id"]
        qty = int(row["quantity"])
        item = by_pid[pid]

        if item.seller_profile_id != seller.id:
            raise Forbidden("Przedmiot nie należy do tego sprzedawcy.")

        if item.status not in ("AVAILABLE", "RESERVED"):
            raise Conflict("Ogłoszenie nie jest dostępne.")

        qty_total_by_pid[pid] = qty_total_by_pid.get(pid, 0) + qty

        up = row.get("unit_price", None)
        price = up if up is not None else _unit_price_for(item)

        if not isinstance(price, Money):
            raise DomainError("Nieprawidłowy format ceny za sztukę.")

        item_cur = str(getattr(item.price, "currency", "PLN"))
        price_cur = str(price.currency)
        if price_cur != item_cur:
            raise DomainError("Waluta ceny za sztukę musi być zgodna z walutą oferty.")

        currency_by_pid[pid] = price_cur
        amount_total_by_pid[pid] = amount_total_by_pid.get(pid, Decimal("0")) + (Decimal(str(price.amount)) * Decimal(qty))

    for pid, qty_sum in qty_total_by_pid.items():
        item = by_pid[pid]

        if item.stock_quantity is not None:
            if item.status == "AVAILABLE":
                avail = _available_qty(item)
            else:
                avail = int(item.stock_quantity or 0)

            if qty_sum > avail:
                raise Conflict("Brak dostępnej ilości (pozycja zarezerwowana lub niewystarczający stan).")

    cust_obj = None
    payload = customer_payload or {}
    cust_pid = (payload.get("customer_public_id") or "").strip()
    if cust_pid:
        cust_obj = Customer.objects.filter(public_id=cust_pid).first()

    cust_snap = make_customer_snapshot(
        first_name=payload.get("first_name", ""),
        last_name=payload.get("last_name", ""),
        email=payload.get("email", ""),
        phone=payload.get("phone", ""),
        address=payload.get("address") or {},
        doc_type=payload.get("document_type", ""),
        doc_number=payload.get("document_number", ""),
        birth_date=payload.get("birth_date"),
    )

    tx_kwargs = {"user": None, "type": "PURCHASE", "status": status}
    if hasattr(Transaction, "customer"):
        tx_kwargs["customer"] = cust_obj
    if hasattr(Transaction, "customer_snapshot"):
        tx_kwargs["customer_snapshot"] = cust_snap

    tx = Transaction.objects.create(**tx_kwargs)

    order = repo.create_order(
        tx=tx, seller=seller, buyer=None,
        fields={
            "order_name": f"Sprzedaż offline u {seller.company_name}",
            "payment_method": payment_method,
            "purchase_date": timezone.now().date(),
            "order_status": status,
            "customer": cust_obj,
            "customer_snapshot": cust_snap,
        }
    )

    for pid, qty_sum in qty_total_by_pid.items():
        item = by_pid[pid]
        total_amt = amount_total_by_pid.get(pid, Decimal("0"))
        cur = currency_by_pid.get(pid, "PLN")

        avg = (total_amt / Decimal(qty_sum)).quantize(Decimal("0.01"))
        unit_price = Money(avg, cur)

        repo.add_order_line(
            order=order,
            item=item,
            quantity=qty_sum,
            unit_price=unit_price,
        )

    order.recalc_totals(save=True)
    _update_tx_expected_total(tx)

    if status == "COMPLETED":
        for pid, qty_sum in qty_total_by_pid.items():
            item = by_pid[pid]
            if item.stock_quantity is None:
                continue
            new_qty = max(0, int(item.stock_quantity) - int(qty_sum))
            item.stock_quantity = new_qty
            if new_qty == 0 and item.status in ("AVAILABLE", "RESERVED"):
                item.status = "SOLD"
            item.save(update_fields=["stock_quantity", "status", "updated_at"])

    return order

@transaction.atomic
def seller_offline_checkout(
    *,
    seller: SellerProfile,
    employee: User,
    item_public_id: str,
    quantity: int = 1,
    payment_method: str = "CASH",
    customer_payload: dict | None = None,
    status: str = "COMPLETED",
) -> "Order":
    return seller_offline_checkout_many(
        seller=seller,
        employee=employee,
        lines=[{"item_public_id": item_public_id, "quantity": quantity}],
        payment_method=payment_method,
        customer_payload=customer_payload,
        status=status,
    )

@transaction.atomic
def seller_pawn_purchase(
    *,
    seller: SellerProfile,
    employee: User,
    lines: list[dict],
    customer_payload: dict | None = None,
    note: str = "",
    purchase_date=None,
    payment_method: str = "CASH",
    create_itemsets: bool = True,
) -> Order:
    cust_obj = None
    cust_snap = {}
    payload = customer_payload or {}
    cust_pid = payload.get("customer_public_id")
    if cust_pid:
        cust_obj = Customer.objects.filter(public_id=cust_pid).first()
    cust_snap = make_customer_snapshot(
        first_name=payload.get("first_name",""),
        last_name=payload.get("last_name",""),
        email=payload.get("email",""),
        phone=payload.get("phone",""),
        address=payload.get("address") or {},
        doc_type=payload.get("document_type",""),
        doc_number=payload.get("document_number",""),
        birth_date=payload.get("birth_date"),
    )

    tx = Transaction.objects.create(
        user=None, type="PAWN_PURCHASE", status="COMPLETED",
        customer=cust_obj, customer_snapshot=cust_snap,
    )

    order = repo.create_order(
        tx=tx, seller=seller, buyer=None,
        fields={
            "order_name": note or "Skup od klienta",
            "description": note or "",
            "purchase_date": purchase_date or timezone.now().date(),
            "payment_method": payment_method,
            "order_status": "COMPLETED",
            "customer": cust_obj,
            "customer_snapshot": cust_snap,
        }
    )

    created_itemsets: list[ItemSet] = []
    for row in lines:
        ol = repo.add_order_line_from_payload(
            order=order,
            title=row["title"],
            quantity=int(row.get("quantity", 1)),
            unit_price=row["unit_price"],
            attributes=row.get("attributes") or {},
            notes=row.get("notes",""),
        )
        if create_itemsets and row.get("item_type_public_id"):
            itype = repo.get_item_type_by_public_id(row["item_type_public_id"])
            if itype:
                listing_price = row.get("listing_price") or row["unit_price"]
                it = repo.create_itemset_from_pawn_line(
                    seller=seller,
                    title=row["title"],
                    description=row.get("notes",""),
                    attributes=row.get("attributes") or {},
                    listing_price=listing_price,
                    item_type=itype,
                )
                created_itemsets.append(it)

    order.recalc_totals(save=True)
    tx.expected_total_amount = order.purchase_cost.amount if order.purchase_cost else 0
    tx.expected_total_currency = str(order.purchase_cost.currency) if order.purchase_cost else "PLN"
    tx.save(update_fields=["expected_total_amount","expected_total_currency","updated_at"])
    return order


def build_receipt_csv(order: Order) -> bytes:
    return render_receipt_csv(order)


def build_receipt_pdf(order: Order) -> bytes:
    return render_receipt_pdf(order)


@transaction.atomic
def buyer_set_line_shipping(
    *, order: Order, line: OrderLine, mode: str, package_type=None
) -> tuple[OrderShipping, bool]:
    if order.buyer_id is None or line.order_id != order.id:
        raise Forbidden("Nieprawidłowe zamówienie.")
    if order.order_status != "PENDING" or order.transaction.status != "PENDING":
        raise Conflict("Nie można zmieniać wysyłki dla tego zamówienia.")

    payment_cancelled = cancel_active_payments_for_tx(
        tx=order.transaction,
        reason="buyer_changed_shipping"
    )

    ship = getattr(line, "shipping", None)
    if ship is None:
        from djmoney.money import Money as _Money
        ship = repo.add_line_shipping(
            order=order, line=line, package_label="PICKUP",
            price=_Money(0, str(line.unit_price.currency))
        )

    if mode == "PICKUP":
        from djmoney.money import Money as _Money
        ship.package_type = None
        ship.package_label = "PICKUP"
        ship.price = _Money(0, str(line.unit_price.currency))
        ship.save(update_fields=["package_type","package_label","price","updated_at"])
    else:
        pkg = package_type
        if not pkg:
            raise DomainError("Brak typu paczki.")
        item = line.item_set
        if not item:
            raise DomainError("Pozycja nie jest powiązana z ofertą.")

        from listings.models import ItemSetShipping
        link = ItemSetShipping.objects.filter(item_set=item, package_type=pkg).first()

        effective = None
        if link is not None and link.price_override is not None:
            effective = link.price_override
        else:
            if link is None and not item.fits_package(pkg):
                raise DomainError("Wymiary/masa nie mieszczą się w wybranej paczce.")
            effective = pkg.price

        if effective is None:
            raise DomainError("Brak ceny dla wybranej metody wysyłki.")

        ship.package_type = pkg
        ship.package_label = _label_for_package(pkg)
        ship.price = effective
        ship.save(update_fields=["package_type","package_label","price","updated_at"])

    order.recalc_totals(save=True)
    _update_tx_expected_total(order.transaction)

    return ship, payment_cancelled


def _addr_ok(addr: dict | None) -> bool:
    if not addr or not isinstance(addr, dict):
        return False
    required = ("first_name","last_name","street","house_number","city","postal_code","country")
    return all(bool(str(addr.get(k,"")).strip()) for k in required)


@transaction.atomic
def set_order_shipping_address(*, order: Order, address: dict) -> Order:
    order.shipping_address = dict(address or {})
    repo.save_order(order)
    return order


@transaction.atomic
def attach_customer_to_order(*, order: Order, customer: Customer, update_snapshot: bool = True) -> Order:
    order.customer = customer
    if update_snapshot:
        order.customer_snapshot = snapshot_from_customer(customer)
    repo.save_order(order)
    return order


@transaction.atomic
def detach_customer_from_order(*, order: Order) -> Order:
    order.customer = None
    repo.save_order(order)
    return order


@transaction.atomic
def ensure_customer_for_order(
    *,
    order: Order,
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    phone: str = "",
    address: dict | None = None,
    document_type: str = "",
    document_number: str = "",
    birth_date = None,
    allow_update_email: bool = False,
    allow_update_phone: bool = False,
):
    email = (email or "").strip()
    phone = (phone or "").strip()

    c_by_email = Customer.objects.filter(email__iexact=email).first() if email else None
    c_by_phone = Customer.objects.filter(phone=phone).first() if phone else None

    cand = None
    if c_by_email and c_by_phone:
        if c_by_email.id != c_by_phone.id:
            return {"result": "conflict", "candidates": [
                {"public_id": c_by_email.public_id, "first_name": c_by_email.first_name, "last_name": c_by_email.last_name,
                 "email": c_by_email.email, "phone": c_by_email.phone, "city": c_by_email.city},
                {"public_id": c_by_phone.public_id, "first_name": c_by_phone.first_name, "last_name": c_by_phone.last_name,
                 "email": c_by_phone.email, "phone": c_by_phone.phone, "city": c_by_phone.city},
            ]}
        cand = c_by_email
    else:
        cand = c_by_email or c_by_phone

    if cand:
        dirty = False
        if not cand.first_name and first_name:
            cand.first_name = first_name; dirty = True
        if not cand.last_name and last_name:
            cand.last_name = last_name; dirty = True
        if allow_update_email and email and cand.email.lower() != email.lower():
            cand.email = email; dirty = True
        if allow_update_phone and phone and cand.phone != phone:
            cand.phone = phone; dirty = True

        if address:
            if not cand.address_line1 and address.get("line1"): cand.address_line1 = address["line1"]; dirty = True
            if not cand.address_line2 and address.get("line2"): cand.address_line2 = address["line2"]; dirty = True
            if not cand.postal_code and address.get("postal_code"): cand.postal_code = address["postal_code"]; dirty = True
            if not cand.city and address.get("city"): cand.city = address["city"]; dirty = True
            if not cand.country and address.get("country"): cand.country = address["country"]; dirty = True
        if not cand.document_type and document_type: cand.document_type = document_type; dirty = True
        if not cand.document_number and document_number: cand.document_number = document_number; dirty = True
        if not cand.birth_date and birth_date: cand.birth_date = birth_date; dirty = True
        if dirty:
            cand.save()

        attach_customer_to_order(order=order, customer=cand, update_snapshot=True)
        return {"result": "attached", "customer_public_id": cand.public_id}

    newc = Customer.objects.create(
        first_name=first_name, last_name=last_name, email=email, phone=phone,
        address_line1=(address or {}).get("line1",""),
        address_line2=(address or {}).get("line2",""),
        postal_code=(address or {}).get("postal_code",""),
        city=(address or {}).get("city",""),
        country=(address or {}).get("country",""),
        document_type=document_type, document_number=document_number, birth_date=birth_date,
    )
    attach_customer_to_order(order=order, customer=newc, update_snapshot=True)
    return {"result": "created", "customer_public_id": newc.public_id}
