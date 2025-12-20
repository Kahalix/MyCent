from __future__ import annotations
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from coupons.models import Coupon
from transactions.services.discounts import (
    validate_and_compute_discount,
    _base_total_for,
)
from .factories import (
    create_user,
    create_transaction,
    create_coupon,
    create_user_coupon,
    create_seller_profile,
    create_order_for_transaction,
)


class DiscountBaseTotalTests(TestCase):
    def test_base_total_sums_order_grand_totals(self):
        user = create_user("base@example.com")
        tx = create_transaction(user=user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=user)
        create_order_for_transaction(tx, seller, grand_total=Money(100, "PLN"))
        create_order_for_transaction(tx, seller, grand_total=Money(50, "PLN"))
        base = _base_total_for(tx)
        self.assertEqual(base, Money(150, "PLN"))


class DiscountValidationTests(TestCase):
    def setUp(self):
        self.user = create_user("disc@example.com")

    def test_not_allowed_for_non_purchase(self):
        tx = create_transaction(
            user=self.user,
            type="PAWN_EXTENSION",
            expected_total_currency="PLN",
        )
        coupon = create_coupon()
        result = validate_and_compute_discount(transaction=tx, coupon=coupon, user_coupon=None)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "Coupons are not allowed for this transaction.")
        self.assertEqual(result.discount, Money(0, "PLN"))

    def test_inactive_coupon(self):
        tx = create_transaction(user=self.user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=self.user)
        create_order_for_transaction(tx, seller, grand_total=Money(100, "PLN"))
        coupon = create_coupon(active=False)
        result = validate_and_compute_discount(transaction=tx, coupon=coupon, user_coupon=None)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "Coupon inactive")
        self.assertEqual(result.discount, Money(0, "PLN"))

    def test_min_purchase_not_met(self):
        tx = create_transaction(user=self.user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=self.user)
        create_order_for_transaction(tx, seller, grand_total=Money(50, "PLN"))
        coupon = create_coupon(
            min_purchase_value=Money(100, "PLN"),
        )
        result = validate_and_compute_discount(transaction=tx, coupon=coupon, user_coupon=None)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "Minimum purchase value not met")
        self.assertEqual(result.discount, Money(0, "PLN"))

    def test_percentage_discount_applied(self):
        tx = create_transaction(user=self.user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=self.user)
        create_order_for_transaction(tx, seller, grand_total=Money(200, "PLN"))
        coupon = create_coupon(
            discount_type="PERCENTAGE",
            discount_value=Money(10, "PLN"),
        )
        result = validate_and_compute_discount(transaction=tx, coupon=coupon, user_coupon=None)
        self.assertTrue(result.ok)
        self.assertIsNone(result.reason)
        self.assertEqual(result.discount, Money(20, "PLN"))

    def test_amount_discount_capped_by_max_discount(self):
        tx = create_transaction(user=self.user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=self.user)
        create_order_for_transaction(tx, seller, grand_total=Money(100, "PLN"))
        coupon = create_coupon(
            discount_type="AMOUNT",
            discount_value=Money(200, "PLN"),
            max_discount_value=Money(90, "PLN"),
        )
        result = validate_and_compute_discount(transaction=tx, coupon=coupon, user_coupon=None)
        self.assertTrue(result.ok)
        self.assertEqual(result.discount, Money(90, "PLN"))

    def test_coupon_redemption_limit_reached(self):
        coupon = create_coupon(max_redemptions=1)
        user1 = self.user
        user2 = create_user("other@example.com")
        tx_completed = create_transaction(
            user=user1,
            type="PURCHASE",
            status="COMPLETED",
            expected_total_amount=Decimal("50.00"),
            expected_total_currency="PLN",
            coupon=coupon,
        )
        tx = create_transaction(
            user=user2,
            type="PURCHASE",
            expected_total_currency="PLN",
        )
        seller = create_seller_profile(owner=user2)
        create_order_for_transaction(tx, seller, grand_total=Money(50, "PLN"))
        result = validate_and_compute_discount(transaction=tx, coupon=coupon, user_coupon=None)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "Coupon redemption limit reached")

    def test_coupon_per_user_limit_reached(self):
        coupon = create_coupon(max_per_user=1)
        tx_completed = create_transaction(
            user=self.user,
            type="PURCHASE",
            status="COMPLETED",
            expected_total_amount=Decimal("50.00"),
            expected_total_currency="PLN",
            coupon=coupon,
        )
        tx = create_transaction(
            user=self.user,
            type="PURCHASE",
            expected_total_currency="PLN",
        )
        seller = create_seller_profile(owner=self.user)
        create_order_for_transaction(tx, seller, grand_total=Money(50, "PLN"))
        result = validate_and_compute_discount(transaction=tx, coupon=coupon, user_coupon=None)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "Per-user redemption limit reached")

    def test_user_coupon_must_belong_to_user(self):
        tx = create_transaction(user=self.user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=self.user)
        create_order_for_transaction(tx, seller, grand_total=Money(100, "PLN"))
        coupon = create_coupon()
        other_user = create_user("ucother@example.com")
        user_coupon = create_user_coupon(user=other_user, coupon=coupon)
        result = validate_and_compute_discount(transaction=tx, coupon=None, user_coupon=user_coupon)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "This coupon does not belong to the user")

    def test_user_coupon_already_redeemed(self):
        tx = create_transaction(user=self.user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=self.user)
        create_order_for_transaction(tx, seller, grand_total=Money(100, "PLN"))
        coupon = create_coupon()
        user_coupon = create_user_coupon(user=self.user, coupon=coupon, redeemed=True)
        result = validate_and_compute_discount(transaction=tx, coupon=None, user_coupon=user_coupon)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "User coupon already redeemed")
