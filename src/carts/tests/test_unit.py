from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from carts.services import commands
from carts.services.exceptions import DomainError, NotFound, Conflict


class CartsUnitTests(SimpleTestCase):
    def _mk_item(self, *, id: int = 1, public_id: str = "I1"):
        return SimpleNamespace(id=id, public_id=public_id)

    def _mk_cart(self):
        return SimpleNamespace(
            id=1,
            public_id="C1",
            status="ACTIVE",
            save=MagicMock(),
            items=MagicMock(),
        )

    def _mk_row(self, *, item, qty: int):
        return SimpleNamespace(
            id=1,
            item_set=item,
            item_set_id=item.id,
            quantity=qty,
        )

    @patch("carts.services.commands._available_qty")
    @patch("carts.services.commands._assert_item_buyable")
    @patch("carts.services.commands.repo")
    @patch("carts.services.commands._get_item_by_public_id")
    def test_add_to_cart_adds_when_available(
        self,
        mock_get_item,
        mock_repo,
        mock_assert_buyable,
        mock_avail,
    ):
        user = SimpleNamespace(id=10, email="u@example.com")
        item = self._mk_item(id=1, public_id="I1")
        cart = self._mk_cart()
        row = self._mk_row(item=item, qty=2)

        mock_get_item.return_value = item
        mock_avail.return_value = 5
        mock_repo.get_or_create_active_cart.return_value = cart
        mock_repo.inc_item_qty.return_value = row

        out = commands.add_to_cart.__wrapped__(user=user, item_public_id="I1", quantity=2)

        self.assertIs(out, row)
        mock_assert_buyable.assert_called_once_with(item)
        mock_repo.inc_item_qty.assert_called_once_with(cart=cart, item=item, qty=2)

    @patch("carts.services.commands._get_item_by_public_id")
    def test_add_to_cart_rejects_non_positive_qty(self, mock_get_item):
        user = SimpleNamespace(id=10)
        with self.assertRaises(DomainError):
            commands.add_to_cart.__wrapped__(user=user, item_public_id="I1", quantity=0)
        mock_get_item.assert_not_called()

    @patch("carts.services.commands._get_item_by_public_id")
    def test_add_to_cart_not_found(self, mock_get_item):
        user = SimpleNamespace(id=10)
        mock_get_item.return_value = None
        with self.assertRaises(NotFound):
            commands.add_to_cart.__wrapped__(user=user, item_public_id="X", quantity=1)

    @patch("carts.services.commands._available_qty")
    @patch("carts.services.commands._assert_item_buyable")
    @patch("carts.services.commands.repo")
    @patch("carts.services.commands._get_item_by_public_id")
    def test_add_to_cart_rejects_when_requested_exceeds_available(
        self,
        mock_get_item,
        mock_repo,
        mock_assert_buyable,
        mock_avail,
    ):
        user = SimpleNamespace(id=10)
        item = self._mk_item(id=1, public_id="I1")
        mock_get_item.return_value = item
        mock_avail.return_value = 1
        mock_repo.get_or_create_active_cart.return_value = self._mk_cart()
        with self.assertRaises(Conflict):
            commands.add_to_cart.__wrapped__(user=user, item_public_id="I1", quantity=2)
        mock_repo.inc_item_qty.assert_not_called()

    @patch("carts.services.commands._available_qty")
    @patch("carts.services.commands._assert_item_buyable")
    @patch("carts.services.commands.repo")
    @patch("carts.services.commands._get_item_by_public_id")
    def test_add_to_cart_rejects_when_resulting_row_qty_exceeds_available(
        self,
        mock_get_item,
        mock_repo,
        mock_assert_buyable,
        mock_avail,
    ):
        user = SimpleNamespace(id=10)
        item = self._mk_item(id=1, public_id="I1")
        cart = self._mk_cart()
        row = self._mk_row(item=item, qty=6)

        mock_get_item.return_value = item
        mock_avail.return_value = 5
        mock_repo.get_or_create_active_cart.return_value = cart
        mock_repo.inc_item_qty.return_value = row

        with self.assertRaises(Conflict):
            commands.add_to_cart.__wrapped__(user=user, item_public_id="I1", quantity=2)

    @patch("carts.services.commands.repo")
    @patch("carts.services.commands._get_item_by_public_id")
    def test_set_quantity_zero_removes_without_buyability_check(self, mock_get_item, mock_repo):
        user = SimpleNamespace(id=10)
        item = self._mk_item(id=1, public_id="I1")
        cart = self._mk_cart()

        mock_get_item.return_value = item
        mock_repo.get_or_create_active_cart.return_value = cart
        mock_repo.set_item_qty.return_value = SimpleNamespace(quantity=0)

        out = commands.set_quantity.__wrapped__(user=user, item_public_id="I1", quantity=0)
        self.assertEqual(out.quantity, 0)
        mock_repo.set_item_qty.assert_called_once_with(cart=cart, item=item, qty=0)

    @patch("carts.services.commands._available_qty")
    @patch("carts.services.commands._assert_item_buyable")
    @patch("carts.services.commands.repo")
    @patch("carts.services.commands._get_item_by_public_id")
    def test_set_quantity_checks_buyability_and_stock_for_positive_qty(
        self,
        mock_get_item,
        mock_repo,
        mock_assert_buyable,
        mock_avail,
    ):
        user = SimpleNamespace(id=10)
        item = self._mk_item(id=1, public_id="I1")
        cart = self._mk_cart()

        mock_get_item.return_value = item
        mock_repo.get_or_create_active_cart.return_value = cart
        mock_repo.current_qty.return_value = 1
        mock_avail.return_value = 3
        mock_repo.set_item_qty.return_value = SimpleNamespace(quantity=4)

        out = commands.set_quantity.__wrapped__(user=user, item_public_id="I1", quantity=4)
        self.assertEqual(out.quantity, 4)

        mock_assert_buyable.assert_called_once_with(item)
        mock_repo.set_item_qty.assert_called_once_with(cart=cart, item=item, qty=4)

    @patch("carts.services.commands._available_qty")
    @patch("carts.services.commands._assert_item_buyable")
    @patch("carts.services.commands.repo")
    @patch("carts.services.commands._get_item_by_public_id")
    def test_set_quantity_rejects_when_exceeds_available_plus_current(
        self,
        mock_get_item,
        mock_repo,
        mock_assert_buyable,
        mock_avail,
    ):
        user = SimpleNamespace(id=10)
        item = self._mk_item(id=1, public_id="I1")
        cart = self._mk_cart()

        mock_get_item.return_value = item
        mock_repo.get_or_create_active_cart.return_value = cart
        mock_repo.current_qty.return_value = 2
        mock_avail.return_value = 1

        with self.assertRaises(Conflict):
            commands.set_quantity.__wrapped__(user=user, item_public_id="I1", quantity=4)

    @patch("carts.services.commands.orders_checkout_cart")
    @patch("carts.services.commands.repo")
    def test_checkout_active_cart_creates_orders_and_marks_cart_checked_out(self, mock_repo, mock_orders_checkout):
        user = SimpleNamespace(id=10, email="u@example.com")
        cart = self._mk_cart()

        item1 = self._mk_item(id=1, public_id="I1")
        item2 = self._mk_item(id=2, public_id="I2")

        row1 = SimpleNamespace(item_set=item1, quantity=2)
        row2 = SimpleNamespace(item_set=item2, quantity=1)

        cart.items.select_related.return_value.all.return_value = [row1, row2]
        mock_repo.get_cart.return_value = cart
        mock_orders_checkout.return_value = ["O1", "O2"]

        out = commands.checkout_active_cart.__wrapped__(user=user, payment_method="CREDIT_CARD")

        self.assertEqual(out, ["O1", "O2"])
        mock_orders_checkout.assert_called_once_with(
            buyer=user,
            cart_items=[(item1, 2), (item2, 1)],
            payment_method="CREDIT_CARD",
        )
        self.assertEqual(cart.status, "CHECKED_OUT")
        cart.save.assert_called_once()

    @patch("carts.services.commands.repo")
    def test_checkout_active_cart_rejects_empty_cart_or_no_rows(self, mock_repo):
        user = SimpleNamespace(id=10)

        mock_repo.get_cart.return_value = None
        with self.assertRaises(DomainError):
            commands.checkout_active_cart.__wrapped__(user=user, payment_method="CREDIT_CARD")

        cart = self._mk_cart()
        cart.items.select_related.return_value.all.return_value = []
        mock_repo.get_cart.return_value = cart
        with self.assertRaises(DomainError):
            commands.checkout_active_cart.__wrapped__(user=user, payment_method="CREDIT_CARD")
