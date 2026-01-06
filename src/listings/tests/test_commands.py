from __future__ import annotations
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from listings.models import ItemSet, ItemSetImage, ItemSetShipping
from listings.services import commands
from listings.services.exceptions import BadRequest, Forbidden
from .factories import (
    create_user,
    create_item_type,
    create_catalog_item,
    create_seller_profile,
    create_item_set,
    create_package_type,
    create_item_image,
)

class ItemSetCreateUpdateCommandsTests(TestCase):
    def test_seller_create_itemset_creates_staff_listing(self):
        seller = create_seller_profile()
        itype = create_item_type()
        data = {
            "set_name": "Seller item",
            "price": Money("10.00", "PLN"),
            "stock_quantity": 1,
            "condition": "USED",
            "status": "AVAILABLE",
            "listing_type": "LISTING",
            "type": itype,
            "attributes": {},
        }
        item = commands.seller_create_itemset(seller=seller, data=data)
        self.assertIsInstance(item, ItemSet)
        self.assertEqual(item.added_by, "STAFF")
        self.assertEqual(item.seller_profile_id, seller.id)
        self.assertIsNone(item.owner_user)

    @patch("listings.services.commands.ensure_slot_matches_state")
    def test_user_create_itemset_forces_no_checkout_and_not_buy(self, mock_ensure):
        owner = create_user()
        itype = create_item_type()
        data = {
            "set_name": "User item",
            "price": Money("5.00", "PLN"),
            "stock_quantity": 1,
            "condition": "USED",
            "status": "AVAILABLE",
            "listing_type": "BUY",
            "type": itype,
            "allow_online_checkout": True,
            "attributes": {},
        }
        item = commands.user_create_itemset(owner=owner, data=data)
        self.assertEqual(item.added_by, "USER")
        self.assertEqual(item.owner_user_id, owner.id)
        self.assertFalse(item.allow_online_checkout)
        self.assertEqual(item.listing_type, "LISTING")
        mock_ensure.assert_called_once_with(user=owner, itemset=item)

    def test_user_create_itemset_validation_error_converted_to_badrequest(self):
        owner = create_user()
        parent = create_item_type(name="Parent")
        child = create_item_type(name="Child", parent=parent)
        data = {
            "set_name": "Bad item",
            "price": Money("5.00", "PLN"),
            "stock_quantity": 1,
            "condition": "USED",
            "status": "AVAILABLE",
            "listing_type": "LISTING",
            "type": parent,
            "attributes": {},
        }
        with self.assertRaises(BadRequest):
            commands.user_create_itemset(owner=owner, data=data)

    @patch("listings.services.commands.ensure_slot_matches_state")
    def test_update_itemset_user_within_24h_allows_type_and_catalog_change(self, mock_ensure):
        owner = create_user()
        old_type = create_item_type(name="Old")
        new_type = create_item_type(name="New")
        cat = create_catalog_item(item_type=new_type, attributes={"x": 1})
        item = create_item_set(
            owner_user=owner,
            item_type=old_type,
            added_by="USER",
            status="AVAILABLE",
        )
        item.created_at = timezone.now() - timedelta(hours=2)
        item.save(update_fields=["created_at"])
        updated = commands.update_itemset(
            itemset=item,
            data={"type": new_type, "catalog_item": cat},
        )
        self.assertEqual(updated.type_id, new_type.id)
        self.assertEqual(updated.catalog_item_id, cat.id)
        mock_ensure.assert_called_once_with(user=owner, itemset=updated)

    @patch("listings.services.commands.ensure_slot_matches_state")
    def test_update_itemset_user_after_24h_forbids_type_and_catalog_change(self, mock_ensure):
        owner = create_user()
        old_type = create_item_type(name="Old")
        new_type = create_item_type(name="New")
        cat = create_catalog_item(item_type=new_type)
        item = create_item_set(
            owner_user=owner,
            item_type=old_type,
            added_by="USER",
            status="AVAILABLE",
        )
        item.created_at = timezone.now() - timedelta(days=2)
        item.save(update_fields=["created_at"])
        with self.assertRaises(Forbidden):
            commands.update_itemset(itemset=item, data={"type": new_type})
        with self.assertRaises(Forbidden):
            commands.update_itemset(itemset=item, data={"catalog_item": cat})
        mock_ensure.assert_not_called()

    def test_update_itemset_rejects_deleted_or_suspended(self):
        owner = create_user()
        itype = create_item_type()
        item_deleted = create_item_set(
            owner_user=owner,
            item_type=itype,
            added_by="USER",
            status="DELETED",
        )
        item_suspended = create_item_set(
            owner_user=owner,
            item_type=itype,
            added_by="USER",
            status="SUSPENDED",
        )
        with self.assertRaises(Forbidden):
            commands.update_itemset(itemset=item_deleted, data={"set_name": "X"})
        with self.assertRaises(Forbidden):
            commands.update_itemset(itemset=item_suspended, data={"set_name": "X"})

    @patch("listings.services.commands.ensure_slot_matches_state")
    def test_update_itemset_user_forces_no_checkout_and_not_buy(self, mock_ensure):
        owner = create_user()
        itype = create_item_type()
        item = create_item_set(
            owner_user=owner,
            item_type=itype,
            added_by="USER",
            listing_type="LISTING",
            allow_online_checkout=False,
        )
        updated = commands.update_itemset(
            itemset=item,
            data={"listing_type": "BUY", "allow_online_checkout": True},
        )
        self.assertEqual(updated.listing_type, "LISTING")
        self.assertFalse(updated.allow_online_checkout)
        mock_ensure.assert_called_once_with(user=owner, itemset=updated)


class StatusCommandsTests(TestCase):
    @patch("listings.services.commands.ensure_slot_matches_state")
    def test_set_status_user_allows_subset(self, mock_ensure):
        owner = create_user()
        itype = create_item_type()
        item = create_item_set(
            owner_user=owner,
            item_type=itype,
            added_by="USER",
            status="AVAILABLE",
        )
        updated = commands.set_status(itemset=item, status="CLOSED")
        self.assertEqual(updated.status, "CLOSED")
        mock_ensure.assert_called_once_with(user=owner, itemset=updated)

    def test_set_status_user_forbidden_status(self):
        owner = create_user()
        itype = create_item_type()
        item = create_item_set(
            owner_user=owner,
            item_type=itype,
            added_by="USER",
            status="AVAILABLE",
        )
        with self.assertRaises(Forbidden):
            commands.set_status(itemset=item, status="SOLD")

    def test_set_status_staff_can_set_sold(self):
        seller = create_seller_profile()
        itype = create_item_type()
        item = create_item_set(
            seller_profile=seller,
            item_type=itype,
            added_by="STAFF",
            status="AVAILABLE",
        )
        updated = commands.set_status(itemset=item, status="SOLD")
        self.assertEqual(updated.status, "SOLD")

    def test_set_status_deleted_or_suspended_block_changes(self):
        owner = create_user()
        itype = create_item_type()
        item_deleted = create_item_set(
            owner_user=owner,
            item_type=itype,
            added_by="USER",
            status="DELETED",
        )
        with self.assertRaises(Forbidden):
            commands.set_status(itemset=item_deleted, status="AVAILABLE")
        item_suspended = create_item_set(
            owner_user=owner,
            item_type=itype,
            added_by="USER",
            status="SUSPENDED",
        )
        with self.assertRaises(Forbidden):
            commands.set_status(itemset=item_suspended, status="AVAILABLE")


class ModeratorStatusCommandsTests(TestCase):
    @patch("listings.services.commands.ensure_slot_matches_state")
    def test_moderator_set_status_only_for_user_listings(self, mock_ensure):
        seller = create_seller_profile()
        staff_item = create_item_set(
            seller_profile=seller,
            added_by="STAFF",
            status="AVAILABLE",
        )
        with self.assertRaises(Forbidden):
            commands.moderator_set_status(itemset=staff_item, status="SUSPENDED")
        owner = create_user()
        user_item = create_item_set(
            owner_user=owner,
            added_by="USER",
            status="AVAILABLE",
        )
        updated = commands.moderator_set_status(itemset=user_item, status="SUSPENDED")
        self.assertEqual(updated.status, "SUSPENDED")
        mock_ensure.assert_called_once_with(user=owner, itemset=updated)
        mock_ensure.reset_mock()
        updated2 = commands.moderator_set_status(itemset=updated, status="AVAILABLE")
        self.assertEqual(updated2.status, "AVAILABLE")
        mock_ensure.assert_called_once_with(user=owner, itemset=updated2)

    def test_moderator_cannot_delete_or_set_deleted_or_other_statuses(self):
        owner = create_user()
        item = create_item_set(
            owner_user=owner,
            added_by="USER",
            status="AVAILABLE",
        )
        with self.assertRaises(Forbidden):
            commands.moderator_set_status(itemset=item, status="DELETED")
        with self.assertRaises(Forbidden):
            commands.moderator_set_status(itemset=item, status="SOLD")


class DeleteCommandsTests(TestCase):
    @patch("listings.services.commands.release_slot_for_itemset")
    def test_soft_delete_sets_deleted_and_releases_slot_for_user(self, mock_release):
        owner = create_user()
        item = create_item_set(
            owner_user=owner,
            added_by="USER",
            status="AVAILABLE",
        )
        commands.soft_delete_itemset(itemset=item)
        item.refresh_from_db()
        self.assertEqual(item.status, "DELETED")
        mock_release.assert_called_once_with(itemset=item)

    @patch("listings.services.commands.release_slot_for_itemset")
    def test_soft_delete_staff_does_not_release_slot(self, mock_release):
        seller = create_seller_profile()
        item = create_item_set(
            seller_profile=seller,
            added_by="STAFF",
            status="AVAILABLE",
        )
        commands.soft_delete_itemset(itemset=item)
        item.refresh_from_db()
        self.assertEqual(item.status, "DELETED")
        mock_release.assert_not_called()

    @patch("listings.services.commands.release_slot_for_itemset")
    def test_hard_delete_releases_slot_for_user_and_deletes(self, mock_release):
        owner = create_user()
        item = create_item_set(
            owner_user=owner,
            added_by="USER",
            status="AVAILABLE",
        )
        commands.hard_delete_itemset(itemset=item)
        self.assertFalse(ItemSet.objects.filter(id=item.id).exists())
        mock_release.assert_called_once_with(itemset=item)

    @patch("listings.services.commands.release_slot_for_itemset")
    def test_hard_delete_staff_does_not_release_slot(self, mock_release):
        seller = create_seller_profile()
        item = create_item_set(
            seller_profile=seller,
            added_by="STAFF",
            status="AVAILABLE",
        )
        commands.hard_delete_itemset(itemset=item)
        self.assertFalse(ItemSet.objects.filter(id=item.id).exists())
        mock_release.assert_not_called()


class MembershipCommandsTests(TestCase):
    @patch("listings.services.commands.is_member_of_seller", return_value=False)
    def test_seller_member_create_itemset_requires_membership(self, mock_is_member):
        seller = create_seller_profile()
        user = create_user()
        itype = create_item_type()
        data = {
            "set_name": "X",
            "price": Money("10.00", "PLN"),
            "stock_quantity": 1,
            "condition": "USED",
            "status": "AVAILABLE",
            "listing_type": "LISTING",
            "type": itype,
        }
        with self.assertRaises(Forbidden):
            commands.seller_member_create_itemset(user=user, seller=seller, data=data)
        mock_is_member.assert_called_once()

    @patch("listings.services.commands.is_member_of_seller", return_value=True)
    def test_seller_member_create_itemset_creates_for_member(self, mock_is_member):
        seller = create_seller_profile()
        user = create_user()
        itype = create_item_type()
        data = {
            "set_name": "Y",
            "price": Money("10.00", "PLN"),
            "stock_quantity": 1,
            "condition": "USED",
            "status": "AVAILABLE",
            "listing_type": "LISTING",
            "type": itype,
        }
        item = commands.seller_member_create_itemset(user=user, seller=seller, data=data)
        self.assertEqual(item.seller_profile_id, seller.id)
        self.assertEqual(item.added_by, "STAFF")
        mock_is_member.assert_called_once_with(user, seller, roles=None)


class ImageCommandsTests(TestCase):
    def test_add_image_forbidden_for_deleted_or_suspended(self):
        item_deleted = create_item_set(status="DELETED")
        item_suspended = create_item_set(status="SUSPENDED")
        with self.assertRaises(Forbidden):
            commands.add_image(itemset=item_deleted, image_path="x.jpg")
        with self.assertRaises(Forbidden):
            commands.add_image(itemset=item_suspended, image_path="y.jpg")

    @patch("listings.services.commands.default_storage")
    @patch("listings.services.commands.repo_create_image")
    def test_add_image_saves_file_and_uses_repo(self, mock_repo, mock_storage):
        item = create_item_set(status="AVAILABLE")
        mock_storage.save.return_value = "stored/path.jpg"

        class DummyFile:
            name = "photo.jpg"

        img_file = DummyFile()
        commands.add_image(itemset=item, image=img_file, image_order=3)
        mock_storage.save.assert_called_once()
        self.assertEqual(
            mock_repo.call_args.kwargs["image_path"],
            "stored/path.jpg",
        )
        self.assertEqual(mock_repo.call_args.kwargs["image_order"], 3)

    @patch("listings.services.commands.default_storage")
    @patch("listings.services.commands.repo_delete_image")
    def test_delete_image_deletes_file_and_row(self, mock_repo_delete, mock_storage):
        item = create_item_set(status="AVAILABLE")
        img = create_item_image(item_set=item, image_path="to/delete.jpg", image_order=0)
        commands.delete_image(image=img)
        mock_storage.delete.assert_called_once_with("to/delete.jpg")
        mock_repo_delete.assert_called_once_with(img)

    def test_delete_image_for_deleted_listing_forbidden(self):
        item = create_item_set(status="DELETED")
        img = create_item_image(item_set=item, image_path="x.jpg")
        with self.assertRaises(Forbidden):
            commands.delete_image(image=img)

    def test_reorder_images_updates_orders_and_validates_set(self):
        item = create_item_set(status="AVAILABLE")
        img1 = create_item_image(item_set=item, image_order=0)
        img2 = create_item_image(item_set=item, image_order=1)
        img3 = create_item_image(item_set=item, image_order=2)
        new_order = [str(img2.public_id), str(img3.public_id), str(img1.public_id)]
        imgs = commands.reorder_images(itemset=item, ordered_public_ids=new_order)
        orders = {str(i.public_id): i.image_order for i in imgs}
        self.assertEqual(orders[str(img2.public_id)], 0)
        self.assertEqual(orders[str(img3.public_id)], 1)
        self.assertEqual(orders[str(img1.public_id)], 2)
        with self.assertRaises(BadRequest):
            commands.reorder_images(itemset=item, ordered_public_ids=[str(img1.public_id)])

    def test_update_image_order_reinserts_properly(self):
        item = create_item_set(status="AVAILABLE")
        img1 = create_item_image(item_set=item, image_order=0)
        img2 = create_item_image(item_set=item, image_order=1)
        img3 = create_item_image(item_set=item, image_order=2)
        updated = commands.update_image_order(image=img3, image_order=0)
        self.assertEqual(updated.image_order, 0)
        refreshed = list(item.images.order_by("image_order", "id"))
        self.assertEqual([i.id for i in refreshed], [img3.id, img1.id, img2.id])

    def test_image_operations_forbidden_for_suspended(self):
        item = create_item_set(status="SUSPENDED")
        with self.assertRaises(Forbidden):
            commands.reorder_images(itemset=item, ordered_public_ids=[])
        img = create_item_image(item_set=item, image_order=0)
        with self.assertRaises(Forbidden):
            commands.update_image_order(image=img, image_order=1)


class ShippingCommandsTests(TestCase):
    def test_add_shipping_option_only_for_staff_buy_checkout(self):
        itype = create_item_type()
        seller = create_seller_profile()
        item_user = create_item_set(
            owner_user=create_user(),
            item_type=itype,
            added_by="USER",
            status="AVAILABLE",
        )
        pkg = create_package_type()
        with self.assertRaises(Forbidden):
            commands.add_shipping_option(itemset=item_user, package_type=pkg)
        item_staff = create_item_set(
            seller_profile=seller,
            item_type=itype,
            added_by="STAFF",
            listing_type="LISTING",
            allow_online_checkout=False,
            status="AVAILABLE",
        )
        with self.assertRaises(Forbidden):
            commands.add_shipping_option(itemset=item_staff, package_type=pkg)
        item_staff.listing_type = "BUY"
        item_staff.allow_online_checkout = True
        item_staff.save(update_fields=["listing_type", "allow_online_checkout"])
        link = commands.add_shipping_option(
            itemset=item_staff,
            package_type=pkg,
            price_override=Money("15.00", "PLN"),
            packed_length_cm=10,
        )
        self.assertIsInstance(link, ItemSetShipping)
        self.assertEqual(link.item_set_id, item_staff.id)
        self.assertEqual(link.package_type_id, pkg.id)
        self.assertEqual(link.price_override.amount, Decimal("15.00"))

    def test_add_and_remove_shipping_option_respects_deleted_or_suspended(self):
        pkg = create_package_type()
        item_deleted = create_item_set(status="DELETED")
        item_suspended = create_item_set(status="SUSPENDED")
        with self.assertRaises(Forbidden):
            commands.add_shipping_option(itemset=item_deleted, package_type=pkg)
        with self.assertRaises(Forbidden):
            commands.remove_shipping_option(itemset=item_deleted, package_type=pkg)
        with self.assertRaises(Forbidden):
            commands.add_shipping_option(itemset=item_suspended, package_type=pkg)
        with self.assertRaises(Forbidden):
            commands.remove_shipping_option(itemset=item_suspended, package_type=pkg)

    def test_remove_shipping_option_deletes_link(self):
        seller = create_seller_profile()
        itype = create_item_type()
        item = create_item_set(
            seller_profile=seller,
            item_type=itype,
            added_by="STAFF",
            listing_type="BUY",
            allow_online_checkout=True,
        )
        pkg = create_package_type()
        link = commands.add_shipping_option(itemset=item, package_type=pkg)
        self.assertTrue(ItemSetShipping.objects.filter(id=link.id).exists())
        commands.remove_shipping_option(itemset=item, package_type=pkg)
        self.assertFalse(ItemSetShipping.objects.filter(id=link.id).exists())


class PrefillFromCatalogCommandsTests(TestCase):
    def test_prefill_from_catalog_returns_attributes(self):
        itype = create_item_type()
        cat = create_catalog_item(item_type=itype, attributes={"color": "red"})
        data = commands.prefill_from_catalog(catalog_item=cat)
        self.assertEqual(data["catalog_item_id"], cat.id)
        self.assertEqual(data["attributes"], {"color": "red"})
