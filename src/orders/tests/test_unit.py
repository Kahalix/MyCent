from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from djmoney.money import Money

from orders.services import commands
from orders.services.exceptions import NotFound, Forbidden, Conflict, DomainError


class OrdersHelpersUnitTests(SimpleTestCase):
    def test_normalize_buyer_payment_rejects_offline(self):
        with self.assertRaises(Forbidden):
            commands._normalize_buyer_payment("CASH")

    def test_normalize_buyer_payment_rejects_unknown(self):
        with self.assertRaises(DomainError):
            commands._normalize_buyer_payment("BITCOIN")

    def test_normalize_buyer_payment_accepts_online(self):
        self.assertEqual(commands._normalize_buyer_payment("CREDIT_CARD"), "CREDIT_CARD")

    def test_assert_item_buyable_rejects_not_available(self):
        item = SimpleNamespace(
            status="SOLD",
            listing_type="BUY",
            allow_online_checkout=True,
            seller_profile_id=1,
        )
        with self.assertRaises(Conflict):
            commands._assert_item_buyable(item)

    def test_assert_item_buyable_rejects_not_buy_or_no_checkout(self):
        item = SimpleNamespace(
            status="AVAILABLE",
            listing_type="SELL",
            allow_online_checkout=True,
            seller_profile_id=1,
        )
        with self.assertRaises(Forbidden):
            commands._assert_item_buyable(item)

        item2 = SimpleNamespace(
            status="AVAILABLE",
            listing_type="BUY",
            allow_online_checkout=False,
            seller_profile_id=1,
        )
        with self.assertRaises(Forbidden):
            commands._assert_item_buyable(item2)

    def test_assert_item_buyable_requires_seller(self):
        item = SimpleNamespace(
            status="AVAILABLE",
            listing_type="BUY",
            allow_online_checkout=True,
            seller_profile_id=None,
        )
        with self.assertRaises(Conflict):
            commands._assert_item_buyable(item)


class CheckoutCartUnitTests(SimpleTestCase):
    def _mk_item(
        self,
        *,
        id: int,
        public_id: str,
        seller_profile_id: int,
        set_name: str = "Item",
        price: Money = Money(100, "PLN"),
        stock_quantity: int = 5,
        status: str = "AVAILABLE",
        listing_type: str = "BUY",
        allow_online_checkout: bool = True,
    ):
        return SimpleNamespace(
            id=id,
            public_id=public_id,
            seller_profile_id=seller_profile_id,
            set_name=set_name,
            price=price,
            stock_quantity=stock_quantity,
            status=status,
            listing_type=listing_type,
            allow_online_checkout=allow_online_checkout,
        )

    def _mk_tx_class(self):
        class DummyTx:
            objects = MagicMock()

            def __init__(self):
                self.pk = 123
                self.id = 123
                self.customer = None
                self.customer_snapshot = {}
                self.coupon = None
                self.expected_total_amount = None
                self.expected_total_currency = None
                self.save = MagicMock()

        DummyTx.objects.filter.return_value.update = MagicMock()
        return DummyTx

    def _mk_order(self, tx, seller, buyer):
        o = SimpleNamespace(
            id=1,
            transaction=tx,
            seller_profile=seller,
            buyer=buyer,
            items_total=None,
            shipping_total=None,
            purchase_cost=None,
            save=MagicMock(),
        )
        return o

    @override_settings(ORDERS_RESERVATION_TTL_MINUTES=30)
    @patch("orders.services.commands.timezone")
    @patch("orders.services.commands.OrderShipping")
    @patch("orders.services.commands.repo")
    @patch("orders.services.commands.SellerProfile")
    @patch("orders.services.commands.Transaction")
    def test_checkout_cart_creates_orders_lines_reservations_and_default_shipping(
        self,
        mock_tx_model,
        mock_seller_model,
        mock_repo,
        mock_ordershipping_model,
        mock_tz,
    ):
        DummyTx = self._mk_tx_class()
        tx = DummyTx()
        mock_tx_model.objects.create.return_value = tx

        seller1 = SimpleNamespace(id=1, company_name="Shop 1")
        seller2 = SimpleNamespace(id=2, company_name="Shop 2")
        mock_seller_model.objects.in_bulk.return_value = {1: seller1, 2: seller2}

        buyer = SimpleNamespace(id=10, email="buyer@example.com")

        it1 = self._mk_item(id=11, public_id="I1", seller_profile_id=1, price=Money(100, "PLN"), stock_quantity=5, set_name="A")
        it2 = self._mk_item(id=22, public_id="I2", seller_profile_id=2, price=Money(50, "PLN"), stock_quantity=3, set_name="B")

        mock_repo.lock_itemsets_for_update.return_value = [it1, it2]
        mock_repo.active_reserved_qty_by_item_ids.return_value = {11: 0, 22: 1}

        orders_created = []

        def _create_order(*, tx, seller, buyer, fields):
            o = self._mk_order(tx, seller, buyer)
            orders_created.append((seller.id, o, fields))
            return o

        mock_repo.create_order.side_effect = _create_order

        def _add_order_line(*, order, item, quantity, unit_price):
            return SimpleNamespace(
                id=100 + item.id,
                public_id=f"L{item.id}",
                order_id=getattr(order, "id", 1),
                item_set=item,
                item_set_id=item.id,
                quantity=int(quantity),
                unit_price=unit_price,
            )

        mock_repo.add_order_line.side_effect = _add_order_line
        mock_repo.create_reservation.return_value = SimpleNamespace(id=999)

        mock_ordershipping_model.objects.create.return_value = SimpleNamespace(id=555)
        mock_tz.now.return_value = SimpleNamespace(date=lambda: SimpleNamespace(), isoformat=lambda: "x")

        out = commands.checkout_cart.__wrapped__(
            buyer=buyer,
            cart_items=[(it1, 2), (it2, 2)],
            payment_method="CREDIT_CARD",
        )

        self.assertEqual(len(out), 2)
        self.assertEqual(mock_repo.create_order.call_count, 2)
        self.assertEqual(mock_repo.add_order_line.call_count, 2)
        self.assertEqual(mock_repo.create_reservation.call_count, 2)
        self.assertEqual(mock_ordershipping_model.objects.create.call_count, 2)

        self.assertEqual(tx.expected_total_amount, Decimal("300.00"))
        self.assertEqual(tx.expected_total_currency, "PLN")
        DummyTx.objects.filter.return_value.update.assert_called_once()

        seller_ids = [sid for sid, _o, _f in orders_created]
        self.assertCountEqual(seller_ids, [1, 2])

    @patch("orders.services.commands.repo")
    def test_checkout_cart_rejects_empty_cart(self, mock_repo):
        with self.assertRaises(DomainError):
            commands.checkout_cart.__wrapped__(buyer=None, cart_items=[], payment_method="CREDIT_CARD")

        mock_repo.lock_itemsets_for_update.assert_not_called()

    @patch("orders.services.commands.repo")
    def test_checkout_cart_rejects_offline_payment_for_buyer(self, mock_repo):
        buyer = SimpleNamespace(id=1, email="b@example.com")
        it = self._mk_item(id=1, public_id="I1", seller_profile_id=1)

        with self.assertRaises(Forbidden):
            commands.checkout_cart.__wrapped__(buyer=buyer, cart_items=[(it, 1)], payment_method="CASH")

        mock_repo.lock_itemsets_for_update.assert_not_called()

    @patch("orders.services.commands.repo")
    def test_checkout_cart_rejects_unknown_payment_for_buyer(self, mock_repo):
        buyer = SimpleNamespace(id=1, email="b@example.com")
        it = self._mk_item(id=1, public_id="I1", seller_profile_id=1)

        with self.assertRaises(DomainError):
            commands.checkout_cart.__wrapped__(buyer=buyer, cart_items=[(it, 1)], payment_method="BLIK")

        mock_repo.lock_itemsets_for_update.assert_not_called()

    @patch("orders.services.commands.repo")
    def test_checkout_cart_rejects_non_positive_quantity(self, mock_repo):
        buyer = SimpleNamespace(id=1, email="b@example.com")
        it = self._mk_item(id=1, public_id="I1", seller_profile_id=1)
        mock_repo.lock_itemsets_for_update.return_value = [it]
        mock_repo.active_reserved_qty_by_item_ids.return_value = {1: 0}

        with self.assertRaises(DomainError):
            commands.checkout_cart.__wrapped__(buyer=buyer, cart_items=[(it, 0)], payment_method="CREDIT_CARD")

    @patch("orders.services.commands.repo")
    def test_checkout_cart_rejects_insufficient_stock_after_reservations(self, mock_repo):
        buyer = SimpleNamespace(id=1, email="b@example.com")
        it = self._mk_item(id=1, public_id="I1", seller_profile_id=1, stock_quantity=2, set_name="AAA")
        mock_repo.lock_itemsets_for_update.return_value = [it]
        mock_repo.active_reserved_qty_by_item_ids.return_value = {1: 2}

        with self.assertRaises(Conflict):
            commands.checkout_cart.__wrapped__(buyer=buyer, cart_items=[(it, 1)], payment_method="CREDIT_CARD")

    @override_settings(ORDERS_RESERVATION_TTL_MINUTES=30)
    @patch("orders.services.commands.repo")
    @patch("orders.services.commands.SellerProfile")
    @patch("orders.services.commands.Transaction")
    def test_checkout_cart_rejects_missing_seller_profile(self, mock_tx_model, mock_seller_model, mock_repo):
        DummyTx = self._mk_tx_class()
        tx = DummyTx()
        mock_tx_model.objects.create.return_value = tx

        it = self._mk_item(id=1, public_id="I1", seller_profile_id=999)
        mock_repo.lock_itemsets_for_update.return_value = [it]
        mock_repo.active_reserved_qty_by_item_ids.return_value = {1: 0}
        mock_seller_model.objects.in_bulk.return_value = {}

        with self.assertRaises(Conflict):
            commands.checkout_cart.__wrapped__(buyer=None, cart_items=[(it, 1)], payment_method="CREDIT_CARD")
