from __future__ import annotations

from django.conf import settings
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from djmoney.money import Money

from identity.models import User
from carts.models import Cart
from payments.models import Payment
from transactions.models import Transaction
from orders.models import Order, OrderLine, ItemReservation

from orders.tests.factories import (
    create_user,
    create_seller_profile,
    create_item_type,
    create_itemset,
)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    STRIPE_SECRET_KEY="",
    STRIPE_PUBLISHABLE_KEY="",
    STRIPE_WEBHOOK_SECRET="",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
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
class OnlineCartPurchaseIntegrationTests(APITestCase):
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

    def _register_and_login(self, *, email: str, password: str) -> None:
        reg_payload = {
            "email": email,
            "password": password,
            "first_name": "Jan",
            "last_name": "Nowak",
        }
        reg = self.client.post("/api/auth/register/", reg_payload, format="json")
        self.assertEqual(reg.status_code, status.HTTP_201_CREATED, getattr(reg, "data", None))

        u = User.objects.get(email=email.lower())
        u.is_active = True
        if hasattr(u, "user_status"):
            u.user_status = "ACTIVE"
            u.save(update_fields=["is_active", "user_status"])
        else:
            u.save(update_fields=["is_active"])

        login_payload = {"email": email, "password": password}
        login = self.client.post("/api/auth/login/", login_payload, format="json")
        self.assertEqual(login.status_code, status.HTTP_200_OK, getattr(login, "data", None))

        access_cookie_name = getattr(settings, "ACCESS_COOKIE_NAME", "access_token")
        refresh_cookie_name = getattr(settings, "AUTH_COOKIE_NAME", "refresh_token")
        self.assertIn(access_cookie_name, self.client.cookies)
        self.assertIn(refresh_cookie_name, self.client.cookies)

        token = self.client.cookies.get("csrftoken")
        self.assertIsNotNone(token)
        self.csrf_token = token.value

    def test_online_purchase_from_cart_creates_tx_orders_reservations_and_updates_stock_after_payment(self):
        seller_owner_1 = create_user(email="seller1@example.com")
        seller_owner_2 = create_user(email="seller2@example.com")

        seller_1 = create_seller_profile(owner=seller_owner_1, slug="shop-1", company_name="Shop 1")
        seller_2 = create_seller_profile(owner=seller_owner_2, slug="shop-2", company_name="Shop 2")

        itype = create_item_type(name="Category")

        item_1 = create_itemset(
            seller=seller_1,
            item_type=itype,
            set_name="Item 1",
            price=Money(100, "PLN"),
            stock_quantity=1,
            status="AVAILABLE",
            listing_type="BUY",
            allow_online_checkout=True,
        )
        item_2 = create_itemset(
            seller=seller_2,
            item_type=itype,
            set_name="Item 2",
            price=Money(50, "PLN"),
            stock_quantity=1,
            status="AVAILABLE",
            listing_type="BUY",
            allow_online_checkout=True,
        )

        email = "buyer@example.com"
        password = "StrongPass123!"
        self._register_and_login(email=email, password=password)

        add1 = self._post(
            "/api/users/me/cart/items/",
            {"item_public_id": item_1.public_id, "quantity": 1},
        )
        self.assertEqual(add1.status_code, status.HTTP_201_CREATED, getattr(add1, "data", None))

        add2 = self._post(
            "/api/users/me/cart/items/",
            {"item_public_id": item_2.public_id, "quantity": 1},
        )
        self.assertEqual(add2.status_code, status.HTTP_201_CREATED, getattr(add2, "data", None))

        checkout = self._post(
            "/api/users/me/cart/checkout/",
            {"payment_method": "ONLINE_PAYMENT"},
        )
        self.assertEqual(checkout.status_code, status.HTTP_201_CREATED, getattr(checkout, "data", None))
        self.assertIsInstance(checkout.data, list)
        self.assertEqual(len(checkout.data), 2)

        tx_public_id = checkout.data[0].get("transaction_public_id")
        self.assertTrue(tx_public_id)

        buyer = User.objects.get(email=email.lower())
        cart = Cart.objects.get(user=buyer, status="CHECKED_OUT")
        self.assertTrue(cart)

        tx = Transaction.objects.get(public_id=tx_public_id)
        self.assertEqual(tx.user_id, buyer.id)
        self.assertEqual(tx.type, "PURCHASE")
        self.assertEqual(tx.status, "PENDING")

        orders = list(Order.objects.filter(transaction=tx).order_by("created_at"))
        self.assertEqual(len(orders), 2)
        self.assertTrue(all(o.order_status == "PENDING" for o in orders))

        lines = list(OrderLine.objects.filter(order__in=orders).select_related("item_set"))
        self.assertEqual(len(lines), 2)

        reservations = list(ItemReservation.objects.filter(transaction=tx).select_related("item_set"))
        self.assertEqual(len(reservations), 2)
        self.assertTrue(all(r.released_at is None for r in reservations))
        self.assertTrue(all(r.expires_at is not None for r in reservations))

        item_1.refresh_from_db()
        item_2.refresh_from_db()
        self.assertEqual(int(item_1.stock_quantity or 0), 1)
        self.assertEqual(int(item_2.stock_quantity or 0), 1)
        self.assertEqual(item_1.status, "AVAILABLE")
        self.assertEqual(item_2.status, "AVAILABLE")

        intent = self._post(
            "/api/users/me/payments/intents/",
            {"transaction_public_id": tx.public_id, "provider": "SIM"},
        )
        self.assertEqual(intent.status_code, status.HTTP_201_CREATED, getattr(intent, "data", None))
        pay_public_id = intent.data["public_id"]

        pay = Payment.objects.get(public_id=pay_public_id)
        self.assertEqual(pay.transaction_id, tx.id)
        self.assertEqual(pay.provider, "SIM")
        self.assertEqual(pay.status, "REQUIRES_CONFIRMATION")
        self.assertEqual(str(pay.metadata.get("tx_public_id", "")), tx.public_id)

        confirm = self._post(
            f"/api/users/me/payments/{pay.public_id}/confirm/",
            {"result": "success"},
        )
        self.assertEqual(confirm.status_code, status.HTTP_200_OK, getattr(confirm, "data", None))

        pay.refresh_from_db()
        tx.refresh_from_db()
        self.assertEqual(pay.status, "SUCCEEDED")
        self.assertEqual(tx.status, "COMPLETED")

        orders = list(Order.objects.filter(transaction=tx))
        self.assertTrue(all(o.order_status == "COMPLETED" for o in orders))

        reservations = list(ItemReservation.objects.filter(transaction=tx))
        self.assertEqual(len(reservations), 2)
        self.assertTrue(all(r.released_at is not None for r in reservations))

        item_1.refresh_from_db()
        item_2.refresh_from_db()
        self.assertEqual(int(item_1.stock_quantity or 0), 0)
        self.assertEqual(int(item_2.stock_quantity or 0), 0)
        self.assertEqual(item_1.status, "SOLD")
        self.assertEqual(item_2.status, "SOLD")
