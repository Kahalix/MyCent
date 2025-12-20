from __future__ import annotations

from django.test import TestCase
from django.db import IntegrityError
from djmoney.money import Money

from payments.models import Payment
from .factories import create_transaction, create_payment


class PaymentModelTests(TestCase):
    def test_str_contains_provider_and_public_id(self):
        tx = create_transaction()
        payment = create_payment(tx=tx, amount=Money(100, "PLN"))
        s = str(payment)
        self.assertIn(payment.provider, s)
        self.assertIn(payment.public_id, s)

    def test_unique_active_payment_per_transaction(self):
        tx = create_transaction()
        create_payment(tx=tx, status="REQUIRES_CONFIRMATION")
        with self.assertRaises(IntegrityError):
            create_payment(tx=tx, status="PROCESSING")

    def test_non_active_payments_can_coexist_for_transaction(self):
        tx = create_transaction()
        p1 = create_payment(tx=tx, status="SUCCEEDED")
        p2 = create_payment(tx=tx, status="FAILED")
        self.assertNotEqual(p1.id, p2.id)

    def test_unique_provider_and_payment_id_when_not_empty(self):
        tx1 = create_transaction()
        tx2 = create_transaction()
        create_payment(tx=tx1, provider="SIM", provider_payment_id="PID123")
        with self.assertRaises(IntegrityError):
            create_payment(tx=tx2, provider="SIM", provider_payment_id="PID123")

    def test_empty_provider_payment_id_not_subject_to_uniqueness(self):
        tx1 = create_transaction()
        tx2 = create_transaction()
        create_payment(tx=tx1, provider="SIM", provider_payment_id="")
        create_payment(tx=tx2, provider="SIM", provider_payment_id="")
        self.assertEqual(Payment.objects.count(), 2)

    def test_default_values(self):
        tx = create_transaction()
        payment = Payment.objects.create(transaction=tx)
        self.assertEqual(payment.provider, "SIM")
        self.assertEqual(payment.status, "REQUIRES_CONFIRMATION")
        self.assertEqual(payment.amount, Money(0, "PLN"))
