from __future__ import annotations

from django.test import override_settings, TestCase
from rest_framework.test import APITestCase, APIRequestFactory, force_authenticate
from rest_framework import status

from listings.models import ItemSet
from listings.api_views import (
    PublicItemSetViewSet,
    SellerItemSetViewSet,
    UserItemSetViewSet,
    AdminItemSetViewSet,
)
from listings.services.cache_utils import get_cache_key
from django.core.cache import cache

from .factories import (
    create_user,
    create_seller_profile,
    create_item_type,
    create_item_set,
    create_saved_listing,
)

# --- TEST CACHE CONFIGURATION ---
TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-public-itemsets",
    }
}

LIST_PATH = "/api/public/item-sets/"

# --- SECURITY TESTS ---

@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES=TEST_CACHES
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
        request = self.factory.get("/api/admin/item-sets/")
        force_authenticate(request, user=self.normal_user)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        request2 = self.factory.get("/api/admin/item-sets/")
        force_authenticate(request2, user=self.admin)
        response2 = view(request2)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)


@override_settings(SECURE_SSL_REDIRECT=False, CACHES=TEST_CACHES)
class PublicItemSetInjectionTests(APITestCase):
    def setUp(self):
        self.item = create_item_set(status="AVAILABLE")

    def test_search_parameter_is_safe_against_injection_like_input(self):
        before = ItemSet.objects.count()
        payload = {"search": "Test'; DROP TABLE listings_itemset;--"}
        resp = self.client.get("/api/public/item-sets/", payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        after = ItemSet.objects.count()
        self.assertEqual(before, after)

    def test_type_path_parameter_is_safe_against_injection_like_input(self):
        before = ItemSet.objects.count()
        payload = {"type_path": "electronics/phones'; DROP TABLE x;--"}
        resp = self.client.get("/api/public/item-sets/", payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        after = ItemSet.objects.count()
        self.assertEqual(before, after)

    def test_statuses_parameter_is_safe_against_injection_like_input(self):
        before = ItemSet.objects.count()
        payload = {"statuses": "AVAILABLE'); DROP TABLE y;--"}
        resp = self.client.get("/api/public/item-sets/", payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        after = ItemSet.objects.count()
        self.assertEqual(before, after)

    def test_by_slug_endpoint_is_safe_against_injection_like_slug(self):
        before = ItemSet.objects.count()
        bad_slug = "nonexistent'; DROP TABLE listings_itemset;--"
        resp = self.client.get(f"/api/public/item-sets/by-slug/{bad_slug}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        after = ItemSet.objects.count()
        self.assertEqual(before, after)


# --- TESTS CACHE / IS_SAVED ---

@override_settings(SECURE_SSL_REDIRECT=False, CACHES=TEST_CACHES)
class PublicItemSetCacheSecurityTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.item = create_item_set(status="AVAILABLE")

    def _list(self):
        resp = self.client.get(LIST_PATH)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return resp.json()

    def test_is_saved_is_user_specific_and_does_not_leak_between_users(self):
        anon_data = self._list()
        results = anon_data.get("results") or anon_data
        self.assertIsInstance(results, list)
        self.assertGreaterEqual(len(results), 1)
        first = results[0]
        self.assertIn("public_id", first)
        if "is_saved" in first:
            self.assertFalse(first["is_saved"])

        user_a = create_user()
        create_saved_listing(user=user_a, item_set=self.item)
        self.client.force_authenticate(user=user_a)
        a_data = self._list()
        a_first = (a_data.get("results") or a_data)[0]
        self.assertTrue(a_first["is_saved"])
        self.client.force_authenticate(user=None)

        user_b = create_user()
        self.client.force_authenticate(user=user_b)
        b_data = self._list()
        b_first = (b_data.get("results") or b_data)[0]
        self.assertFalse(b_first["is_saved"])
        self.client.force_authenticate(user=None)

        anon2 = self._list()
        anon2_first = (anon2.get("results") or anon2)[0]
        if "is_saved" in anon2_first:
            self.assertFalse(anon2_first["is_saved"])

    def test_cache_payload_is_not_mutated_by_injecting_is_saved_on_auth_requests(self):
        cache.clear()
        _ = self._list()
        user_a = create_user()
        create_saved_listing(user=user_a, item_set=self.item)
        self.client.force_authenticate(user=user_a)
        auth_resp = self._list()
        auth_first = (auth_resp.get("results") or auth_resp)[0]
        self.assertTrue(auth_first["is_saved"])
        self.client.force_authenticate(user=None)

        cache_key = get_cache_key("public_itemsets:list", LIST_PATH)
        cached = cache.get(cache_key)
        self.assertIsNotNone(cached)
        rows = cached.get("results", cached) if isinstance(cached, dict) else cached
        if isinstance(rows, list) and rows:
            self.assertNotIn("is_saved", rows[0])
        else:
            if isinstance(cached, dict):
                self.assertNotIn("is_saved", cached)
