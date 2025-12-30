from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from moneyed import Money

from listings.models import ItemSetShipping
from listings.services import queries
from .factoriesOLD import (
    make_user,
    make_seller,
    make_leaf_item_type,
    make_package_type,
    make_staff_itemset,
)


class PublicItemsetsQueriesTests(TestCase):
    def setUp(self):
        self.user = make_user("owner@example.com")
        self.seller = make_seller(self.user)
        self.item_type = make_leaf_item_type()

    def test_public_itemsets_qs_only_available_and_ordered_desc(self):
        older = make_staff_itemset(self.seller, self.item_type, status="AVAILABLE")
        newer = make_staff_itemset(self.seller, self.item_type, status="AVAILABLE")
        closed = make_staff_itemset(self.seller, self.item_type, status="CLOSED")

        older.created_at = timezone.now() - timedelta(hours=1)
        older.save(update_fields=["created_at"])
        newer.created_at = timezone.now()
        newer.save(update_fields=["created_at"])

        qs = queries.public_itemsets_qs()
        ids = list(qs.values_list("public_id", flat=True))
        self.assertEqual(ids, [newer.public_id, older.public_id])
        self.assertNotIn(closed.public_id, ids)

    def test_itemset_by_slug_uses_public_id_suffix_and_slug_fallback(self):
        item = make_staff_itemset(self.seller, self.item_type, set_name="Phone X", status="AVAILABLE")
        slug_with_tail = f"whatever-{item.public_id}"
        found = queries.itemset_by_slug(slug_with_tail)
        self.assertIsNotNone(found)
        self.assertEqual(found.public_id, item.public_id)

        item2 = make_staff_itemset(self.seller, self.item_type, set_name="Other", status="AVAILABLE")
        item2.slug = "custom-slug"
        item2.save(update_fields=["slug"])

        found2 = queries.itemset_by_slug("custom-slug")
        self.assertIsNotNone(found2)
        self.assertEqual(found2.public_id, item2.public_id)

        item3 = make_staff_itemset(self.seller, self.item_type, set_name="Closed", status="CLOSED")
        slug3 = item3.slug
        not_found = queries.itemset_by_slug(slug3)
        self.assertIsNone(not_found)


class SuggestPackageTypesTests(TestCase):
    def setUp(self):
        self.user = make_user("pack@example.com")
        self.seller = make_seller(self.user)
        self.item_type = make_leaf_item_type()
        self.item = make_staff_itemset(
            self.seller,
            self.item_type,
            status="AVAILABLE",
            listing_type="BUY",
            allow_online_checkout=True,
            length_cm=10,
            width_cm=10,
            height_cm=10,
            weight_kg=1,
        )
        self.pkg_plain = make_package_type(
            provider="PP",
            dimensions="S",
            max_length_cm=20,
            max_width_cm=20,
            max_height_cm=20,
            max_weight_kg=2,
            price_amount=8,
        )
        self.pkg_link = make_package_type(
            provider="PP",
            dimensions="M",
            max_length_cm=20,
            max_width_cm=20,
            max_height_cm=20,
            max_weight_kg=2,
            price_amount=15,
        )
        self.pkg_small = make_package_type(
            provider="PP",
            dimensions="XS",
            max_length_cm=5,
            max_width_cm=5,
            max_height_cm=5,
            max_weight_kg=1,
            price_amount=5,
        )
        self.link = ItemSetShipping.objects.create(
            item_set=self.item,
            package_type=self.pkg_link,
            price_override=Money(12, "PLN"),
        )

    def test_suggest_package_types_returns_only_fitting_and_sorted_by_effective_price(self):
        rows = queries.suggest_package_types(self.item)
        self.assertEqual(len(rows), 2)
        ids = {r["package_type"].public_id for r in rows}
        self.assertIn(self.pkg_plain.public_id, ids)
        self.assertIn(self.pkg_link.public_id, ids)

        first = rows[0]
        second = rows[1]

        self.assertEqual(first["package_type"].public_id, self.pkg_plain.public_id)
        self.assertEqual(first["effective_price"], self.pkg_plain.price)
        self.assertEqual(first["price_source"], "catalog")
        self.assertFalse(first["already_linked"])

        self.assertEqual(second["package_type"].public_id, self.pkg_link.public_id)
        self.assertEqual(second["effective_price"], self.link.price_override)
        self.assertEqual(second["price_source"], "override")
        self.assertTrue(second["already_linked"])
