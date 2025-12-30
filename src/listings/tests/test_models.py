from __future__ import annotations
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from djmoney.money import Money

from listings.models import ItemSet, ItemSetShipping
from .factories import (
    create_item_type,
    create_catalog_item,
    create_item_set,
    create_package_type,
    create_user,
    create_seller_profile,
)


class ItemSetModelTests(TestCase):
    def test_slug_is_generated_and_contains_public_id(self):
        itype = create_item_type(name="Elektronika")
        item = create_item_set(item_type=itype)
        self.assertTrue(item.slug)
        self.assertIn(str(item.public_id), item.slug)

    def test_clean_rejects_non_leaf_type(self):
        parent = create_item_type(name="Root")
        child = create_item_type(name="Child", parent=parent)
        item = create_item_set(item_type=parent)
        with self.assertRaises(ValidationError) as ctx:
            item.clean()
        self.assertIn("type", ctx.exception.message_dict)

    def test_clean_prefills_attributes_from_catalog_item_when_empty(self):
        itype = create_item_type(name="Books")
        catalog = create_catalog_item(item_type=itype, attributes={"pages": 100})
        item = create_item_set(item_type=itype, catalog_item=catalog, attributes={})
        item.clean()
        self.assertEqual(item.attributes.get("pages"), 100)

    def test_clean_user_rules_are_enforced(self):
        itype = create_item_type()
        owner = create_user()

        item = ItemSet(
            set_name="User item",
            description="",
            price=Money("10.00", "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=True,
            added_by="USER",
            owner_user=owner,
            type=itype,
            attributes={},
        )
        with self.assertRaises(ValidationError) as ctx1:
            item.clean()
        self.assertIn("allow_online_checkout", ctx1.exception.message_dict)

        item.allow_online_checkout = False
        seller = create_seller_profile()
        item.seller_profile = seller
        with self.assertRaises(ValidationError) as ctx2:
            item.clean()
        self.assertIn("seller_profile", ctx2.exception.message_dict)

    def test_clean_user_requires_owner_and_only_listing_or_exchange(self):
        itype = create_item_type()
        item = ItemSet(
            set_name="User item",
            description="",
            price=Money("10.00", "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=False,
            added_by="USER",
            owner_user=None,
            type=itype,
            attributes={},
        )
        with self.assertRaises(ValidationError) as ctx1:
            item.clean()
        self.assertIn("owner_user", ctx1.exception.message_dict)

        owner = create_user()
        item.owner_user = owner
        item.listing_type = "BUY"
        with self.assertRaises(ValidationError) as ctx2:
            item.clean()
        self.assertIn("listing_type", ctx2.exception.message_dict)

    def test_clean_checkout_rules_for_staff(self):
        itype = create_item_type()
        seller = create_seller_profile()

        item = ItemSet(
            set_name="Staff item",
            description="",
            price=Money("10.00", "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=True,
            added_by="STAFF",
            seller_profile=seller,
            type=itype,
            attributes={},
        )
        with self.assertRaises(ValidationError) as ctx1:
            item.clean()
        self.assertIn("allow_online_checkout", ctx1.exception.message_dict)

        item.listing_type = "BUY"
        item.seller_profile = None
        with self.assertRaises(ValidationError) as ctx2:
            item.clean()
        self.assertIn("seller_profile", ctx2.exception.message_dict)

    def test_fits_package_respects_dimensions_and_weight(self):
        itype = create_item_type()
        item = create_item_set(
            item_type=itype,
            length_cm=10,
            width_cm=20,
            height_cm=30,
            weight_kg=Decimal("1.0"),
        )

        class DummyPkg:
            max_length_cm = 15
            max_width_cm = 25
            max_height_cm = 35
            max_weight_kg = Decimal("2.0")

        pkg_ok = DummyPkg()
        self.assertTrue(item.fits_package(pkg_ok))
        pkg_bad = DummyPkg()
        pkg_bad.max_weight_kg = Decimal("0.5")
        self.assertFalse(item.fits_package(pkg_bad))


class ItemSetShippingModelTests(TestCase):
    def test_clean_requires_staff_buy_with_checkout(self):
        itype = create_item_type()
        item = create_item_set(
            item_type=itype,
            added_by="STAFF",
            listing_type="LISTING",
            allow_online_checkout=False,
        )
        pkg = create_package_type()
        shipping = ItemSetShipping(
            item_set=item,
            package_type=pkg,
        )
        with self.assertRaises(ValidationError):
            shipping.clean()
        item.listing_type = "BUY"
        item.allow_online_checkout = True
        shipping = ItemSetShipping(
            item_set=item,
            package_type=pkg,
        )
        shipping.clean()

    def test_clean_validates_positive_dimensions_and_weight_and_fit(self):
        itype = create_item_type()
        item = create_item_set(
            item_type=itype,
            added_by="STAFF",
            listing_type="BUY",
            allow_online_checkout=True,
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
        )
        shipping = ItemSetShipping(
            item_set=item,
            package_type=pkg,
            packed_length_cm=12,
            packed_width_cm=22,
            packed_height_cm=32,
            packed_weight_kg=Decimal("1.5"),
        )
        shipping.clean()
        shipping_bad = ItemSetShipping(
            item_set=item,
            package_type=pkg,
            packed_length_cm=0,
        )
        with self.assertRaises(ValidationError):
            shipping_bad.clean()
        shipping_too_big = ItemSetShipping(
            item_set=item,
            package_type=pkg,
            packed_length_cm=1000,
        )
        with self.assertRaises(ValidationError):
            shipping_too_big.clean()
