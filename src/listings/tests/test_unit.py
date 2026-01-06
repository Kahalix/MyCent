from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.utils import timezone
from moneyed import Money as M

from catalog.models import _normalize_and_validate_attrs
from listings.models import ItemSet, ItemSetShipping
from listings.services.exceptions import BadRequest, Forbidden


class AttributesSchemaUnitTests(SimpleTestCase):
    def test_normalize_attrs_coerces_and_applies_defaults(self):
        schema = {
            "type": "object",
            "properties": {
                "size": {"type": "integer", "minimum": 1, "maximum": 10},
                "flag": {"type": "boolean", "default": False},
                "color": {"type": "string", "enum": ["red", "blue"]},
            },
            "required": ["size", "color"],
        }
        out = _normalize_and_validate_attrs(
            {"size": "2", "color": "red", "flag": "tak"},
            schema,
            where="attributes",
            require_same_fields=False,
        )
        self.assertEqual(out["size"], 2)
        self.assertEqual(out["color"], "red")
        self.assertEqual(out["flag"], True)

    def test_normalize_attrs_missing_required_raises_validation_error(self):
        schema = {
            "type": "object",
            "properties": {"size": {"type": "integer"}, "color": {"type": "string"}},
            "required": ["size", "color"],
        }
        with self.assertRaises(ValidationError) as ctx:
            _normalize_and_validate_attrs(
                {"color": "x"},
                schema,
                where="attributes",
                require_same_fields=False,
            )
        self.assertIn("attributes", ctx.exception.message_dict)

    def test_normalize_attrs_allows_extra_fields_when_require_same_fields_false(self):
        schema = {
            "type": "object",
            "properties": {"size": {"type": "integer"}},
            "required": ["size"],
        }
        out = _normalize_and_validate_attrs(
            {"size": "1", "extra": "ok"},
            schema,
            where="attributes",
            require_same_fields=False,
        )
        self.assertEqual(out["size"], 1)
        self.assertEqual(out["extra"], "ok")

    def test_normalize_attrs_rejects_extra_fields_when_require_same_fields_true(self):
        schema = {
            "type": "object",
            "properties": {"size": {"type": "integer"}},
            "required": ["size"],
        }
        with self.assertRaises(ValidationError) as ctx:
            _normalize_and_validate_attrs(
                {"size": 1, "extra": "x"},
                schema,
                where="attributes",
                require_same_fields=True,
            )
        self.assertIn("attributes", ctx.exception.message_dict)


class ItemSetCleanUnitTests(SimpleTestCase):
    def _mock_itemtype_queries(self, *, has_children: bool, schema_json: dict | None):
        filter_qs = MagicMock()
        filter_qs.exists.return_value = bool(has_children)

        only_qs = MagicMock()
        only_filter_qs = MagicMock()
        only_filter_qs.first.return_value = SimpleNamespace(schema_json=schema_json or {})
        only_qs.filter.return_value = only_filter_qs

        return filter_qs, only_qs

    @patch("listings.models.ItemType.objects.only")
    @patch("listings.models.ItemType.objects.filter")
    def test_clean_user_cannot_enable_online_checkout(self, mock_filter, mock_only):
        filter_qs, only_qs = self._mock_itemtype_queries(has_children=False, schema_json={})
        mock_filter.return_value = filter_qs
        mock_only.return_value = only_qs

        it = ItemSet(
            set_name="X",
            price=M(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=True,
            added_by="USER",
            seller_profile_id=None,
            owner_user_id=1,
            type_id=123,
            attributes={},
        )
        it._state.fields_cache["owner_user"] = SimpleNamespace(id=1)

        with self.assertRaises(ValidationError) as ctx:
            it.clean()
        self.assertIn("allow_online_checkout", ctx.exception.message_dict)

    @patch("listings.models.ItemType.objects.only")
    @patch("listings.models.ItemType.objects.filter")
    def test_clean_staff_checkout_requires_buy(self, mock_filter, mock_only):
        filter_qs, only_qs = self._mock_itemtype_queries(has_children=False, schema_json={})
        mock_filter.return_value = filter_qs
        mock_only.return_value = only_qs

        it = ItemSet(
            set_name="X",
            price=M(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=True,
            added_by="STAFF",
            seller_profile_id=1,
            owner_user_id=None,
            type_id=123,
            attributes={},
        )

        with self.assertRaises(ValidationError) as ctx:
            it.clean()
        self.assertIn("allow_online_checkout", ctx.exception.message_dict)

    @patch("listings.models.ItemType.objects.only")
    @patch("listings.models.ItemType.objects.filter")
    def test_clean_staff_checkout_requires_seller_profile(self, mock_filter, mock_only):
        filter_qs, only_qs = self._mock_itemtype_queries(has_children=False, schema_json={})
        mock_filter.return_value = filter_qs
        mock_only.return_value = only_qs

        it = ItemSet(
            set_name="X",
            price=M(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="BUY",
            allow_online_checkout=True,
            added_by="STAFF",
            seller_profile_id=None,
            owner_user_id=None,
            type_id=123,
            attributes={},
        )

        with self.assertRaises(ValidationError) as ctx:
            it.clean()
        self.assertIn("seller_profile", ctx.exception.message_dict)

    @patch("listings.models.ItemType.objects.only")
    @patch("listings.models.ItemType.objects.filter")
    def test_clean_available_requires_stock_gt_zero(self, mock_filter, mock_only):
        filter_qs, only_qs = self._mock_itemtype_queries(has_children=False, schema_json={})
        mock_filter.return_value = filter_qs
        mock_only.return_value = only_qs

        it = ItemSet(
            set_name="X",
            price=M(10, "PLN"),
            stock_quantity=0,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=False,
            added_by="USER",
            seller_profile_id=None,
            owner_user_id=1,
            type_id=123,
            attributes={},
        )
        it._state.fields_cache["owner_user"] = SimpleNamespace(id=1)

        with self.assertRaises(ValidationError) as ctx:
            it.clean()
        self.assertIn("stock_quantity", ctx.exception.message_dict)

    @patch("listings.models.ItemType.objects.only")
    @patch("listings.models.ItemType.objects.filter")
    def test_clean_requires_leaf_itemtype(self, mock_filter, mock_only):
        filter_qs, only_qs = self._mock_itemtype_queries(has_children=True, schema_json={})
        mock_filter.return_value = filter_qs
        mock_only.return_value = only_qs

        it = ItemSet(
            set_name="X",
            price=M(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=False,
            added_by="USER",
            seller_profile_id=None,
            owner_user_id=1,
            type_id=123,
            attributes={},
        )

        with self.assertRaises(ValidationError) as ctx:
            it.clean()
        self.assertIn("type", ctx.exception.message_dict)


class ItemSetShippingCleanUnitTests(SimpleTestCase):
    def test_shipping_clean_requires_staff_buy_checkout(self):
        link = SimpleNamespace(
            item_set=SimpleNamespace(allow_online_checkout=False, listing_type="BUY", added_by="STAFF"),
            package_type=SimpleNamespace(max_length_cm=100, max_width_cm=100, max_height_cm=100, max_weight_kg=10),
            packed_length_cm=None,
            packed_width_cm=None,
            packed_height_cm=None,
            packed_weight_kg=None,
        )
        with self.assertRaises(ValidationError):
            ItemSetShipping.clean(link)

    def test_shipping_clean_rejects_non_positive_packed_fields(self):
        link = SimpleNamespace(
            item_set=SimpleNamespace(
                allow_online_checkout=True,
                listing_type="BUY",
                added_by="STAFF",
                length_cm=10,
                width_cm=10,
                height_cm=10,
                weight_kg=1,
            ),
            package_type=SimpleNamespace(max_length_cm=100, max_width_cm=100, max_height_cm=100, max_weight_kg=10),
            packed_length_cm=0,
            packed_width_cm=None,
            packed_height_cm=None,
            packed_weight_kg=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            ItemSetShipping.clean(link)
        self.assertIn("packed_length_cm", ctx.exception.message_dict)

    def test_shipping_clean_rejects_package_overflow(self):
        link = SimpleNamespace(
            item_set=SimpleNamespace(
                allow_online_checkout=True,
                listing_type="BUY",
                added_by="STAFF",
                length_cm=200,
                width_cm=10,
                height_cm=10,
                weight_kg=1,
            ),
            package_type=SimpleNamespace(max_length_cm=100, max_width_cm=100, max_height_cm=100, max_weight_kg=10),
            packed_length_cm=None,
            packed_width_cm=None,
            packed_height_cm=None,
            packed_weight_kg=None,
        )
        with self.assertRaises(ValidationError):
            ItemSetShipping.clean(link)

    def test_shipping_clean_accepts_packed_override_that_fits(self):
        link = SimpleNamespace(
            item_set=SimpleNamespace(
                allow_online_checkout=True,
                listing_type="BUY",
                added_by="STAFF",
                length_cm=200,
                width_cm=10,
                height_cm=10,
                weight_kg=1,
            ),
            package_type=SimpleNamespace(max_length_cm=100, max_width_cm=100, max_height_cm=100, max_weight_kg=10),
            packed_length_cm=80,
            packed_width_cm=None,
            packed_height_cm=None,
            packed_weight_kg=None,
        )
        ItemSetShipping.clean(link)


class CommandsUnitTests(SimpleTestCase):
    @patch("listings.services.commands.invalidate_public_itemsets_cache")
    @patch("listings.services.commands.ensure_slot_matches_state")
    @patch("listings.services.commands._clean_and_save")
    @patch("listings.services.commands.create_itemset_user")
    def test_user_create_itemset_forces_no_checkout_and_not_buy(
        self,
        mock_create,
        mock_clean_save,
        mock_ensure,
        mock_invalidate,
    ):
        from listings.services import commands

        owner = SimpleNamespace(id=1)
        item = SimpleNamespace(owner_user=owner)
        mock_create.return_value = item
        mock_clean_save.return_value = item

        data = {"listing_type": "BUY", "allow_online_checkout": True}
        out = commands.user_create_itemset.__wrapped__(owner=owner, data=data)

        self.assertIs(out, item)
        sent_data = mock_create.call_args.kwargs["data"]
        self.assertEqual(sent_data["listing_type"], "LISTING")
        self.assertEqual(sent_data["allow_online_checkout"], False)
        mock_ensure.assert_called_once_with(user=owner, itemset=item)

    @patch("listings.services.commands.ensure_slot_matches_state")
    @patch("listings.services.commands._clean_and_save")
    def test_update_itemset_user_after_24h_forbids_type_and_catalog_change(self, mock_clean_save, mock_ensure):
        from listings.services import commands

        owner = SimpleNamespace(id=1)
        itemset = SimpleNamespace(
            status="AVAILABLE",
            added_by="USER",
            created_at=timezone.now() - timedelta(days=2),
            type_id=1,
            catalog_item_id=10,
            owner_user=owner,
            listing_type="LISTING",
            allow_online_checkout=False,
        )

        with self.assertRaises(Forbidden):
            commands.update_itemset.__wrapped__(itemset=itemset, data={"type": SimpleNamespace(id=2)})

        with self.assertRaises(Forbidden):
            commands.update_itemset.__wrapped__(itemset=itemset, data={"catalog_item": SimpleNamespace(id=11)})

        mock_clean_save.assert_not_called()
        mock_ensure.assert_not_called()

    @patch("listings.services.commands.ensure_slot_matches_state")
    @patch("listings.services.commands._clean_and_save")
    def test_update_itemset_user_forces_no_checkout_and_not_buy(self, mock_clean_save, mock_ensure):
        from listings.services import commands

        owner = SimpleNamespace(id=1)
        itemset = SimpleNamespace(
            status="AVAILABLE",
            added_by="USER",
            created_at=timezone.now() - timedelta(hours=1),
            type_id=1,
            catalog_item_id=None,
            owner_user=owner,
            listing_type="LISTING",
            allow_online_checkout=False,
        )
        mock_clean_save.side_effect = lambda obj: obj

        out = commands.update_itemset.__wrapped__(itemset=itemset, data={"listing_type": "BUY", "allow_online_checkout": True})

        self.assertEqual(out.listing_type, "LISTING")
        self.assertEqual(out.allow_online_checkout, False)
        mock_ensure.assert_called_once_with(user=owner, itemset=out)

    @patch("listings.services.commands.invalidate_public_itemsets_cache")
    @patch("listings.services.commands.ensure_slot_matches_state")
    @patch("listings.services.commands._clean_and_save")
    def test_set_status_user_allows_reserved(self, mock_clean_save, mock_ensure, mock_invalidate):
        from listings.services import commands

        owner = SimpleNamespace(id=1)
        itemset = SimpleNamespace(status="AVAILABLE", added_by="USER", stock_quantity=1, owner_user=owner)
        mock_clean_save.side_effect = lambda obj: obj

        out = commands.set_status.__wrapped__(itemset=itemset, status="RESERVED")

        self.assertEqual(out.status, "RESERVED")
        mock_ensure.assert_called_once_with(user=owner, itemset=out)

    def test_set_status_user_forbidden_sold(self):
        from listings.services import commands

        itemset = SimpleNamespace(status="AVAILABLE", added_by="USER", stock_quantity=1, owner_user=SimpleNamespace(id=1))
        with self.assertRaises(Forbidden):
            commands.set_status.__wrapped__(itemset=itemset, status="SOLD")

    @patch("listings.services.commands._clean_and_save")
    def test_set_status_available_requires_stock_gt_zero(self, mock_clean_save):
        from listings.services import commands

        itemset = SimpleNamespace(status="CLOSED", added_by="USER", stock_quantity=0, owner_user=SimpleNamespace(id=1))
        with self.assertRaises(BadRequest):
            commands.set_status.__wrapped__(itemset=itemset, status="AVAILABLE")
        mock_clean_save.assert_not_called()

    def test_set_status_deleted_blocks_change(self):
        from listings.services import commands

        itemset = SimpleNamespace(status="DELETED", added_by="USER", stock_quantity=1, owner_user=SimpleNamespace(id=1))
        with self.assertRaises(Forbidden):
            commands.set_status.__wrapped__(itemset=itemset, status="AVAILABLE")

    def test_set_status_user_suspended_blocks_change(self):
        from listings.services import commands

        itemset = SimpleNamespace(status="SUSPENDED", added_by="USER", stock_quantity=1, owner_user=SimpleNamespace(id=1))
        with self.assertRaises(Forbidden):
            commands.set_status.__wrapped__(itemset=itemset, status="AVAILABLE")

    @patch("listings.services.commands._clean_and_save")
    @patch("listings.services.commands.upsert_shipping_link")
    def test_add_shipping_option_forbidden_when_not_staff_buy_checkout(self, mock_upsert, mock_clean_save):
        from listings.services import commands

        itemset = SimpleNamespace(status="AVAILABLE", added_by="USER", listing_type="BUY", allow_online_checkout=True)
        with self.assertRaises(Forbidden):
            commands.add_shipping_option.__wrapped__(itemset=itemset, package_type=SimpleNamespace(id=1))

        itemset2 = SimpleNamespace(status="AVAILABLE", added_by="STAFF", listing_type="LISTING", allow_online_checkout=True)
        with self.assertRaises(Forbidden):
            commands.add_shipping_option.__wrapped__(itemset=itemset2, package_type=SimpleNamespace(id=1))

        itemset3 = SimpleNamespace(status="AVAILABLE", added_by="STAFF", listing_type="BUY", allow_online_checkout=False)
        with self.assertRaises(Forbidden):
            commands.add_shipping_option.__wrapped__(itemset=itemset3, package_type=SimpleNamespace(id=1))

        mock_upsert.assert_not_called()
        mock_clean_save.assert_not_called()

    @patch("listings.services.commands._clean_and_save")
    @patch("listings.services.commands.upsert_shipping_link")
    def test_add_shipping_option_sets_fields_and_cleans(self, mock_upsert, mock_clean_save):
        from listings.services import commands

        itemset = SimpleNamespace(status="AVAILABLE", added_by="STAFF", listing_type="BUY", allow_online_checkout=True)
        pkg = SimpleNamespace(id=1)

        link = SimpleNamespace(price_override=None, packed_length_cm=None, packed_width_cm=None, packed_height_cm=None, packed_weight_kg=None)
        mock_upsert.return_value = link
        mock_clean_save.side_effect = lambda obj: obj

        out = commands.add_shipping_option.__wrapped__(itemset=itemset, package_type=pkg, packed_length_cm=10)

        self.assertIs(out, link)
        self.assertEqual(out.packed_length_cm, 10)
        mock_upsert.assert_called_once_with(itemset=itemset, package_type=pkg)


class ExpireTaskUnitTests(SimpleTestCase):
    def _lock_cm(self, ok: bool):
        @contextmanager
        def cm():
            yield ok
        return cm()

    def _atomic_cm(self):
        @contextmanager
        def cm():
            yield
        return cm()

    @patch("listings.tasks.invalidate_public_itemsets_cache")
    @patch("listings.tasks.ensure_slot_matches_state")
    @patch("listings.tasks.transaction.atomic")
    @patch("listings.tasks.task_lock")
    @patch("listings.tasks.ItemSet")
    def test_expire_task_skips_when_locked(
        self,
        mock_itemset,
        mock_lock,
        mock_atomic,
        mock_ensure,
        mock_invalidate,
    ):
        from listings import tasks as listing_tasks

        mock_lock.side_effect = lambda *args, **kwargs: self._lock_cm(False)
        mock_atomic.side_effect = lambda *args, **kwargs: self._atomic_cm()

        res = listing_tasks.expire_stale_user_itemsets_periodic.run(days=30, limit=0)
        self.assertEqual(res.get("skipped"), "already running")
        mock_ensure.assert_not_called()

    @patch("listings.tasks.invalidate_public_itemsets_cache")
    @patch("listings.tasks.ensure_slot_matches_state")
    @patch("listings.tasks.transaction.atomic")
    @patch("listings.tasks.task_lock")
    @patch("listings.tasks.ItemSet")
    def test_expire_task_expires_ids_and_calls_ensure(
        self,
        mock_itemset,
        mock_lock,
        mock_atomic,
        mock_ensure,
        mock_invalidate,
    ):
        from listings import tasks as listing_tasks

        mock_lock.side_effect = lambda *args, **kwargs: self._lock_cm(True)
        mock_atomic.side_effect = lambda *args, **kwargs: self._atomic_cm()

        qs = MagicMock()
        qs.filter.return_value = qs
        qs.order_by.return_value = qs
        qs.values_list.return_value = [1, 2]
        qs.__getitem__.return_value = qs

        update_qs = MagicMock()

        items_filter_qs = MagicMock()
        items = [
            SimpleNamespace(id=1, owner_user=SimpleNamespace(id=10)),
            SimpleNamespace(id=2, owner_user=SimpleNamespace(id=11)),
        ]
        items_filter_qs.select_related.return_value = items

        mgr = MagicMock()
        mgr.select_for_update.return_value = qs
        mgr.filter.side_effect = [update_qs, items_filter_qs]
        mock_itemset.objects = mgr

        res = listing_tasks.expire_stale_user_itemsets_periodic.run(days=30, limit=0)

        self.assertEqual(res["expired"], 2)
        update_qs.update.assert_called_once()
        self.assertEqual(mock_ensure.call_count, 2)


class ItemSetCleanSchemaIntegrationUnitTests(SimpleTestCase):
    @patch("listings.models._normalize_and_validate_attrs")
    @patch("listings.models.ItemType.objects.only")
    @patch("listings.models.ItemType.objects.filter")
    def test_clean_applies_schema_normalization_to_attributes(self, mock_filter, mock_only, mock_norm):
        filter_qs = MagicMock()
        filter_qs.exists.return_value = False
        mock_filter.return_value = filter_qs

        only_qs = MagicMock()
        only_filter_qs = MagicMock()
        only_filter_qs.first.return_value = SimpleNamespace(
            schema_json={"type": "object", "properties": {"x": {"type": "integer"}}}
        )
        only_qs.filter.return_value = only_filter_qs
        mock_only.return_value = only_qs

        mock_norm.return_value = {"x": 2, "defaulted": True}

        it = ItemSet(
            set_name="X",
            price=M(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=False,
            added_by="USER",
            seller_profile_id=None,
            owner_user_id=1,
            type_id=123,
            attributes={"x": "2"},
        )
        it._state.fields_cache["owner_user"] = SimpleNamespace(id=1)

        it.clean()

        mock_norm.assert_called_once()
        _, kwargs = mock_norm.call_args
        self.assertEqual(kwargs["where"], "attributes")
        self.assertEqual(kwargs["require_same_fields"], False)
        self.assertEqual(it.attributes, {"x": 2, "defaulted": True})

    @patch("listings.models.ItemType.objects.only")
    @patch("listings.models.ItemType.objects.filter")
    def test_clean_schema_validation_error_propagates_as_validationerror(self, mock_filter, mock_only):
        filter_qs = MagicMock()
        filter_qs.exists.return_value = False
        mock_filter.return_value = filter_qs

        schema = {
            "type": "object",
            "properties": {"size": {"type": "integer", "minimum": 1}},
            "required": ["size"],
        }

        only_qs = MagicMock()
        only_filter_qs = MagicMock()
        only_filter_qs.first.return_value = SimpleNamespace(schema_json=schema)
        only_qs.filter.return_value = only_filter_qs
        mock_only.return_value = only_qs

        it = ItemSet(
            set_name="X",
            price=M(10, "PLN"),
            stock_quantity=1,
            condition="USED",
            status="AVAILABLE",
            listing_type="LISTING",
            allow_online_checkout=False,
            added_by="USER",
            seller_profile_id=None,
            owner_user_id=1,
            type_id=123,
            attributes={"size": 0},
        )

        with self.assertRaises(ValidationError) as ctx:
            it.clean()
        self.assertIn("attributes", ctx.exception.message_dict)


class StatusSOLDUnitTests(SimpleTestCase):
    @patch("listings.services.commands.invalidate_public_itemsets_cache")
    @patch("listings.services.commands.ensure_slot_matches_state")
    @patch("listings.services.commands._clean_and_save")
    def test_set_status_staff_allows_sold(self, mock_clean_save, mock_ensure, mock_invalidate):
        from listings.services import commands

        itemset = SimpleNamespace(
            status="AVAILABLE",
            added_by="STAFF",
            stock_quantity=1,
            owner_user=None,
        )
        mock_clean_save.side_effect = lambda obj: obj

        out = commands.set_status.__wrapped__(itemset=itemset, status="SOLD")

        self.assertEqual(out.status, "SOLD")
        mock_ensure.assert_called_once_with(user=None, itemset=out)

    def test_set_status_user_forbidden_sold(self):
        from listings.services import commands

        itemset = SimpleNamespace(
            status="AVAILABLE",
            added_by="USER",
            stock_quantity=1,
            owner_user=SimpleNamespace(id=1),
        )
        with self.assertRaises(Forbidden):
            commands.set_status.__wrapped__(itemset=itemset, status="SOLD")

    def test_set_status_staff_rejects_expired(self):
        from listings.services import commands

        itemset = SimpleNamespace(
            status="AVAILABLE",
            added_by="STAFF",
            stock_quantity=1,
            owner_user=None,
        )
        with self.assertRaises(BadRequest):
            commands.set_status.__wrapped__(itemset=itemset, status="EXPIRED")
