from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from djmoney.money import Money

from pawns.services import commands
from pawns.services.exceptions import DomainError, Conflict
from pawns.services.fees import calc_extension_fee


class PawnFeeUnitTests(SimpleTestCase):
    def test_calc_extension_fee_percentage_and_minimum(self):
        principal = Money(100, "PLN")
        fee_30 = calc_extension_fee(principal=principal, days=30)
        self.assertEqual(fee_30, Money(10, "PLN"))

        principal_small = Money(10, "PLN")
        fee_7 = calc_extension_fee(principal=principal_small, days=7)
        self.assertEqual(fee_7, Money(5, "PLN"))


class PawnHelpersUnitTests(SimpleTestCase):
    @patch("pawns.services.commands.timezone")
    def test_pawn_is_expired_true_only_for_active_and_past_due(self, mock_tz):
        mock_tz.now.return_value = SimpleNamespace(date=lambda: date(2026, 1, 10))

        pawn = SimpleNamespace(due_date=date(2026, 1, 9), status="ACTIVE")
        self.assertTrue(commands.pawn_is_expired(pawn))

        pawn2 = SimpleNamespace(due_date=date(2026, 1, 10), status="ACTIVE")
        self.assertFalse(commands.pawn_is_expired(pawn2))

        pawn3 = SimpleNamespace(due_date=date(2026, 1, 9), status="CANCELLED")
        self.assertFalse(commands.pawn_is_expired(pawn3))

    def test_snapshot_from_itemset_builds_expected_keys(self):
        it = SimpleNamespace(
            public_id="IT1",
            set_name="Telefon",
            slug="telefon",
            description="opis",
            price=Money(123, "PLN"),
            condition="USED",
            length_cm=10,
            width_cm=5,
            height_cm=2,
            weight_kg=0.3,
            type_id=1,
            type=SimpleNamespace(path="ELEC.PHONE"),
            catalog_item_id=None,
            attributes={"color": "black"},
            seller_profile_id=1,
            seller_profile=SimpleNamespace(slug="shop"),
        )
        snap = commands._snapshot_from_itemset(it, unit_price=None)
        self.assertEqual(snap["public_id"], "IT1")
        self.assertEqual(snap["set_name"], "Telefon")
        self.assertEqual(snap["currency"], "PLN")
        self.assertEqual(snap["type_path"], "ELEC.PHONE")
        self.assertEqual(snap["seller_slug"], "shop")


class CreatePawnUnitTests(SimpleTestCase):
    def _mk_operator(self):
        return SimpleNamespace(id=1, public_id="U1", email="op@example.com")

    def _mk_seller(self):
        return SimpleNamespace(id=10, public_id="S1", slug="shop", company_name="Shop")

    @patch("pawns.services.commands.repo")
    @patch("pawns.services.commands.snapshot_from_user")
    @patch("pawns.services.commands.snapshot_from_customer")
    @patch("pawns.services.commands.timezone")
    def test_create_pawn_creates_tx_pawn_and_lines_and_recalc(
        self,
        mock_tz,
        mock_snap_customer,
        mock_snap_user,
        mock_repo,
    ):
        mock_tz.now.return_value = SimpleNamespace(date=lambda: date(2026, 1, 6))
        mock_snap_customer.return_value = {"x": "cust"}
        mock_snap_user.return_value = {"x": "op"}

        operator = self._mk_operator()
        seller = self._mk_seller()
        customer = SimpleNamespace(id=55, public_id="C1")

        principal = Money(200, "PLN")

        tx = SimpleNamespace(id=100, pk=100)
        mock_repo.create_transaction.return_value = tx

        pawn = SimpleNamespace(
            id=500,
            public_id="P1",
            principal=principal,
            due_date=None,
            recalc_appraisal=MagicMock(),
        )
        mock_repo.create_pawn.return_value = pawn

        item = SimpleNamespace(
            public_id="IT1",
            set_name="Telefon",
            slug="telefon",
            description="",
            price=Money(100, "PLN"),
            condition="USED",
            length_cm=None,
            width_cm=None,
            height_cm=None,
            weight_kg=None,
            type_id=1,
            type=SimpleNamespace(path="ELEC.PHONE"),
            catalog_item_id=None,
            attributes={},
            seller_profile_id=1,
            seller_profile=SimpleNamespace(slug="shop"),
        )

        lines = [
            {"item_set": item, "quantity": 2, "appraisal_value": Money(50, "PLN")},  # brak title -> z item_set
            {
                "title": "Zegarek",
                "description": "opis",
                "quantity": 1,
                "appraisal_value": Money(25, "PLN"),
                "item_set": None,
                "item_snapshot": {"type_path": "WATCH"},
            },
        ]

        out = commands.create_pawn.__wrapped__(
            operator=operator,
            seller=seller,
            principal=principal,
            due_in_days=14,
            customer=customer,
            customer_snapshot_override=None,
            lines=lines,
        )

        self.assertIs(out, pawn)

        mock_repo.create_transaction.assert_called_once()
        _, tx_kwargs = mock_repo.create_transaction.call_args
        self.assertEqual(tx_kwargs["type"], "PLEDGE")
        self.assertEqual(tx_kwargs["status"], "COMPLETED")
        self.assertEqual(tx_kwargs["expected_total_amount"], 0)
        self.assertEqual(tx_kwargs["expected_total_currency"], "PLN")

        mock_repo.create_pawn.assert_called_once()
        _, pawn_kwargs = mock_repo.create_pawn.call_args
        self.assertEqual(pawn_kwargs["seller"], seller)
        self.assertEqual(pawn_kwargs["operator"], operator)
        self.assertEqual(pawn_kwargs["customer"], customer)
        self.assertEqual(pawn_kwargs["customer_snapshot"], {"x": "cust"})
        self.assertEqual(pawn_kwargs["start_date"], date(2026, 1, 6))
        self.assertEqual(pawn_kwargs["due_date"], date(2026, 1, 20))

        self.assertEqual(mock_repo.add_pawn_line.call_count, 2)
        first_call = mock_repo.add_pawn_line.call_args_list[0]
        _, first_kwargs = first_call
        self.assertEqual(first_kwargs["title"], "Telefon")
        self.assertEqual(first_kwargs["quantity"], 2)
        self.assertTrue(isinstance(first_kwargs["item_snapshot"], dict))
        self.assertEqual(first_kwargs["item_snapshot"]["public_id"], "IT1")

        second_call = mock_repo.add_pawn_line.call_args_list[1]
        _, second_kwargs = second_call
        self.assertEqual(second_kwargs["title"], "Zegarek")
        self.assertEqual(second_kwargs["item_snapshot"], {"type_path": "WATCH"})

        pawn.recalc_appraisal.assert_called_once_with(save=True)

    @patch("pawns.services.commands.repo")
    @patch("pawns.services.commands.snapshot_from_user")
    @patch("pawns.services.commands.timezone")
    def test_create_pawn_prefers_snapshot_override(self, mock_tz, mock_snap_user, mock_repo):
        mock_tz.now.return_value = SimpleNamespace(date=lambda: date(2026, 1, 6))
        mock_snap_user.return_value = {"x": "op"}

        tx = SimpleNamespace(id=1, pk=1)
        mock_repo.create_transaction.return_value = tx

        pawn = SimpleNamespace(recalc_appraisal=MagicMock())
        mock_repo.create_pawn.return_value = pawn

        override = {"first_name": "A", "last_name": "B"}

        commands.create_pawn.__wrapped__(
            operator=self._mk_operator(),
            seller=self._mk_seller(),
            principal=Money(100, "PLN"),
            due_in_days=30,
            customer=None,
            customer_snapshot_override=override,
            lines=[],
        )

        _, pawn_kwargs = mock_repo.create_pawn.call_args
        self.assertEqual(pawn_kwargs["customer_snapshot"], override)
        mock_snap_user.assert_not_called()

    @patch("pawns.services.commands.repo")
    @patch("pawns.services.commands.snapshot_from_user")
    @patch("pawns.services.commands.timezone")
    def test_create_pawn_uses_operator_snapshot_when_no_customer_and_no_override(self, mock_tz, mock_snap_user, mock_repo):
        mock_tz.now.return_value = SimpleNamespace(date=lambda: date(2026, 1, 6))
        mock_snap_user.return_value = {"x": "op"}

        tx = SimpleNamespace(id=1, pk=1)
        mock_repo.create_transaction.return_value = tx

        pawn = SimpleNamespace(recalc_appraisal=MagicMock())
        mock_repo.create_pawn.return_value = pawn

        commands.create_pawn.__wrapped__(
            operator=self._mk_operator(),
            seller=self._mk_seller(),
            principal=Money(100, "PLN"),
            due_in_days=30,
            customer=None,
            customer_snapshot_override=None,
            lines=[],
        )

        _, pawn_kwargs = mock_repo.create_pawn.call_args
        self.assertEqual(pawn_kwargs["customer_snapshot"], {"x": "op"})


class ExtendPawnUnitTests(SimpleTestCase):
    def _mk_pawn(self):
        return SimpleNamespace(
            status="ACTIVE",
            due_date=date(2026, 1, 20),
            principal=Money(200, "PLN"),
            save=MagicMock(),
        )

    @patch("pawns.services.commands.repo")
    @patch("pawns.services.commands.calc_extension_fee")
    @patch("pawns.services.commands.pawn_is_expired", return_value=False)
    def test_extend_pawn_success_moves_due_and_creates_extension(self, mock_exp, mock_fee, mock_repo):
        pawn = self._mk_pawn()
        operator = SimpleNamespace(id=1)

        fee = Money(7, "PLN")
        mock_fee.return_value = fee

        tx = SimpleNamespace(id=10, pk=10)
        mock_repo.create_transaction.return_value = tx

        commands.extend_pawn.__wrapped__(pawn=pawn, days=7, operator=operator)

        self.assertEqual(pawn.due_date, date(2026, 1, 27))
        pawn.save.assert_called_once()
        _, save_kwargs = pawn.save.call_args
        self.assertIn("due_date", save_kwargs["update_fields"])

        mock_repo.create_transaction.assert_called_once()
        _, tx_kwargs = mock_repo.create_transaction.call_args
        self.assertEqual(tx_kwargs["type"], "PAWN_EXTENSION")
        self.assertEqual(tx_kwargs["status"], "COMPLETED")
        self.assertEqual(tx_kwargs["expected_total_amount"], fee.amount)
        self.assertEqual(tx_kwargs["expected_total_currency"], "PLN")

        mock_repo.create_extension.assert_called_once()
        _, ext_kwargs = mock_repo.create_extension.call_args
        self.assertEqual(ext_kwargs["days"], 7)
        self.assertEqual(ext_kwargs["fee"], fee)
        self.assertEqual(ext_kwargs["previous_due"], date(2026, 1, 20))
        self.assertEqual(ext_kwargs["new_due"], date(2026, 1, 27))
        self.assertEqual(ext_kwargs["tx"], tx)
        self.assertEqual(ext_kwargs["operator"], operator)

    @patch("pawns.services.commands.pawn_is_expired", return_value=True)
    def test_extend_pawn_rejects_expired(self, _mock_exp):
        pawn = self._mk_pawn()
        with self.assertRaises(Conflict):
            commands.extend_pawn.__wrapped__(pawn=pawn, days=7, operator=SimpleNamespace(id=1))

    def test_extend_pawn_rejects_non_active(self):
        pawn = self._mk_pawn()
        pawn.status = "REDEEMED"
        with self.assertRaises(Conflict):
            commands.extend_pawn.__wrapped__(pawn=pawn, days=7, operator=SimpleNamespace(id=1))

    def test_extend_pawn_rejects_invalid_days(self):
        pawn = self._mk_pawn()
        with self.assertRaises(DomainError):
            commands.extend_pawn.__wrapped__(pawn=pawn, days=5, operator=SimpleNamespace(id=1))


class RedeemPawnUnitTests(SimpleTestCase):
    @patch("pawns.services.commands.repo")
    @patch("pawns.services.commands.timezone")
    def test_redeem_pawn_success_creates_tx_and_sets_status(self, mock_tz, mock_repo):
        mock_tz.now.return_value = datetime(2026, 1, 6, 12, 0, 0)

        pawn = SimpleNamespace(
            status="ACTIVE",
            principal=Money(300, "PLN"),
            redeemed_at=None,
            save=MagicMock(),
        )
        operator = SimpleNamespace(id=1)

        commands.redeem_pawn.__wrapped__(pawn=pawn, operator=operator)

        mock_repo.create_transaction.assert_called_once()
        _, tx_kwargs = mock_repo.create_transaction.call_args
        self.assertEqual(tx_kwargs["type"], "PAWN_REDEEM")
        self.assertEqual(tx_kwargs["status"], "COMPLETED")
        self.assertEqual(tx_kwargs["expected_total_amount"], pawn.principal.amount)
        self.assertEqual(tx_kwargs["expected_total_currency"], "PLN")

        self.assertEqual(pawn.status, "REDEEMED")
        self.assertEqual(pawn.redeemed_at, datetime(2026, 1, 6, 12, 0, 0))
        pawn.save.assert_called_once()

    def test_redeem_pawn_rejects_non_active(self):
        pawn = SimpleNamespace(status="FORFEITED", principal=Money(10, "PLN"))
        with self.assertRaises(Conflict):
            commands.redeem_pawn.__wrapped__(pawn=pawn, operator=SimpleNamespace(id=1))


class ForfeitPawnUnitTests(SimpleTestCase):
    def _mk_pawn(self):
        lines = SimpleNamespace(
            select_related=lambda *a, **k: SimpleNamespace(
                first=lambda: SimpleNamespace(title="Towar z zastawu")
            )
        )
        return SimpleNamespace(
            status="ACTIVE",
            forfeited_at=None,
            forfeited_item=None,
            forfeited_item_id=None,
            appraisal_total=Money(150, "PLN"),
            seller_profile=SimpleNamespace(id=1, slug="shop"),
            lines=lines,
            save=MagicMock(),
        )

    @patch("pawns.services.commands.pawn_is_expired", return_value=False)
    def test_forfeit_pawn_rejects_not_expired(self, _mexp):
        pawn = self._mk_pawn()
        with self.assertRaises(Conflict):
            commands.forfeit_pawn.__wrapped__(pawn=pawn, operator=SimpleNamespace(id=1), create_listing=True)

    def test_forfeit_pawn_rejects_non_active(self):
        pawn = self._mk_pawn()
        pawn.status = "CANCELLED"
        with self.assertRaises(Conflict):
            commands.forfeit_pawn.__wrapped__(pawn=pawn, operator=SimpleNamespace(id=1), create_listing=True)

    @patch("pawns.services.commands.pawn_is_expired", return_value=True)
    def test_forfeit_pawn_create_listing_false_does_not_create_item(self, _mexp):
        pawn = self._mk_pawn()
        with patch("pawns.services.commands.ItemSet") as mock_itemset_model:
            out = commands.forfeit_pawn.__wrapped__(pawn=pawn, operator=SimpleNamespace(id=1), create_listing=False)
            self.assertIs(out, pawn)
            mock_itemset_model.objects.create.assert_not_called()
            self.assertEqual(pawn.status, "FORFEITED")
            self.assertIsNotNone(pawn.forfeited_at)

    @patch("pawns.services.commands.pawn_is_expired", return_value=True)
    @patch("pawns.services.commands._pick_itemtype_for_listing")
    @patch("pawns.services.commands.ItemSet")
    @patch("pawns.services.commands.timezone")
    def test_forfeit_pawn_creates_listing_when_expired(
        self,
        mock_tz,
        mock_itemset_model,
        mock_pick_type,
        _mexp,
    ):
        mock_tz.now.return_value = datetime(2026, 1, 6, 12, 0, 0)

        pawn = self._mk_pawn()
        operator = SimpleNamespace(id=1)

        itype = SimpleNamespace(id=99, path="ELEC.PHONE")
        mock_pick_type.return_value = itype

        created_item = SimpleNamespace(id=777)
        mock_itemset_model.objects.create.return_value = created_item

        out = commands.forfeit_pawn.__wrapped__(pawn=pawn, operator=operator, create_listing=True)
        self.assertIs(out, pawn)

        self.assertEqual(pawn.status, "FORFEITED")
        self.assertEqual(pawn.forfeited_at, datetime(2026, 1, 6, 12, 0, 0))
        self.assertIs(pawn.forfeited_item, created_item)

        mock_itemset_model.objects.create.assert_called_once()
        _, kwargs = mock_itemset_model.objects.create.call_args
        self.assertEqual(kwargs["price"], pawn.appraisal_total)
        self.assertEqual(kwargs["stock_quantity"], 1)
        self.assertEqual(kwargs["status"], "RESERVED")
        self.assertEqual(kwargs["listing_type"], "BUY")
        self.assertFalse(kwargs["allow_online_checkout"])
        self.assertEqual(kwargs["type"], itype)

    @patch("pawns.services.commands.pawn_is_expired", return_value=True)
    @patch("pawns.services.commands._pick_itemtype_for_listing", return_value=None)
    def test_forfeit_pawn_raises_when_no_itemtype_and_create_listing_true(self, _mpick, _mexp):
        pawn = self._mk_pawn()
        with self.assertRaises(Conflict):
            commands.forfeit_pawn.__wrapped__(pawn=pawn, operator=SimpleNamespace(id=1), create_listing=True)

    @patch("pawns.services.commands.pawn_is_expired", return_value=True)
    @patch("pawns.services.commands.ItemSet")
    def test_forfeit_pawn_is_idempotent_when_forfeited_item_id_exists(self, mock_itemset_model, _mexp):
        pawn = self._mk_pawn()
        pawn.forfeited_item_id = 123
        out = commands.forfeit_pawn.__wrapped__(pawn=pawn, operator=SimpleNamespace(id=1), create_listing=True)
        self.assertIs(out, pawn)
        mock_itemset_model.objects.create.assert_not_called()


class CreateExtensionTransactionUnitTests(SimpleTestCase):
    def _mk_pawn(self):
        return SimpleNamespace(
            status="ACTIVE",
            principal=Money(100, "PLN"),
            customer=SimpleNamespace(id=1),
            customer_snapshot={"a": 1},
            public_id="P1",
            due_date=date(2099, 1, 1),
        )

    def test_create_extension_transaction_rejects_invalid_days(self):
        pawn = self._mk_pawn()
        with self.assertRaises(DomainError):
            commands.create_extension_transaction.__wrapped__(pawn=pawn, days=5, operator=SimpleNamespace(id=1))

    @patch("pawns.services.commands.pawn_is_expired", return_value=True)
    def test_create_extension_transaction_rejects_expired(self, _mexp):
        pawn = self._mk_pawn()
        with self.assertRaises(Conflict):
            commands.create_extension_transaction.__wrapped__(pawn=pawn, days=7, operator=SimpleNamespace(id=1))

    def test_create_extension_transaction_rejects_non_active(self):
        pawn = self._mk_pawn()
        pawn.status = "CANCELLED"
        with self.assertRaises(Conflict):
            commands.create_extension_transaction.__wrapped__(pawn=pawn, days=7, operator=SimpleNamespace(id=1))

    @patch("pawns.services.commands.repo")
    @patch("pawns.services.commands.calc_extension_fee")
    @patch("pawns.services.commands.pawn_is_expired", return_value=False)
    def test_create_extension_transaction_sets_context_and_notes(self, _mexp, mock_fee, mock_repo):
        pawn = self._mk_pawn()
        operator = SimpleNamespace(id=10)

        fee = Money(7, "PLN")
        mock_fee.return_value = fee

        tx = SimpleNamespace(
            type="PAWN_EXTENSION",
            status="PENDING",
            expected_total_amount=None,
            expected_total_currency=None,
            customer=None,
            customer_snapshot=None,
            notes="",
            save=MagicMock(),
        )
        mock_repo.create_transaction.return_value = tx

        out = commands.create_extension_transaction.__wrapped__(pawn=pawn, days=7, operator=operator)
        self.assertIs(out, tx)

        mock_repo.create_transaction.assert_called_once()
        _, tx_kwargs = mock_repo.create_transaction.call_args
        self.assertEqual(tx_kwargs["type"], "PAWN_EXTENSION")
        self.assertEqual(tx_kwargs["status"], "PENDING")
        self.assertEqual(tx_kwargs["expected_total_amount"], fee.amount)
        self.assertEqual(tx_kwargs["expected_total_currency"], "PLN")

        self.assertEqual(tx.customer, pawn.customer)
        self.assertEqual(tx.customer_snapshot, pawn.customer_snapshot)
        self.assertEqual(tx.notes, "PAWN_EXT:P1:7")
        self.assertEqual(tx.save.call_count, 2)


class FinalizeExtensionAfterPaymentUnitTests(SimpleTestCase):
    def _mk_tx(self, *, status="COMPLETED", notes="PAWN_EXT:P1:7"):
        return SimpleNamespace(type="PAWN_EXTENSION", status=status, notes=notes)

    def _mk_pawn(self):
        return SimpleNamespace(
            status="ACTIVE",
            public_id="P1",
            principal=Money(100, "PLN"),
            due_date=date(2026, 1, 20),
            save=MagicMock(),
        )

    def test_finalize_extension_ignores_wrong_type_or_status(self):
        tx1 = SimpleNamespace(type="PLEDGE", status="COMPLETED", notes="PAWN_EXT:P1:7")
        self.assertIsNone(commands.finalize_extension_after_payment.__wrapped__(tx=tx1))

        tx2 = SimpleNamespace(type="PAWN_EXTENSION", status="PENDING", notes="PAWN_EXT:P1:7")
        self.assertIsNone(commands.finalize_extension_after_payment.__wrapped__(tx=tx2))

    @patch("pawns.services.commands.PawnExtension")
    def test_finalize_extension_idempotent_when_extension_already_exists(self, mock_ext_model):
        pawn = self._mk_pawn()
        existing = SimpleNamespace(pawn=pawn)

        mock_ext_model.objects.filter.return_value.select_related.return_value.first.return_value = existing

        tx = self._mk_tx()
        out = commands.finalize_extension_after_payment.__wrapped__(tx=tx)
        self.assertIs(out, pawn)

    @patch("pawns.services.commands.repo")
    @patch("pawns.services.commands.calc_extension_fee")
    @patch("pawns.services.commands.pawn_is_expired", return_value=False)
    @patch("pawns.services.commands.Pawn")
    @patch("pawns.services.commands.PawnExtension")
    def test_finalize_extension_creates_extension_and_moves_due(
        self,
        mock_ext_model,
        mock_pawn_model,
        _mexp,
        mock_fee,
        mock_repo,
    ):
        mock_ext_model.objects.filter.return_value.select_related.return_value.first.return_value = None

        pawn = self._mk_pawn()
        mock_pawn_model.objects.select_for_update.return_value.filter.return_value.first.return_value = pawn

        fee = Money(5, "PLN")
        mock_fee.return_value = fee

        tx = self._mk_tx(notes="PAWN_EXT:P1:7")
        tx.user = SimpleNamespace(id=1)

        out = commands.finalize_extension_after_payment.__wrapped__(tx=tx)
        self.assertIs(out, pawn)

        self.assertEqual(pawn.due_date, date(2026, 1, 27))
        pawn.save.assert_called_once()

        mock_repo.create_extension.assert_called_once()
        _, ext_kwargs = mock_repo.create_extension.call_args
        self.assertEqual(ext_kwargs["pawn"], pawn)
        self.assertEqual(ext_kwargs["days"], 7)
        self.assertEqual(ext_kwargs["fee"], fee)
        self.assertEqual(ext_kwargs["previous_due"], date(2026, 1, 20))
        self.assertEqual(ext_kwargs["new_due"], date(2026, 1, 27))
        self.assertEqual(ext_kwargs["tx"], tx)
        self.assertEqual(ext_kwargs["operator"], tx.user)

    @patch("pawns.services.commands.PawnExtension")
    def test_finalize_extension_returns_none_for_malformed_notes(self, mock_ext_model):
        mock_ext_model.objects.filter.return_value.select_related.return_value.first.return_value = None
        tx = self._mk_tx(notes="BAD:P1:7")
        out = commands.finalize_extension_after_payment.__wrapped__(tx=tx)
        self.assertIsNone(out)

    @patch("pawns.services.commands.PawnExtension")
    @patch("pawns.services.commands.Pawn")
    def test_finalize_extension_returns_none_when_pawn_not_found(self, mock_pawn_model, mock_ext_model):
        mock_ext_model.objects.filter.return_value.select_related.return_value.first.return_value = None
        mock_pawn_model.objects.select_for_update.return_value.filter.return_value.first.return_value = None
        tx = self._mk_tx(notes="PAWN_EXT:NOPE:7")
        out = commands.finalize_extension_after_payment.__wrapped__(tx=tx)
        self.assertIsNone(out)

    @patch("pawns.services.commands.PawnExtension")
    @patch("pawns.services.commands.Pawn")
    @patch("pawns.services.commands.pawn_is_expired", return_value=True)
    def test_finalize_extension_returns_none_when_pawn_expired_or_not_active(self, _mexp, mock_pawn_model, mock_ext_model):
        mock_ext_model.objects.filter.return_value.select_related.return_value.first.return_value = None
        pawn = self._mk_pawn()
        mock_pawn_model.objects.select_for_update.return_value.filter.return_value.first.return_value = pawn

        tx = self._mk_tx(notes="PAWN_EXT:P1:7")
        out = commands.finalize_extension_after_payment.__wrapped__(tx=tx)
        self.assertIsNone(out)
