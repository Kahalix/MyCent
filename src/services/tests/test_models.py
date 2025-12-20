from __future__ import annotations
from decimal import Decimal

from django.test import TestCase

from services.models import (
    ListingPackage,
    UserListingPackage,
    ListingUsageHistory,
    ServicePurchaseHistory,
)
from .factories import (
    create_user,
    create_item_type,
    create_listing_package,
    create_user_listing_package,
    create_listing_usage_history,
    create_service_purchase_history,
)


class ListingPackageModelTests(TestCase):
    def test_str_includes_type_free_price_points(self):
        item_type = create_item_type(name="Elektronika")
        pkg = create_listing_package(
            item_type=item_type,
            listings_free=5,
            price_amount=Decimal("10.00"),
            points=25,
        )
        s = str(pkg)
        self.assertIn("Elektronika", s)
        self.assertIn("free:5", s)
        self.assertIn("pts:25", s)


class UserListingPackageModelTests(TestCase):
    def test_str_includes_user_and_package_public_id(self):
        user = create_user(email="user@example.com")
        pkg = create_listing_package()
        up = create_user_listing_package(user=user, listing_package=pkg, free_total=3, paid_total=1)
        s = str(up)
        self.assertIn("user@example.com", s)
        self.assertIn(str(pkg.public_id), s)
        self.assertIn("free:3", s)
        self.assertIn("paid:1", s)


class ListingUsageHistoryModelTests(TestCase):
    def test_str_active_free(self):
        user = create_user(email="user1@example.com")
        itype = create_item_type(name="Kategoria A")
        usage = create_listing_usage_history(user=user, item_type=itype, is_bought=False)
        s = str(usage)
        self.assertIn("user1@example.com", s)
        self.assertIn("Kategoria A", s)
        self.assertIn("FREE", s)
        self.assertIn("ACTIVE", s)

    def test_str_released_paid(self):
        from django.utils import timezone

        user = create_user(email="user2@example.com")
        itype = create_item_type(name="Kategoria B")
        usage = create_listing_usage_history(
            user=user,
            item_type=itype,
            is_bought=True,
            released_at=timezone.now(),
        )
        s = str(usage)
        self.assertIn("user2@example.com", s)
        self.assertIn("Kategoria B", s)
        self.assertIn("PAID", s)
        self.assertIn("RELEASED", s)


class ServicePurchaseHistoryModelTests(TestCase):
    def test_str_with_money_cost(self):
        user = create_user(email="money@example.com")
        pkg = create_listing_package()
        sph = create_service_purchase_history(
            user=user,
            listing_package=pkg,
            cost_amount=Decimal("12.50"),
            cost_currency="PLN",
            points_used=None,
        )
        s = str(sph)
        self.assertEqual(s, "money@example.com 12.50 PLN")

    def test_str_with_points(self):
        user = create_user(email="points@example.com")
        pkg = create_listing_package()
        sph = create_service_purchase_history(
            user=user,
            listing_package=pkg,
            cost_amount=None,
            cost_currency="PLN",
            points_used=100,
        )
        s = str(sph)
        self.assertEqual(s, "points@example.com 100 pts")

    def test_str_free(self):
        user = create_user(email="free@example.com")
        pkg = create_listing_package()
        sph = create_service_purchase_history(
            user=user,
            listing_package=pkg,
            cost_amount=None,
            cost_currency="PLN",
            points_used=None,
        )
        s = str(sph)
        self.assertEqual(s, "free@example.com FREE")
