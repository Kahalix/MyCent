from __future__ import annotations
from decimal import Decimal

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from services.models import ListingPackage, UserListingPackage
from services.services import commands
from services.services.exceptions import Forbidden
from .factories import (
    create_user,
    create_item_type,
    create_listing_package,
    create_user_listing_package,
    create_item_set,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class PublicListingPackageSecurityTests(APITestCase):
    def setUp(self):
        self.itype = create_item_type(name="Bezpieczna")
        self.pkg = create_listing_package(
            item_type=self.itype,
            listings_free=1,
            price_amount=Decimal("5.00"),
            points=0,
        )

    def test_search_parameter_is_safe_against_injection_like_input(self):
        payload = {
            "search": "Bezpieczna'; DROP TABLE services_listingpackage;--"
        }
        resp = self.client.get(
            "/api/public/services/listing-packages/",
            payload,
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get("results", resp.data)
        self.assertGreaterEqual(len(results), 0)
        self.assertEqual(ListingPackage.objects.count(), 1)

    def test_price_filters_with_invalid_number_return_400_or_200(self):
        resp = self.client.get(
            "/api/public/services/listing-packages/",
            {"price_min": "0 OR 1=1"},
        )
        self.assertIn(
            resp.status_code,
            (status.HTTP_400_BAD_REQUEST, status.HTTP_200_OK),
        )


@override_settings(SECURE_SSL_REDIRECT=False)
class MyServicesSecurityTests(APITestCase):
    def setUp(self):
        self.user = create_user("secured-services@example.com")
        self.other = create_user("other-secured-services@example.com")
        self.itype = create_item_type()
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

    def test_my_services_requires_authentication(self):
        resp1 = self.client.get("/api/users/me/services/packages/")
        resp2 = self.client.get("/api/users/me/services/slot-summary/")
        self.assertEqual(resp1.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp2.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_my_packages_does_not_leak_other_users_data(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/users/me/services/packages/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsInstance(resp.data, list)

        other_ids = set(
            UserListingPackage.objects.filter(user=self.other).values_list(
                "listing_package__public_id",
                flat=True,
            )
        )
        self.assertTrue(
            all(row["listing_package"]["public_id"] not in other_ids for row in resp.data)
        )


@override_settings(SECURE_SSL_REDIRECT=False)
class CommandsSecurityTests(APITestCase):
    def test_consume_slot_cannot_be_used_for_foreign_itemset(self):
        owner = create_user("owner@example.com")
        attacker = create_user("attacker@example.com")
        itype = create_item_type()
        item = create_item_set(
            owner_user=owner,
            item_type=itype,
            added_by="USER",
            status="AVAILABLE",
        )
        with self.assertRaises(Forbidden):
            commands.consume_slot_for_itemset(user=attacker, itemset=item)

    def test_ensure_slot_matches_state_cannot_be_used_for_foreign_itemset(self):
        owner = create_user("owner2@example.com")
        attacker = create_user("attacker2@example.com")
        itype = create_item_type()
        item = create_item_set(
            owner_user=owner,
            item_type=itype,
            added_by="USER",
            status="AVAILABLE",
        )
        with self.assertRaises(Forbidden):
            commands.ensure_slot_matches_state(user=attacker, itemset=item)
