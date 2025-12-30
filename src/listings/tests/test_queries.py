from __future__ import annotations
from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from listings.services import queries
from listings.services.queries import itemset_by_slug
from .factories import (
    create_item_set,
    create_item_type,
    create_package_type,
    create_item_shipping,
)


class PublicItemsetsQsTests(TestCase):
    def test_public_itemsets_qs_returns_only_available_and_ordered(self):
        itype = create_item_type()
        item1 = create_item_set(item_type=itype, status="AVAILABLE")
        item2 = create_item_set(item_type=itype, status="AVAILABLE")
        item3 = create_item_set(item_type=itype, status="SOLD")

        now = timezone.now()
        item1.created_at = now - timedelta(minutes=1)
        item1.save(update_fields=["created_at"])
        item2.created_at = now
        item2.save(update_fields=["created_at"])

        qs = queries.public_itemsets_qs()
        ids = list(qs.values_list("id", flat=True))
        self.assertIn(item1.id, ids)
        self.assertIn(item2.id, ids)
        self.assertNotIn(item3.id, ids)
        self.assertEqual(ids, [item2.id, item1.id])


class SuggestPackageTypesTests(TestCase):
    def test_suggest_package_types_returns_empty_when_no_packages(self):
        item = create_item_set()
        result = queries.suggest_package_types(item)
        self.assertEqual(result, [])

    def test_suggest_package_types_includes_fitting_packages(self):
        item = create_item_set(
            length_cm=10,
            width_cm=20,
            height_cm=30,
            weight_kg=Decimal("1.0"),
        )
        pkg = create_package_type(
            max_length_cm=15,
            max_width_cm=25,
            max_height_cm=35,
            max_weight_kg=Decimal("2.0"),
            price_amount=Decimal("9.99"),
        )
        result = queries.suggest_package_types(item)
        self.assertEqual(len(result), 1)
        row = result[0]
        self.assertEqual(row["package_type"].id, pkg.id)
        self.assertEqual(row["effective_price"].amount, Decimal("9.99"))
        self.assertEqual(row["price_source"], "catalog")
        self.assertFalse(row["already_linked"])

    def test_suggest_package_types_respects_existing_links_and_override(self):
        item = create_item_set(
            length_cm=10,
            width_cm=20,
            height_cm=30,
            weight_kg=Decimal("1.0"),
        )
        pkg = create_package_type(
            max_length_cm=15,
            max_width_cm=25,
            max_height_cm=35,
            max_weight_kg=Decimal("2.0"),
            price_amount=Decimal("5.00"),
        )
        create_item_shipping(
            item_set=item,
            package_type=pkg,
            price_override_amount=Decimal("7.00"),
            packed_length_cm=12,
        )
        result = queries.suggest_package_types(item)
        self.assertEqual(len(result), 1)
        row = result[0]
        self.assertTrue(row["already_linked"])
        self.assertEqual(row["price_source"], "override")
        self.assertEqual(row["effective_price"].amount, Decimal("7.00"))

    def test_suggest_package_types_excludes_not_fitting_packages(self):
        item = create_item_set(
            length_cm=100,
            width_cm=100,
            height_cm=100,
            weight_kg=Decimal("10.0"),
        )
        create_package_type(
            max_length_cm=10,
            max_width_cm=10,
            max_height_cm=10,
            max_weight_kg=Decimal("1.0"),
        )
        result = queries.suggest_package_types(item)
        self.assertEqual(result, [])


class ItemsetBySlugTests(TestCase):
    def test_itemset_by_slug_uses_public_id_tail(self):
        item = create_item_set()
        slug = item.slug
        found = itemset_by_slug(slug)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, item.id)

    def test_itemset_by_slug_fallback_to_plain_slug(self):
        item = create_item_set()
        item.slug = "custom-slug"
        item.save(update_fields=["slug"])
        found = itemset_by_slug("custom-slug")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, item.id)

    def test_itemset_by_slug_returns_none_for_unavailable(self):
        item = create_item_set(status="SOLD")
        found = itemset_by_slug(item.slug)
        self.assertIsNone(found)
