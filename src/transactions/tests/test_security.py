from __future__ import annotations

from django.test import override_settings
from djmoney.money import Money
from rest_framework import status
from rest_framework.test import APITestCase

from .factories import (
    create_user,
    create_transaction,
    create_seller_profile,
    create_seller_membership,
    create_order_for_transaction,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class UserTransactionSecurityTests(APITestCase):
    def setUp(self):
        self.user1 = create_user("secuser1@example.com")
        self.user2 = create_user("secuser2@example.com")
        self.tx1 = create_transaction(user=self.user1)
        self.tx2 = create_transaction(user=self.user2)

    def test_unauthenticated_cannot_access_user_transactions(self):
        resp = self.client.get("/api/users/me/transactions/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_cannot_see_other_users_transactions_in_list(self):
        self.client.force_authenticate(user=self.user1)
        resp = self.client.get("/api/users/me/transactions/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = {item["public_id"] for item in resp.data["results"]}
        self.assertIn(self.tx1.public_id, ids)
        self.assertNotIn(self.tx2.public_id, ids)

    def test_user_cannot_retrieve_other_users_transaction(self):
        self.client.force_authenticate(user=self.user1)
        resp = self.client.get(f"/api/users/me/transactions/{self.tx2.public_id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(SECURE_SSL_REDIRECT=False)
class SellerTransactionSecurityTests(APITestCase):
    def setUp(self):
        self.seller_user = create_user("secseller@example.com")
        self.other_user = create_user("secsellerother@example.com")
        self.buyer = create_user("secsellerbuyer@example.com")
        self.seller_profile = create_seller_profile(owner=self.seller_user)
        self.other_profile = create_seller_profile(owner=self.other_user, slug="secseller-other")
        create_seller_membership(self.seller_profile, self.seller_user, role="OWNER", is_active=True)
        create_seller_membership(self.other_profile, self.other_user, role="OWNER", is_active=True)
        self.tx1 = create_transaction(user=self.buyer)
        self.tx2 = create_transaction(user=self.buyer)
        create_order_for_transaction(self.tx1, self.seller_profile, buyer=self.buyer, grand_total=Money(100, "PLN"))
        create_order_for_transaction(self.tx2, self.other_profile, buyer=self.buyer, grand_total=Money(50, "PLN"))

    def test_unauthenticated_cannot_access_seller_transactions(self):
        resp = self.client.get("/api/sellers/mine/transactions/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_seller_sees_only_their_transactions(self):
        self.client.force_authenticate(user=self.seller_user)
        resp = self.client.get("/api/sellers/mine/transactions/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = {item["public_id"] for item in resp.data["results"]}
        self.assertIn(self.tx1.public_id, ids)
        self.assertNotIn(self.tx2.public_id, ids)

    def test_user_without_membership_sees_no_transactions(self):
        user_no_seller = create_user("nosec@example.com")
        self.client.force_authenticate(user=user_no_seller)
        resp = self.client.get("/api/sellers/mine/transactions/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 0)


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminTransactionSecurityTests(APITestCase):
    def setUp(self):
        self.admin = create_user("secadmin@example.com", is_staff=True, is_superuser=True)
        self.user = create_user("secnormal@example.com")
        self.tx = create_transaction(user=self.user)

    def test_admin_endpoint_denies_non_admin(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/admin/transactions/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_endpoint_allows_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/admin/transactions/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_admin_endpoint_requires_authentication(self):
        resp = self.client.get("/api/admin/transactions/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(SECURE_SSL_REDIRECT=False)
class TransactionFilterSecurityTests(APITestCase):
    def setUp(self):
        self.user = create_user("secfilter@example.com")
        self.tx = create_transaction(user=self.user, notes="safe note")

    def test_search_parameter_is_safe_against_injection_like_input(self):
        self.client.force_authenticate(user=self.user)
        query = "PENDING'); DROP TABLE transactions_transaction; --"
        resp = self.client.get(f"/api/users/me/transactions/?search={query}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
