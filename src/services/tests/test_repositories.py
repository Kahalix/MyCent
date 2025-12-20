from __future__ import annotations
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from services.services import repositories as repo
from .factories import (
    create_user,
    create_item_type,
    create_listing_package,
    create_user_listing_package,
    create_item_set,
    create_listing_usage_history,
)


class RepositoryLookupTests(TestCase):
    def test_get_package_by_public_id_returns_package(self):
        pkg = create_listing_package()
        found = repo.get_package_by_public_id(pkg.public_id)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, pkg.id)

    def test_get_package_by_public_id_unknown_returns_none(self):
        found = repo.get_package_by_public_id("non-existent")
        self.assertIsNone(found)

    def test_get_or_create_user_pkg_creates_and_then_reuses(self):
        user = create_user()
        pkg = create_listing_package()
        up1 = repo.get_or_create_user_pkg(user, pkg)
        up2 = repo.get_or_create_user_pkg(user, pkg)
        self.assertEqual(up1.id, up2.id)
        self.assertEqual(up1.free_total, 0)
        self.assertEqual(up1.paid_total, 0)

    def test_get_active_usage_for_itemset_filters_released(self):
        user = create_user()
        itype = create_item_type()
        itemset = create_item_set(owner_user=user, item_type=itype)
        active = create_listing_usage_history(user=user, item_type=itype, itemset=itemset, is_bought=False)
        found = repo.get_active_usage_for_itemset(itemset)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, active.id)

        active.released_at = timezone.now()
        active.save(update_fields=["released_at"])
        found2 = repo.get_active_usage_for_itemset(itemset)
        self.assertIsNone(found2)


class RepositoryTotalsTests(TestCase):
    def test_totals_for_user_and_type_aggregates_all_packages(self):
        user = create_user()
        itype = create_item_type()
        pkg1 = create_listing_package(item_type=itype)
        pkg2 = create_listing_package(item_type=itype)
        create_user_listing_package(user=user, listing_package=pkg1, free_total=1, paid_total=2)
        create_user_listing_package(user=user, listing_package=pkg2, free_total=3, paid_total=4)

        other_type = create_item_type()
        other_pkg = create_listing_package(item_type=other_type)
        create_user_listing_package(user=user, listing_package=other_pkg, free_total=10, paid_total=10)

        free_total, paid_total = repo.totals_for_user_and_type(user, itype)
        self.assertEqual(free_total, 4)
        self.assertEqual(paid_total, 6)

    def test_active_free_used_count_counts_only_active_free(self):
        user = create_user()
        itype = create_item_type()
        item1 = create_item_set(owner_user=user, item_type=itype)
        item2 = create_item_set(owner_user=user, item_type=itype)
        create_listing_usage_history(user=user, item_type=itype, itemset=item1, is_bought=False)
        create_listing_usage_history(user=user, item_type=itype, itemset=item2, is_bought=False)

        other_type = create_item_type()
        other_item = create_item_set(owner_user=user, item_type=other_type)
        create_listing_usage_history(user=user, item_type=other_type, itemset=other_item, is_bought=False)

        from django.utils import timezone as tz

        released = create_listing_usage_history(user=user, item_type=itype, itemset=None, is_bought=False)
        released.released_at = tz.now()
        released.save(update_fields=["released_at"])

        self.assertEqual(repo.active_free_used_count(user, itype), 2)

    def test_paid_consumed_count_counts_all_paid_lifetime(self):
        user = create_user()
        itype = create_item_type()
        item = create_item_set(owner_user=user, item_type=itype)
        create_listing_usage_history(user=user, item_type=itype, itemset=item, is_bought=True)
        create_listing_usage_history(user=user, item_type=itype, itemset=None, is_bought=True)

        other_type = create_item_type()
        create_listing_usage_history(user=user, item_type=other_type, itemset=None, is_bought=True)

        self.assertEqual(repo.paid_consumed_count(user, itype), 2)

    def test_active_itemsets_count_filters_by_owner_added_by_and_status(self):
        user = create_user()
        itype = create_item_type()
        create_item_set(owner_user=user, item_type=itype, added_by="USER", status="AVAILABLE")
        create_item_set(owner_user=user, item_type=itype, added_by="USER", status="AVAILABLE")

        create_item_set(owner_user=user, item_type=itype, added_by="USER", status="SOLD")
        create_item_set(owner_user=user, item_type=itype, added_by="STAFF", status="AVAILABLE")

        other_user = create_user()
        create_item_set(owner_user=other_user, item_type=itype, added_by="USER", status="AVAILABLE")

        other_type = create_item_type()
        create_item_set(owner_user=user, item_type=other_type, added_by="USER", status="AVAILABLE")

        self.assertEqual(repo.active_itemsets_count(user, itype), 2)


class RepositoryMutationTests(TestCase):
    def test_add_free_capacity_increments_total(self):
        up = create_user_listing_package(free_total=1, paid_total=0)
        updated = repo.add_free_capacity(up, 3)
        self.assertEqual(updated.free_total, 4)

    def test_add_paid_credits_increments_total(self):
        up = create_user_listing_package(free_total=0, paid_total=2)
        updated = repo.add_paid_credits(up, 5)
        self.assertEqual(updated.paid_total, 7)

    def test_create_usage_and_release_usage(self):
        user = create_user()
        itype = create_item_type()
        item = create_item_set(owner_user=user, item_type=itype)
        usage = repo.create_usage(user, itype, item, is_bought=False)
        self.assertIsNone(usage.released_at)
        repo.release_usage(usage)
        usage.refresh_from_db()
        self.assertIsNotNone(usage.released_at)


class RepositoryActivityTests(TestCase):
    def test_item_types_with_activity_for_user_combines_packages_and_usages(self):
        user = create_user()
        type_from_usage = create_item_type(name="T1")
        type_from_pkg = create_item_type(name="T2")

        item = create_item_set(owner_user=user, item_type=type_from_usage)
        create_listing_usage_history(user=user, item_type=type_from_usage, itemset=item, is_bought=False)

        pkg = create_listing_package(item_type=type_from_pkg)
        create_user_listing_package(user=user, listing_package=pkg, free_total=1, paid_total=0)

        result = list(repo.item_types_with_activity_for_user(user))
        ids = {t.id for t in result}
        self.assertEqual(ids, {type_from_usage.id, type_from_pkg.id})
