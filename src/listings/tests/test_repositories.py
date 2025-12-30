from __future__ import annotations
from decimal import Decimal

from django.test import TestCase

from listings.models import ItemSetImage, ItemSetShipping
from listings.services import repositories as repo
from .factories import (
    create_user,
    create_seller_profile,
    create_item_set,
    create_item_type,
    create_package_type,
)


class MembershipRepositoryTests(TestCase):
    def test_is_member_of_seller_checks_active_membership(self):
        owner = create_user()
        seller = create_seller_profile(owner=owner)
        member = create_user()
        from identity.models import SellerMembership

        SellerMembership.objects.create(
            seller_profile=seller,
            user=member,
            role="EMPLOYEE",
            is_active=True,
        )
        self.assertTrue(repo.is_member_of_seller(member, seller, roles=None))
        self.assertFalse(repo.is_member_of_seller(owner, seller, roles={"EMPLOYEE"}))


class ItemsetRepositoryTests(TestCase):
    def test_get_itemset_by_public_id_returns_item(self):
        item = create_item_set()
        found = repo.get_itemset_by_public_id(str(item.public_id))
        self.assertIsNotNone(found)
        self.assertEqual(found.id, item.id)

    def test_create_itemset_staff_and_user_set_proper_fields(self):
        seller = create_seller_profile()
        owner = create_user()
        itype = create_item_type()
        staff = repo.create_itemset_staff(
            seller=seller,
            data={
                "set_name": "Staff",
                "price": Decimal("10.00"),
                "stock_quantity": 1,
                "condition": "USED",
                "status": "AVAILABLE",
                "listing_type": "LISTING",
                "type": itype,
            },
        )
        self.assertEqual(staff.added_by, "STAFF")
        self.assertEqual(staff.seller_profile_id, seller.id)
        user_it = repo.create_itemset_user(
            owner=owner,
            data={
                "set_name": "User",
                "price": Decimal("5.00"),
                "stock_quantity": 1,
                "condition": "USED",
                "status": "AVAILABLE",
                "listing_type": "LISTING",
                "type": itype,
            },
        )
        self.assertEqual(user_it.added_by, "USER")
        self.assertEqual(user_it.owner_user_id, owner.id)

    def test_save_and_delete_itemset(self):
        item = create_item_set()
        repo.save_itemset(item)
        self.assertTrue(ItemSetImage.objects.filter(item_set=item).count() == 0)
        repo.delete_itemset(item)
        from listings.models import ItemSet

        self.assertFalse(ItemSet.objects.filter(id=item.id).exists())


class ImageRepositoryTests(TestCase):
    def test_create_image_appends_when_no_order_provided(self):
        item = create_item_set()
        img1 = repo.create_image(itemset=item, image_path="a.jpg")
        img2 = repo.create_image(itemset=item, image_path="b.jpg")
        self.assertEqual(img1.image_order, 0)
        self.assertEqual(img2.image_order, 1)

    def test_create_image_with_order_inserts_and_shifts(self):
        item = create_item_set()
        img1 = repo.create_image(itemset=item, image_path="a.jpg")
        img2 = repo.create_image(itemset=item, image_path="b.jpg")
        img3 = repo.create_image(itemset=item, image_path="c.jpg")
        img_new = repo.create_image(itemset=item, image_path="d.jpg", image_order=1)
        imgs = list(
            ItemSetImage.objects.filter(item_set=item).order_by("image_order", "id")
        )
        self.assertEqual([i.image_order for i in imgs], [0, 1, 2, 3])
        self.assertEqual(imgs[1].id, img_new.id)

    def test_bulk_update_image_orders_persists_changes(self):
        item = create_item_set()
        img1 = repo.create_image(itemset=item, image_path="a.jpg")
        img2 = repo.create_image(itemset=item, image_path="b.jpg")
        img1.image_order = 1
        img2.image_order = 0
        repo.bulk_update_image_orders([img1, img2])
        imgs = list(
            ItemSetImage.objects.filter(item_set=item).order_by("image_order", "id")
        )
        self.assertEqual([i.id for i in imgs], [img2.id, img1.id])


class ShippingRepositoryTests(TestCase):
    def test_package_type_and_shipping_link_helpers(self):
        pkg = create_package_type()
        from listings.models import ItemSet

        item = create_item_set()
        found_pkg = repo.get_package_type_by_public_id(str(pkg.public_id))
        self.assertIsNotNone(found_pkg)
        self.assertEqual(found_pkg.id, pkg.id)
        self.assertIsNone(repo.get_shipping_link(itemset=item, package_type=pkg))
        link = repo.upsert_shipping_link(itemset=item, package_type=pkg)
        self.assertIsInstance(link, ItemSetShipping)
        self.assertIsNotNone(repo.get_shipping_link(itemset=item, package_type=pkg))
        repo.delete_shipping_link(itemset=item, package_type=pkg)
        self.assertIsNone(repo.get_shipping_link(itemset=item, package_type=pkg))
