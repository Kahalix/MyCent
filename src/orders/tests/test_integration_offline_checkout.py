from __future__ import annotations

from django.conf import settings
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from djmoney.money import Money

from identity.models import SellerMembership, User
from transactions.models import Transaction
from orders.models import Order, OrderLine
from listings.models import ItemSet

from orders.tests.factories import (
    create_user,
    create_seller_profile,
    create_seller_member,
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
class OfflineSaleIntegrationTests(APITestCase):
    OFFLINE_CHECKOUT_URL = "/api/sellers/mine/orders/offline-checkout/"

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

    def test_offline_sale_creates_completed_tx_and_order_and_decreases_stock(self):
        owner_password = "OwnerPass123!"
        employee_password = "EmployeePass123!"

        owner = create_user(email="owner@example.com", password=owner_password, role="OWNER")
        employee = create_user(email="employee@example.com", password=employee_password, role="EMPLOYEE")

        for u in (owner, employee):
            dbu = User.objects.get(pk=u.pk)
            dbu.is_active = True
            if hasattr(dbu, "user_status"):
                dbu.user_status = "ACTIVE"
                dbu.save(update_fields=["is_active", "user_status"])
            else:
                dbu.save(update_fields=["is_active"])

        seller = create_seller_profile(owner=owner, slug="shop-1", company_name="Shop 1")
        create_seller_member(seller=seller, user=employee, role="EMPLOYEE", is_active=True)

        self.assertTrue(
            SellerMembership.objects.filter(
                seller_profile=seller, user=employee, is_active=True
            ).exists()
        )

        itype = create_item_type(name="Category")

        item = create_itemset(
            seller=seller,
            item_type=itype,
            set_name="Item 1",
            price=Money(100, "PLN"),
            stock_quantity=2,
            status="AVAILABLE",
            listing_type="BUY",
            allow_online_checkout=True,
        )

        self._login(email=employee.email, password=employee_password)

        payload = {
            "lines": [{"item_public_id": item.public_id, "quantity": 2}],
            "payment_method": "CASH",
            "customer": {
                "first_name": "Jan",
                "last_name": "Kowalski",
                "email": "customer@example.com",
                "phone": "123456789",
            },
            "status": "COMPLETED",
        }

        resp = self._post(self.OFFLINE_CHECKOUT_URL, payload)
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED), getattr(resp, "data", None))

        order_public_id = resp.data.get("public_id")
        tx_public_id = resp.data.get("transaction_public_id")
        self.assertTrue(order_public_id)
        self.assertTrue(tx_public_id)

        tx = Transaction.objects.get(public_id=tx_public_id)
        self.assertEqual(tx.type, "PURCHASE")
        self.assertEqual(tx.status, "COMPLETED")

        order = Order.objects.get(public_id=order_public_id)
        self.assertEqual(order.transaction_id, tx.id)
        self.assertEqual(order.order_status, "COMPLETED")
        self.assertEqual(getattr(order, "seller_profile_id", None), seller.id)

        lines = list(OrderLine.objects.filter(order=order).select_related("item_set"))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].item_set_id, item.id)
        self.assertEqual(int(lines[0].quantity), 2)

        item.refresh_from_db()
        self.assertEqual(int(item.stock_quantity or 0), 0)
        self.assertEqual(item.status, "SOLD")

        item2 = ItemSet.objects.get(pk=item.pk)
        self.assertEqual(int(item2.stock_quantity or 0), 0)
        self.assertEqual(item2.status, "SOLD")
