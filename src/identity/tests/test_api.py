from __future__ import annotations

from django.conf import settings
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from identity.models import User
from .factories import (
    create_user,
    create_seller_profile,
    create_seller_bank_account,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class AuthApiTests(APITestCase):
    def test_register_creates_user_and_returns_201(self):
        payload = {
            "email": "api-register@example.com",
            "password": "StrongPass123!",
            "first_name": "Jan",
            "last_name": "Nowak",
        }
        resp = self.client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="api-register@example.com").exists())

    def test_login_returns_payload_and_sets_refresh_cookie_for_active_user(self):
        create_user(email="api-login@example.com")
        payload = {"email": "api-login@example.com", "password": "pass1234"}

        resp = self.client.post("/api/auth/login/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertIn("user", resp.data)

        if getattr(settings, "JWT_ACCESS_IN_COOKIE", False):
            self.assertNotIn("access", resp.data)
            access_cookie_name = getattr(settings, "ACCESS_COOKIE_NAME", "access_token")
            self.assertIn(access_cookie_name, resp.cookies)
        else:
            self.assertIn("access", resp.data)

        if getattr(settings, "JWT_REFRESH_IN_COOKIE", False):
            self.assertNotIn("refresh", resp.data)
            refresh_cookie_name = getattr(settings, "AUTH_COOKIE_NAME", "refresh_token")
            self.assertIn(refresh_cookie_name, resp.cookies)

    def test_login_invalid_credentials_returns_401(self):
        payload = {"email": "missing@example.com", "password": "pass1234"}
        resp = self.client.post("/api/auth/login/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_missing_returns_401(self):
        resp = self.client.post("/api/auth/refresh/", {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


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
    ACCESS_COOKIE_PATH="/",
    AUTH_COOKIE_PATH="/",
)
class CookieAuthCsrfFlowTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient(enforce_csrf_checks=True)

    def _get_csrf_token(self) -> str:
        token = self.client.cookies.get("csrftoken")
        self.assertIsNotNone(token)
        return token.value

    def test_cookie_login_refresh_logout_flow_with_csrf(self):
        create_user(email="cookie-user@example.com")

        resp_csrf = self.client.get("/api/auth/csrf/")
        self.assertEqual(resp_csrf.status_code, 204)
        csrf_token = self._get_csrf_token()

        login_payload = {"email": "cookie-user@example.com", "password": "pass1234"}
        resp_login = self.client.post("/api/auth/login/", login_payload, format="json")
        self.assertEqual(resp_login.status_code, 200)

        self.assertIn("user", resp_login.data)
        self.assertNotIn("refresh", resp_login.data)
        self.assertNotIn("access", resp_login.data)

        self.assertIn(settings.ACCESS_COOKIE_NAME, self.client.cookies)
        self.assertIn(settings.AUTH_COOKIE_NAME, self.client.cookies)

        refresh_before = self.client.cookies.get(settings.AUTH_COOKIE_NAME)
        self.assertIsNotNone(refresh_before)
        refresh_before_value = refresh_before.value

        resp_refresh_no_csrf = self.client.post("/api/auth/refresh/", {}, format="json")
        self.assertEqual(resp_refresh_no_csrf.status_code, 403)

        resp_refresh = self.client.post(
            "/api/auth/refresh/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(resp_refresh.status_code, 200)

        self.assertIn("user", resp_refresh.data)
        self.assertNotIn("refresh", resp_refresh.data)
        self.assertNotIn("access", resp_refresh.data)

        refresh_after = self.client.cookies.get(settings.AUTH_COOKIE_NAME)
        self.assertIsNotNone(refresh_after)
        self.assertNotEqual(refresh_after.value, refresh_before_value)

        resp_logout_no_csrf = self.client.post("/api/auth/logout/", {}, format="json")
        self.assertEqual(resp_logout_no_csrf.status_code, 403)

        resp_logout = self.client.post(
            "/api/auth/logout/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(resp_logout.status_code, 204)

        deleted_refresh = resp_logout.cookies.get(settings.AUTH_COOKIE_NAME)
        self.assertIsNotNone(deleted_refresh)
        self.assertEqual(deleted_refresh.value, "")
        self.assertEqual(int(deleted_refresh["max-age"]), 0)

        deleted_access = resp_logout.cookies.get(settings.ACCESS_COOKIE_NAME)
        self.assertIsNotNone(deleted_access)
        self.assertEqual(deleted_access.value, "")
        self.assertEqual(int(deleted_access["max-age"]), 0)

        self.assertTrue(deleted_refresh["expires"])
        self.assertTrue(deleted_access["expires"])

@override_settings(SECURE_SSL_REDIRECT=False)
class SelfUserApiTests(APITestCase):
    def setUp(self):
        self.user = create_user(email="me-api@example.com", first_name="Old", last_name="Name")

    def test_me_requires_authentication(self):
        resp = self.client.get("/api/users/me/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user_data(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/users/me/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["email"], "me-api@example.com")

    def test_me_partial_update_updates_fields(self):
        self.client.force_authenticate(user=self.user)
        payload = {"first_name": "New", "phone_number": "555"}
        resp = self.client.patch("/api/users/me/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "New")
        self.assertEqual(self.user.phone_number, "555")


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminUserApiTests(APITestCase):
    def setUp(self):
        self.admin = create_user(email="admin@example.com", is_staff=True, is_superuser=True)
        self.user = create_user(email="normal@example.com")

    def test_non_admin_cannot_access_admin_user_list(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/admin/users/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_user(self):
        self.client.force_authenticate(user=self.admin)
        payload = {
            "email": "created-via-api@example.com",
            "password": "StrongPass123!",
            "first_name": "A",
            "last_name": "B",
            "role": "EMPLOYEE",
            "user_status": "ACTIVE",
        }
        resp = self.client.post("/api/admin/users/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="created-via-api@example.com").exists())


@override_settings(SECURE_SSL_REDIRECT=False)
class SellerApiTests(APITestCase):
    def setUp(self):
        self.owner = create_user(email="owner-api@example.com", role="OWNER")
        self.other = create_user(email="other-api@example.com")
        self.seller = create_seller_profile(owner=self.owner, company_name="Sklep API", slug="sklep-api")

    def test_public_sellers_list(self):
        resp = self.client.get("/api/public/sellers/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get("results", resp.data)
        self.assertTrue(any(r["slug"] == "sklep-api" for r in results))

    def test_my_seller_returns_profile_for_owner(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get("/api/sellers/mine/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["slug"], "sklep-api")

    def test_admin_sellers_requires_admin(self):
        self.client.force_authenticate(user=self.other)
        resp = self.client.get("/api/admin/sellers/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.owner)
        resp2 = self.client.get("/api/admin/sellers/")
        self.assertIn(resp2.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_200_OK))


@override_settings(SECURE_SSL_REDIRECT=False)
class BankAccountApiTests(APITestCase):
    def setUp(self):
        self.owner = create_user(email="owner-bank-api@example.com", role="OWNER")
        self.non_owner = create_user(email="non-owner@example.com")
        self.seller = create_seller_profile(owner=self.owner)
        self.acc = create_seller_bank_account(
            seller_profile=self.seller,
            iban="PL00111111111111111",
            bank_name="Bank",
            account_holder="Holder",
            is_default=True,
        )

    def test_my_bank_accounts_requires_owner_role(self):
        resp = self.client.get("/api/sellers/mine/bank-accounts/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(user=self.non_owner)
        resp2 = self.client.get("/api/sellers/mine/bank-accounts/")
        self.assertEqual(resp2.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.owner)
        resp3 = self.client.get("/api/sellers/mine/bank-accounts/")
        self.assertEqual(resp3.status_code, status.HTTP_200_OK)

    def test_admin_bank_accounts_requires_admin(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get("/api/admin/seller-bank-accounts/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        admin = create_user(email="admin-bank@example.com", is_staff=True, is_superuser=True)
        self.client.force_authenticate(user=admin)
        resp2 = self.client.get("/api/admin/seller-bank-accounts/")
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
