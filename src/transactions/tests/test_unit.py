from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from djmoney.money import Money

from transactions.services import commands
from transactions.services.discounts import DiscountResult
from transactions.services.exceptions import DomainError, Conflict


class TransactionsCommandsUnitTests(SimpleTestCase):
    def _mk_orders(self, *grand_totals: Money):
        orders = []
        for gt in grand_totals:
            orders.append(SimpleNamespace(grand_total=gt))
        return SimpleNamespace(all=MagicMock(return_value=orders))

    def _mk_tx(
        self,
        *,
        type: str = "PURCHASE",
        status: str = "PENDING",
        currency: str = "PLN",
        expected_total_amount: Decimal | None = None,
        user_id: int | None = 1,
        coupon=None,
        user_coupon=None,
    ):
        tx = SimpleNamespace(
            id=1,
            pk=1,
            public_id="TX1",
            type=type,
            status=status,
            expected_total_amount=expected_total_amount,
            expected_total_currency=currency,
            user_id=user_id,
            coupon=coupon,
            coupon_id=getattr(coupon, "id", None),
            user_coupon=user_coupon,
            user_coupon_id=getattr(user_coupon, "id", None),
            orders=self._mk_orders(),
            save=MagicMock(),
        )
        return tx

    def test_attach_coupon_rejects_non_purchase(self):
        tx = self._mk_tx(type="PAWN_EXTENSION", currency="PLN")
        with self.assertRaises(DomainError) as cm:
            commands.attach_coupon_and_recalculate.__wrapped__(transaction=tx, coupon_code="X", user_coupon_public_id=None)
        self.assertEqual(str(cm.exception.detail), "Kupony nie są dostępne dla tej transakcji.")

    def test_attach_coupon_conflict_when_both_inputs(self):
        tx = self._mk_tx(type="PURCHASE", currency="PLN")
        with self.assertRaises(Conflict) as cm:
            commands.attach_coupon_and_recalculate.__wrapped__(transaction=tx, coupon_code="X", user_coupon_public_id="UC1")
        self.assertIn("Podaj kod kuponu albo kupon użytkownika", str(cm.exception.detail))

    @patch("transactions.services.commands.Coupon")
    def test_attach_coupon_invalid_code_domain_error(self, CouponModel):
        tx = self._mk_tx(type="PURCHASE", currency="PLN")
        qs = MagicMock()
        qs.first.return_value = None
        CouponModel.objects.filter.return_value = qs
        with self.assertRaises(DomainError) as cm:
            commands.attach_coupon_and_recalculate.__wrapped__(transaction=tx, coupon_code="BAD", user_coupon_public_id=None)
        self.assertEqual(str(cm.exception.detail), "Nieprawidłowy kod kuponu.")

    @patch("transactions.services.commands.UserCoupon")
    def test_attach_coupon_invalid_user_coupon_domain_error(self, UCModel):
        tx = self._mk_tx(type="PURCHASE", currency="PLN")
        qs = MagicMock()
        qs.first.return_value = None
        UCModel.objects.select_related.return_value.filter.return_value = qs
        with self.assertRaises(DomainError) as cm:
            commands.attach_coupon_and_recalculate.__wrapped__(transaction=tx, coupon_code="", user_coupon_public_id="UCX")
        self.assertEqual(str(cm.exception.detail), "Kupon użytkownika nie istnieje.")

    @patch("transactions.services.commands.validate_and_compute_discount")
    def test_attach_coupon_clears_when_no_inputs(self, validate_mock):
        tx = self._mk_tx(type="PURCHASE", currency="PLN")
        tx.orders = self._mk_orders(Money(100, "PLN"))
        tx.coupon = SimpleNamespace(id=10)
        tx.coupon_id = 10
        tx.user_coupon = SimpleNamespace(id=11)
        tx.user_coupon_id = 11
        validate_mock.return_value = DiscountResult(ok=True, reason=None, discount=Money(0, "PLN"))

        out = commands.attach_coupon_and_recalculate.__wrapped__(transaction=tx, coupon_code="", user_coupon_public_id="")
        self.assertIs(out, tx)
        self.assertIsNone(tx.coupon)
        self.assertIsNone(tx.user_coupon)
        self.assertEqual(Decimal(str(tx.expected_total_amount)), Decimal("100"))
        self.assertEqual(tx.expected_total_currency, "PLN")
        tx.save.assert_called_once()

    @patch("transactions.services.commands.UserCoupon")
    def test_attach_coupon_user_coupon_must_belong_to_user(self, UCModel):
        tx = self._mk_tx(type="PURCHASE", currency="PLN", user_id=1)
        coupon = SimpleNamespace(id=55)
        uc = SimpleNamespace(id=99, public_id="UC99", user_id=2, coupon=coupon)
        qs = MagicMock()
        qs.first.return_value = uc
        UCModel.objects.select_related.return_value.filter.return_value = qs

        with self.assertRaises(Conflict) as cm:
            commands.attach_coupon_and_recalculate.__wrapped__(transaction=tx, coupon_code="", user_coupon_public_id="UC99")
        self.assertEqual(str(cm.exception.detail), "Ten kupon użytkownika nie należy do tego klienta.")

    @patch("transactions.services.commands.validate_and_compute_discount")
    @patch("transactions.services.commands.Coupon")
    def test_attach_coupon_success_sets_coupon_and_recomputes(self, CouponModel, validate_mock):
        tx = self._mk_tx(type="PURCHASE", currency="PLN")
        tx.orders = self._mk_orders(Money(100, "PLN"), Money(50, "PLN"))
        coupon = SimpleNamespace(id=7, public_id="C7", code="SAVE10")
        qs = MagicMock()
        qs.first.return_value = coupon
        CouponModel.objects.filter.return_value = qs

        validate_mock.return_value = DiscountResult(ok=True, reason=None, discount=Money(10, "PLN"))

        out = commands.attach_coupon_and_recalculate.__wrapped__(transaction=tx, coupon_code="SAVE10", user_coupon_public_id=None)
        self.assertIs(out, tx)
        self.assertEqual(tx.coupon, coupon)
        self.assertEqual(Decimal(str(tx.expected_total_amount)), Decimal("140"))
        self.assertEqual(tx.expected_total_currency, "PLN")
        tx.save.assert_called_once()

    @patch("transactions.services.commands.validate_and_compute_discount")
    @patch("transactions.services.commands.Coupon")
    def test_attach_coupon_maps_reason_to_message(self, CouponModel, validate_mock):
        tx = self._mk_tx(type="PURCHASE", currency="PLN")
        tx.orders = self._mk_orders(Money(100, "PLN"))
        coupon = SimpleNamespace(id=7, public_id="C7", code="EXP")
        qs = MagicMock()
        qs.first.return_value = coupon
        CouponModel.objects.filter.return_value = qs

        validate_mock.return_value = DiscountResult(ok=False, reason="Coupon expired", discount=Money(0, "PLN"))

        with self.assertRaises(Conflict) as cm:
            commands.attach_coupon_and_recalculate.__wrapped__(transaction=tx, coupon_code="EXP", user_coupon_public_id=None)
        self.assertEqual(str(cm.exception.detail), "Kupon wygasł.")

    @patch("transactions.services.commands.validate_and_compute_discount")
    def test_recompute_expected_total_non_purchase_keeps_amount_and_sets_currency(self, validate_mock):
        tx = self._mk_tx(type="PAWN_EXTENSION", currency="", expected_total_amount=Decimal("50.00"))
        commands._recompute_expected_total(tx)
        self.assertEqual(Decimal(str(tx.expected_total_amount)), Decimal("50.00"))
        self.assertEqual(tx.expected_total_currency, "PLN")
        validate_mock.assert_not_called()

    @patch("transactions.services.commands.validate_and_compute_discount")
    def test_recompute_expected_total_purchase_sums_orders_no_coupon(self, validate_mock):
        tx = self._mk_tx(type="PURCHASE", currency="PLN")
        tx.orders = self._mk_orders(Money(100, "PLN"), Money(50, "PLN"))
        tx.coupon = None
        tx.user_coupon = None
        validate_mock.return_value = DiscountResult(ok=True, reason=None, discount=Money(0, "PLN"))
        commands._recompute_expected_total(tx)
        self.assertEqual(Decimal(str(tx.expected_total_amount)), Decimal("150"))
        self.assertEqual(tx.expected_total_currency, "PLN")

    @patch("transactions.services.commands.validate_and_compute_discount")
    def test_recompute_expected_total_never_negative(self, validate_mock):
        tx = self._mk_tx(type="PURCHASE", currency="PLN")
        tx.orders = self._mk_orders(Money(50, "PLN"))
        validate_mock.return_value = DiscountResult(ok=True, reason=None, discount=Money(200, "PLN"))
        commands._recompute_expected_total(tx)
        self.assertEqual(Decimal(str(tx.expected_total_amount)), Decimal("0"))
        self.assertEqual(tx.expected_total_currency, "PLN")

    def test_set_transaction_status_rejects_invalid_status(self):
        tx = self._mk_tx(type="PURCHASE", status="PENDING", currency="PLN")
        with self.assertRaises(DomainError) as cm:
            commands.set_transaction_status.__wrapped__(tx=tx, to_status="XXX", reason="")
        self.assertEqual(str(cm.exception.detail), "Invalid status")

    def test_set_transaction_status_rejects_disallowed_transition(self):
        tx = self._mk_tx(type="PURCHASE", status="COMPLETED", currency="PLN")
        with self.assertRaises(Conflict) as cm:
            commands.set_transaction_status.__wrapped__(tx=tx, to_status="PENDING", reason="")
        self.assertIn("Transition COMPLETED → PENDING", str(cm.exception.detail))

    @patch("django.utils.timezone.now")
    def test_set_transaction_status_completed_marks_user_coupon_redeemed(self, now_mock):
        now_mock.return_value = SimpleNamespace()
        uc = SimpleNamespace(id=10, redeemed=False, redeemed_at=None, save=MagicMock())
        tx = self._mk_tx(type="PURCHASE", status="PENDING", currency="PLN", user_coupon=uc)
        tx.user_coupon_id = 10
        commands.set_transaction_status.__wrapped__(tx=tx, to_status="COMPLETED", reason="")
        self.assertEqual(tx.status, "COMPLETED")
        self.assertTrue(uc.redeemed)
        self.assertIsNotNone(uc.redeemed_at)
        uc.save.assert_called_once()

    def test_set_transaction_status_non_purchase_does_not_touch_user_coupon(self):
        uc = SimpleNamespace(id=10, redeemed=False, redeemed_at=None, save=MagicMock())
        tx = self._mk_tx(type="PAWN_EXTENSION", status="PENDING", currency="PLN", user_coupon=uc)
        tx.user_coupon_id = 10
        commands.set_transaction_status.__wrapped__(tx=tx, to_status="COMPLETED", reason="")
        self.assertEqual(tx.status, "COMPLETED")
        self.assertFalse(uc.redeemed)
        uc.save.assert_not_called()

    @patch("transactions.services.commands._base_total_for")
    @patch("transactions.services.commands.validate_and_compute_discount")
    def test_preview_coupon_discount_purchase_formats_amounts(self, validate_mock, base_mock):
        tx = self._mk_tx(type="PURCHASE", currency="PLN")
        base_mock.return_value = Money(100, "PLN")
        validate_mock.return_value = DiscountResult(ok=True, reason=None, discount=Money(10, "PLN"))

        out = commands.preview_coupon_discount.__wrapped__(tx=tx, coupon_code=None, user_coupon_public_id=None)

        self.assertTrue(out["ok"])
        self.assertIsNone(out["reason"])
        self.assertEqual(out["gross_amount"], "100.00")
        self.assertEqual(out["discount_amount"], "10.00")
        self.assertEqual(out["net_amount"], "90.00")

    def test_preview_coupon_discount_non_purchase_returns_not_available(self):
        tx = self._mk_tx(type="PAWN_EXTENSION", currency="PLN", expected_total_amount=Decimal("50.00"))
        out = commands.preview_coupon_discount.__wrapped__(tx=tx, coupon_code="X", user_coupon_public_id=None)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "Coupons are not available for this transaction.")
        self.assertEqual(out["gross_amount"], "50.00")
        self.assertEqual(out["discount_amount"], "0.00")
        self.assertEqual(out["net_amount"], "50.00")

    @patch("transactions.services.commands.Transaction")
    @patch("transactions.services.commands.set_transaction_status")
    def test_cancel_stale_pending_transactions_cancels_only_old(self, set_status_mock, TxModel):
        tx1 = self._mk_tx(type="PURCHASE", status="PENDING", currency="PLN")
        tx2 = self._mk_tx(type="PURCHASE", status="PENDING", currency="PLN")

        TxModel.objects.select_for_update.return_value.filter.return_value = [tx1, tx2]
        set_status_mock.side_effect = lambda tx, to_status, reason="": tx

        out = commands.cancel_stale_pending_transactions.__wrapped__(minutes=60)
        self.assertEqual(out, 2)
        self.assertEqual(set_status_mock.call_count, 2)
