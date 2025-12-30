from datetime import timedelta

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from moneyed import Money

from catalog.models import ItemType, CatalogItem
from listings.models import ItemSet, ItemSetShipping
from .factoriesOLD import (
    make_user,
    make_seller,
    make_leaf_item_type,
    make_package_type,
    make_staff_itemset,
)


class ItemSetModelCleanTests(TestCase):
    def setUp(self):
        self.user = make_user("user@example.com")
        self.item_type = make_leaf_item_type()

    def test_user_rules_invalid_combinations_raise(self):
        item = ItemSet(
            set_name="Invalid user 1",
            description="",
            price=Money(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=True,
            added_by="USER",
            seller_profile=None,
            owner_user=self.user,
            type=self.item_type,
            catalog_item=None,
            length_cm=10,
            width_cm=10,
            height_cm=10,
            weight_kg=1,
            attributes={},
        )
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("allow_online_checkout", ctx.exception.message_dict)

        item2 = ItemSet(
            set_name="Invalid user 2",
            description="",
            price=Money(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="BUY",
            allow_online_checkout=False,
            added_by="USER",
            seller_profile=None,
            owner_user=self.user,
            type=self.item_type,
            catalog_item=None,
            length_cm=10,
            width_cm=10,
            height_cm=10,
            weight_kg=1,
            attributes={},
        )
        with self.assertRaises(ValidationError) as ctx2:
            item2.full_clean()
        self.assertIn("listing_type", ctx2.exception.message_dict)

        item3 = ItemSet(
            set_name="Invalid user 3",
            description="",
            price=Money(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=False,
            added_by="USER",
            seller_profile=make_seller(self.user),
            owner_user=self.user,
            type=self.item_type,
            catalog_item=None,
            length_cm=10,
            width_cm=10,
            height_cm=10,
            weight_kg=1,
            attributes={},
        )
        with self.assertRaises(ValidationError) as ctx3:
            item3.full_clean()
        self.assertIn("seller_profile", ctx3.exception.message_dict)

        item4 = ItemSet(
            set_name="Invalid user 4",
            description="",
            price=Money(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=False,
            added_by="USER",
            seller_profile=None,
            owner_user=None,
            type=self.item_type,
            catalog_item=None,
            length_cm=10,
            width_cm=10,
            height_cm=10,
            weight_kg=1,
            attributes={},
        )
        with self.assertRaises(ValidationError) as ctx4:
            item4.full_clean()
        self.assertIn("owner_user", ctx4.exception.message_dict)

    def test_user_valid_combination_passes_clean(self):
        item = ItemSet(
            set_name="Valid user",
            description="",
            price=Money(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=False,
            added_by="USER",
            seller_profile=None,
            owner_user=self.user,
            type=self.item_type,
            catalog_item=None,
            length_cm=10,
            width_cm=10,
            height_cm=10,
            weight_kg=1,
            attributes={},
        )
        item.full_clean()

    def test_staff_checkout_rules(self):
        seller = make_seller(self.user)
        item = ItemSet(
            set_name="Bad staff",
            description="",
            price=Money(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=True,
            added_by="STAFF",
            seller_profile=seller,
            owner_user=None,
            type=self.item_type,
            catalog_item=None,
            length_cm=10,
            width_cm=10,
            height_cm=10,
            weight_kg=1,
            attributes={},
        )
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("allow_online_checkout", ctx.exception.message_dict)

        item2 = ItemSet(
            set_name="Bad staff no seller",
            description="",
            price=Money(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="BUY",
            allow_online_checkout=True,
            added_by="STAFF",
            seller_profile=None,
            owner_user=None,
            type=self.item_type,
            catalog_item=None,
            length_cm=10,
            width_cm=10,
            height_cm=10,
            weight_kg=1,
            attributes={},
        )
        with self.assertRaises(ValidationError) as ctx2:
            item2.full_clean()
        self.assertIn("seller_profile", ctx2.exception.message_dict)

        item3 = ItemSet(
            set_name="Good staff",
            description="",
            price=Money(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="BUY",
            allow_online_checkout=True,
            added_by="STAFF",
            seller_profile=seller,
            owner_user=None,
            type=self.item_type,
            catalog_item=None,
            length_cm=10,
            width_cm=10,
            height_cm=10,
            weight_kg=1,
            attributes={},
        )
        item3.full_clean()

    def test_type_leaf_and_catalog_item_rules(self):
        parent = ItemType.objects.create(name="Electronics", slug="electronics", path="electronics")
        child = ItemType.objects.create(
            name="Phones",
            slug="electronics-phones",
            path="electronics/phones",
            parent=parent,
        )
        item = ItemSet(
            set_name="Non leaf type",
            description="",
            price=Money(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=False,
            added_by="STAFF",
            seller_profile=None,
            owner_user=None,
            type=parent,
            catalog_item=None,
            length_cm=10,
            width_cm=10,
            height_cm=10,
            weight_kg=1,
            attributes={},
        )
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("type", ctx.exception.message_dict)

        other = ItemType.objects.create(name="Other", slug="other", path="other")
        catalog = CatalogItem.objects.create(
            type=other,
            slug="phone-1",
            item_name="Phone 1",
            image_path="",
            attributes={"color": "black"},
        )
        item2 = ItemSet(
            set_name="Cat mismatch",
            description="",
            price=Money(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=False,
            added_by="STAFF",
            seller_profile=None,
            owner_user=None,
            type=child,
            catalog_item=catalog,
            length_cm=10,
            width_cm=10,
            height_cm=10,
            weight_kg=1,
            attributes={},
        )
        with self.assertRaises(ValidationError) as ctx2:
            item2.full_clean()
        self.assertIn("catalog_item", ctx2.exception.message_dict)

        catalog2 = CatalogItem.objects.create(
            type=child,
            slug="phone-2",
            item_name="Phone 2",
            image_path="",
            attributes={"memory": "128GB"},
        )
        item3 = ItemSet(
            set_name="Cat fallback",
            description="",
            price=Money(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=False,
            added_by="STAFF",
            seller_profile=None,
            owner_user=None,
            type=None,
            catalog_item=catalog2,
            length_cm=10,
            width_cm=10,
            height_cm=10,
            weight_kg=1,
            attributes={},
        )
        item3.clean()
        self.assertEqual(item3.type_id, catalog2.type_id)
        self.assertEqual(item3.attributes, catalog2.attributes)


class ItemSetFitsPackageTests(TestCase):
    def test_fits_package_respects_dimensions_and_weight(self):
        user = make_user("u@example.com")
        item_type = make_leaf_item_type()
        seller = make_seller(user)
        item = make_staff_itemset(
            seller,
            item_type,
            length_cm=20,
            width_cm=10,
            height_cm=5,
            weight_kg=1,
        )
        pkg_ok = make_package_type(
            max_length_cm=25,
            max_width_cm=15,
            max_height_cm=10,
            max_weight_kg=2,
        )
        pkg_small = make_package_type(
            provider="P2",
            dimensions="XS",
            max_length_cm=10,
            max_width_cm=10,
            max_height_cm=5,
            max_weight_kg=1,
        )
        self.assertTrue(item.fits_package(pkg_ok))
        self.assertFalse(item.fits_package(pkg_small))


class ItemSetShippingCleanTests(TestCase):
    def setUp(self):
        self.user = make_user("s@example.com")
        self.item_type = make_leaf_item_type()
        self.seller = make_seller(self.user)
        self.pkg = make_package_type(
            max_length_cm=30,
            max_width_cm=30,
            max_height_cm=30,
            max_weight_kg=3,
        )

    def test_shipping_clean_rejects_non_checkout_itemsets(self):
        item = make_staff_itemset(
            self.seller,
            self.item_type,
            listing_type="LISTING",
            allow_online_checkout=False,
        )
        link = ItemSetShipping(
            item_set=item,
            package_type=self.pkg,
            packed_length_cm=10,
            packed_width_cm=10,
            packed_height_cm=10,
            packed_weight_kg=1,
        )
        with self.assertRaises(ValidationError):
            link.clean()

    def test_shipping_clean_validates_dimensions_and_weight(self):
        item = make_staff_itemset(
            self.seller,
            self.item_type,
            listing_type="BUY",
            allow_online_checkout=True,
            length_cm=20,
            width_cm=20,
            height_cm=20,
            weight_kg=1,
        )
        link = ItemSetShipping(
            item_set=item,
            package_type=self.pkg,
            packed_length_cm=0,
            packed_width_cm=10,
            packed_height_cm=10,
            packed_weight_kg=1,
        )
        with self.assertRaises(ValidationError) as ctx:
            link.clean()
        self.assertIn("packed_length_cm", ctx.exception.message_dict)

        link2 = ItemSetShipping(
            item_set=item,
            package_type=self.pkg,
            packed_length_cm=40,
            packed_width_cm=10,
            packed_height_cm=10,
            packed_weight_kg=1,
        )
        with self.assertRaises(ValidationError):
            link2.clean()

        link3 = ItemSetShipping(
            item_set=item,
            package_type=self.pkg,
            packed_length_cm=None,
            packed_width_cm=None,
            packed_height_cm=None,
            packed_weight_kg=None,
        )
        link3.clean()
