from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from djmoney.money import Money

from payments.services import commands
from payments.services.exceptions import Forbidden, DomainError, Conflict


class PaymentsUnitTests(SimpleTestCase):
    def _mk_orders_for_payment(self, *, currency: str = "PLN", gross: Money = Money(100, "PLN")):
        shipping = SimpleNamespace(price=Money(10, currency), package_type_id=None)
        ln = SimpleNamespace(shipping=shipping)
        order_lines = SimpleNamespace(
            select_related=MagicMock(return_value=[ln]),
            all=MagicMock(return_value=[ln]),
        )
        order = SimpleNamespace(
            grand_total=gross,
            order_lines=order_lines,
            shipping_address={},
        )
        return SimpleNamespace(all=MagicMock(return_value=[order]))

    def _mk_tx(
        self,
        *,
        status: str = "PENDING",
        type: str = "PURCHASE",
        expected_total_amount: Decimal = Decimal("100.00"),
        currency: str = "PLN",
        coupon=None,
        user_coupon=None,
    ):
        tx = SimpleNamespace(
            id=1,
            pk=1,
            public_id="TX1",
            status=status,
            type=type,
            expected_total_amount=expected_total_amount,
            expected_total_currency=currency,
            coupon=coupon,
            coupon_id=getattr(coupon, "id", None),
            user_coupon=user_coupon,
            user_coupon_id=getattr(user_coupon, "id", None),
            user=SimpleNamespace(id=1),
            orders=self._mk_orders_for_payment(currency=currency, gross=Money(100, currency)),
        )
        return tx

    def _mk_payment(self, *, tx, status: str = "REQUIRES_CONFIRMATION", amount: Money | None = None, metadata=None):
        p = SimpleNamespace(
            id=10,
            pk=10,
            public_id="P1",
            transaction=tx,
            status=status,
            amount=amount or Money(tx.expected_total_amount or 0, tx.expected_total_currency or "PLN"),
            metadata=metadata or {},
            save=MagicMock(),
        )
        return p

    @patch("payments.services.commands.Transaction")
    @patch("payments.services.commands.attach_coupon_and_recalculate")
    def test_create_payment_rejects_non_pending(self, attach_mock, TxModel):
        tx = self._mk_tx(status="COMPLETED", type="PURCHASE")
        TxModel.objects.select_for_update.return_value.get.return_value = tx

        with self.assertRaises(Forbidden):
            commands.create_payment_for_transaction.__wrapped__(tx=tx)

        attach_mock.assert_not_called()

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("payments.services.commands.Transaction")
    @patch("payments.services.commands.Payment")
    @patch("payments.services.commands.repo")
    @patch("payments.services.commands._ensure_purchase_tx_stock_available_and_reserve")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_returns_existing_active_payment(
        self,
        addr_ok_mock,
        ensure_reserve_mock,
        repo_mock,
        PaymentModel,
        TxModel,
    ):
        tx = self._mk_tx(status="PENDING", type="PURCHASE", expected_total_amount=Decimal("100.00"))
        TxModel.objects.select_for_update.return_value.get.return_value = tx

        existing = SimpleNamespace(id=999)
        PaymentModel.objects.select_for_update.return_value.filter.return_value.order_by.return_value.first.return_value = existing

        out = commands.create_payment_for_transaction.__wrapped__(
            tx=tx,
            provider="SIM",
            coupon_code=None,
            user_coupon_public_id=None,
        )
        self.assertIs(out, existing)
        repo_mock.create_payment.assert_not_called()

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("payments.services.commands.Transaction")
    @patch("payments.services.commands.Payment")
    @patch("payments.services.commands.repo")
    @patch("payments.services.commands._ensure_purchase_tx_stock_available_and_reserve")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_amount_must_be_positive(self, addr_ok_mock, ensure_reserve_mock, repo_mock, PaymentModel, TxModel):
        tx = self._mk_tx(status="PENDING", type="PURCHASE", expected_total_amount=Decimal("0.00"))
        TxModel.objects.select_for_update.return_value.get.return_value = tx

        PaymentModel.objects.select_for_update.return_value.filter.return_value.order_by.return_value.first.return_value = None

        with self.assertRaises(DomainError):
            commands.create_payment_for_transaction.__wrapped__(
                tx=tx,
                provider="SIM",
                coupon_code=None,
                user_coupon_public_id=None,
            )

        repo_mock.create_payment.assert_not_called()

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("payments.services.commands.Transaction")
    @patch("payments.services.commands.Payment")
    @patch("payments.services.commands.repo")
    @patch("payments.services.commands._ensure_purchase_tx_stock_available_and_reserve")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_sets_discount_metadata_for_coupon(
        self,
        addr_ok_mock,
        ensure_reserve_mock,
        repo_mock,
        PaymentModel,
        TxModel,
    ):
        coupon = SimpleNamespace(id=1, public_id="C1", code="SAVE10")
        tx = self._mk_tx(status="PENDING", type="PURCHASE", expected_total_amount=Decimal("90.00"), coupon=coupon)
        tx.coupon_id = 1
        tx.orders = self._mk_orders_for_payment(gross=Money(100, "PLN"))
        TxModel.objects.select_for_update.return_value.get.return_value = tx

        PaymentModel.objects.select_for_update.return_value.filter.return_value.order_by.return_value.first.return_value = None

        created = SimpleNamespace(provider="SIM", amount=Money(90, "PLN"), metadata={})

        def _create_payment(**kwargs):
            created.provider = kwargs.get("provider")
            created.amount = kwargs.get("amount")
            created.metadata = kwargs.get("metadata")
            return created

        repo_mock.create_payment.side_effect = _create_payment

        out = commands.create_payment_for_transaction.__wrapped__(
            tx=tx,
            provider="SIM",
            coupon_code=None,
            user_coupon_public_id=None,
        )
        self.assertIs(out, created)
        self.assertEqual(Decimal(created.metadata.get("discount_applied")), Decimal("10"))
        cm = created.metadata.get("coupon") or {}
        self.assertEqual(cm.get("mode"), "code")
        self.assertEqual(cm.get("coupon_public_id"), "C1")
        self.assertEqual(cm.get("code"), "SAVE10")
        self.assertEqual(Decimal(cm.get("discount")), Decimal("10"))

    @override_settings(STRIPE_SECRET_KEY="sk", STRIPE_PUBLISHABLE_KEY="pk")
    @patch("payments.services.commands.Transaction")
    @patch("payments.services.commands.Payment")
    @patch("payments.services.commands.StripeClient")
    @patch("payments.services.commands.repo")
    @patch("payments.services.commands._ensure_purchase_tx_stock_available_and_reserve")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_uses_stripe_when_available(
        self,
        addr_ok_mock,
        ensure_reserve_mock,
        repo_mock,
        StripeClientCls,
        PaymentModel,
        TxModel,
    ):
        tx = self._mk_tx(status="PENDING", type="PURCHASE", expected_total_amount=Decimal("100.00"))
        TxModel.objects.select_for_update.return_value.get.return_value = tx

        PaymentModel.objects.select_for_update.return_value.filter.return_value.order_by.return_value.first.return_value = None

        StripeClientCls.return_value.create_intent.return_value = ("pi_1", "cs_1")

        created = SimpleNamespace(provider="STRIPE", provider_payment_id="pi_1", client_secret="cs_1")
        repo_mock.create_payment.return_value = created

        out = commands.create_payment_for_transaction.__wrapped__(
            tx=tx,
            provider="STRIPE",
            coupon_code=None,
            user_coupon_public_id=None,
        )
        self.assertIs(out, created)
        StripeClientCls.return_value.create_intent.assert_called_once()
        self.assertEqual(out.provider, "STRIPE")

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("payments.services.commands.Transaction")
    @patch("payments.services.commands.Payment")
    @patch("payments.services.commands.repo")
    @patch("payments.services.commands._ensure_purchase_tx_stock_available_and_reserve")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_integrity_error_returns_revived(
        self,
        addr_ok_mock,
        ensure_reserve_mock,
        repo_mock,
        PaymentModel,
        TxModel,
    ):
        tx = self._mk_tx(status="PENDING", type="PURCHASE", expected_total_amount=Decimal("100.00"))
        TxModel.objects.select_for_update.return_value.get.return_value = tx

        PaymentModel.objects.select_for_update.return_value.filter.return_value.order_by.return_value.first.return_value = None

        revived = SimpleNamespace(id=777)
        PaymentModel.objects.filter.return_value.order_by.return_value.first.return_value = revived

        from django.db import IntegrityError
        repo_mock.create_payment.side_effect = IntegrityError("uq")

        out = commands.create_payment_for_transaction.__wrapped__(
            tx=tx,
            provider="SIM",
            coupon_code=None,
            user_coupon_public_id=None,
        )
        self.assertEqual(out.id, 777)

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
    @patch("payments.services.commands.Transaction")
    @patch("payments.services.commands.Payment")
    @patch("payments.services.commands.repo")
    @patch("payments.services.commands._ensure_purchase_tx_stock_available_and_reserve")
    @patch("orders.services.commands._addr_ok", return_value=True)
    def test_create_payment_integrity_error_no_revived_raises_conflict(
        self,
        addr_ok_mock,
        ensure_reserve_mock,
        repo_mock,
        PaymentModel,
        TxModel,
    ):
        tx = self._mk_tx(status="PENDING", type="PURCHASE", expected_total_amount=Decimal("100.00"))
        TxModel.objects.select_for_update.return_value.get.return_value = tx

        PaymentModel.objects.select_for_update.return_value.filter.return_value.order_by.return_value.first.return_value = None
        PaymentModel.objects.filter.return_value.order_by.return_value.first.return_value = None

        from django.db import IntegrityError
        repo_mock.create_payment.side_effect = IntegrityError("uq")

        with self.assertRaises(Conflict) as cm:
            commands.create_payment_for_transaction.__wrapped__(
                tx=tx,
                provider="SIM",
                coupon_code=None,
                user_coupon_public_id=None,
            )
        self.assertEqual(str(cm.exception.detail), "Istnieje już aktywna płatność dla tej transakcji.")

    @patch("payments.services.commands.Payment")
    @patch("payments.services.commands.set_transaction_status")
    @patch("payments.services.commands.loyalty_add_points")
    @patch("payments.services.commands._notify_order_confirmed")
    def test_mark_payment_succeeded_cancels_other_active_payments(
        self,
        notify_mock,
        add_points_mock,
        set_status_mock,
        PaymentModel,
    ):
        tx = self._mk_tx(status="PENDING", type="PURCHASE", expected_total_amount=Decimal("100.00"))
        main = self._mk_payment(tx=tx, status="REQUIRES_CONFIRMATION", metadata={})
        other1 = self._mk_payment(tx=tx, status="PROCESSING", metadata={})
        other2 = self._mk_payment(tx=tx, status="REQUIRES_ACTION", metadata={})

        qs = MagicMock()
        qs.filter.return_value.exclude.return_value = [other1, other2]
        PaymentModel.objects.select_for_update.return_value = qs

        out = commands.mark_payment_succeeded.__wrapped__(payment=main, reason="ok")
        self.assertIs(out, main)
        self.assertEqual(main.status, "SUCCEEDED")
        self.assertEqual(other1.status, "CANCELLED")
        self.assertTrue(other1.metadata.get("auto_cancelled_due_to_success"))
        self.assertEqual(other2.status, "CANCELLED")
        self.assertTrue(other2.metadata.get("auto_cancelled_due_to_success"))
        set_status_mock.assert_called_once()
        add_points_mock.assert_called_once()
        notify_mock.assert_called_once()

    @patch("payments.services.commands.Payment")
    def test_cancel_active_payments_for_tx_cancels_all_active_statuses(self, PaymentModel):
        tx = self._mk_tx(status="PENDING", type="PURCHASE", expected_total_amount=Decimal("100.00"))
        p1 = self._mk_payment(tx=tx, status="REQUIRES_CONFIRMATION", metadata={})
        p2 = self._mk_payment(tx=tx, status="PROCESSING", metadata={})
        p3 = self._mk_payment(tx=tx, status="REQUIRES_ACTION", metadata={})

        qs = MagicMock()
        qs.filter.return_value = [p1, p2, p3]
        PaymentModel.objects.select_for_update.return_value = qs

        out = commands.cancel_active_payments_for_tx.__wrapped__(tx=tx, reason="Changed")
        self.assertTrue(out)
        self.assertEqual(p1.status, "CANCELLED")
        self.assertEqual(p2.status, "CANCELLED")
        self.assertEqual(p3.status, "CANCELLED")
        self.assertTrue(p1.metadata.get("auto_cancelled_due_to_change"))
        self.assertEqual(p1.metadata.get("auto_cancel_reason"), "Changed")

    @patch("payments.services.commands.Payment")
    @patch("payments.services.commands.cancel_active_payment")
    def test_expire_stale_payments_calls_cancel_for_old_active(self, cancel_mock, PaymentModel):
        p1 = self._mk_payment(tx=self._mk_tx(), status="REQUIRES_CONFIRMATION")
        p2 = self._mk_payment(tx=self._mk_tx(), status="PROCESSING")

        PaymentModel.objects.select_related.return_value.filter.return_value = [p1, p2]

        out = commands.expire_stale_payments.__wrapped__(minutes=30)
        self.assertEqual(out, 2)
        self.assertEqual(cancel_mock.call_count, 2)
