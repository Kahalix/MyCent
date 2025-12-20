from __future__ import annotations
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from transactions.models import Transaction, TransactionStatusHistory
from .factories import create_user, create_transaction


class TransactionModelTests(TestCase):
    def test_str_contains_type_and_public_id(self):
        user = create_user("txuser@example.com")
        tx = create_transaction(user=user, type="PURCHASE", status="PENDING")
        s = str(tx)
        self.assertIn("PURCHASE", s)
        self.assertIn(tx.public_id, s)

    def test_expected_total_nonnegative_constraint(self):
        user = create_user("neg@example.com")
        with self.assertRaises(IntegrityError):
            Transaction.objects.create(
                user=user,
                type="PURCHASE",
                status="PENDING",
                expected_total_amount=Decimal("-1.00"),
                expected_total_currency="PLN",
            )


class TransactionStatusHistoryTests(TestCase):
    def test_history_created_on_transaction_create(self):
        user = create_user("hist@example.com")
        tx = create_transaction(user=user, status="PENDING")
        self.assertEqual(tx.status_history.count(), 1)
        entry = tx.status_history.first()
        self.assertEqual(entry.from_status, "")
        self.assertEqual(entry.to_status, "PENDING")
        self.assertEqual(entry.reason, "created")

    def test_history_created_on_status_change(self):
        user = create_user("hist2@example.com")
        tx = create_transaction(user=user, status="PENDING")
        tx.status = "COMPLETED"
        tx.save()
        history = list(tx.status_history.order_by("created_at"))
        self.assertEqual(len(history), 2)
        last = history[-1]
        self.assertEqual(last.from_status, "PENDING")
        self.assertEqual(last.to_status, "COMPLETED")

    def test_status_history_str_contains_public_id_and_statuses(self):
        user = create_user("hist3@example.com")
        tx = create_transaction(user=user, status="PENDING")
        entry = tx.status_history.first()
        s = str(entry)
        self.assertIn(tx.public_id, s)
        self.assertIn("PENDING", s)
        self.assertIn("→", s)
