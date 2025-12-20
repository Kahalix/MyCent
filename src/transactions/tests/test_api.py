from __future__ import annotations
from decimal import Decimal

from django.test import override_settings
from djmoney.money import Money
from rest_framework import status
from rest_framework.test import APITestCase

from .factories import (
    create_user,
    create_transaction,
    create_coupon,
    create_seller_profile,
    create_order_for_transaction,
    create_seller_membership,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class UserTransactionApiTests(APITestCase):
    def setUp(self):
        self.user = create_user("apiuser@example.com")
        self.other_user = create_user("apiother@example.com")
        self.tx_own = create_transaction(user=self.user)
        self.tx_other = create_transaction(user=self.other_user)

    def test_list_returns_only_user_transactions(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/users/me/transactions/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = {item["public_id"] for item in resp.data["results"]}
        self.assertIn(self.tx_own.public_id, ids)
        self.assertNotIn(self.tx_other.public_id, ids)

    def test_retrieve_own_transaction(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get(f"/api/users/me/transactions/{self.tx_own.public_id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["public_id"], self.tx_own.public_id)

    def test_cannot_retrieve_other_users_transaction(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get(f"/api/users/me/transactions/{self.tx_other.public_id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_attach_coupon_endpoint_applies_coupon(self):
        self.client.force_authenticate(user=self.user)
        tx = create_transaction(user=self.user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=self.user)
        create_order_for_transaction(tx, seller, grand_total=Money(100, "PLN"))
        coupon = create_coupon(
            code="API10",
            discount_type="PERCENTAGE",
            discount_value=Money(10, "PLN"),
        )
        resp = self.client.post(
            f"/api/users/me/transactions/{tx.public_id}/attach-coupon/",
            {"coupon_code": "API10"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["public_id"], tx.public_id)
        self.assertEqual(resp.data["expected_total_currency"], "PLN")
        self.assertEqual(resp.data["expected_total_amount"], "90.00")

    def test_preview_discount_endpoint_returns_preview(self):
        self.client.force_authenticate(user=self.user)
        tx = create_transaction(user=self.user, type="PURCHASE", expected_total_currency="PLN")
        seller = create_seller_profile(owner=self.user)
        create_order_for_transaction(tx, seller, grand_total=Money(50, "PLN"))
        coupon = create_coupon(
            code="API5",
            discount_type="PERCENTAGE",
            discount_value=Money(10, "PLN"),
        )
        resp = self.client.post(
            f"/api/users/me/transactions/{tx.public_id}/preview-discount/",
            {"coupon_code": "API5"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["ok"])
        self.assertEqual(resp.data["gross_amount"], "50.00")
        self.assertEqual(resp.data["discount_amount"], "5.00")
        self.assertEqual(resp.data["net_amount"], "45.00")
        self.assertEqual(resp.data["coupon_public_id"], coupon.public_id)


@override_settings(SECURE_SSL_REDIRECT=False)
class SellerTransactionApiTests(APITestCase):
    def setUp(self):
        self.seller_user = create_user("sellerapi@example.com")
        self.other_user = create_user("sellerother@example.com")
        self.buyer = create_user("sellerbuyer@example.com")
        self.seller_profile = create_seller_profile(owner=self.seller_user)
        self.other_profile = create_seller_profile(owner=self.other_user, slug="seller-api-other")
        create_seller_membership(self.seller_profile, self.seller_user, role="OWNER", is_active=True)
        self.tx_seller = create_transaction(user=self.buyer)
        self.tx_other = create_transaction(user=self.buyer)
        create_order_for_transaction(self.tx_seller, self.seller_profile, buyer=self.buyer, grand_total=Money(100, "PLN"))
        create_order_for_transaction(self.tx_other, self.other_profile, buyer=self.buyer, grand_total=Money(50, "PLN"))

    def test_list_returns_only_sellers_transactions(self):
        self.client.force_authenticate(user=self.seller_user)
        resp = self.client.get("/api/sellers/mine/transactions/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = {item["public_id"] for item in resp.data["results"]}
        self.assertIn(self.tx_seller.public_id, ids)
        self.assertNotIn(self.tx_other.public_id, ids)

    def test_set_status_valid_transition(self):
        self.client.force_authenticate(user=self.seller_user)
        tx = create_transaction(user=self.buyer, status="PENDING")
        create_order_for_transaction(tx, self.seller_profile, buyer=self.buyer, grand_total=Money(100, "PLN"))
        resp = self.client.post(
            f"/api/sellers/mine/transactions/{tx.public_id}/set-status/",
            {"status": "COMPLETED"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "COMPLETED")

    def test_set_status_invalid_transition_returns_409(self):
        self.client.force_authenticate(user=self.seller_user)
        tx = create_transaction(user=self.buyer, status="COMPLETED")
        create_order_for_transaction(tx, self.seller_profile, buyer=self.buyer, grand_total=Money(100, "PLN"))
        resp = self.client.post(
            f"/api/sellers/mine/transactions/{tx.public_id}/set-status/",
            {"status": "PENDING"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminTransactionApiTests(APITestCase):
    def setUp(self):
        self.admin = create_user("adminapi@example.com", is_staff=True, is_superuser=True)
        self.user = create_user("normalapi@example.com")
        self.tx1 = create_transaction(user=self.user)
        self.tx2 = create_transaction(user=self.user)

    def test_admin_can_list_transactions(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/admin/transactions/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = {item["public_id"] for item in resp.data["results"]}
        self.assertIn(self.tx1.public_id, ids)
        self.assertIn(self.tx2.public_id, ids)

    def test_non_admin_cannot_access_admin_endpoint(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/admin/transactions/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_change_status_via_set_status(self):
        self.client.force_authenticate(user=self.admin)
        tx = create_transaction(user=self.user, status="PENDING")
        resp = self.client.post(
            f"/api/admin/transactions/{tx.public_id}/set-status/",
            {"status": "CANCELLED"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "CANCELLED")
