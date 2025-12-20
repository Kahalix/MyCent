from __future__ import annotations
from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from transactions.services import repositories as repo
from .factories import (
    create_user,
    create_transaction,
    create_seller_profile,
    create_seller_membership,
    create_order_for_transaction,
)


class TransactionRepositoryTests(TestCase):
    def test_get_tx_by_public_id_returns_transaction_with_prefetches(self):
        user = create_user("repo1@example.com")
        tx = create_transaction(
            user=user,
            expected_total_amount=Decimal("10.00"),
            expected_total_currency="PLN",
        )
        fetched = repo.get_tx_by_public_id(tx.public_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, tx.id)
        self.assertEqual(fetched.user_id, user.id)

    def test_user_transactions_qs_returns_only_given_user(self):
        user1 = create_user("repo2a@example.com")
        user2 = create_user("repo2b@example.com")
        tx1 = create_transaction(user=user1)
        tx2 = create_transaction(user=user2)
        qs1 = repo.user_transactions_qs(user1)
        self.assertIn(tx1, qs1)
        self.assertNotIn(tx2, qs1)

    def test_seller_transactions_qs_returns_transactions_for_seller_memberships(self):
        seller_user = create_user("seller@example.com")
        other_user = create_user("other@example.com")
        buyer = create_user("buyer@example.com")
        seller_profile = create_seller_profile(owner=seller_user)
        create_seller_membership(seller_profile, seller_user, role="OWNER", is_active=True)
        seller_profile_other = create_seller_profile(owner=other_user, slug="seller-other")
        create_seller_membership(seller_profile_other, other_user, role="OWNER", is_active=True)
        tx1 = create_transaction(user=buyer)
        tx2 = create_transaction(user=buyer)
        tx3 = create_transaction(user=buyer)
        create_order_for_transaction(tx1, seller_profile, buyer=buyer, grand_total=Money(100, "PLN"))
        create_order_for_transaction(tx2, seller_profile_other, buyer=buyer, grand_total=Money(50, "PLN"))
        qs = repo.seller_transactions_qs(seller_user)
        self.assertIn(tx1, qs)
        self.assertNotIn(tx2, qs)
        self.assertNotIn(tx3, qs)

    def test_admin_transactions_qs_returns_all_transactions(self):
        user = create_user("adminrepo@example.com")
        tx1 = create_transaction(user=user)
        tx2 = create_transaction(user=user)
        qs = repo.admin_transactions_qs()
        self.assertIn(tx1, qs)
        self.assertIn(tx2, qs)
