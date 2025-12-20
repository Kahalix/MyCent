from __future__ import annotations
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from services.models import UserListingPackage, ListingUsageHistory, ServicePurchaseHistory
from services.services import commands
from services.services.exceptions import PurchaseError, NoSlotsLeft, Forbidden
from services.services import repositories as repo
from .factories import (
    create_user,
    create_item_type,
    create_listing_package,
    create_user_listing_package,
    create_item_set,
    create_listing_usage_history,
)


class PurchasePackageTests(TestCase):
    def test_purchase_with_points_success(self):
        user = create_user(points=100)
        itype = create_item_type()
        pkg = create_listing_package(item_type=itype, listings_free=3, price_amount=None, points=50)

        up = commands.purchase_package(user=user, package=pkg, pay_with="points")

        user.refresh_from_db()
        self.assertEqual(user.points, 50)
        self.assertEqual(up.free_total, 3)
        self.assertEqual(up.paid_total, 0)
        history = ServicePurchaseHistory.objects.filter(user=user, listing_package=pkg).first()
        self.assertIsNotNone(history)
        self.assertIsNone(history.purchase_cost_amount)
        self.assertEqual(history.points_used, 50)

    def test_purchase_with_points_insufficient_raises_and_does_not_change_state(self):
        user = create_user(points=10)
        itype = create_item_type()
        pkg = create_listing_package(item_type=itype, listings_free=1, price_amount=None, points=50)

        with self.assertRaises(PurchaseError):
            commands.purchase_package(user=user, package=pkg, pay_with="points")

        user.refresh_from_db()
        self.assertEqual(user.points, 10)
        self.assertFalse(UserListingPackage.objects.filter(user=user, listing_package=pkg).exists())
        self.assertFalse(ServicePurchaseHistory.objects.filter(user=user, listing_package=pkg).exists())

    def test_purchase_with_money_success(self):
        user = create_user(points=0)
        itype = create_item_type()
        pkg = create_listing_package(item_type=itype, listings_free=0, price_amount=Decimal("10.00"), points=0)

        up = commands.purchase_package(user=user, package=pkg, pay_with="money")

        user.refresh_from_db()
        self.assertEqual(user.points, 0)
        self.assertEqual(up.free_total, 0)
        self.assertEqual(up.paid_total, 1)
        history = ServicePurchaseHistory.objects.filter(user=user, listing_package=pkg).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.purchase_cost_amount, Decimal("10.00"))
        self.assertEqual(history.purchase_cost_currency, "PLN")
        self.assertIsNone(history.points_used)

    def test_purchase_with_money_without_price_raises(self):
        user = create_user(points=0)
        itype = create_item_type()
        pkg = create_listing_package(item_type=itype, listings_free=0, price_amount=None, points=0)

        with self.assertRaises(PurchaseError):
            commands.purchase_package(user=user, package=pkg, pay_with="money")

        self.assertFalse(ServicePurchaseHistory.objects.filter(user=user, listing_package=pkg).exists())

    def test_purchase_auto_selects_points_or_money_or_free(self):
        user = create_user(points=100)
        itype = create_item_type()
        pkg_points = create_listing_package(item_type=itype, listings_free=2, price_amount=Decimal("5.00"), points=20)
        up1 = commands.purchase_package(user=user, package=pkg_points, pay_with=None)
        user.refresh_from_db()
        self.assertEqual(user.points, 80)
        self.assertEqual(up1.free_total, 2)

        pkg_money = create_listing_package(item_type=itype, listings_free=0, price_amount=Decimal("7.00"), points=0)
        up2 = commands.purchase_package(user=user, package=pkg_money, pay_with=None)
        self.assertEqual(up2.paid_total, 1)

        pkg_free = create_listing_package(item_type=itype, listings_free=1, price_amount=None, points=0)
        up3 = commands.purchase_package(user=user, package=pkg_free, pay_with=None)
        self.assertEqual(up3.free_total, 1)


class ConsumeReleaseSlotTests(TestCase):
    def test_consume_slot_returns_existing_active_usage(self):
        user = create_user()
        itype = create_item_type()
        item = create_item_set(owner_user=user, item_type=itype)
        existing = create_listing_usage_history(user=user, item_type=itype, itemset=item, is_bought=False)

        usage = commands.consume_slot_for_itemset(user=user, itemset=item)
        self.assertEqual(usage.id, existing.id)
        self.assertEqual(ListingUsageHistory.objects.count(), 1)

    def test_consume_slot_for_foreign_item_raises_forbidden(self):
        owner = create_user()
        other = create_user()
        itype = create_item_type()
        item = create_item_set(owner_user=owner, item_type=itype)

        with self.assertRaises(Forbidden):
            commands.consume_slot_for_itemset(user=other, itemset=item)

    def test_consume_slot_uses_free_when_available(self):
        user = create_user()
        itype = create_item_type()
        item = create_item_set(owner_user=user, item_type=itype)
        pkg = create_listing_package(item_type=itype)
        create_user_listing_package(user=user, listing_package=pkg, free_total=2, paid_total=0)

        usage = commands.consume_slot_for_itemset(user=user, itemset=item)
        self.assertFalse(usage.is_bought)
        self.assertEqual(ListingUsageHistory.objects.filter(user=user, item_type=itype).count(), 1)

    def test_consume_slot_uses_paid_when_free_exhausted(self):
        user = create_user()
        itype = create_item_type()
        item_free = create_item_set(owner_user=user, item_type=itype)
        item_paid = create_item_set(owner_user=user, item_type=itype)
        pkg = create_listing_package(item_type=itype)
        create_user_listing_package(user=user, listing_package=pkg, free_total=1, paid_total=2)
        create_listing_usage_history(user=user, item_type=itype, itemset=item_free, is_bought=False)

        usage = commands.consume_slot_for_itemset(user=user, itemset=item_paid)
        self.assertTrue(usage.is_bought)

    class ConsumeReleaseSlotTests(TestCase):
        def test_consume_slot_raises_when_no_slots_left(self):
            user = create_user()
            itype = create_item_type()
            item1 = create_item_set(owner_user=user, item_type=itype)
            item2 = create_item_set(owner_user=user, item_type=itype)
            item3 = create_item_set(owner_user=user, item_type=itype)
            pkg = create_listing_package(item_type=itype)
            create_user_listing_package(user=user, listing_package=pkg, free_total=1, paid_total=1)

            create_listing_usage_history(user=user, item_type=itype, itemset=item1, is_bought=False)
            create_listing_usage_history(user=user, item_type=itype, itemset=item2, is_bought=True)

            with self.assertRaises(NoSlotsLeft):
                commands.consume_slot_for_itemset(user=user, itemset=item3)

    def test_release_slot_for_itemset_releases_active_usage(self):
        user = create_user()
        itype = create_item_type()
        item = create_item_set(owner_user=user, item_type=itype)
        usage = create_listing_usage_history(user=user, item_type=itype, itemset=item, is_bought=False)
        self.assertIsNone(usage.released_at)

        commands.release_slot_for_itemset(itemset=item)

        usage.refresh_from_db()
        self.assertIsNotNone(usage.released_at)

    def test_release_slot_for_itemset_without_usage_is_noop(self):
        user = create_user()
        itype = create_item_type()
        item = create_item_set(owner_user=user, item_type=itype)
        commands.release_slot_for_itemset(itemset=item)
        self.assertEqual(ListingUsageHistory.objects.count(), 0)


class EnsureSlotMatchesStateTests(TestCase):
    def test_non_user_listing_is_ignored(self):
        user = create_user()
        itype = create_item_type()
        item = create_item_set(owner_user=None, item_type=itype, added_by="STAFF", status="AVAILABLE")
        commands.ensure_slot_matches_state(user=user, itemset=item)
        self.assertEqual(ListingUsageHistory.objects.count(), 0)

    def test_ensure_slot_for_foreign_user_raises_forbidden(self):
        owner = create_user()
        other = create_user()
        itype = create_item_type()
        item = create_item_set(owner_user=owner, item_type=itype, added_by="USER", status="AVAILABLE")
        with self.assertRaises(Forbidden):
            commands.ensure_slot_matches_state(user=other, itemset=item)

    def test_available_user_listing_without_usage_creates_usage(self):
        user = create_user()
        itype = create_item_type()
        item = create_item_set(owner_user=user, item_type=itype, added_by="USER", status="AVAILABLE")
        pkg = create_listing_package(item_type=itype)
        create_user_listing_package(user=user, listing_package=pkg, free_total=1, paid_total=0)

        commands.ensure_slot_matches_state(user=user, itemset=item)

        active = repo.get_active_usage_for_itemset(item)
        self.assertIsNotNone(active)

    def test_available_listing_with_same_type_usage_no_change(self):
        user = create_user()
        itype = create_item_type()
        item = create_item_set(owner_user=user, item_type=itype, added_by="USER", status="AVAILABLE")
        pkg = create_listing_package(item_type=itype)
        create_user_listing_package(user=user, listing_package=pkg, free_total=2, paid_total=0)
        usage = create_listing_usage_history(user=user, item_type=itype, itemset=item, is_bought=False)

        commands.ensure_slot_matches_state(user=user, itemset=item)

        self.assertEqual(ListingUsageHistory.objects.filter(item_set=item).count(), 1)
        usage.refresh_from_db()
        self.assertIsNone(usage.released_at)

    def test_available_listing_with_changed_type_moves_usage(self):
        user = create_user()
        old_type = create_item_type(name="Old")
        new_type = create_item_type(name="New")
        item = create_item_set(owner_user=user, item_type=old_type, added_by="USER", status="AVAILABLE")
        old_pkg = create_listing_package(item_type=old_type)
        new_pkg = create_listing_package(item_type=new_type)
        create_user_listing_package(user=user, listing_package=old_pkg, free_total=1, paid_total=0)
        create_user_listing_package(user=user, listing_package=new_pkg, free_total=1, paid_total=0)
        old_usage = create_listing_usage_history(user=user, item_type=old_type, itemset=item, is_bought=False)

        item.type = new_type
        item.save(update_fields=["type"])

        commands.ensure_slot_matches_state(user=user, itemset=item)

        old_usage.refresh_from_db()
        self.assertIsNotNone(old_usage.released_at)
        new_usage = repo.get_active_usage_for_itemset(item)
        self.assertIsNotNone(new_usage)
        self.assertEqual(new_usage.item_type_id, new_type.id)

    def test_non_available_listing_releases_active_usage(self):
        user = create_user()
        itype = create_item_type()
        item = create_item_set(owner_user=user, item_type=itype, added_by="USER", status="AVAILABLE")
        pkg = create_listing_package(item_type=itype)
        create_user_listing_package(user=user, listing_package=pkg, free_total=1, paid_total=0)
        commands.ensure_slot_matches_state(user=user, itemset=item)

        item.status = "SOLD"
        item.save(update_fields=["status"])
        commands.ensure_slot_matches_state(user=user, itemset=item)

        usage = ListingUsageHistory.objects.filter(item_set=item).first()
        self.assertIsNotNone(usage)
        self.assertIsNotNone(usage.released_at)


class GrantSignupFreebiesTests(TestCase):
    @override_settings(SERVICES_SIGNUP_FREE_PACKAGE_PUBLIC_IDS=[])
    def test_grant_signup_freebies_with_empty_settings_does_nothing(self):
        user = create_user()
        commands.grant_signup_freebies(user)
        self.assertEqual(UserListingPackage.objects.count(), 0)
        self.assertEqual(ServicePurchaseHistory.objects.count(), 0)

    @override_settings(SERVICES_SIGNUP_FREE_PACKAGE_PUBLIC_IDS=None)
    def test_grant_signup_freebies_with_none_settings_does_nothing(self):
        user = create_user()
        commands.grant_signup_freebies(user)
        self.assertEqual(UserListingPackage.objects.count(), 0)
        self.assertEqual(ServicePurchaseHistory.objects.count(), 0)

    @override_settings(SERVICES_SIGNUP_FREE_PACKAGE_PUBLIC_IDS=["PKGFREE1"])
    def test_grant_signup_freebies_grants_only_once(self):
        user = create_user()
        itype = create_item_type()
        pkg = create_listing_package(item_type=itype, listings_free=2, price_amount=None, points=0)
        pkg.public_id = "PKGFREE1"
        pkg.save(update_fields=["public_id"])

        commands.grant_signup_freebies(user)
        commands.grant_signup_freebies(user)

        up = UserListingPackage.objects.filter(user=user, listing_package=pkg).first()
        self.assertIsNotNone(up)
        self.assertEqual(up.free_total, 2)

        histories = ServicePurchaseHistory.objects.filter(
            user=user,
            listing_package=pkg,
            description="SIGNUP_FREE",
        )
        self.assertEqual(histories.count(), 1)


class SlotSummaryForUserTests(TestCase):
    def test_slot_summary_for_user_returns_expected_structure(self):
        user = create_user()
        itype = create_item_type(name="Kategoria X")
        pkg = create_listing_package(item_type=itype)
        create_user_listing_package(user=user, listing_package=pkg, free_total=5, paid_total=2)

        item = create_item_set(owner_user=user, item_type=itype, added_by="USER", status="AVAILABLE")
        create_listing_usage_history(user=user, item_type=itype, itemset=item, is_bought=False)
        create_listing_usage_history(user=user, item_type=itype, itemset=None, is_bought=True)
        create_listing_usage_history(
            user=user,
            item_type=itype,
            itemset=None,
            is_bought=True,
            released_at=timezone.now(),
        )

        rows = commands.slot_summary_for_user(user)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["item_type"]["name"], "Kategoria X")
        self.assertEqual(row["free_total"], 5)
        self.assertEqual(row["free_used_active"], 1)
        self.assertEqual(row["free_left"], 4)
        self.assertEqual(row["paid_total"], 2)
        self.assertEqual(row["paid_used_lifetime"], 2)
        self.assertEqual(row["paid_left"], 0)
        self.assertEqual(row["active_itemsets"], 1)
