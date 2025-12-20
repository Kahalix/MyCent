from django.test import TestCase
from djmoney.money import Money

from pawns.services import queries
from .factories import (
    create_user,
    create_seller_profile,
    create_customer,
    create_transaction,
    create_pawn,
)


class PawnQueriesTests(TestCase):
    def setUp(self):
        self.owner1 = create_user(email="owner1@example.com", role="OWNER")
        self.owner2 = create_user(email="owner2@example.com", role="OWNER")
        self.seller1 = create_seller_profile(owner=self.owner1, slug="shop-1")
        self.seller2 = create_seller_profile(owner=self.owner2, slug="shop-2")
        self.customer_user = create_user(email="customer@example.com")
        self.customer = create_customer(email="cust@example.com", user=self.customer_user)
        self.tx1 = create_transaction(user=self.owner1, type="PLEDGE", status="COMPLETED", expected_total_amount=0)
        self.tx2 = create_transaction(user=self.owner2, type="PLEDGE", status="COMPLETED", expected_total_amount=0)
        self.pawn1 = create_pawn(transaction=self.tx1, seller_profile=self.seller1, operator=self.owner1, customer=self.customer, principal=Money(100, "PLN"))
        self.pawn2 = create_pawn(transaction=self.tx2, seller_profile=self.seller2, operator=self.owner2, customer=None, principal=Money(200, "PLN"))

    def test_seller_pawns_qs_filters_by_memberships(self):
        qs = queries.seller_pawns_qs(self.owner1)
        self.assertIn(self.pawn1, list(qs))
        self.assertNotIn(self.pawn2, list(qs))

    def test_admin_pawns_qs_returns_all(self):
        qs = queries.admin_pawns_qs()
        self.assertIn(self.pawn1, list(qs))
        self.assertIn(self.pawn2, list(qs))

    def test_user_pawns_qs_filters_by_customer_user(self):
        qs = queries.user_pawns_qs(self.customer_user)
        self.assertIn(self.pawn1, list(qs))
        self.assertNotIn(self.pawn2, list(qs))
