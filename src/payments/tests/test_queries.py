from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from payments.models import Payment
from payments.services import repositories as repo
from payments.filters import PaymentFilter
from .factories import (
    create_user,
    create_seller_profile,
    create_seller_membership,
    create_transaction,
    create_order,
    create_payment,
)


class PaymentRepositoryTests(TestCase):
    def test_get_by_public_id_returns_payment(self):
        tx = create_transaction()
        payment = create_payment(tx=tx)
        res = repo.get_by_public_id(payment.public_id)
        self.assertEqual(res, payment)

    def test_get_by_public_id_returns_none_for_unknown(self):
        res = repo.get_by_public_id("non-existent")
        self.assertIsNone(res)

    def test_list_for_user_returns_payments_ordered(self):
        u1 = create_user(email="u1@example.com")
        u2 = create_user(email="u2@example.com")
        tx1 = create_transaction(user=u1, amount=Decimal("50.00"))
        tx2 = create_transaction(user=u1, amount=Decimal("60.00"))
        tx3 = create_transaction(user=u2, amount=Decimal("70.00"))
        p1 = create_payment(tx=tx1)
        p2 = create_payment(tx=tx2)
        create_payment(tx=tx3)
        qs = repo.list_for_user(u1)
        res = list(qs)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].pk, p2.pk)
        self.assertEqual(res[1].pk, p1.pk)

    def test_list_for_seller_returns_payments_for_seller_orders(self):
        seller_user = create_user(email="seller@example.com")
        other_user = create_user(email="other@example.com")
        seller_profile1 = create_seller_profile(owner=seller_user, slug="shop1")
        seller_profile2 = create_seller_profile(owner=other_user, slug="shop2")
        create_seller_membership(seller_profile=seller_profile1, user=seller_user, is_active=True)

        tx1 = create_transaction(user=create_user(email="buyer1@example.com"), amount=Decimal("100.00"))
        tx2 = create_transaction(user=create_user(email="buyer2@example.com"), amount=Decimal("200.00"))
        tx_other = create_transaction(user=create_user(email="buyer3@example.com"), amount=Decimal("150.00"))

        order1 = create_order(tx=tx1, seller_profile=seller_profile1)
        order2 = create_order(tx=tx2, seller_profile=seller_profile1)
        create_order(tx=tx_other, seller_profile=seller_profile2)

        p1 = create_payment(tx=tx1)
        p2 = create_payment(tx=tx2)
        create_payment(tx=tx_other)

        qs = repo.list_for_seller(seller_user)
        res = set(qs)
        self.assertEqual(res, {p1, p2})

    def test_list_for_admin_returns_all_payments(self):
        tx1 = create_transaction(amount=Decimal("10.00"))
        tx2 = create_transaction(amount=Decimal("20.00"))
        p1 = create_payment(tx=tx1)
        p2 = create_payment(tx=tx2)
        qs = repo.list_for_admin()
        res = list(qs)
        self.assertEqual(set(res), {p1, p2})

    def test_create_and_save_payment_helpers(self):
        tx = create_transaction(amount=Decimal("50.00"))
        p = repo.create_payment(
            tx=tx,
            provider="SIM",
            amount=Money(50, "PLN"),
            status="REQUIRES_CONFIRMATION",
            metadata={"foo": "bar"},
        )
        self.assertIsInstance(p, Payment)
        p.metadata["foo"] = "baz"
        repo.save_payment(p)
        p2 = Payment.objects.get(pk=p.pk)
        self.assertEqual(p2.metadata.get("foo"), "baz")


class PaymentFilterTests(TestCase):
    def test_filter_search_matches_public_id_and_transaction_public_id(self):
        tx1 = create_transaction()
        tx2 = create_transaction()
        p1 = create_payment(tx=tx1)
        p2 = create_payment(tx=tx2)
        p1.public_id = "PAY-ABC"
        p1.save(update_fields=["public_id", "updated_at"])
        tx2.public_id = "TX-ABC"
        tx2.save(update_fields=["public_id", "updated_at"])

        f = PaymentFilter(data={"search": "ABC"}, queryset=Payment.objects.all())
        res = set(f.qs)
        self.assertEqual(res, {p1, p2})

    def test_filter_active_true_returns_only_active_statuses(self):
        tx1 = create_transaction()
        tx2 = create_transaction()
        tx3 = create_transaction()
        tx4 = create_transaction()
        p1 = create_payment(tx=tx1, status="REQUIRES_CONFIRMATION")
        p2 = create_payment(tx=tx2, status="REQUIRES_ACTION")
        p3 = create_payment(tx=tx3, status="PROCESSING")
        create_payment(tx=tx4, status="SUCCEEDED")

        f = PaymentFilter(data={"active": "true"}, queryset=Payment.objects.all())
        res = set(f.qs)
        self.assertEqual(res, {p1, p2, p3})

    def test_filter_active_false_excludes_active_statuses(self):
        tx1 = create_transaction()
        tx2 = create_transaction()
        create_payment(tx=tx1, status="REQUIRES_CONFIRMATION")
        p2 = create_payment(tx=tx2, status="FAILED")

        f = PaymentFilter(data={"active": "false"}, queryset=Payment.objects.all())
        res = list(f.qs)
        self.assertEqual(res, [p2])
