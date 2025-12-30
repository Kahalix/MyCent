from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from moneyed import Money

from django.contrib.auth import get_user_model

from identity.models import SellerMembership
from catalog.models import CatalogItem
from listings.models import ItemSetImage, ItemSetShipping
from listings.services import commands
from listings.services.exceptions import Forbidden, BadRequest
from shipping.models import PackageType
from .factoriesOLD import (
    make_user,
    make_seller,
    make_leaf_item_type,
    make_staff_itemset,
    make_user_itemset,
    make_package_type,
)

User = get_user_model()


class CommandsItemsetCoreTests(TestCase):
    def setUp(self):
        self.user = make_user("cmd@example.com")
        self.item_type = make_leaf_item_type()
        self.seller = make_seller(self.user)

    def test_user_create_itemset_forces_listing_and_checkout_rules_and_calls_slot_sync(self):
        data = {
            "set_name": "User created item",
            "description": "",
            "price": Money(20, "PLN"),
            "stock_quantity": 1,
            "condition": "USED",
            "status": "AVAILABLE",
            "listing_type": "BUY",
            "allow_online_checkout": True,
            "type": self.item_type,
            "catalog_item": None,
            "length_cm": 10,
            "width_cm": 10,
            "height_cm": 10,
            "weight_kg": 1,
            "attributes": {},
        }
        with patch("listings.services.commands.ensure_slot_matches_state") as slot_mock:
            it = commands.user_create_itemset(owner=self.user, data=data)
        self.assertEqual(it.added_by, "USER")
        self.assertEqual(it.owner_user, self.user)
        self.assertIsNone(it.seller_profile)
        self.assertFalse(it.allow_online_checkout)
        self.assertEqual(it.listing_type, "LISTING")
        slot_mock.assert_called_once_with(user=self.user, itemset=it)

    def test_seller_create_itemset_uses_staff_and_respects_data(self):
        data = {
            "set_name": "Seller item",
            "description": "",
            "price": Money(30, "PLN"),
            "stock_quantity": 1,
            "condition": "USED",
            "status": "AVAILABLE",
            "listing_type": "BUY",
            "allow_online_checkout": True,
            "type": self.item_type,
            "catalog_item": None,
            "length_cm": 10,
            "width_cm": 10,
            "height_cm": 10,
            "weight_kg": 1,
            "attributes": {},
        }
        it = commands.seller_create_itemset(seller=self.seller, data=data)
        self.assertEqual(it.added_by, "STAFF")
        self.assertEqual(it.seller_profile, self.seller)
        self.assertTrue(it.allow_online_checkout)
        self.assertEqual(it.listing_type, "BUY")

    def test_seller_member_create_itemset_requires_membership(self):
        member = make_user("member@example.com")
        data = {
            "set_name": "Seller member item",
            "description": "",
            "price": Money(40, "PLN"),
            "stock_quantity": 1,
            "condition": "USED",
            "status": "AVAILABLE",
            "listing_type": "BUY",
            "allow_online_checkout": True,
            "type": self.item_type,
            "catalog_item": None,
            "length_cm": 10,
            "width_cm": 10,
            "height_cm": 10,
            "weight_kg": 1,
            "attributes": {},
        }
        with self.assertRaises(Forbidden):
            commands.seller_member_create_itemset(user=member, seller=self.seller, data=data)

        SellerMembership.objects.create(
            seller_profile=self.seller,
            user=member,
            role="EMPLOYEE",
            is_active=True,
        )
        it = commands.seller_member_create_itemset(user=member, seller=self.seller, data=data)
        self.assertEqual(it.added_by, "STAFF")
        self.assertEqual(it.seller_profile, self.seller)

    def test_update_itemset_for_user_blocks_type_and_catalog_change_after_24h(self):
        item = make_user_itemset(self.user, self.item_type)
        other_type = make_leaf_item_type(name="Other", slug="other", path="other")
        other_cat = CatalogItem.objects.create(
            type=other_type,
            slug="other-phone",
            item_name="Other Phone",
            image_path="",
            attributes={},
        )
        item.created_at = timezone.now() - timedelta(hours=25)
        item.save(update_fields=["created_at"])

        with patch("listings.services.commands.ensure_slot_matches_state"):
            with self.assertRaises(Forbidden):
                commands.update_itemset(itemset=item, data={"type": other_type})
        with patch("listings.services.commands.ensure_slot_matches_state"):
            with self.assertRaises(Forbidden):
                commands.update_itemset(itemset=item, data={"catalog_item": other_cat})

    def test_update_itemset_for_user_coerces_listing_type_and_checkout_flags(self):
        item = make_user_itemset(self.user, self.item_type)
        data = {"listing_type": "BUY", "allow_online_checkout": True}
        with patch("listings.services.commands.ensure_slot_matches_state") as slot_mock:
            updated = commands.update_itemset(itemset=item, data=data)
        self.assertEqual(updated.listing_type, "LISTING")
        self.assertFalse(updated.allow_online_checkout)
        slot_mock.assert_called_once_with(user=self.user, itemset=updated)

    def test_set_status_rules_and_slot_sync_for_user(self):
        item = make_user_itemset(self.user, self.item_type, status="AVAILABLE")
        with patch("listings.services.commands.ensure_slot_matches_state") as slot_mock:
            updated = commands.set_status(itemset=item, status="CLOSED")
        self.assertEqual(updated.status, "CLOSED")
        slot_mock.assert_called_once_with(user=self.user, itemset=updated)

        with self.assertRaises(Forbidden):
            commands.set_status(itemset=updated, status="SOLD")

    def test_set_status_blocks_deleted_and_suspended(self):
        item_deleted = make_user_itemset(self.user, self.item_type, status="DELETED")
        with self.assertRaises(Forbidden):
            commands.set_status(itemset=item_deleted, status="AVAILABLE")

        item_suspended = make_user_itemset(self.user, self.item_type, status="SUSPENDED")
        with self.assertRaises(Forbidden):
            commands.set_status(itemset=item_suspended, status="AVAILABLE")

    def test_set_status_invalid_for_staff_raises_bad_request(self):
        item = make_staff_itemset(self.seller, self.item_type, status="AVAILABLE")
        with self.assertRaises(BadRequest):
            commands.set_status(itemset=item, status="INVALID_STATUS")

    def test_soft_and_hard_delete_release_slots_for_user_only(self):
        item_user = make_user_itemset(self.user, self.item_type, status="AVAILABLE")
        item_staff = make_staff_itemset(self.seller, self.item_type, status="AVAILABLE")

        with patch("listings.services.commands.release_slot_for_itemset") as release_mock:
            commands.soft_delete_itemset(itemset=item_user)
            release_mock.assert_called_once_with(itemset=item_user)
        item_user.refresh_from_db()
        self.assertEqual(item_user.status, "DELETED")

        with patch("listings.services.commands.release_slot_for_itemset") as release_mock:
            commands.soft_delete_itemset(itemset=item_staff)
            release_mock.assert_not_called()

        item_user_id = item_user.id
        item_staff_id = item_staff.id

        with patch("listings.services.commands.release_slot_for_itemset") as release_mock:
            commands.hard_delete_itemset(itemset=item_user)
            release_mock.assert_called_once_with(itemset=item_user)

        self.assertFalse(ItemSetImage.objects.filter(item_set_id=item_user_id).exists())
        self.assertFalse(item_user.__class__.objects.filter(pk=item_user_id).exists())

        with patch("listings.services.commands.release_slot_for_itemset") as release_mock:
            commands.hard_delete_itemset(itemset=item_staff)
            release_mock.assert_not_called()

        self.assertFalse(item_staff.__class__.objects.filter(pk=item_staff_id).exists())


class CommandsImagesTests(TestCase):
    def setUp(self):
        self.user = make_user("img@example.com")
        self.item_type = make_leaf_item_type()
        self.seller = make_seller(self.user)
        self.item = make_staff_itemset(
            self.seller,
            self.item_type,
            status="AVAILABLE",
        )

    def test_add_image_creates_with_correct_order(self):
        img1 = commands.add_image(itemset=self.item, image_path="a.jpg", image_order=0)
        img2 = commands.add_image(itemset=self.item, image_path="b.jpg", image_order=0)

        self.assertEqual(self.item.images.count(), 2)
        orders = list(self.item.images.order_by("image_order", "id").values_list("image_path", "image_order"))
        self.assertEqual(orders[0][0], "b.jpg")
        self.assertEqual(orders[0][1], 0)
        self.assertEqual(orders[1][0], "a.jpg")
        self.assertEqual(orders[1][1], 1)

    def test_add_image_for_deleted_or_suspended_raises(self):
        self.item.status = "DELETED"
        self.item.save(update_fields=["status"])
        with self.assertRaises(Forbidden):
            commands.add_image(itemset=self.item, image_path="x.jpg")

        self.item.status = "SUSPENDED"
        self.item.save(update_fields=["status"])
        with self.assertRaises(Forbidden):
            commands.add_image(itemset=self.item, image_path="y.jpg")

    def test_delete_image_removes_record_and_respects_deleted_flag(self):
        img = commands.add_image(itemset=self.item, image_path="a.jpg")
        self.assertEqual(self.item.images.count(), 1)
        commands.delete_image(image=img)
        self.assertEqual(self.item.images.count(), 0)

        img2 = commands.add_image(itemset=self.item, image_path="b.jpg")
        self.item.status = "DELETED"
        self.item.save(update_fields=["status"])
        with self.assertRaises(Forbidden):
            commands.delete_image(image=img2)

    def test_reorder_images_changes_orders_and_validates_ids(self):
        img1 = commands.add_image(itemset=self.item, image_path="a.jpg", image_order=0)
        img2 = commands.add_image(itemset=self.item, image_path="b.jpg", image_order=1)
        img3 = commands.add_image(itemset=self.item, image_path="c.jpg", image_order=2)

        ordered = [img3.public_id, img1.public_id, img2.public_id]
        imgs = commands.reorder_images(itemset=self.item, ordered_public_ids=ordered)
        paths = [i.image_path for i in imgs]
        self.assertEqual(paths, ["c.jpg", "a.jpg", "b.jpg"])
        orders = list(self.item.images.order_by("image_order", "id").values_list("public_id", "image_order"))
        self.assertEqual(orders[0][0], img3.public_id)
        self.assertEqual(orders[0][1], 0)

        with self.assertRaises(BadRequest):
            commands.reorder_images(itemset=self.item, ordered_public_ids=[img1.public_id])

    def test_update_image_order_inserts_image_at_position(self):
        img1 = commands.add_image(itemset=self.item, image_path="a.jpg", image_order=0)
        img2 = commands.add_image(itemset=self.item, image_path="b.jpg", image_order=1)
        img3 = commands.add_image(itemset=self.item, image_path="c.jpg", image_order=2)

        commands.update_image_order(image=img3, image_order=0)
        orders = list(self.item.images.order_by("image_order", "id").values_list("image_path", "image_order"))
        self.assertEqual(orders[0][0], "c.jpg")
        self.assertEqual(orders[0][1], 0)
        self.assertEqual(orders[1][0], "a.jpg")
        self.assertEqual(orders[1][1], 1)
        self.assertEqual(orders[2][0], "b.jpg")
        self.assertEqual(orders[2][1], 2)


class CommandsShippingTests(TestCase):
    def setUp(self):
        self.user = make_user("ship@example.com")
        self.item_type = make_leaf_item_type()
        self.seller = make_seller(self.user)
        self.item_staff = make_staff_itemset(
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
        self.item_user = make_user_itemset(self.user, self.item_type, status="AVAILABLE")
        self.pkg = make_package_type(
            provider="P1",
            dimensions="S",
            max_length_cm=20,
            max_width_cm=20,
            max_height_cm=20,
            max_weight_kg=2,
        )

    def test_add_shipping_option_creates_link_for_valid_item(self):
        link = commands.add_shipping_option(
            itemset=self.item_staff,
            package_type=self.pkg,
            price_override=Money(11, "PLN"),
            packed_length_cm=10,
            packed_width_cm=10,
            packed_height_cm=10,
            packed_weight_kg=1,
        )
        self.assertIsInstance(link, ItemSetShipping)
        self.assertEqual(link.item_set_id, self.item_staff.id)
        self.assertEqual(link.package_type_id, self.pkg.id)
        self.assertEqual(link.price_override, Money(11, "PLN"))

    def test_add_shipping_option_rejects_invalid_item(self):
        with self.assertRaises(Forbidden):
            commands.add_shipping_option(
                itemset=self.item_user,
                package_type=self.pkg,
                price_override=Money(11, "PLN"),
            )

        item = make_staff_itemset(
            self.seller,
            self.item_type,
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=False,
        )
        with self.assertRaises(Forbidden):
            commands.add_shipping_option(
                itemset=item,
                package_type=self.pkg,
                price_override=Money(11, "PLN"),
            )

    def test_add_and_remove_shipping_option_respects_deleted_and_suspended(self):
        link = commands.add_shipping_option(
            itemset=self.item_staff,
            package_type=self.pkg,
            price_override=Money(11, "PLN"),
        )
        self.assertEqual(self.item_staff.shipping_options.count(), 1)
        commands.remove_shipping_option(itemset=self.item_staff, package_type=self.pkg)
        self.assertEqual(self.item_staff.shipping_options.count(), 0)

        self.item_staff.status = "DELETED"
        self.item_staff.save(update_fields=["status"])
        with self.assertRaises(Forbidden):
            commands.add_shipping_option(
                itemset=self.item_staff,
                package_type=self.pkg,
                price_override=Money(11, "PLN"),
            )
        with self.assertRaises(Forbidden):
            commands.remove_shipping_option(
                itemset=self.item_staff,
                package_type=self.pkg,
            )


class PrefillFromCatalogTests(TestCase):
    def setUp(self):
        self.user = make_user("prefill@example.com")
        self.item_type = make_leaf_item_type()
        self.seller = make_seller(self.user)

    def test_prefill_from_catalog_returns_correct_structure(self):
        catalog = CatalogItem.objects.create(
            type=self.item_type,
            slug="phone-1",
            item_name="Phone 1",
            image_path="",
            attributes={"color": "black"},
        )
        data = commands.prefill_from_catalog(catalog_item=catalog)
        self.assertEqual(data["catalog_item_id"], catalog.id)
        self.assertEqual(data["attributes"], catalog.attributes or {})
