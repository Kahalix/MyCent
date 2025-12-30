from __future__ import annotations

from django.test import override_settings
from rest_framework.test import APITestCase
from listings.models import ItemSet

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from listings.api_views import (
    PublicItemSetViewSet,
    SellerItemSetViewSet,
    UserItemSetViewSet,
    AdminItemSetViewSet,
)
from .factories import (
    create_user,
    create_seller_profile,
    create_item_type,
    create_item_set,
)


class PublicSecurityTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_public_itemsets_list_allows_anonymous(self):
        create_item_set(status="AVAILABLE")
        view = PublicItemSetViewSet.as_view({"get": "list"})
        request = self.factory.get("/public/item-sets/")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class SellerSecurityTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = create_user(email="seller@example.com")
        self.seller = create_seller_profile(owner=self.user)
        itype = create_item_type()
        create_item_set(
            item_type=itype,
            seller_profile=self.seller,
            added_by="STAFF",
        )

    def test_seller_itemsets_requires_authentication(self):
        view = SellerItemSetViewSet.as_view({"get": "list"})
        request = self.factory.get("/api/sellers/mine/item-sets/")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_access_own_items(self):
        view = SellerItemSetViewSet.as_view({"get": "list"})
        request = self.factory.get("/api/sellers/mine/item-sets/")
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class UserSecurityTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = create_user(email="user@example.com")
        itype = create_item_type()
        create_item_set(
            item_type=itype,
            added_by="USER",
            owner_user=self.user,
            seller_profile=None,
        )

    def test_user_itemsets_requires_authentication(self):
        view = UserItemSetViewSet.as_view({"get": "list"})
        request = self.factory.get("/api/users/me/item-sets/")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_access_own_items(self):
        view = UserItemSetViewSet.as_view({"get": "list"})
        request = self.factory.get("/api/users/me/item-sets/")
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class AdminSecurityTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        # IsAdmin -> is_superuser
        self.admin = create_user(
            email="admin@example.com",
            is_staff=True,
            is_superuser=True,
            role="ADMIN",
        )
        self.normal_user = create_user(
            email="user@example.com",
            is_staff=False,
            role="EMPLOYEE",
        )
        create_item_set(status="AVAILABLE")

    def test_admin_itemsets_anonymous_gets_401(self):
        view = AdminItemSetViewSet.as_view({"get": "list"})
        request = self.factory.get("/api/admin/item-sets/")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_itemsets_requires_admin(self):
        view = AdminItemSetViewSet.as_view({"get": "list"})

        # zalogowany, ale nie admin -> 403
        request = self.factory.get("/api/admin/item-sets/")
        force_authenticate(request, user=self.normal_user)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # admin (superuser) -> 200
        request2 = self.factory.get("/api/admin/item-sets/")
        force_authenticate(request2, user=self.admin)
        response2 = view(request2)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

@override_settings(SECURE_SSL_REDIRECT=False)
class PublicItemSetInjectionTests(APITestCase):
    def setUp(self):
        # jeden normalny rekord, żeby lista nie była pusta
        self.item = create_item_set(status="AVAILABLE")

    def test_search_parameter_is_safe_against_injection_like_input(self):
        before = ItemSet.objects.count()
        payload = {
            "search": "Test'; DROP TABLE listings_itemset;--"
        }
        resp = self.client.get("/api/public/item-sets/", payload)
        # oczekujemy 200, bez wyjątków SQL i bez zmiany danych
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        after = ItemSet.objects.count()
        self.assertEqual(before, after)

    def test_type_path_parameter_is_safe_against_injection_like_input(self):
        before = ItemSet.objects.count()
        payload = {
            "type_path": "electronics/phones'; DROP TABLE x;--"
        }
        resp = self.client.get("/api/public/item-sets/", payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        after = ItemSet.objects.count()
        self.assertEqual(before, after)

    def test_statuses_parameter_is_safe_against_injection_like_input(self):
        before = ItemSet.objects.count()
        payload = {
            "statuses": "AVAILABLE'); DROP TABLE y;--"
        }
        resp = self.client.get("/api/public/item-sets/", payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        after = ItemSet.objects.count()
        self.assertEqual(before, after)

    def test_by_slug_endpoint_is_safe_against_injection_like_slug(self):
        before = ItemSet.objects.count()
        bad_slug = "nonexistent'; DROP TABLE listings_itemset;--"
        resp = self.client.get(f"/api/public/item-sets/by-slug/{bad_slug}/")
        # tu w normalnym flow spodziewamy się po prostu 404
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        after = ItemSet.objects.count()
        self.assertEqual(before, after)
