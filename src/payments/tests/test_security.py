# src/payments/tests/test_security.py
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from djmoney.money import Money

from .factories import create_user, create_transaction, create_payment


@override_settings(SECURE_SSL_REDIRECT=False)
class UserPaymentSecurityTests(APITestCase):
    def setUp(self):
        self.user1 = create_user(email="user1@example.com")
        self.user2 = create_user(email="user2@example.com")

        self.tx1 = create_transaction(user=self.user1)
        self.tx2 = create_transaction(user=self.user2)

        self.pay1 = create_payment(tx=self.tx1, amount=Money(50, "PLN"))
        self.pay2 = create_payment(tx=self.tx2, amount=Money(75, "PLN"))

    def _extract_ids(self, data):
        if isinstance(data, list):
            return [row["public_id"] for row in data]
        if isinstance(data, dict) and "results" in data:
            return [row["public_id"] for row in data["results"]]
        return []

    def test_user_cannot_see_other_users_payments_in_list(self):
        self.client.force_authenticate(user=self.user1)
        url = reverse("payments:user-payments-list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        ids = self._extract_ids(resp.data)
        self.assertIn(self.pay1.public_id, ids)
        self.assertNotIn(self.pay2.public_id, ids)

    def test_user_cannot_retrieve_payment_of_another_user(self):
        self.client.force_authenticate(user=self.user1)
        url = reverse(
            "payments:user-payments-detail",
            kwargs={"public_id": self.pay2.public_id},
        )
        resp = self.client.get(url)
        # powinien dostać 404, bo queryset jest odfiltrowany po transaction__user
        self.assertEqual(resp.status_code, 404)


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminPaymentSecurityTests(APITestCase):
    def setUp(self):
        self.user = create_user(email="user@example.com")
        self.admin = create_user(
            email="admin@example.com",
            is_staff=True,
            is_superuser=True,
        )

        self.tx = create_transaction(user=self.user)
        self.pay = create_payment(tx=self.tx, amount=Money(100, "PLN"))

    def _extract_ids(self, data):
        if isinstance(data, list):
            return [row["public_id"] for row in data]
        if isinstance(data, dict) and "results" in data:
            return [row["public_id"] for row in data["results"]]
        return []

    def test_admin_endpoint_denies_non_admin(self):
        self.client.force_authenticate(user=self.user)
        url = reverse("payments:admin-payments-list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

    def test_admin_endpoint_allows_admin(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse("payments:admin-payments-list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        data = resp.data
        ids = self._extract_ids(data)
        self.assertIn(self.pay.public_id, ids)


@override_settings(SECURE_SSL_REDIRECT=False)
class PaymentWebhookSecurityTests(APITestCase):
    def setUp(self):
        self.user = create_user(email="wh-user@example.com")
        self.tx = create_transaction(user=self.user)
        self.payment = create_payment(
            tx=self.tx,
            amount=Money(120, "PLN"),
            provider="STRIPE",
            status="REQUIRES_CONFIRMATION",
            provider_payment_id="pi_test_123",
        )

    @override_settings(
        SECURE_SSL_REDIRECT=False,
        STRIPE_SECRET_KEY="sk_test",
        STRIPE_WEBHOOK_SECRET="whsec_test",
    )
    @patch(
        "payments.api_views.StripeClient.parse_webhook",
        side_effect=Exception("bad signature"),
    )
    def test_stripe_webhook_invalid_signature_does_not_change_payment(
        self,
        parse_mock,
    ):
        url = reverse(
            "payments:payments-webhook",
            kwargs={"provider": "stripe"},
        )
        body = {
            "event": "payment_intent.succeeded",
            "provider_payment_id": self.payment.provider_payment_id,
        }
        resp = self.client.post(url, data=body, format="json")
        self.assertEqual(resp.status_code, 400)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "REQUIRES_CONFIRMATION")

    def test_sim_webhook_missing_payment_id_returns_400(self):
        url = reverse(
            "payments:payments-webhook",
            kwargs={"provider": "sim"},
        )
        body = {"event": "payment_intent.succeeded"}
        resp = self.client.post(url, data=body, format="json")
        self.assertEqual(resp.status_code, 400)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "REQUIRES_CONFIRMATION")
