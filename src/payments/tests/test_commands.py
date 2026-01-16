from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.db import IntegrityError
from django.utils import timezone
from djmoney.money import Money

from payments.models import Payment
from payments.services import commands
from payments.services.exceptions import Conflict, Forbidden, DomainError
from .factories import (
    create_transaction,
    create_payment,
    create_order,
    create_order_line,
    create_order_shipping,
    create_coupon,
    create_user_coupon,
    create_user,
)
from orders.models import OrderShipping


class CalcPointsTests(TestCase):
    @override_settings(LOYALTY_RATE_BPS=200)
    def test_calc_points_for_amount_uses_bps_rate(self):
        amount = Money(100, "PLN")
        pts = commands._calc_points_for_amount(amount)
        self.assertEqual(pts, 2)

    @override_settings(LOYALTY_RATE_BPS=0)
    def test_calc_points_for_zero_rate(self):
        amount = Money(100, "PLN")
        pts = commands._calc_points_for_amount(amount)
        self.assertEqual(pts, 0)


class AwardPointsAfterSuccessTests(TestCase):
    @override_settings(LOYALTY_RATE_BPS=200)
    @patch("payments.services.commands.loyalty_add_points")
    def test_award_points_for_purchase_updates_metadata(self, add_points_mock):
        tx = create_transaction(type="PURCHASE", amount=Decimal("100.00"))
        payment = create_payment(tx=tx, amount=Money(100, "PLN"))
        pts = commands._award_points_after_success(payment=payment)
        self.assertEqual(pts, 2)
        add_points_mock.assert_called_once()
        payment.refresh_from_db()
        self.assertEqual(payment.metadata.get("loyalty_points_awarded"), 2)

    @patch("payments.services.commands.loyalty_add_points")
    def test_award_points_for_non_purchase_returns_zero(self, add_points_mock):
        tx = create_transaction(type="PAWN_EXTENSION", amount=Decimal("50.00"))
        payment = create_payment(tx=tx, amount=Money(50, "PLN"))
        pts = commands._award_points_after_success(payment=payment)
        self.assertEqual(pts, 0)
        add_points_mock.assert_not_called()


class CreatePaymentForTransactionTests(TestCase):
    def setUp(self):
        super().setUp()
        self._ensure_patch = patch("payments.services.commands._ensure_purchase_tx_stock_available_and_reserve")
        self._ensure_patch.start()

    def tearDown(self):
        self._ensure_patch.stop()
        super().tearDown()

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("payments.services.commands.attach_coupon_and_recalculate")
    def test_create_payment_for_non_purchase_ignores_coupons(self, attach_mock):
        tx = create_transaction(type="PAWN_EXTENSION", amount=Decimal("50.00"))
        payment = commands.create_payment_for_transaction(
            tx=tx,
            provider=None,
            coupon_code="CODE",
            user_coupon_public_id="UCID",
        )
        attach_mock.assert_not_called()
        self.assertEqual(payment.transaction, tx)
        self.assertEqual(payment.provider, "SIM")
        self.assertEqual(payment.amount, Money(50, "PLN"))
        self.assertEqual(payment.status, "REQUIRES_CONFIRMATION")

    def test_create_payment_for_non_pending_tx_raises_forbidden(self):
        tx = create_transaction(status="COMPLETED")
        with self.assertRaises(Forbidden):
            commands.create_payment_for_transaction(tx=tx)

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_for_purchase_requires_shipping_for_all_lines(self, addr_ok_mock):
        tx = create_transaction(type="PURCHASE", amount=Decimal("100.00"))
        order = create_order(tx=tx)
        create_order_line(order=order)
        with self.assertRaises(DomainError):
            commands.create_payment_for_transaction(tx=tx)

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_for_purchase_requires_shipping_price(self, addr_ok_mock):
        tx = create_transaction(type="PURCHASE", amount=Decimal("100.00"))
        order = create_order(tx=tx)
        line = create_order_line(order=order)
        OrderShipping.objects.create(order=order, order_line=line, price=None)
        with self.assertRaises(DomainError):
            commands.create_payment_for_transaction(tx=tx)

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("orders.services.commands._addr_ok", return_value=False)
    def test_create_payment_for_purchase_requires_shipping_address_when_package(self, addr_ok_mock):
        tx = create_transaction(type="PURCHASE", amount=Decimal("100.00"))
        order = create_order(tx=tx, shipping_address={})
        line = create_order_line(order=order)
        create_order_shipping(order=order, order_line=line)
        with self.assertRaises(DomainError):
            commands.create_payment_for_transaction(tx=tx)

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_for_purchase_success_basic(self, addr_ok_mock):
        tx = create_transaction(type="PURCHASE")
        order = create_order(tx=tx)
        line = create_order_line(order=order)
        create_order_shipping(order=order, order_line=line)

        order.recalc_totals(save=True)
        tx.expected_total_amount = order.purchase_cost.amount
        tx.expected_total_currency = str(order.purchase_cost.currency)
        tx.save(update_fields=["expected_total_amount", "expected_total_currency", "updated_at"])

        payment = commands.create_payment_for_transaction(tx=tx, provider="SIM")

        self.assertEqual(payment.provider, "SIM")
        self.assertEqual(payment.amount, Money(tx.expected_total_amount, tx.expected_total_currency))
        self.assertEqual(Decimal(payment.metadata.get("discount_applied")), Decimal("0"))

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_for_purchase_amount_must_be_positive(self, addr_ok_mock):
        tx = create_transaction(type="PURCHASE")
        order = create_order(tx=tx)
        line = create_order_line(order=order)
        create_order_shipping(order=order, order_line=line)

        tx.expected_total_amount = Decimal("0.00")
        tx.expected_total_currency = "PLN"
        tx.save(update_fields=["expected_total_amount", "expected_total_currency", "updated_at"])

        with self.assertRaises(DomainError):
            commands.create_payment_for_transaction(tx=tx)

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("payments.services.commands.attach_coupon_and_recalculate")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_for_purchase_with_coupon_sets_metadata(self, addr_ok_mock, attach_mock):
        tx = create_transaction(type="PURCHASE")
        order = create_order(tx=tx)
        line = create_order_line(order=order)
        create_order_shipping(order=order, order_line=line)

        order.recalc_totals(save=True)
        tx.expected_total_amount = order.purchase_cost.amount
        tx.expected_total_currency = str(order.purchase_cost.currency)
        tx.save(update_fields=["expected_total_amount", "expected_total_currency", "updated_at"])

        coupon = create_coupon(code="SAVE10")

        before_amount = Decimal(str(tx.expected_total_amount or 0))
        expected_discount: dict[str, Decimal] = {}

        def fake_attach(transaction, coupon_code=None, user_coupon_public_id=None):
            self.assertEqual(coupon_code, "SAVE10")
            transaction.coupon = coupon
            original = Decimal(str(transaction.expected_total_amount or 0))

            new_amount = original - Decimal("5.00")
            if new_amount <= 0:
                new_amount = Decimal("1.00")

            expected_discount["val"] = original - new_amount

            transaction.expected_total_amount = new_amount
            transaction.expected_total_currency = "PLN"
            transaction.save(
                update_fields=[
                    "expected_total_amount",
                    "expected_total_currency",
                    "coupon",
                    "updated_at",
                ]
            )
            return transaction

        attach_mock.side_effect = fake_attach

        payment = commands.create_payment_for_transaction(
            tx=tx,
            provider=None,
            coupon_code="SAVE10",
            user_coupon_public_id=None,
        )

        attach_mock.assert_called_once()

        self.assertEqual(
            Decimal(str(payment.amount.amount)),
            before_amount - expected_discount["val"],
        )

        self.assertEqual(
            Decimal(payment.metadata.get("discount_applied")),
            expected_discount["val"],
        )

        coupon_meta = payment.metadata.get("coupon") or {}
        self.assertEqual(coupon_meta.get("mode"), "code")
        self.assertEqual(coupon_meta.get("coupon_public_id"), coupon.public_id)
        self.assertEqual(coupon_meta.get("code"), coupon.code)
        self.assertEqual(
            Decimal(coupon_meta.get("discount")),
            expected_discount["val"],
        )
        self.assertEqual(coupon_meta.get("currency"), "PLN")

    @override_settings(STRIPE_SECRET_KEY="sk_test_x", STRIPE_PUBLISHABLE_KEY="pk_test_y")
    @patch("payments.services.commands.StripeClient")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_prefers_stripe_when_available(self, addr_ok_mock, stripe_client_cls):
        client = stripe_client_cls.return_value
        client.create_intent.return_value = ("pi_123", "cs_456")
        tx = create_transaction(type="PURCHASE", amount=Decimal("100.00"))
        order = create_order(tx=tx)
        line = create_order_line(order=order)
        create_order_shipping(order=order, order_line=line)
        order.recalc_totals(save=True)
        tx.expected_total_amount = order.purchase_cost.amount
        tx.expected_total_currency = str(order.purchase_cost.currency)
        tx.save(update_fields=["expected_total_amount", "expected_total_currency", "updated_at"])
        payment = commands.create_payment_for_transaction(tx=tx, provider="STRIPE")
        client.create_intent.assert_called_once()
        self.assertEqual(payment.provider, "STRIPE")
        self.assertEqual(payment.provider_payment_id, "pi_123")
        self.assertEqual(payment.client_secret, "cs_456")

    @override_settings(STRIPE_SECRET_KEY="sk_test_x", STRIPE_PUBLISHABLE_KEY="pk_test_y")
    @patch("payments.services.commands.StripeClient")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_falls_back_to_sim_when_stripe_fails(self, addr_ok_mock, stripe_client_cls):
        client = stripe_client_cls.return_value
        client.create_intent.side_effect = Exception("stripe error")
        tx = create_transaction(type="PURCHASE", amount=Decimal("100.00"))
        order = create_order(tx=tx)
        line = create_order_line(order=order)
        create_order_shipping(order=order, order_line=line)
        order.recalc_totals(save=True)
        tx.expected_total_amount = order.purchase_cost.amount
        tx.expected_total_currency = str(order.purchase_cost.currency)
        tx.save(update_fields=["expected_total_amount", "expected_total_currency", "updated_at"])
        payment = commands.create_payment_for_transaction(tx=tx, provider="STRIPE")
        self.assertEqual(payment.provider, "SIM")

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("payments.services.commands.repo.create_payment")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_returns_existing_active_when_present(self, addr_ok_mock, create_payment_mock):
        tx = create_transaction(type="PURCHASE", amount=Decimal("100.00"))
        order = create_order(tx=tx)
        line = create_order_line(order=order)
        create_order_shipping(order=order, order_line=line)
        order.recalc_totals(save=True)
        tx.expected_total_amount = order.purchase_cost.amount
        tx.expected_total_currency = str(order.purchase_cost.currency)
        tx.save(update_fields=["expected_total_amount", "expected_total_currency", "updated_at"])
        existing = create_payment(tx=tx, status="REQUIRES_CONFIRMATION")
        payment = commands.create_payment_for_transaction(tx=tx, provider="SIM")
        self.assertEqual(payment.id, existing.id)
        create_payment_mock.assert_not_called()

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("payments.services.commands.repo.create_payment")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_handles_integrity_error_and_returns_revived(self, addr_ok_mock, create_payment_mock):
        tx = create_transaction(type="PURCHASE", amount=Decimal("100.00"))
        order = create_order(tx=tx)
        line = create_order_line(order=order)
        create_order_shipping(order=order, order_line=line)
        order.recalc_totals(save=True)
        tx.expected_total_amount = order.purchase_cost.amount
        tx.expected_total_currency = str(order.purchase_cost.currency)
        tx.save(update_fields=["expected_total_amount", "expected_total_currency", "updated_at"])

        def side_effect(*args, **kwargs):
            create_payment(tx=tx, status="REQUIRES_CONFIRMATION")
            raise IntegrityError("unique")

        create_payment_mock.side_effect = side_effect

        payment = commands.create_payment_for_transaction(tx=tx, provider="SIM")
        self.assertIsInstance(payment, Payment)
        self.assertEqual(payment.transaction, tx)
        self.assertEqual(payment.status, "REQUIRES_CONFIRMATION")

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("payments.services.commands.repo.create_payment")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_raises_conflict_when_integrity_and_no_revived(self, addr_ok_mock, create_payment_mock):
        tx = create_transaction(type="PURCHASE", amount=Decimal("100.00"))
        order = create_order(tx=tx)
        line = create_order_line(order=order)
        create_order_shipping(order=order, order_line=line)
        order.recalc_totals(save=True)
        tx.expected_total_amount = order.purchase_cost.amount
        tx.expected_total_currency = str(order.purchase_cost.currency)
        tx.save(update_fields=["expected_total_amount", "expected_total_currency", "updated_at"])

        create_payment_mock.side_effect = IntegrityError("unique")
        with self.assertRaises(Conflict):
            commands.create_payment_for_transaction(tx=tx, provider="SIM")


class MarkPaymentSucceededTests(TestCase):
    @override_settings(LOYALTY_RATE_BPS=200)
    @patch("payments.services.commands.loyalty_add_points")
    @patch("payments.services.commands._notify_order_confirmed")
    @patch("payments.services.commands.set_transaction_status")
    def test_mark_payment_succeeded_completes_tx_and_awards_points(
        self,
        set_status_mock,
        notify_mock,
        add_points_mock,
    ):
        user = create_user(email="buyer@example.com")
        tx = create_transaction(user=user, type="PURCHASE", amount=Decimal("100.00"), status="PENDING")
        main = create_payment(tx=tx, amount=Money(100, "PLN"), status="REQUIRES_CONFIRMATION")
        other_final = create_payment(tx=tx, amount=Money(100, "PLN"), status="FAILED")

        result = commands.mark_payment_succeeded(payment=main, reason="ok")

        self.assertEqual(result.id, main.id)
        main.refresh_from_db()
        other_final.refresh_from_db()

        self.assertEqual(main.status, "SUCCEEDED")
        self.assertEqual(other_final.status, "FAILED")

        set_status_mock.assert_called_once()
        add_points_mock.assert_called_once()
        notify_mock.assert_called_once()

        self.assertEqual(
            main.metadata.get("loyalty_points_awarded"),
            commands._calc_points_for_amount(main.amount),
        )

    @patch("payments.services.commands.loyalty_add_points")
    @patch("payments.services.commands._notify_order_confirmed")
    @patch("payments.services.commands.set_transaction_status")
    def test_mark_payment_succeeded_for_non_purchase_no_points_and_no_notify(
        self,
        set_status_mock,
        notify_mock,
        add_points_mock,
    ):
        tx = create_transaction(type="PAWN_EXTENSION", amount=Decimal("50.00"), status="PENDING")
        main = create_payment(tx=tx, amount=Money(50, "PLN"), status="REQUIRES_CONFIRMATION")
        commands.mark_payment_succeeded(payment=main, reason="ok")
        main.refresh_from_db()
        self.assertEqual(main.status, "SUCCEEDED")
        set_status_mock.assert_called_once()
        add_points_mock.assert_not_called()
        notify_mock.assert_not_called()

    @patch("pawns.services.commands.finalize_extension_after_payment")
    @patch("payments.services.commands.set_transaction_status")
    def test_mark_payment_succeeded_finalizes_pawn_extension(self, set_status_mock, finalize_mock):
        tx = create_transaction(type="PAWN_EXTENSION", amount=Decimal("50.00"), status="PENDING")
        main = create_payment(tx=tx, amount=Money(50, "PLN"), status="REQUIRES_CONFIRMATION")
        commands.mark_payment_succeeded(payment=main, reason="ext")
        finalize_mock.assert_called_once()
        args, kwargs = finalize_mock.call_args
        self.assertEqual(kwargs.get("tx"), tx)


class MarkPaymentFailedOrCancelledTests(TestCase):
    def test_mark_payment_failed_or_cancelled_sets_status(self):
        tx = create_transaction()
        payment = create_payment(tx=tx, status="REQUIRES_CONFIRMATION")
        commands.mark_payment_failed_or_cancelled(payment=payment, status="FAILED", reason="fail")
        payment.refresh_from_db()
        self.assertEqual(payment.status, "FAILED")


class ConfirmPaymentSimulatorTests(TestCase):
    @patch("payments.services.commands.mark_payment_succeeded")
    def test_confirm_payment_simulator_calls_success_on_true(self, mark_succeeded_mock):
        tx = create_transaction()
        payment = create_payment(tx=tx, status="REQUIRES_CONFIRMATION")
        mark_succeeded_mock.return_value = payment
        result = commands.confirm_payment_simulator(payment=payment, succeed=True)
        mark_succeeded_mock.assert_called_once()
        self.assertEqual(result, payment)

    @patch("payments.services.commands.mark_payment_failed_or_cancelled")
    def test_confirm_payment_simulator_calls_failed_on_false(self, mark_failed_mock):
        tx = create_transaction()
        payment = create_payment(tx=tx, status="REQUIRES_CONFIRMATION")
        mark_failed_mock.return_value = payment
        result = commands.confirm_payment_simulator(payment=payment, succeed=False)
        mark_failed_mock.assert_called_once()
        self.assertEqual(result, payment)

    @patch("payments.services.commands.mark_payment_succeeded")
    @patch("payments.services.commands.mark_payment_failed_or_cancelled")
    def test_confirm_payment_simulator_ignores_final_statuses(self, mark_failed_mock, mark_succeeded_mock):
        tx = create_transaction()
        payment = create_payment(tx=tx, status="SUCCEEDED")
        result = commands.confirm_payment_simulator(payment=payment, succeed=True)
        self.assertEqual(result, payment)
        mark_succeeded_mock.assert_not_called()
        mark_failed_mock.assert_not_called()


class ConfirmPaymentTests(TestCase):
    @patch("payments.services.commands.confirm_payment_simulator")
    def test_confirm_payment_delegates_to_sim_for_sim_provider(self, sim_mock):
        tx = create_transaction()
        payment = create_payment(tx=tx, status="REQUIRES_CONFIRMATION", provider="SIM")
        sim_mock.return_value = payment
        result = commands.confirm_payment(payment=payment, succeed=True)
        sim_mock.assert_called_once()
        self.assertEqual(result, payment)

    @patch("payments.services.commands.confirm_payment_simulator")
    def test_confirm_payment_noop_for_non_sim_provider(self, sim_mock):
        tx = create_transaction()
        payment = create_payment(tx=tx, status="REQUIRES_CONFIRMATION", provider="STRIPE")
        result = commands.confirm_payment(payment=payment, succeed=True)
        sim_mock.assert_not_called()
        self.assertEqual(result, payment)


class CancelActivePaymentTests(TestCase):
    @patch("payments.services.commands.mark_payment_failed_or_cancelled")
    def test_cancel_active_payment_sets_cancelled(self, mark_failed_mock):
        tx = create_transaction()
        payment = create_payment(tx=tx, status="REQUIRES_CONFIRMATION")
        mark_failed_mock.return_value = payment
        result = commands.cancel_active_payment(payment=payment, reason="cancel")
        mark_failed_mock.assert_called_once()
        self.assertEqual(result, payment)

    @patch("payments.services.commands.mark_payment_failed_or_cancelled")
    def test_cancel_active_payment_on_final_status_is_noop(self, mark_failed_mock):
        tx = create_transaction()
        payment = create_payment(tx=tx, status="SUCCEEDED")
        result = commands.cancel_active_payment(payment=payment, reason="cancel")
        mark_failed_mock.assert_not_called()
        self.assertEqual(result, payment)


class ExpireStalePaymentsTests(TestCase):
    def test_expire_stale_payments_cancels_only_old_active(self):
        tx1 = create_transaction()
        tx2 = create_transaction()
        tx3 = create_transaction()
        tx4 = create_transaction()

        old1 = create_payment(tx=tx1, status="REQUIRES_CONFIRMATION")
        old2 = create_payment(tx=tx2, status="PROCESSING")
        new = create_payment(tx=tx3, status="REQUIRES_CONFIRMATION")
        done = create_payment(tx=tx4, status="SUCCEEDED")

        long_ago = timezone.now() - timedelta(minutes=120)
        Payment.objects.filter(pk__in=[old1.pk, old2.pk]).update(updated_at=long_ago)

        count = commands.expire_stale_payments(minutes=30)
        self.assertEqual(count, 2)

        old1.refresh_from_db()
        old2.refresh_from_db()
        new.refresh_from_db()
        done.refresh_from_db()

        self.assertEqual(old1.status, "CANCELLED")
        self.assertEqual(old2.status, "CANCELLED")
        self.assertEqual(new.status, "REQUIRES_CONFIRMATION")
        self.assertEqual(done.status, "SUCCEEDED")


class CancelActivePaymentsForTxTests(TestCase):
    def test_cancel_active_payments_for_tx_cancels_confirmation_and_sets_metadata(self):
        tx = create_transaction()
        p_active = create_payment(tx=tx, status="REQUIRES_CONFIRMATION", metadata={})

        other_tx = create_transaction()
        p_other = create_payment(tx=other_tx, status="REQUIRES_CONFIRMATION", metadata={})

        result = commands.cancel_active_payments_for_tx(tx=tx, reason="Changed order")
        self.assertTrue(result)

        p_active.refresh_from_db()
        p_other.refresh_from_db()

        self.assertEqual(p_active.status, "CANCELLED")
        self.assertTrue(p_active.metadata.get("auto_cancelled_due_to_change"))
        self.assertEqual(p_active.metadata.get("auto_cancel_reason"), "Changed order")

        self.assertEqual(p_other.status, "REQUIRES_CONFIRMATION")
        self.assertFalse(p_other.metadata.get("auto_cancelled_due_to_change"))

    def test_cancel_active_payments_for_tx_cancels_processing_and_sets_metadata(self):
        tx = create_transaction()
        p_active = create_payment(tx=tx, status="PROCESSING", metadata={})

        result = commands.cancel_active_payments_for_tx(tx=tx, reason="")
        self.assertTrue(result)

        p_active.refresh_from_db()
        self.assertEqual(p_active.status, "CANCELLED")
        self.assertTrue(p_active.metadata.get("auto_cancelled_due_to_change"))
        self.assertNotIn("auto_cancel_reason", p_active.metadata)

    def test_cancel_active_payments_for_tx_cancels_requires_action_and_sets_metadata(self):
        tx = create_transaction()
        p = create_payment(tx=tx, status="REQUIRES_ACTION", metadata={})

        result = commands.cancel_active_payments_for_tx(tx=tx, reason="Changed order")
        self.assertTrue(result)

        p.refresh_from_db()
        self.assertEqual(p.status, "CANCELLED")
        self.assertTrue(p.metadata.get("auto_cancelled_due_to_change"))
        self.assertEqual(p.metadata.get("auto_cancel_reason"), "Changed order")

    def test_cancel_active_payments_for_tx_returns_false_when_nothing_to_cancel(self):
        tx = create_transaction()
        create_payment(tx=tx, status="SUCCEEDED")
        result = commands.cancel_active_payments_for_tx(tx=tx, reason="none")
        self.assertFalse(result)
