# from datetime import timedelta
#
# from django.test import TestCase
# from django.utils import timezone
# from django.contrib.auth import get_user_model
# from django.core.exceptions import ValidationError
# from moneyed import Money
#
# from identity.models import SellerProfile
# from catalog.models import ItemType, CatalogItem
# from shipping.models import PackageType
# from listings.models import ItemSet, ItemSetImage, ItemSetShipping
# from listings.services import queries, commands
# from listings.services.exceptions import BadRequest, Forbidden
#
#
# User = get_user_model()
#
#
# def make_user(email, **extra):
#     data = {"password": "testpass123", "first_name": "", "last_name": ""}
#     data.update(extra)
#     return User.objects.create_user(email=email, **data)
#
#
# def make_leaf_item_type(name="Phones", slug="phones", path="phones"):
#     return ItemType.objects.create(name=name, slug=slug, path=path)
#
#
# def make_seller(owner, slug="shop-1", **extra):
#     data = {"owner": owner, "slug": slug, "company_name": "Test Shop"}
#     data.update(extra)
#     return SellerProfile.objects.create(**data)
#
#
# def make_package_type(
#     provider="P1",
#     dimensions="S",
#     max_length_cm=50,
#     max_width_cm=50,
#     max_height_cm=50,
#     max_weight_kg=5,
#     price_amount=10,
# ):
#     return PackageType.objects.create(
#         provider=provider,
#         dimensions=dimensions,
#         max_length_cm=max_length_cm,
#         max_width_cm=max_width_cm,
#         max_height_cm=max_height_cm,
#         max_weight_kg=max_weight_kg,
#         price=Money(price_amount, "PLN"),
#         points=0,
#     )
#
#
# def make_staff_itemset(
#     seller,
#     item_type,
#     set_name="Item",
#     status="AVAILABLE",
#     listing_type="BUY",
#     allow_online_checkout=False,
#     **extra,
# ):
#     data = {
#         "set_name": set_name,
#         "description": "",
#         "price": Money(100, "PLN"),
#         "stock_quantity": 1,
#         "condition": "USED",
#         "status": status,
#         "listing_type": listing_type,
#         "allow_online_checkout": allow_online_checkout,
#         "added_by": "STAFF",
#         "seller_profile": seller,
#         "owner_user": None,
#         "type": item_type,
#         "catalog_item": None,
#         "length_cm": 10,
#         "width_cm": 10,
#         "height_cm": 10,
#         "weight_kg": 1,
#         "attributes": {},
#     }
#     data.update(extra)
#     return ItemSet.objects.create(**data)
#
#
# def make_user_itemset(
#     owner,
#     item_type,
#     set_name="User item",
#     status="AVAILABLE",
#     listing_type="LISTING",
#     **extra,
# ):
#     data = {
#         "set_name": set_name,
#         "description": "",
#         "price": Money(50, "PLN"),
#         "stock_quantity": 1,
#         "condition": "USED",
#         "status": status,
#         "listing_type": listing_type,
#         "allow_online_checkout": False,
#         "added_by": "USER",
#         "seller_profile": None,
#         "owner_user": owner,
#         "type": item_type,
#         "catalog_item": None,
#         "length_cm": 10,
#         "width_cm": 10,
#         "height_cm": 10,
#         "weight_kg": 1,
#         "attributes": {},
#     }
#     data.update(extra)
#     return ItemSet.objects.create(**data)
#
#
# class ItemSetModelCleanTests(TestCase):
#     def setUp(self):
#         self.user = make_user("user@example.com")
#         self.item_type = make_leaf_item_type()
#
#     def test_user_rules_in_clean_invalid_combinations_raise(self):
#         item = ItemSet(
#             set_name="Invalid user 1",
#             description="",
#             price=Money(10, "PLN"),
#             stock_quantity=1,
#             condition="USED",
#             status="AVAILABLE",
#             listing_type="LISTING",
#             allow_online_checkout=True,
#             added_by="USER",
#             seller_profile=None,
#             owner_user=self.user,
#             type=self.item_type,
#             catalog_item=None,
#             length_cm=10,
#             width_cm=10,
#             height_cm=10,
#             weight_kg=1,
#             attributes={},
#         )
#         with self.assertRaises(ValidationError) as ctx:
#             item.full_clean()
#         self.assertIn("allow_online_checkout", ctx.exception.message_dict)
#
#         item = ItemSet(
#             set_name="Invalid user 2",
#             description="",
#             price=Money(10, "PLN"),
#             stock_quantity=1,
#             condition="USED",
#             status="AVAILABLE",
#             listing_type="BUY",
#             allow_online_checkout=False,
#             added_by="USER",
#             seller_profile=None,
#             owner_user=self.user,
#             type=self.item_type,
#             catalog_item=None,
#             length_cm=10,
#             width_cm=10,
#             height_cm=10,
#             weight_kg=1,
#             attributes={},
#         )
#         with self.assertRaises(ValidationError) as ctx2:
#             item.full_clean()
#         self.assertIn("listing_type", ctx2.exception.message_dict)
#
#         item = ItemSet(
#             set_name="Invalid user 3",
#             description="",
#             price=Money(10, "PLN"),
#             stock_quantity=1,
#             condition="USED",
#             status="AVAILABLE",
#             listing_type="LISTING",
#             allow_online_checkout=False,
#             added_by="USER",
#             seller_profile=make_seller(self.user),
#             owner_user=self.user,
#             type=self.item_type,
#             catalog_item=None,
#             length_cm=10,
#             width_cm=10,
#             height_cm=10,
#             weight_kg=1,
#             attributes={},
#         )
#         with self.assertRaises(ValidationError) as ctx3:
#             item.full_clean()
#         self.assertIn("seller_profile", ctx3.exception.message_dict)
#
#         item = ItemSet(
#             set_name="Invalid user 4",
#             description="",
#             price=Money(10, "PLN"),
#             stock_quantity=1,
#             condition="USED",
#             status="AVAILABLE",
#             listing_type="LISTING",
#             allow_online_checkout=False,
#             added_by="USER",
#             seller_profile=None,
#             owner_user=None,
#             type=self.item_type,
#             catalog_item=None,
#             length_cm=10,
#             width_cm=10,
#             height_cm=10,
#             weight_kg=1,
#             attributes={},
#         )
#         with self.assertRaises(ValidationError) as ctx4:
#             item.full_clean()
#         self.assertIn("owner_user", ctx4.exception.message_dict)
#
#     def test_user_valid_combination_passes_clean(self):
#         item = ItemSet(
#             set_name="Valid user",
#             description="",
#             price=Money(10, "PLN"),
#             stock_quantity=1,
#             condition="USED",
#             status="AVAILABLE",
#             listing_type="LISTING",
#             allow_online_checkout=False,
#             added_by="USER",
#             seller_profile=None,
#             owner_user=self.user,
#             type=self.item_type,
#             catalog_item=None,
#             length_cm=10,
#             width_cm=10,
#             height_cm=10,
#             weight_kg=1,
#             attributes={},
#         )
#         item.full_clean()
#
#     def test_staff_checkout_rules(self):
#         seller = make_seller(self.user)
#         item = ItemSet(
#             set_name="Bad staff",
#             description="",
#             price=Money(10, "PLN"),
#             stock_quantity=1,
#             condition="USED",
#             status="AVAILABLE",
#             listing_type="LISTING",
#             allow_online_checkout=True,
#             added_by="STAFF",
#             seller_profile=seller,
#             owner_user=None,
#             type=self.item_type,
#             catalog_item=None,
#             length_cm=10,
#             width_cm=10,
#             height_cm=10,
#             weight_kg=1,
#             attributes={},
#         )
#         with self.assertRaises(ValidationError) as ctx:
#             item.full_clean()
#         self.assertIn("allow_online_checkout", ctx.exception.message_dict)
#
#         item = ItemSet(
#             set_name="Bad staff no seller",
#             description="",
#             price=Money(10, "PLN"),
#             stock_quantity=1,
#             condition="USED",
#             status="AVAILABLE",
#             listing_type="BUY",
#             allow_online_checkout=True,
#             added_by="STAFF",
#             seller_profile=None,
#             owner_user=None,
#             type=self.item_type,
#             catalog_item=None,
#             length_cm=10,
#             width_cm=10,
#             height_cm=10,
#             weight_kg=1,
#             attributes={},
#         )
#         with self.assertRaises(ValidationError) as ctx2:
#             item.full_clean()
#         self.assertIn("seller_profile", ctx2.exception.message_dict)
#
#         item = ItemSet(
#             set_name="Good staff",
#             description="",
#             price=Money(10, "PLN"),
#             stock_quantity=1,
#             condition="USED",
#             status="AVAILABLE",
#             listing_type="BUY",
#             allow_online_checkout=True,
#             added_by="STAFF",
#             seller_profile=seller,
#             owner_user=None,
#             type=self.item_type,
#             catalog_item=None,
#             length_cm=10,
#             width_cm=10,
#             height_cm=10,
#             weight_kg=1,
#             attributes={},
#         )
#         item.full_clean()
#
#     def test_type_leaf_and_catalog_item_rules(self):
#         parent = ItemType.objects.create(name="Electronics", slug="electronics", path="electronics")
#         child = ItemType.objects.create(name="Phones", slug="electronics-phones", path="electronics/phones", parent=parent)
#         item = ItemSet(
#             set_name="Non leaf type",
#             description="",
#             price=Money(10, "PLN"),
#             stock_quantity=1,
#             condition="USED",
#             status="AVAILABLE",
#             listing_type="LISTING",
#             allow_online_checkout=False,
#             added_by="STAFF",
#             seller_profile=None,
#             owner_user=None,
#             type=parent,
#             catalog_item=None,
#             length_cm=10,
#             width_cm=10,
#             height_cm=10,
#             weight_kg=1,
#             attributes={},
#         )
#         with self.assertRaises(ValidationError) as ctx:
#             item.full_clean()
#         self.assertIn("type", ctx.exception.message_dict)
#
#         other = ItemType.objects.create(name="Other", slug="other", path="other")
#         catalog = CatalogItem.objects.create(
#             type=other,
#             slug="phone-1",
#             item_name="Phone 1",
#             image_path="",
#             attributes={"color": "black"},
#         )
#         item2 = ItemSet(
#             set_name="Cat mismatch",
#             description="",
#             price=Money(10, "PLN"),
#             stock_quantity=1,
#             condition="USED",
#             status="AVAILABLE",
#             listing_type="LISTING",
#             allow_online_checkout=False,
#             added_by="STAFF",
#             seller_profile=None,
#             owner_user=None,
#             type=child,
#             catalog_item=catalog,
#             length_cm=10,
#             width_cm=10,
#             height_cm=10,
#             weight_kg=1,
#             attributes={},
#         )
#         with self.assertRaises(ValidationError) as ctx2:
#             item2.full_clean()
#         self.assertIn("catalog_item", ctx2.exception.message_dict)
#
#         catalog2 = CatalogItem.objects.create(
#             type=child,
#             slug="phone-2",
#             item_name="Phone 2",
#             image_path="",
#             attributes={"memory": "128GB"},
#         )
#         item3 = ItemSet(
#             set_name="Cat fallback",
#             description="",
#             price=Money(10, "PLN"),
#             stock_quantity=1,
#             condition="USED",
#             status="AVAILABLE",
#             listing_type="LISTING",
#             allow_online_checkout=False,
#             added_by="STAFF",
#             seller_profile=None,
#             owner_user=None,
#             type=None,
#             catalog_item=catalog2,
#             length_cm=10,
#             width_cm=10,
#             height_cm=10,
#             weight_kg=1,
#             attributes={},
#         )
#         item3.clean()
#         self.assertEqual(item3.type_id, catalog2.type_id)
#         self.assertEqual(item3.attributes, catalog2.attributes)
#
#
# class ItemSetFitsPackageTests(TestCase):
#     def test_fits_package_respects_dimensions_and_weight(self):
#         user = make_user("u@example.com")
#         itype = make_leaf_item_type()
#         seller = make_seller(user)
#         item = make_staff_itemset(
#             seller,
#             itype,
#             length_cm=20,
#             width_cm=10,
#             height_cm=5,
#             weight_kg=1,
#         )
#         pkg_ok = make_package_type(
#             max_length_cm=25,
#             max_width_cm=15,
#             max_height_cm=10,
#             max_weight_kg=2,
#         )
#         pkg_small = make_package_type(
#             provider="P2",
#             dimensions="XS",
#             max_length_cm=10,
#             max_width_cm=10,
#             max_height_cm=5,
#             max_weight_kg=1,
#         )
#         self.assertTrue(item.fits_package(pkg_ok))
#         self.assertFalse(item.fits_package(pkg_small))
#
#
# class ItemSetShippingCleanTests(TestCase):
#     def setUp(self):
#         self.user = make_user("s@example.com")
#         self.item_type = make_leaf_item_type()
#         self.seller = make_seller(self.user)
#         self.pkg = make_package_type(
#             max_length_cm=30,
#             max_width_cm=30,
#             max_height_cm=30,
#             max_weight_kg=3,
#         )
#
#     def test_shipping_clean_rejects_non_checkout_itemsets(self):
#         item = make_staff_itemset(
#             self.seller,
#             self.item_type,
#             listing_type="LISTING",
#             allow_online_checkout=False,
#         )
#         link = ItemSetShipping(
#             item_set=item,
#             package_type=self.pkg,
#             packed_length_cm=10,
#             packed_width_cm=10,
#             packed_height_cm=10,
#             packed_weight_kg=1,
#         )
#         with self.assertRaises(ValidationError):
#             link.clean()
#
#     def test_shipping_clean_validates_dimensions_and_weight(self):
#         item = make_staff_itemset(
#             self.seller,
#             self.item_type,
#             listing_type="BUY",
#             allow_online_checkout=True,
#             length_cm=20,
#             width_cm=20,
#             height_cm=20,
#             weight_kg=1,
#         )
#         link = ItemSetShipping(
#             item_set=item,
#             package_type=self.pkg,
#             packed_length_cm=0,
#             packed_width_cm=10,
#             packed_height_cm=10,
#             packed_weight_kg=1,
#         )
#         with self.assertRaises(ValidationError) as ctx:
#             link.clean()
#         self.assertIn("packed_length_cm", ctx.exception.message_dict)
#
#         link = ItemSetShipping(
#             item_set=item,
#             package_type=self.pkg,
#             packed_length_cm=40,
#             packed_width_cm=10,
#             packed_height_cm=10,
#             packed_weight_kg=1,
#         )
#         with self.assertRaises(ValidationError):
#             link.clean()
#
#         link = ItemSetShipping(
#             item_set=item,
#             package_type=self.pkg,
#             packed_length_cm=None,
#             packed_width_cm=None,
#             packed_height_cm=None,
#             packed_weight_kg=None,
#         )
#         link.clean()
#
#
# class PublicItemsetsQueriesTests(TestCase):
#     def setUp(self):
#         self.user = make_user("owner@example.com")
#         self.seller = make_seller(self.user)
#         self.item_type = make_leaf_item_type()
#
#     def test_public_itemsets_qs_only_available_and_ordered_desc(self):
#         older = make_staff_itemset(self.seller, self.item_type, status="AVAILABLE")
#         newer = make_staff_itemset(self.seller, self.item_type, status="AVAILABLE")
#         closed = make_staff_itemset(self.seller, self.item_type, status="CLOSED")
#
#         older.created_at = timezone.now() - timedelta(hours=1)
#         older.save(update_fields=["created_at"])
#         newer.created_at = timezone.now()
#         newer.save(update_fields=["created_at"])
#
#         qs = queries.public_itemsets_qs()
#         ids = list(qs.values_list("public_id", flat=True))
#         self.assertEqual(ids, [newer.public_id, older.public_id])
#         self.assertNotIn(closed.public_id, ids)
#
#     def test_itemset_by_slug_uses_public_id_suffix_and_slug_fallback(self):
#         item = make_staff_itemset(self.seller, self.item_type, set_name="Phone X", status="AVAILABLE")
#         slug_with_tail = f"whatever-{item.public_id}"
#         found = queries.itemset_by_slug(slug_with_tail)
#         self.assertIsNotNone(found)
#         self.assertEqual(found.public_id, item.public_id)
#
#         item2 = make_staff_itemset(self.seller, self.item_type, set_name="Other", status="AVAILABLE")
#         item2.slug = "custom-slug"
#         item2.save(update_fields=["slug"])
#
#         found2 = queries.itemset_by_slug("custom-slug")
#         self.assertIsNotNone(found2)
#         self.assertEqual(found2.public_id, item2.public_id)
#
#         item3 = make_staff_itemset(self.seller, self.item_type, set_name="Closed", status="CLOSED")
#         slug3 = item3.slug
#         not_found = queries.itemset_by_slug(slug3)
#         self.assertIsNone(not_found)
#
#
# class SuggestPackageTypesTests(TestCase):
#     def setUp(self):
#         self.user = make_user("pack@example.com")
#         self.seller = make_seller(self.user)
#         self.item_type = make_leaf_item_type()
#         self.item = make_staff_itemset(
#             self.seller,
#             self.item_type,
#             status="AVAILABLE",
#             listing_type="BUY",
#             allow_online_checkout=True,
#             length_cm=10,
#             width_cm=10,
#             height_cm=10,
#             weight_kg=1,
#         )
#         self.pkg_plain = make_package_type(
#             provider="PP",
#             dimensions="S",
#             max_length_cm=20,
#             max_width_cm=20,
#             max_height_cm=20,
#             max_weight_kg=2,
#             price_amount=8,
#         )
#         self.pkg_link = make_package_type(
#             provider="PP",
#             dimensions="M",
#             max_length_cm=20,
#             max_width_cm=20,
#             max_height_cm=20,
#             max_weight_kg=2,
#             price_amount=15,
#         )
#         self.pkg_small = make_package_type(
#             provider="PP",
#             dimensions="XS",
#             max_length_cm=5,
#             max_width_cm=5,
#             max_height_cm=5,
#             max_weight_kg=1,
#             price_amount=5,
#         )
#         self.link = ItemSetShipping.objects.create(
#             item_set=self.item,
#             package_type=self.pkg_link,
#             price_override=Money(12, "PLN"),
#         )
#
#     def test_suggest_package_types_returns_only_fitting_and_sorted_by_effective_price(self):
#         rows = queries.suggest_package_types(self.item)
#         self.assertEqual(len(rows), 2)
#         pk_plain = {r["package_type"].public_id for r in rows}
#         self.assertIn(self.pkg_plain.public_id, pk_plain)
#         self.assertIn(self.pkg_link.public_id, pk_plain)
#
#         first = rows[0]
#         second = rows[1]
#
#         self.assertEqual(first["package_type"].public_id, self.pkg_plain.public_id)
#         self.assertEqual(first["effective_price"], self.pkg_plain.price)
#         self.assertEqual(first["price_source"], "catalog")
#         self.assertFalse(first["already_linked"])
#
#         self.assertEqual(second["package_type"].public_id, self.pkg_link.public_id)
#         self.assertEqual(second["effective_price"], self.link.price_override)
#         self.assertEqual(second["price_source"], "override")
#         self.assertTrue(second["already_linked"])
#
#
# class CommandsItemsetStatusTests(TestCase):
#     def setUp(self):
#         self.user = make_user("cmd@example.com")
#         self.item_type = make_leaf_item_type()
#         self.seller = make_seller(self.user)
#
#     def test_user_create_itemset_forces_listing_and_checkout_rules_and_calls_slot_sync(self):
#         data = {
#             "set_name": "User created item",
#             "description": "",
#             "price": Money(20, "PLN"),
#             "stock_quantity": 1,
#             "condition": "USED",
#             "status": "AVAILABLE",
#             "listing_type": "BUY",
#             "allow_online_checkout": True,
#             "type": self.item_type,
#             "catalog_item": None,
#             "length_cm": 10,
#             "width_cm": 10,
#             "height_cm": 10,
#             "weight_kg": 1,
#             "attributes": {},
#         }
#         from unittest.mock import patch
#
#         with patch("listings.services.commands.ensure_slot_matches_state") as slot_mock:
#             it = commands.user_create_itemset(owner=self.user, data=data)
#         self.assertEqual(it.added_by, "USER")
#         self.assertEqual(it.owner_user, self.user)
#         self.assertIsNone(it.seller_profile)
#         self.assertFalse(it.allow_online_checkout)
#         self.assertEqual(it.listing_type, "LISTING")
#         slot_mock.assert_called_once_with(user=self.user, itemset=it)
#
#     def test_seller_create_itemset_uses_staff_and_respects_data(self):
#         data = {
#             "set_name": "Seller item",
#             "description": "",
#             "price": Money(30, "PLN"),
#             "stock_quantity": 1,
#             "condition": "USED",
#             "status": "AVAILABLE",
#             "listing_type": "BUY",
#             "allow_online_checkout": True,
#             "type": self.item_type,
#             "catalog_item": None,
#             "length_cm": 10,
#             "width_cm": 10,
#             "height_cm": 10,
#             "weight_kg": 1,
#             "attributes": {},
#         }
#         it = commands.seller_create_itemset(seller=self.seller, data=data)
#         self.assertEqual(it.added_by, "STAFF")
#         self.assertEqual(it.seller_profile, self.seller)
#         self.assertTrue(it.allow_online_checkout)
#         self.assertEqual(it.listing_type, "BUY")
#
#     def test_update_itemset_for_user_blocks_type_and_catalog_change_after_24h(self):
#         item = make_user_itemset(self.user, self.item_type)
#         other_type = make_leaf_item_type(name="Other", slug="other", path="other")
#         other_cat = CatalogItem.objects.create(
#             type=other_type,
#             slug="other-phone",
#             item_name="Other Phone",
#             image_path="",
#             attributes={},
#         )
#         item.created_at = timezone.now() - timedelta(hours=25)
#         item.save(update_fields=["created_at"])
#         from unittest.mock import patch
#
#         with patch("listings.services.commands.ensure_slot_matches_state"):
#             with self.assertRaises(Forbidden):
#                 commands.update_itemset(itemset=item, data={"type": other_type})
#         with patch("listings.services.commands.ensure_slot_matches_state"):
#             with self.assertRaises(Forbidden):
#                 commands.update_itemset(itemset=item, data={"catalog_item": other_cat})
#
#     def test_update_itemset_for_user_coerces_listing_type_and_checkout_flags(self):
#         item = make_user_itemset(self.user, self.item_type)
#         from unittest.mock import patch
#
#         data = {"listing_type": "BUY", "allow_online_checkout": True}
#         with patch("listings.services.commands.ensure_slot_matches_state") as slot_mock:
#             updated = commands.update_itemset(itemset=item, data=data)
#         self.assertEqual(updated.listing_type, "LISTING")
#         self.assertFalse(updated.allow_online_checkout)
#         slot_mock.assert_called_once_with(user=self.user, itemset=updated)
#
#     def test_set_status_rules_and_slot_sync_for_user(self):
#         item = make_user_itemset(self.user, self.item_type, status="AVAILABLE")
#         from unittest.mock import patch
#
#         with patch("listings.services.commands.ensure_slot_matches_state") as slot_mock:
#             updated = commands.set_status(itemset=item, status="CLOSED")
#         self.assertEqual(updated.status, "CLOSED")
#         slot_mock.assert_called_once_with(user=self.user, itemset=updated)
#
#         with self.assertRaises(Forbidden):
#             commands.set_status(itemset=updated, status="SOLD")
#
#     def test_set_status_blocks_deleted_and_suspended(self):
#         item_deleted = make_user_itemset(self.user, self.item_type, status="DELETED")
#         with self.assertRaises(Forbidden):
#             commands.set_status(itemset=item_deleted, status="AVAILABLE")
#
#         item_suspended = make_user_itemset(self.user, self.item_type, status="SUSPENDED")
#         with self.assertRaises(Forbidden):
#             commands.set_status(itemset=item_suspended, status="AVAILABLE")
#
#     def test_soft_and_hard_delete_release_slots_for_user_only(self):
#         item_user = make_user_itemset(self.user, self.item_type, status="AVAILABLE")
#         item_staff = make_staff_itemset(self.seller, self.item_type, status="AVAILABLE")
#         from unittest.mock import patch
#
#         with patch("listings.services.commands.release_slot_for_itemset") as release_mock:
#             commands.soft_delete_itemset(itemset=item_user)
#             release_mock.assert_called_once_with(itemset=item_user)
#         item_user.refresh_from_db()
#         self.assertEqual(item_user.status, "DELETED")
#
#         with patch("listings.services.commands.release_slot_for_itemset") as release_mock:
#             commands.soft_delete_itemset(itemset=item_staff)
#             release_mock.assert_not_called()
#
#         with patch("listings.services.commands.release_slot_for_itemset") as release_mock:
#             commands.hard_delete_itemset(itemset=item_user)
#             release_mock.assert_called_once_with(itemset=item_user)
#         self.assertFalse(ItemSet.objects.filter(pk=item_user.pk).exists())
#
#         with patch("listings.services.commands.release_slot_for_itemset") as release_mock:
#             commands.hard_delete_itemset(itemset=item_staff)
#             release_mock.assert_not_called()
#         self.assertFalse(ItemSet.objects.filter(pk=item_staff.pk).exists())
