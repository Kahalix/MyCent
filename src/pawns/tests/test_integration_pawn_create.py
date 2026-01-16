from __future__ import annotations

from django.conf import settings
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from customers.models import Customer
from identity.models import SellerMembership, User
from pawns.models import Pawn, PawnLine
from transactions.models import Transaction

from pawns.tests.factories import (
    create_user,
    create_seller_profile,
    create_item_type,
    create_itemset,
)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    JWT_ACCESS_IN_COOKIE=True,
    JWT_REFRESH_IN_COOKIE=True,
    ACCESS_COOKIE_NAME="access_token",
    AUTH_COOKIE_NAME="refresh_token",
    ACCESS_COOKIE_HTTPONLY=True,
    AUTH_COOKIE_HTTPONLY=True,
    ACCESS_COOKIE_SECURE=False,
    AUTH_COOKIE_SECURE=False,
    ACCESS_COOKIE_SAMESITE="Lax",
    AUTH_COOKIE_SAMESITE="Lax",
    ACCESS_COOKIE_DOMAIN="",
    AUTH_COOKIE_DOMAIN="",
    ACCESS_COOKIE_PATH="/api/",
    AUTH_COOKIE_PATH="/api/auth/",
)
class PawnCreateIntegrationTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient(enforce_csrf_checks=True)

        resp_csrf = self.client.get("/api/auth/csrf/")
        self.assertIn(resp_csrf.status_code, (200, 204))
        token = self.client.cookies.get("csrftoken")
        self.assertIsNotNone(token)
        self.csrf_token = token.value

    def _post(self, path: str, data: dict):
        return self.client.post(path, data, format="json", HTTP_X_CSRFTOKEN=self.csrf_token)

    def _activate_user(self, u):
        dbu = User.objects.get(pk=u.pk)
        dbu.is_active = True
        if hasattr(dbu, "user_status"):
            dbu.user_status = "ACTIVE"
            dbu.save(update_fields=["is_active", "user_status"])
        else:
            dbu.save(update_fields=["is_active"])

    def _login(self, *, email: str, password: str) -> None:
        resp = self.client.post(
            "/api/auth/login/",
            {"email": email, "password": password},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, getattr(resp, "data", None))

        access_cookie_name = getattr(settings, "ACCESS_COOKIE_NAME", "access_token")
        refresh_cookie_name = getattr(settings, "AUTH_COOKIE_NAME", "refresh_token")
        self.assertIn(access_cookie_name, self.client.cookies)
        self.assertIn(refresh_cookie_name, self.client.cookies)

        token = self.client.cookies.get("csrftoken")
        self.assertIsNotNone(token)
        self.csrf_token = token.value

    def test_create_pawn_creates_pledge_tx_links_seller_and_ensures_customer(self):
        owner = create_user(email="owner@example.com", role="OWNER")
        employee = create_user(email="employee@example.com", role="EMPLOYEE")

        self._activate_user(owner)
        self._activate_user(employee)

        seller = create_seller_profile(owner=owner, slug="shop-pledge")

        SellerMembership.objects.create(
            seller_profile=seller,
            user=employee,
            role="EMPLOYEE",
            is_active=True,
        )

        itype = create_item_type(name="Category")
        item = create_itemset(
            seller_profile=seller,
            item_type=itype,
            stock_quantity=1,
        )

        self._login(email=employee.email, password="pwd")

        create_payload = {
            "seller_public_id": seller.public_id,
            "principal": "100.00",
            "due_in_days": 30,
            "lines": [
                {
                    "title": "Złoty pierścionek",
                    "description": "Opis",
                    "quantity": 1,
                    "item_set_public_id": item.public_id,
                    "appraisal_value": "150.00",
                }
            ],
        }

        created = self._post(
            "/api/sellers/mine/pawns/create/",
            create_payload,
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, getattr(created, "data", None))

        pawn_public_id = created.data.get("public_id")
        self.assertTrue(pawn_public_id)

        pawn = Pawn.objects.select_related(
            "transaction", "seller_profile", "operator", "customer"
        ).get(public_id=pawn_public_id)

        self.assertEqual(pawn.operator_id, employee.id)
        self.assertEqual(pawn.seller_profile_id, seller.id)
        self.assertEqual(pawn.status, "ACTIVE")
        self.assertIsNone(pawn.customer_id)

        tx = Transaction.objects.get(id=pawn.transaction_id)
        self.assertEqual(tx.user_id, employee.id)
        self.assertEqual(tx.type, "PLEDGE")
        self.assertEqual(tx.status, "COMPLETED")

        self.assertEqual(PawnLine.objects.filter(pawn=pawn).count(), 1)

        ensure_payload = {
            "first_name": "Adam",
            "last_name": "Kowalski",
            "email": "customer1@example.com",
            "phone": "500600700",
            "address": {
                "line1": "Testowa 1",
                "line2": "",
                "postal_code": "00-001",
                "city": "Warszawa",
                "country": "PL",
            },
            "document_type": "ID",
            "document_number": "ABC123456",
        }

        ensured = self._post(
            f"/api/sellers/mine/pawns/{pawn.public_id}/ensure-customer/",
            ensure_payload,
        )
        self.assertIn(
            ensured.status_code,
            (status.HTTP_200_OK, status.HTTP_201_CREATED),
            getattr(ensured, "data", None),
        )

        pawn.refresh_from_db()
        self.assertIsNotNone(pawn.customer_id)

        cust = Customer.objects.get(id=pawn.customer_id)
        self.assertEqual((cust.email or "").lower(), "customer1@example.com")
        self.assertEqual(cust.phone, "500600700")

        pawn.refresh_from_db()
        snap = pawn.customer_snapshot or {}
        self.assertEqual((snap.get("email") or "").lower(), "customer1@example.com")
        self.assertEqual(snap.get("first_name"), "Adam")
        self.assertEqual(snap.get("last_name"), "Kowalski")
