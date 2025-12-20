from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from customers.models import Customer
from orders.models import Order, OrderShipping, ItemReservation
from orders.services import commands
from orders.services.exceptions import Forbidden, Conflict, DomainError
from orders.services.repositories import active_reserved_qty
from transactions.models import Transaction
from listings.models import ItemSetShipping
from .factories import (
    create_user,
    create_seller_profile,
    create_item_type,
    create_itemset,
    create_package_type,
    create_customer,
    create_transaction,
    create_order,
    create_order_line,
    create_order_shipping,
    create_item_reservation,
)


class CheckoutCommandsTests(TestCase):
    def setUp(self):
        self.buyer = create_user(email="buyer@example.com")
        self.owner = create_user(email="owner@example.com")
        self.seller = create_seller_profile(owner=self.owner, slug="shop-checkout")
        self.item_type = create_item_type()
        self.item = create_itemset(self.seller, self.item_type, price=Money(100, "PLN"), stock_quantity=5)

    def test_checkout_single_item_creates_order_and_reservation(self):
        order = commands.checkout_single_item(
            buyer=self.buyer,
            item_public_id=self.item.public_id,
            quantity=2,
            payment_method="CREDIT_CARD",
            order_name="My order",
            description="Test desc",
        )
        self.assertIsInstance(order, Order)
        self.assertEqual(order.buyer, self.buyer)
        self.assertEqual(order.seller_profile, self.seller)
        self.assertEqual(order.order_name, "My order")
        self.assertEqual(order.transaction.type, "PURCHASE")
        self.assertEqual(order.order_lines.count(), 1)
        line = order.order_lines.first()
        self.assertEqual(line.quantity, 2)
        self.assertEqual(active_reserved_qty(self.item), 2)
        self.assertEqual(order.purchase_cost.amount, Decimal("200.00"))

    def test_checkout_single_item_forbids_offline_payment_for_buyer(self):
        with self.assertRaises(Forbidden):
            commands.checkout_single_item(
                buyer=self.buyer,
                item_public_id=self.item.public_id,
                quantity=1,
                payment_method="CASH",
            )

    def test_checkout_cart_groups_by_seller_and_sets_expected_total(self):
        seller2_owner = create_user(email="owner2@example.com")
        seller2 = create_seller_profile(owner=seller2_owner, slug="shop-2")
        item2 = create_itemset(seller2, self.item_type, price=Money(50, "PLN"), stock_quantity=3)
        orders = commands.checkout_cart(
            buyer=self.buyer,
            cart_items=[(self.item, 1), (item2, 2)],
            payment_method="CREDIT_CARD",
        )
        self.assertEqual(len(orders), 2)
        tx = orders[0].transaction
        amounts = [o.purchase_cost.amount for o in orders if o.purchase_cost]
        self.assertEqual(sum(amounts), tx.expected_total_amount)


class ShippingCommandsTests(TestCase):
    def setUp(self):
        self.buyer = create_user(email="buyer-shipping@example.com")
        self.owner = create_user(email="owner-shipping@example.com")
        self.seller = create_seller_profile(owner=self.owner, slug="shop-shipping")
        self.item_type = create_item_type()
        self.item = create_itemset(self.seller, self.item_type, price=Money(80, "PLN"), stock_quantity=2)
        self.tx = create_transaction(user=self.buyer)
        self.order = create_order(self.tx, self.seller, buyer=self.buyer)
        self.line = create_order_line(self.order, self.item, quantity=1, unit_price=self.item.price)
        self.order.recalc_totals(save=True)

    def test_seller_add_line_shipping_pickup_sets_zero_price(self):
        ship = commands.seller_add_line_shipping(
            order=self.order,
            line=self.line,
            tracking_number="TRK1",
            package_type=None,
            price=None,
        )
        self.assertIsInstance(ship, OrderShipping)
        self.assertIsNone(ship.package_type)
        self.assertEqual(ship.package_label, "PICKUP")
        self.assertEqual(ship.price, Money(0, "PLN"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.shipping_total, Money(0, "PLN"))
        self.assertIsNotNone(self.order.purchase_cost)
        self.assertEqual(self.order.transaction.expected_total_amount, self.order.purchase_cost.amount)

    def test_seller_add_line_shipping_with_package_uses_label_and_price(self):
        pkg = create_package_type(provider="INPOST", dimensions="A", price=Money(15, "PLN"))
        ship = commands.seller_add_line_shipping(
            order=self.order,
            line=self.line,
            tracking_number="TRK2",
            package_type=pkg,
            price=None,
        )
        self.assertEqual(ship.package_type, pkg)
        self.assertEqual(ship.package_label, "InPost A")
        self.assertEqual(ship.price, pkg.price)
        self.order.refresh_from_db()
        self.assertEqual(self.order.shipping_total, pkg.price)
        self.assertEqual(self.order.transaction.expected_total_amount, self.order.purchase_cost.amount)

    @patch("orders.services.notifications.notify_order_shipped")
    def test_set_shipping_status_sends_notification_when_all_non_pickup_shipped(self, notify_mock):
        pkg = create_package_type(provider="INPOST", dimensions="B", price=Money(10, "PLN"))
        line2 = create_order_line(self.order, self.item, quantity=1, unit_price=self.item.price)
        ship1 = create_order_shipping(self.order, self.line, package_type=pkg, price=pkg.price, package_label="X")
        ship2 = create_order_shipping(self.order, line2, package_type=pkg, price=pkg.price, package_label="Y")
        commands.set_shipping_status(shipping=ship1, status="SHIPPED")
        notify_mock.assert_not_called()
        commands.set_shipping_status(shipping=ship2, status="SHIPPED")
        notify_mock.assert_called_once()

    def test_buyer_set_line_shipping_pickup_and_package(self):
        pkg = create_package_type(provider="INPOST", dimensions="C", price=Money(12, "PLN"))
        with patch("orders.services.commands.cancel_active_payments_for_tx", return_value=True) as cancel_mock:
            ship, cancelled = commands.buyer_set_line_shipping(order=self.order, line=self.line, mode="PICKUP", package_type=None)
        self.assertTrue(cancelled)
        self.assertEqual(ship.package_label, "PICKUP")
        self.assertIsNone(ship.package_type)
        self.assertEqual(ship.price, Money(0, "PLN"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.shipping_total, Money(0, "PLN"))
        cancel_mock.assert_called_once()
        ItemSetShipping.objects.create(
            item_set=self.item,
            package_type=pkg,
            price_override=Money(9, "PLN"),
        )
        with patch("orders.services.commands.cancel_active_payments_for_tx", return_value=False):
            ship2, cancelled2 = commands.buyer_set_line_shipping(order=self.order, line=self.line, mode="PACKAGE", package_type=pkg)
        self.assertFalse(cancelled2)
        self.assertEqual(ship2.package_type, pkg)
        self.assertEqual(ship2.price, Money(9, "PLN"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.shipping_total, Money(9, "PLN"))

    def test_buyer_set_line_shipping_raises_for_missing_package_in_package_mode(self):
        with self.assertRaises(DomainError):
            commands.buyer_set_line_shipping(order=self.order, line=self.line, mode="PACKAGE", package_type=None)

    def test_set_order_shipping_address_sets_snapshot(self):
        address = {
            "first_name": "Jan",
            "last_name": "Kowalski",
            "street": "Ulica",
            "house_number": "1",
            "city": "Miasto",
            "postal_code": "00-001",
            "country": "PL",
        }
        commands.set_order_shipping_address(order=self.order, address=address)
        self.order.refresh_from_db()
        self.assertEqual(self.order.shipping_address["first_name"], "Jan")
        self.assertEqual(self.order.shipping_address["postal_code"], "00-001")


class StatusAndSyncCommandsTests(TestCase):
    def setUp(self):
        self.buyer = create_user(email="buyer-status@example.com")
        self.owner = create_user(email="owner-status@example.com")
        self.seller = create_seller_profile(owner=self.owner, slug="shop-status")
        self.item_type = create_item_type()
        self.item = create_itemset(self.seller, self.item_type, price=Money(50, "PLN"), stock_quantity=5)
        self.tx = create_transaction(user=self.buyer, status="PENDING")
        self.order = create_order(self.tx, self.seller, buyer=self.buyer, status="PENDING")
        self.line = create_order_line(self.order, self.item, quantity=3, unit_price=self.item.price)
        self.order.recalc_totals(save=True)

    def test_set_order_status_valid_transition(self):
        commands.set_order_status(order=self.order, to_status="COMPLETED")
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, "COMPLETED")

    def test_set_order_status_invalid_transition_raises_conflict(self):
        self.order.order_status = "COMPLETED"
        self.order.save(update_fields=["order_status"])
        with self.assertRaises(Conflict):
            commands.set_order_status(order=self.order, to_status="PENDING")

    def test_sync_orders_with_transaction_updates_status_and_stock(self):
        commands.sync_orders_with_transaction(tx=self.tx)
        self.order.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.order.order_status, "PENDING")
        self.assertEqual(self.item.stock_quantity, 5)

        self.tx.status = "COMPLETED"
        self.tx.save(update_fields=["status"])

        self.order.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.order.order_status, "COMPLETED")
        self.assertEqual(self.item.stock_quantity, 2)
        self.assertEqual(self.item.status, "AVAILABLE")

        self.tx2 = create_transaction(user=self.buyer, status="COMPLETED")
        order2 = create_order(self.tx2, self.seller, buyer=self.buyer, status="PENDING")
        line2 = create_order_line(order2, self.item, quantity=2, unit_price=self.item.price)
        order2.recalc_totals(save=True)
        commands.sync_orders_with_transaction(tx=self.tx2)

        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_quantity, 0)
        self.assertEqual(self.item.status, "SOLD")


class CustomerCommandsTests(TestCase):
    def setUp(self):
        self.buyer = create_user(email="buyer-cust@example.com")
        self.owner = create_user(email="owner-cust@example.com")
        self.seller = create_seller_profile(owner=self.owner, slug="shop-cust")
        self.item_type = create_item_type()
        self.item = create_itemset(self.seller, self.item_type, price=Money(30, "PLN"), stock_quantity=1)
        self.tx = create_transaction(user=self.buyer)
        self.order = create_order(self.tx, self.seller, buyer=self.buyer)

    def test_attach_and_detach_customer(self):
        c = create_customer(email="attach@example.com")
        commands.attach_customer_to_order(order=self.order, customer=c, update_snapshot=True)
        self.order.refresh_from_db()
        self.assertEqual(self.order.customer, c)
        self.assertEqual(self.order.customer_snapshot.get("email"), "attach@example.com")
        commands.detach_customer_from_order(order=self.order)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.customer)

    def test_ensure_customer_created_when_not_exists(self):
        res = commands.ensure_customer_for_order(
            order=self.order,
            first_name="Nowy",
            last_name="Klient",
            email="new@example.com",
            phone="111222333",
            address={"line1": "Ulica", "postal_code": "00-001", "city": "Miasto", "country": "PL"},
            document_type="ID",
            document_number="ABC123",
        )
        self.assertIn(res["result"], ("created", "attached"))
        self.assertTrue(res.get("customer_public_id"))
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.customer)
        self.assertEqual(self.order.customer.email, "new@example.com")

    def test_ensure_customer_conflict_returns_candidates(self):
        c1 = Customer.objects.create(first_name="Jan", last_name="A", email="conf@example.com")
        c2 = Customer.objects.create(first_name="Jan", last_name="B", phone="999888777", email="jan.b@example.com")
        res = commands.ensure_customer_for_order(
            order=self.order,
            first_name="X",
            last_name="Y",
            email="conf@example.com",
            phone="999888777",
        )
        self.assertEqual(res["result"], "conflict")
        self.assertEqual(len(res["candidates"]), 2)


class OfflineCheckoutCommandsTests(TestCase):
    def setUp(self):
        self.employee = create_user(email="employee-offline@example.com")
        self.owner = create_user(email="owner-offline@example.com")
        self.seller = create_seller_profile(owner=self.owner, slug="shop-offline")
        self.item_type = create_item_type()
        self.item = create_itemset(self.seller, self.item_type, price=Money(40, "PLN"), stock_quantity=4, status="AVAILABLE")
        self.customer = create_customer(email="offline@example.com")

    def test_seller_offline_checkout_reduces_stock_and_completes(self):
        order = commands.seller_offline_checkout(
            seller=self.seller,
            employee=self.employee,
            item_public_id=self.item.public_id,
            quantity=2,
            payment_method="CASH",
            customer_payload={
                "customer_public_id": self.customer.public_id,
                "first_name": self.customer.first_name,
                "last_name": self.customer.last_name,
                "email": self.customer.email,
            },
            status="COMPLETED",
        )
        self.assertEqual(order.order_status, "COMPLETED")
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_quantity, 2)

    def test_seller_offline_checkout_raises_when_item_not_belongs_to_seller(self):
        other_owner = create_user(email="other-owner@example.com")
        other_seller = create_seller_profile(owner=other_owner, slug="shop-other")
        item_other = create_itemset(other_seller, self.item_type, price=Money(10, "PLN"), stock_quantity=1)
        with self.assertRaises(Forbidden):
            commands.seller_offline_checkout(
                seller=self.seller,
                employee=self.employee,
                item_public_id=item_other.public_id,
                quantity=1,
                payment_method="CASH",
            )

    def test_seller_offline_checkout_raises_when_quantity_exceeds_available(self):
        with self.assertRaises(Conflict):
            commands.seller_offline_checkout(
                seller=self.seller,
                employee=self.employee,
                item_public_id=self.item.public_id,
                quantity=10,
                payment_method="CASH",
            )


class PawnPurchaseCommandsTests(TestCase):
    def setUp(self):
        self.employee = create_user(email="employee-pawn@example.com")
        self.owner = create_user(email="owner-pawn@example.com")
        self.seller = create_seller_profile(owner=self.owner, slug="shop-pawn")
        self.item_type = create_item_type()

    def test_seller_pawn_purchase_creates_completed_order(self):
        order = commands.seller_pawn_purchase(
            seller=self.seller,
            employee=self.employee,
            lines=[
                {
                    "title": "Telefon",
                    "quantity": 1,
                    "unit_price": Money(100, "PLN"),
                    "listing_price": Money(200, "PLN"),
                    "notes": "sprawny",
                    "attributes": {"color": "black"},
                    "item_type_public_id": self.item_type.public_id,
                }
            ],
            customer_payload={
                "first_name": "Jan",
                "last_name": "Klient",
                "email": "pawn@example.com",
            },
            note="Skup",
            payment_method="CASH",
            create_itemsets=True,
        )
        self.assertEqual(order.order_status, "COMPLETED")
        self.assertEqual(order.transaction.type, "PAWN_PURCHASE")
        self.assertEqual(order.order_lines.count(), 1)
        line = order.order_lines.first()
        self.assertIsNone(line.item_set)
        self.assertEqual(line.item_snapshot.get("title"), "Telefon")
        self.assertIsNotNone(order.purchase_cost)
        self.assertEqual(order.transaction.expected_total_amount, order.purchase_cost.amount)
