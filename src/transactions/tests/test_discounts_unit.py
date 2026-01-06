from __future__ import annotations

from datetime import datetime, timezone as dtz
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from djmoney.money import Money

from transactions.services import discounts


class TransactionsDiscountsUnitTests(SimpleTestCase):
    def _mk_tx(self, *, type: str = "PURCHASE", currency: str = "PLN", user_id: int | None = 1, base: Money | None = None):
        orders = []
        if base is not None:
            orders = [SimpleNamespace(grand_total=base)]
        tx = SimpleNamespace(
            type=type,
            expected_total_currency=currency,
            user_id=user_id,
            orders=SimpleNamespace(all=MagicMock(return_value=orders)),
        )
        return tx

    def _mk_coupon(
        self,
        *,
        active: bool = True,
        expiration_date=None,
        discount_type: str = "PERCENTAGE",
        discount_value: Money | None = Money(10, "PLN"),
        max_discount_value: Money | None = None,
        min_purchase_value: Money | None = None,
        max_redemptions: int | None = None,
        max_per_user: int | None = None,
    ):
        return SimpleNamespace(
            active=active,
            expiration_date=expiration_date,
            discount_type=discount_type,
            discount_value=discount_value,
            max_discount_value=max_discount_value,
            min_purchase_value=min_purchase_value,
            max_redemptions=max_redemptions,
            max_per_user=max_per_user,
        )

    def _mk_user_coupon(self, *, user_id: int = 1, redeemed: bool = False, coupon=None):
        return SimpleNamespace(user_id=user_id, redeemed=redeemed, coupon=coupon)

    def test_not_allowed_for_non_purchase(self):
        tx = self._mk_tx(type="PAWN_EXTENSION")
        c = self._mk_coupon()
        res = discounts.validate_and_compute_discount(transaction=tx, coupon=c, user_coupon=None)
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "Coupons are not allowed for this transaction.")
        self.assertEqual(res.discount, Money(0, "PLN"))

    def test_no_coupon_ok_zero_discount(self):
        tx = self._mk_tx(type="PURCHASE")
        res = discounts.validate_and_compute_discount(transaction=tx, coupon=None, user_coupon=None)
        self.assertTrue(res.ok)
        self.assertIsNone(res.reason)
        self.assertEqual(res.discount, Money(0, "PLN"))

    @patch("transactions.services.discounts.timezone")
    def test_inactive_coupon(self, tz):
        tz.now.return_value = datetime(2026, 1, 6, tzinfo=dtz.utc)
        tx = self._mk_tx(type="PURCHASE")
        c = self._mk_coupon(active=False)
        res = discounts.validate_and_compute_discount(transaction=tx, coupon=c, user_coupon=None)
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "Coupon inactive")

    @patch("transactions.services.discounts.timezone")
    def test_expired_coupon(self, tz):
        now = datetime(2026, 1, 6, tzinfo=dtz.utc)
        tz.now.return_value = now
        tx = self._mk_tx(type="PURCHASE")
        c = self._mk_coupon(expiration_date=now)
        res = discounts.validate_and_compute_discount(transaction=tx, coupon=c, user_coupon=None)
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "Coupon expired")

    @patch("transactions.services.discounts._count_redemptions")
    @patch("transactions.services.discounts._base_total_for")
    @patch("transactions.services.discounts.timezone")
    def test_coupon_redemption_limit_reached(self, tz, base_mock, count_mock):
        tz.now.return_value = datetime(2026, 1, 6, tzinfo=dtz.utc)
        tx = self._mk_tx(type="PURCHASE")
        base_mock.return_value = Money(100, "PLN")
        count_mock.return_value = (10, 0)
        c = self._mk_coupon(max_redemptions=5)
        res = discounts.validate_and_compute_discount(transaction=tx, coupon=c, user_coupon=None)
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "Coupon redemption limit reached")

    @patch("transactions.services.discounts._count_redemptions")
    @patch("transactions.services.discounts._base_total_for")
    @patch("transactions.services.discounts.timezone")
    def test_coupon_per_user_limit_reached(self, tz, base_mock, count_mock):
        tz.now.return_value = datetime(2026, 1, 6, tzinfo=dtz.utc)
        tx = self._mk_tx(type="PURCHASE", user_id=1)
        base_mock.return_value = Money(100, "PLN")
        count_mock.return_value = (0, 3)
        c = self._mk_coupon(max_per_user=2)
        res = discounts.validate_and_compute_discount(transaction=tx, coupon=c, user_coupon=None)
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "Per-user redemption limit reached")

    @patch("transactions.services.discounts._count_redemptions", return_value=(0, 0))
    @patch("transactions.services.discounts._base_total_for", return_value=Money(50, "PLN"))
    @patch("transactions.services.discounts.timezone")
    def test_min_purchase_value_not_met(self, tz, base_mock, count_mock):
        tz.now.return_value = datetime(2026, 1, 6, tzinfo=dtz.utc)
        tx = self._mk_tx(type="PURCHASE")
        c = self._mk_coupon(min_purchase_value=Money(100, "PLN"))
        res = discounts.validate_and_compute_discount(transaction=tx, coupon=c, user_coupon=None)
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "Minimum purchase value not met")

    @patch("transactions.services.discounts._count_redemptions", return_value=(0, 0))
    @patch("transactions.services.discounts._base_total_for", return_value=Money(200, "PLN"))
    @patch("transactions.services.discounts.timezone")
    def test_percentage_discount_with_cap(self, tz, base_mock, count_mock):
        tz.now.return_value = datetime(2026, 1, 6, tzinfo=dtz.utc)
        tx = self._mk_tx(type="PURCHASE")
        c = self._mk_coupon(
            discount_type="PERCENTAGE",
            discount_value=Money(50, "PLN"),
            max_discount_value=Money(20, "PLN"),
        )
        res = discounts.validate_and_compute_discount(transaction=tx, coupon=c, user_coupon=None)
        self.assertTrue(res.ok)
        self.assertEqual(res.discount, Money(20, "PLN"))

    @patch("transactions.services.discounts._count_redemptions", return_value=(0, 0))
    @patch("transactions.services.discounts._base_total_for", return_value=Money(100, "PLN"))
    @patch("transactions.services.discounts.timezone")
    def test_amount_discount_cannot_exceed_base(self, tz, base_mock, count_mock):
        tz.now.return_value = datetime(2026, 1, 6, tzinfo=dtz.utc)
        tx = self._mk_tx(type="PURCHASE")
        c = self._mk_coupon(discount_type="AMOUNT", discount_value=Money(200, "PLN"))
        res = discounts.validate_and_compute_discount(transaction=tx, coupon=c, user_coupon=None)
        self.assertTrue(res.ok)
        self.assertEqual(res.discount, Money(100, "PLN"))

    @patch("transactions.services.discounts._count_redemptions", return_value=(0, 0))
    @patch("transactions.services.discounts._base_total_for", return_value=Money(100, "PLN"))
    @patch("transactions.services.discounts.timezone")
    def test_user_coupon_must_belong_to_user(self, tz, base_mock, count_mock):
        tz.now.return_value = datetime(2026, 1, 6, tzinfo=dtz.utc)
        tx = self._mk_tx(type="PURCHASE", user_id=1)
        c = self._mk_coupon()
        uc = self._mk_user_coupon(user_id=2, redeemed=False, coupon=c)
        res = discounts.validate_and_compute_discount(transaction=tx, coupon=None, user_coupon=uc)
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "This coupon does not belong to the user")

    @patch("transactions.services.discounts._count_redemptions", return_value=(0, 0))
    @patch("transactions.services.discounts._base_total_for", return_value=Money(100, "PLN"))
    @patch("transactions.services.discounts.timezone")
    def test_user_coupon_already_redeemed(self, tz, base_mock, count_mock):
        tz.now.return_value = datetime(2026, 1, 6, tzinfo=dtz.utc)
        tx = self._mk_tx(type="PURCHASE", user_id=1)
        c = self._mk_coupon()
        uc = self._mk_user_coupon(user_id=1, redeemed=True, coupon=c)
        res = discounts.validate_and_compute_discount(transaction=tx, coupon=None, user_coupon=uc)
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "User coupon already redeemed")
