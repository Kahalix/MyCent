from __future__ import annotations
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from transactions.services.commands import (
    attach_coupon_and_recalculate,
    _recompute_expected_total,
    set_transaction_status,
    preview_coupon_discount,
    cancel_stale_pending_transactions,
)
from transactions.services.discounts import DiscountResult
from transactions.services.exceptions import DomainError, Conflict
from transactions.models import Transaction
from .factories import (
    create_user,
    create_transaction,
    create_coupon,
    create_user_coupon,
    create_seller_profile,
    create_order_for_transaction,
)


class AttachCouponAndRecalculateTests(TestCase):
    def test_raises_for_non_purchase_transaction(self):
        user = create_user("np@example.com")
        tx = create_transaction(user=user, type="PAWN_EXTENSION", expected_total_currency="PLN")
        with self.assertRaises(DomainError) as cm:
            attach_coupon_and_recalculate(
                transaction=tx,
                coupon_code="CODE1",
                user_coupon_public_id=None,
            )
        self.assertEqual(str(cm.exception.detail), "Kupony nie są dostępne dla tej transakcji.")

    def test_conflict_when_both_code_and_user_coupon_given(self):
        user = create_user("both@example.com")
        tx = create_transaction(user=user, type="PURCHASE", expected_total_currency="PLN")
        with self.assertRaises(Conflict) as cm:
            attach_coupon_and_recalculate(
                transaction=tx,
                coupon_code="CODE1",
                user_coupon_public_id="uc1",
            )
        self.assertIn("Podaj kod kuponu albo kupon użytkownika", str(cm.exception.detail))

    def test_domain_error_when_coupon_code_invalid(self):
        user = create_user("invcode@example.com")
        tx = create_transaction(user=user, type="PURCHASE", expected_total_currency="PLN")
        with self.assertRaises(DomainError) as cm:
            attach_coupon_and_recalculate(
                transaction=tx,
                coupon_code="UNKNOWN",
                user_coupon_public_id=None,
            )
        self.assertEqual(str(cm.exception.detail), "Nieprawidłowy kod kuponu.")

    def test_domain_error_when_user_coupon_not_found(self):
        user = create_user("invuc@example.com")
        tx = create_transaction(user=user, type="PURCHASE", expected_total_currency="PLN")
        with self.assertRaises(DomainError) as cm:
            attach_coupon_and_recalculate(
                transaction=tx,
                coupon_code="",
                user_coupon_public_id="nonexistent",
            )
        self.assertEqual(str(cm.exception.detail), "Kupon użytkownika nie istnieje.")

    def test_clear_coupon_when_no_values_and_recompute_total(self):
        user = create_user("clear@example.com")
        tx = create_transaction(user=user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=user)
        create_order_for_transaction(tx, seller, grand_total=Money(100, "PLN"))
        coupon = create_coupon(code="CLEAR1")
        user_coupon = create_user_coupon(user=user, coupon=coupon)
        tx.coupon = coupon
        tx.user_coupon = user_coupon
        tx.save(update_fields=["coupon", "user_coupon", "updated_at"])
        tx = attach_coupon_and_recalculate(
            transaction=tx,
            coupon_code="",
            user_coupon_public_id="",
        )
        tx.refresh_from_db()
        self.assertIsNone(tx.coupon)
        self.assertIsNone(tx.user_coupon)
        self.assertEqual(Decimal(str(tx.expected_total_amount)), Decimal("100.00"))
        self.assertEqual(tx.expected_total_currency, "PLN")

    def test_conflict_when_user_coupon_belongs_to_other_user(self):
        user1 = create_user("owner1@example.com")
        user2 = create_user("owner2@example.com")
        tx = create_transaction(user=user1, type="PURCHASE", expected_total_currency="PLN")
        coupon = create_coupon(code="UC1")
        uc = create_user_coupon(user=user2, coupon=coupon)
        with self.assertRaises(Conflict) as cm:
            attach_coupon_and_recalculate(
                transaction=tx,
                coupon_code="",
                user_coupon_public_id=uc.public_id,
            )
        self.assertEqual(str(cm.exception.detail), "Ten kupon użytkownika nie należy do tego klienta.")

    def test_attach_coupon_success_recalculates_totals(self):
        user = create_user("ok@example.com")
        tx = create_transaction(user=user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=user)
        create_order_for_transaction(tx, seller, grand_total=Money(100, "PLN"))
        coupon = create_coupon(
            code="SAVE10",
            discount_type="PERCENTAGE",
            discount_value=Money(10, "PLN"),
        )
        tx = attach_coupon_and_recalculate(
            transaction=tx,
            coupon_code="SAVE10",
            user_coupon_public_id=None,
        )
        tx.refresh_from_db()
        self.assertEqual(tx.coupon_id, coupon.id)
        self.assertIsNone(tx.user_coupon_id)
        self.assertEqual(Decimal(str(tx.expected_total_amount)), Decimal("90.00"))
        self.assertEqual(tx.expected_total_currency, "PLN")

    def test_reason_mapping_for_discount_errors(self):
        user = create_user("map@example.com")
        tx = create_transaction(user=user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=user)
        create_order_for_transaction(tx, seller, grand_total=Money(100, "PLN"))
        coupon = create_coupon(code="EXP1")
        with patch("transactions.services.commands.validate_and_compute_discount") as mock_validate:
            mock_validate.return_value = DiscountResult(
                ok=False,
                reason="Coupon expired",
                discount=Money(0, "PLN"),
            )
            with self.assertRaises(Conflict) as cm:
                attach_coupon_and_recalculate(
                    transaction=tx,
                    coupon_code="EXP1",
                    user_coupon_public_id=None,
                )
            self.assertEqual(str(cm.exception.detail), "Kupon wygasł.")


class RecomputeExpectedTotalTests(TestCase):
    def test_non_purchase_keeps_amount_and_sets_currency(self):
        user = create_user("np2@example.com")
        tx = create_transaction(
            user=user,
            type="PAWN_EXTENSION",
            expected_total_amount=Decimal("50.00"),
            expected_total_currency="",
        )
        _recompute_expected_total(tx)
        self.assertEqual(Decimal(str(tx.expected_total_amount)), Decimal("50.00"))
        self.assertEqual(tx.expected_total_currency, "PLN")

    def test_purchase_without_coupon_sets_sum_of_orders(self):
        user = create_user("sum@example.com")
        tx = create_transaction(user=user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=user)
        create_order_for_transaction(tx, seller, grand_total=Money(100, "PLN"))
        create_order_for_transaction(tx, seller, grand_total=Money(50, "PLN"))
        _recompute_expected_total(tx)
        self.assertEqual(Decimal(str(tx.expected_total_amount)), Decimal("150.00"))
        self.assertEqual(tx.expected_total_currency, "PLN")

    def test_purchase_with_coupon_never_negative(self):
        user = create_user("negdisc@example.com")
        tx = create_transaction(user=user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=user)
        create_order_for_transaction(tx, seller, grand_total=Money(100, "PLN"))
        coupon = create_coupon(
            discount_type="AMOUNT",
            discount_value=Money(200, "PLN"),
        )
        tx.coupon = coupon
        tx.save(update_fields=["coupon", "updated_at"])
        _recompute_expected_total(tx)
        self.assertEqual(Decimal(str(tx.expected_total_amount)), Decimal("0.00"))
        self.assertEqual(tx.expected_total_currency, "PLN")


class SetTransactionStatusTests(TestCase):
    def test_invalid_status_raises_domain_error(self):
        user = create_user("badstatus@example.com")
        tx = create_transaction(user=user, status="PENDING")
        with self.assertRaises(DomainError) as cm:
            set_transaction_status(tx=tx, to_status="UNKNOWN", reason="")
        self.assertEqual(str(cm.exception.detail), "Invalid status")

    def test_disallowed_transition_raises_conflict(self):
        user = create_user("trans@example.com")
        tx = create_transaction(user=user, status="COMPLETED")
        with self.assertRaises(Conflict) as cm:
            set_transaction_status(tx=tx, to_status="PENDING", reason="")
        self.assertIn("Transition COMPLETED", str(cm.exception.detail))
        self.assertIn("not allowed", str(cm.exception.detail))

    def test_completion_marks_user_coupon_redeemed(self):
        user = create_user("redeem@example.com")
        coupon = create_coupon()
        user_coupon = create_user_coupon(user=user, coupon=coupon, redeemed=False)
        tx = create_transaction(
            user=user,
            status="PENDING",
            type="PURCHASE",
            user_coupon=user_coupon,
        )
        set_transaction_status(tx=tx, to_status="COMPLETED", reason="")
        user_coupon.refresh_from_db()
        self.assertTrue(user_coupon.redeemed)
        self.assertIsNotNone(user_coupon.redeemed_at)

    def test_refund_unredeems_user_coupon(self):
        user = create_user("refund@example.com")
        coupon = create_coupon()
        user_coupon = create_user_coupon(user=user, coupon=coupon, redeemed=True)
        tx = create_transaction(
            user=user,
            status="COMPLETED",
            type="PURCHASE",
            user_coupon=user_coupon,
        )
        set_transaction_status(tx=tx, to_status="REFUNDED", reason="")
        user_coupon.refresh_from_db()
        self.assertFalse(user_coupon.redeemed)
        self.assertIsNone(user_coupon.redeemed_at)

    def test_non_purchase_does_not_touch_user_coupon(self):
        user = create_user("np3@example.com")
        coupon = create_coupon()
        user_coupon = create_user_coupon(user=user, coupon=coupon, redeemed=False)
        tx = create_transaction(
            user=user,
            status="PENDING",
            type="PAWN_EXTENSION",
            user_coupon=user_coupon,
        )
        set_transaction_status(tx=tx, to_status="COMPLETED", reason="")
        user_coupon.refresh_from_db()
        self.assertFalse(user_coupon.redeemed)

    def test_setting_same_status_is_allowed(self):
        user = create_user("same@example.com")
        tx = create_transaction(user=user, status="PENDING")
        set_transaction_status(tx=tx, to_status="PENDING", reason="")
        tx.refresh_from_db()
        self.assertEqual(tx.status, "PENDING")


class PreviewCouponDiscountTests(TestCase):
    def test_non_purchase_returns_not_available(self):
        user = create_user("prevnp@example.com")
        tx = create_transaction(
            user=user,
            type="PAWN_EXTENSION",
            expected_total_amount=Decimal("50.00"),
            expected_total_currency="PLN",
        )
        result = preview_coupon_discount(tx=tx, coupon_code="CODE1")
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "Coupons are not available for this transaction.")
        self.assertEqual(result["gross_amount"], "50.00")
        self.assertEqual(result["net_amount"], "50.00")
        self.assertEqual(result["discount_amount"], "0.00")
        self.assertIsNone(result["coupon_public_id"])
        self.assertIsNone(result["user_coupon_public_id"])

    def test_purchase_with_coupon_code_returns_preview_without_saving(self):
        user = create_user("prevok@example.com")
        tx = create_transaction(user=user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=user)
        create_order_for_transaction(tx, seller, grand_total=Money(100, "PLN"))
        coupon = create_coupon(
            code="PREVIEW10",
            discount_type="PERCENTAGE",
            discount_value=Money(10, "PLN"),
        )
        tx.expected_total_amount = Decimal("0.00")
        tx.save(update_fields=["expected_total_amount", "updated_at"])
        result = preview_coupon_discount(tx=tx, coupon_code="PREVIEW10")
        self.assertTrue(result["ok"])
        self.assertIsNone(result["reason"])
        self.assertEqual(result["currency"], "PLN")
        self.assertEqual(result["gross_amount"], "100.00")
        self.assertEqual(result["discount_amount"], "10.00")
        self.assertEqual(result["net_amount"], "90.00")
        self.assertEqual(result["coupon_public_id"], coupon.public_id)
        self.assertIsNone(result["user_coupon_public_id"])
        tx.refresh_from_db()
        self.assertEqual(Decimal(str(tx.expected_total_amount)), Decimal("0.00"))


class CancelStalePendingTransactionsTests(TestCase):
    def test_cancels_only_old_pending_transactions(self):
        user = create_user("stale@example.com")
        tx_old = create_transaction(
            user=user,
            status="PENDING",
            expected_total_amount=Decimal("10.00"),
            expected_total_currency="PLN",
        )
        tx_recent = create_transaction(
            user=user,
            status="PENDING",
            expected_total_amount=Decimal("20.00"),
            expected_total_currency="PLN",
        )
        tx_completed = create_transaction(
            user=user,
            status="COMPLETED",
            expected_total_amount=Decimal("30.00"),
            expected_total_currency="PLN",
        )
        old_time = timezone.now() - timezone.timedelta(minutes=120)
        recent_time = timezone.now() - timezone.timedelta(minutes=10)
        Transaction.objects.filter(id=tx_old.id).update(updated_at=old_time)
        Transaction.objects.filter(id=tx_recent.id).update(updated_at=recent_time)
        Transaction.objects.filter(id=tx_completed.id).update(updated_at=old_time)
        count = cancel_stale_pending_transactions(minutes=60)
        self.assertEqual(count, 1)
        tx_old.refresh_from_db()
        tx_recent.refresh_from_db()
        tx_completed.refresh_from_db()
        self.assertEqual(tx_old.status, "CANCELLED")
        self.assertEqual(tx_recent.status, "PENDING")
        self.assertEqual(tx_completed.status, "COMPLETED")
