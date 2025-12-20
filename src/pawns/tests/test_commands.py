from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from pawns.models import PawnExtension
from pawns.services import commands
from pawns.services.exceptions import DomainError, Conflict
from pawns.services.fees import calc_extension_fee
from transactions.models import Transaction
from .factories import (
    create_user,
    create_seller_profile,
    create_customer,
    create_item_type,
    create_itemset,
    create_transaction,
    create_pawn,
    create_pawn_line,
)


class PawnFeeTests(TestCase):
    def test_calc_extension_fee_percentage_and_minimum(self):
        principal = Money(100, "PLN")
        fee_30 = calc_extension_fee(principal=principal, days=30)
        self.assertEqual(fee_30, Money(10, "PLN"))
        principal_small = Money(10, "PLN")
        fee_7 = calc_extension_fee(principal=principal_small, days=7)
        self.assertEqual(fee_7, Money(5, "PLN"))


class PawnCreatePawnTests(TestCase):
    def setUp(self):
        self.operator = create_user(email="pawn-operator@example.com")
        self.seller = create_seller_profile(owner=self.operator, slug="pawn-shop")
        self.customer = create_customer(email="pawn-cust@example.com")
        self.principal = Money(200, "PLN")

    def test_create_pawn_with_customer_and_lines(self):
        with patch("pawns.services.commands.snapshot_from_customer") as sfc:
            sfc.return_value = {"first_name": "Jan", "last_name": "Klient"}
            lines = [
                {
                    "title": "Telefon",
                    "description": "opis",
                    "quantity": 1,
                    "appraisal_value": Money(100, "PLN"),
                    "item_set": None,
                    "item_snapshot": {},
                },
                {
                    "title": "Laptop",
                    "description": "",
                    "quantity": 2,
                    "appraisal_value": Money(25, "PLN"),
                    "item_set": None,
                    "item_snapshot": {},
                },
            ]
            pawn = commands.create_pawn(
                operator=self.operator,
                seller=self.seller,
                principal=self.principal,
                due_in_days=14,
                customer=self.customer,
                customer_snapshot_override=None,
                lines=lines,
            )
        self.assertEqual(pawn.transaction.type, "PLEDGE")
        self.assertEqual(pawn.transaction.status, "COMPLETED")
        self.assertEqual(pawn.transaction.expected_total_amount, Decimal("0"))
        self.assertEqual(pawn.transaction.expected_total_currency, "PLN")
        self.assertEqual(pawn.customer, self.customer)
        self.assertEqual(pawn.customer_snapshot, {"first_name": "Jan", "last_name": "Klient"})
        self.assertEqual(pawn.lines.count(), 2)
        self.assertEqual(pawn.principal, self.principal)
        self.assertEqual(pawn.appraisal_total, Money(150, "PLN"))

    def test_create_pawn_uses_operator_snapshot_when_no_customer(self):
        with patch("pawns.services.commands.snapshot_from_user") as sfu:
            sfu.return_value = {"first_name": "Op", "last_name": "User"}
            pawn = commands.create_pawn(
                operator=self.operator,
                seller=self.seller,
                principal=self.principal,
                due_in_days=30,
                customer=None,
                customer_snapshot_override=None,
                lines=[],
            )
        self.assertIsNone(pawn.customer)
        self.assertEqual(pawn.customer_snapshot, {"first_name": "Op", "last_name": "User"})
        self.assertEqual(pawn.lines.count(), 0)

    def test_create_pawn_prefers_snapshot_override(self):
        override = {"first_name": "Override", "last_name": "Snapshot"}
        with patch("pawns.services.commands.snapshot_from_user") as sfu:
            pawn = commands.create_pawn(
                operator=self.operator,
                seller=self.seller,
                principal=self.principal,
                due_in_days=10,
                customer=None,
                customer_snapshot_override=override,
                lines=[],
            )
        self.assertEqual(pawn.customer_snapshot, override)


class PawnExtendTests(TestCase):
    def setUp(self):
        self.operator = create_user(email="extend-op@example.com")
        self.seller = create_seller_profile(owner=self.operator, slug="extend-shop")
        self.pawn = create_pawn(operator=self.operator, seller_profile=self.seller)

    def test_extend_pawn_creates_extension_and_moves_due_date(self):
        old_due = self.pawn.due_date
        with patch("pawns.services.commands.calc_extension_fee") as fee_mock:
            fee_mock.return_value = Money(7, "PLN")
            commands.extend_pawn(pawn=self.pawn, days=7, operator=self.operator)
        self.pawn.refresh_from_db()
        self.assertEqual(self.pawn.due_date, old_due + timedelta(days=7))
        ext = PawnExtension.objects.get(pawn=self.pawn)
        self.assertEqual(ext.days, 7)
        self.assertEqual(ext.fee, Money(7, "PLN"))
        self.assertEqual(ext.previous_due, old_due)
        self.assertEqual(ext.new_due, old_due + timedelta(days=7))
        self.assertEqual(ext.transaction.type, "PAWN_EXTENSION")
        self.assertEqual(ext.transaction.status, "COMPLETED")

    def test_extend_pawn_raises_conflict_for_non_active(self):
        self.pawn.status = "REDEEMED"
        self.pawn.save(update_fields=["status", "updated_at"])
        with self.assertRaises(Conflict):
            commands.extend_pawn(pawn=self.pawn, days=7, operator=self.operator)

    def test_extend_pawn_raises_conflict_for_expired(self):
        self.pawn.status = "ACTIVE"
        past_start = timezone.now().date() - timedelta(days=10)
        past_due = timezone.now().date() - timedelta(days=1)
        self.pawn.start_date = past_start
        self.pawn.due_date = past_due
        self.pawn.save(update_fields=["status", "start_date", "due_date", "updated_at"])
        with self.assertRaises(Conflict):
            commands.extend_pawn(pawn=self.pawn, days=7, operator=self.operator)

    def test_extend_pawn_raises_domain_error_for_invalid_days(self):
        with self.assertRaises(DomainError):
            commands.extend_pawn(pawn=self.pawn, days=5, operator=self.operator)


class PawnRedeemTests(TestCase):
    def setUp(self):
        self.operator = create_user(email="redeem-op@example.com")
        self.seller = create_seller_profile(owner=self.operator, slug="redeem-shop")
        self.pawn = create_pawn(operator=self.operator, seller_profile=self.seller, principal=Money(300, "PLN"))

    def test_redeem_pawn_creates_transaction_and_updates_status(self):
        pawn = commands.redeem_pawn(pawn=self.pawn, operator=self.operator)
        pawn.refresh_from_db()
        self.assertEqual(pawn.status, "REDEEMED")
        self.assertIsNotNone(pawn.redeemed_at)
        tx = Transaction.objects.filter(type="PAWN_REDEEM", expected_total_amount=pawn.principal.amount).first()
        self.assertIsNotNone(tx)

    def test_redeem_pawn_raises_conflict_when_not_active(self):
        self.pawn.status = "FORFEITED"
        self.pawn.save(update_fields=["status", "updated_at"])
        with self.assertRaises(Conflict):
            commands.redeem_pawn(pawn=self.pawn, operator=self.operator)


class PawnForfeitTests(TestCase):
    def setUp(self):
        self.operator = create_user(email="forfeit-op@example.com")
        self.seller = create_seller_profile(owner=self.operator, slug="forfeit-shop")
        self.item_type = create_item_type(name="Elektronika")
        self.item_set = create_itemset(
            seller_profile=self.seller,
            item_type=self.item_type,
            price=Money(100, "PLN"),
            stock_quantity=1,
        )
        past_start = timezone.now().date() - timedelta(days=10)
        past_due = timezone.now().date() - timedelta(days=1)
        self.pawn = create_pawn(
            operator=self.operator,
            seller_profile=self.seller,
            principal=Money(200, "PLN"),
            start_date=past_start,
            due_date=past_due,
            status="ACTIVE",
        )
        create_pawn_line(self.pawn, title="Telefon", appraisal_value=Money(150, "PLN"), item_set=self.item_set)
        self.pawn.recalc_appraisal(save=True)
        self.pawn.refresh_from_db()

    def test_forfeit_pawn_creates_listing_when_expired(self):
        pawn = commands.forfeit_pawn(pawn=self.pawn, operator=self.operator, create_listing=True)
        pawn.refresh_from_db()
        self.assertEqual(pawn.status, "FORFEITED")
        self.assertIsNotNone(pawn.forfeited_at)
        self.assertIsNotNone(pawn.forfeited_item)
        item = pawn.forfeited_item
        self.assertEqual(item.seller_profile, pawn.seller_profile)
        self.assertEqual(item.listing_type, "BUY")
        self.assertFalse(item.allow_online_checkout)
        self.assertEqual(item.price, pawn.appraisal_total)
        self.assertEqual(item.status, "AVAILABLE")
        self.assertEqual(item.stock_quantity, 1)
        self.assertEqual(item.type, self.item_type)

    def test_forfeit_pawn_without_listing_does_not_create_item(self):
        pawn = commands.forfeit_pawn(pawn=self.pawn, operator=self.operator, create_listing=False)
        pawn.refresh_from_db()
        self.assertEqual(pawn.status, "FORFEITED")
        self.assertIsNone(pawn.forfeited_item)

    def test_forfeit_pawn_raises_conflict_if_not_active(self):
        self.pawn.status = "CANCELLED"
        self.pawn.save(update_fields=["status", "updated_at"])
        with self.assertRaises(Conflict):
            commands.forfeit_pawn(pawn=self.pawn, operator=self.operator, create_listing=True)

    def test_forfeit_pawn_raises_conflict_if_not_expired(self):
        future_due = timezone.now().date() + timedelta(days=5)
        self.pawn.due_date = future_due
        self.pawn.save(update_fields=["due_date", "updated_at"])
        with self.assertRaises(Conflict):
            commands.forfeit_pawn(pawn=self.pawn, operator=self.operator, create_listing=True)


class PawnExtensionTransactionTests(TestCase):
    def setUp(self):
        self.operator = create_user(email="ext-op@example.com")
        self.seller = create_seller_profile(owner=self.operator, slug="ext-shop")
        self.customer = create_customer(email="extcust@example.com")
        self.pawn = create_pawn(
            operator=self.operator,
            seller_profile=self.seller,
            customer=self.customer,
            principal=Money(100, "PLN"),
        )
        self.pawn.customer_snapshot = {"first_name": "Jan", "last_name": "Klient"}
        self.pawn.save(update_fields=["customer_snapshot", "updated_at"])

    def test_create_extension_transaction_creates_pending_tx_with_context(self):
        with patch("pawns.services.commands.calc_extension_fee") as fee_mock:
            fee = Money(7, "PLN")
            fee_mock.return_value = fee
            tx = commands.create_extension_transaction(pawn=self.pawn, days=7, operator=self.operator)
        self.assertEqual(tx.type, "PAWN_EXTENSION")
        self.assertEqual(tx.status, "PENDING")
        self.assertEqual(tx.expected_total_amount, fee.amount)
        self.assertEqual(tx.expected_total_currency, "PLN")
        self.assertEqual(tx.customer, self.pawn.customer)
        self.assertEqual(tx.customer_snapshot, self.pawn.customer_snapshot)
        self.assertEqual(tx.notes, f"PAWN_EXT:{self.pawn.public_id}:7")

    def test_create_extension_transaction_raises_conflict_for_non_active(self):
        self.pawn.status = "CANCELLED"
        self.pawn.save(update_fields=["status", "updated_at"])
        with self.assertRaises(Conflict):
            commands.create_extension_transaction(pawn=self.pawn, days=7, operator=self.operator)

    def test_create_extension_transaction_raises_conflict_for_expired(self):
        past_start = timezone.now().date() - timedelta(days=10)
        past_due = timezone.now().date() - timedelta(days=1)
        self.pawn.start_date = past_start
        self.pawn.due_date = past_due
        self.pawn.save(update_fields=["start_date", "due_date", "updated_at"])
        with self.assertRaises(Conflict):
            commands.create_extension_transaction(pawn=self.pawn, days=7, operator=self.operator)

    def test_create_extension_transaction_raises_domain_error_for_invalid_days(self):
        with self.assertRaises(DomainError):
            commands.create_extension_transaction(pawn=self.pawn, days=5, operator=self.operator)


class FinalizeExtensionAfterPaymentTests(TestCase):
    def setUp(self):
        self.operator = create_user(email="final-op@example.com")
        self.seller = create_seller_profile(owner=self.operator, slug="final-shop")
        self.pawn = create_pawn(operator=self.operator, seller_profile=self.seller, principal=Money(100, "PLN"))
        self.old_due = self.pawn.due_date
        self.tx = create_transaction(
            user=self.operator,
            type="PAWN_EXTENSION",
            status="COMPLETED",
            expected_total_amount=0,
            currency="PLN",
        )
        self.tx.notes = f"PAWN_EXT:{self.pawn.public_id}:7"
        self.tx.save(update_fields=["notes", "updated_at"])

    def test_finalize_extension_after_payment_creates_extension_and_moves_due_date(self):
        with patch("pawns.services.commands.calc_extension_fee") as fee_mock:
            fee = Money(5, "PLN")
            fee_mock.return_value = fee
            pawn = commands.finalize_extension_after_payment(tx=self.tx)
        self.assertEqual(pawn, self.pawn)
        self.pawn.refresh_from_db()
        self.assertEqual(self.pawn.due_date, self.old_due + timedelta(days=7))
        ext = PawnExtension.objects.filter(transaction=self.tx).first()
        self.assertIsNotNone(ext)
        self.assertEqual(ext.days, 7)
        self.assertEqual(ext.fee, fee)
        self.assertEqual(ext.previous_due, self.old_due)
        self.assertEqual(ext.new_due, self.old_due + timedelta(days=7))

    def test_finalize_extension_after_payment_is_idempotent(self):
        with patch("pawns.services.commands.calc_extension_fee") as fee_mock:
            fee_mock.return_value = Money(5, "PLN")
            commands.finalize_extension_after_payment(tx=self.tx)
        count_before = PawnExtension.objects.filter(transaction=self.tx).count()
        pawn = commands.finalize_extension_after_payment(tx=self.tx)
        self.assertEqual(count_before, PawnExtension.objects.filter(transaction=self.tx).count())
        self.assertEqual(pawn, self.pawn)

    def test_finalize_extension_after_payment_ignores_non_extension_or_non_completed(self):
        tx2 = create_transaction(
            user=self.operator,
            type="PLEDGE",
            status="COMPLETED",
            expected_total_amount=0,
            currency="PLN",
        )
        res = commands.finalize_extension_after_payment(tx=tx2)
        self.assertIsNone(res)
        tx3 = create_transaction(
            user=self.operator,
            type="PAWN_EXTENSION",
            status="PENDING",
            expected_total_amount=0,
            currency="PLN",
        )
        res2 = commands.finalize_extension_after_payment(tx=tx3)
        self.assertIsNone(res2)


class PawnCustomerCommandsTests(TestCase):
    def setUp(self):
        self.operator = create_user(email="cust-op@example.com")
        self.seller = create_seller_profile(owner=self.operator, slug="cust-shop")
        self.pawn = create_pawn(operator=self.operator, seller_profile=self.seller)

    def test_attach_and_detach_customer(self):
        c = create_customer(email="attach@example.com")
        commands.attach_customer_to_pawn(pawn=self.pawn, customer=c, update_snapshot=True)
        self.pawn.refresh_from_db()
        self.assertEqual(self.pawn.customer, c)
        self.assertIsInstance(self.pawn.customer_snapshot, dict)
        commands.detach_customer_from_pawn(pawn=self.pawn)
        self.pawn.refresh_from_db()
        self.assertIsNone(self.pawn.customer)

    def test_ensure_customer_created_when_not_exists(self):
        res = commands.ensure_customer_for_pawn(
            pawn=self.pawn,
            first_name="Nowy",
            last_name="Klient",
            email="newpawn@example.com",
            phone="111222333",
            address={"line1": "Ulica", "postal_code": "00-001", "city": "Miasto", "country": "PL"},
            document_type="ID",
            document_number="ABC123",
        )
        self.assertEqual(res["result"], "created")
        self.assertTrue(res.get("customer_public_id"))
        self.pawn.refresh_from_db()
        self.assertIsNotNone(self.pawn.customer)
        self.assertEqual(self.pawn.customer.email, "newpawn@example.com")

    def test_ensure_customer_attaches_existing_by_email(self):
        c = create_customer(email="exists@example.com")
        res = commands.ensure_customer_for_pawn(
            pawn=self.pawn,
            first_name="Jan",
            last_name="Klient",
            email="exists@example.com",
            phone="123456789",
        )
        self.pawn.refresh_from_db()
        self.assertEqual(res["result"], "attached")
        self.assertEqual(self.pawn.customer, c)

    def test_ensure_customer_attaches_existing_by_phone(self):
        c = create_customer(email="phone@example.com", phone="555666777")
        res = commands.ensure_customer_for_pawn(
            pawn=self.pawn,
            first_name="Jan",
            last_name="Test",
            email="",
            phone="555666777",
        )
        self.pawn.refresh_from_db()
        self.assertEqual(res["result"], "attached")
        self.assertEqual(self.pawn.customer, c)

    def test_ensure_customer_conflict_returns_candidates(self):
        c1 = create_customer(email="conf@example.com")
        c2 = create_customer(email="jan.b@example.com", phone="999888777")
        res = commands.ensure_customer_for_pawn(
            pawn=self.pawn,
            first_name="X",
            last_name="Y",
            email="conf@example.com",
            phone="999888777",
        )
        self.assertEqual(res["result"], "conflict")
        self.assertEqual(len(res["candidates"]), 2)
        emails = {c["email"] for c in res["candidates"]}
        self.assertSetEqual(emails, {"conf@example.com", "jan.b@example.com"})
