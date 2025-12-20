from __future__ import annotations
from decimal import Decimal

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from services.models import ListingPackage
from services.services import commands
from .factories import (
    create_user,
    create_item_type,
    create_listing_package,
    create_user_listing_package,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class PublicListingPackageApiTests(APITestCase):
    def setUp(self):
        self.itype1 = create_item_type(name="Elektronika")
        self.itype2 = create_item_type(name="Książki")
        self.pkg1 = create_listing_package(
            item_type=self.itype1,
            listings_free=1,
            price_amount=Decimal("5.00"),
            points=0,
        )
        self.pkg2 = create_listing_package(
            item_type=self.itype2,
            listings_free=2,
            price_amount=Decimal("10.00"),
            points=0,
        )

    def test_list_returns_public_packages(self):
        resp = self.client.get("/api/public/services/listing-packages/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get("results", resp.data)
        self.assertGreaterEqual(len(results), 2)

    def test_list_filters_by_item_type_public_id(self):
        resp = self.client.get(
            "/api/public/services/listing-packages/",
            {"item_type": str(self.itype1.public_id)},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get("results", resp.data)
        ids = {row["public_id"] for row in results}
        self.assertEqual(ids, {str(self.pkg1.public_id)})

    def test_list_filters_by_search_on_item_type_name(self):
        resp = self.client.get(
            "/api/public/services/listing-packages/",
            {"search": "elektr"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get("results", resp.data)
        self.assertTrue(
            any("Elektronika" in r["item_type"]["name"] for r in results)
        )

    def test_retrieve_returns_single_package(self):
        resp = self.client.get(
            f"/api/public/services/listing-packages/{self.pkg1.public_id}/"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["public_id"], str(self.pkg1.public_id))
        self.assertIn("item_type", resp.data)
        self.assertIn("listings_free", resp.data)
        self.assertIn("points", resp.data)


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminListingPackageApiTests(APITestCase):
    def setUp(self):
        self.admin = create_user(
            "admin-services@example.com",
            is_staff=True,
            is_superuser=True,
        )
        self.user = create_user("user-services@example.com")
        self.itype = create_item_type(name="Foto")

    def test_non_admin_cannot_access_admin_list(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/admin/services/listing-packages/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_package_without_price(self):
        self.client.force_authenticate(user=self.admin)
        data = {
            "listings_free": 3,
            "points": 0,
            "item_type": self.itype.id,
        }
        resp = self.client.post(
            "/api/admin/services/listing-packages/",
            data,
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ListingPackage.objects.count(), 1)
        pkg = ListingPackage.objects.first()
        self.assertEqual(pkg.listings_free, 3)
        self.assertEqual(pkg.points, 0)
        self.assertEqual(pkg.item_type_id, self.itype.id)


@override_settings(SECURE_SSL_REDIRECT=False)
class MyServicesApiTests(APITestCase):
    def setUp(self):
        self.user = create_user("me-services@example.com")
        self.other = create_user("other-services@example.com")
        self.itype = create_item_type(name="Dom")
        self.pkg1 = create_listing_package(item_type=self.itype)
        self.pkg2 = create_listing_package(item_type=self.itype)
        create_user_listing_package(
            user=self.user,
            listing_package=self.pkg1,
            free_total=2,
            paid_total=0,
        )
        create_user_listing_package(
            user=self.other,
            listing_package=self.pkg2,
            free_total=5,
            paid_total=1,
        )

    def test_my_packages_returns_only_current_user_packages(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/users/me/services/packages/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsInstance(resp.data, list)
        ids = {row["listing_package"]["public_id"] for row in resp.data}
        self.assertEqual(ids, {str(self.pkg1.public_id)})

    def test_slot_summary_returns_rows_for_authenticated_user(self):
        self.client.force_authenticate(user=self.user)
        commands.purchase_package(user=self.user, package=self.pkg1, pay_with="free")
        resp = self.client.get("/api/users/me/services/slot-summary/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsInstance(resp.data, list)
