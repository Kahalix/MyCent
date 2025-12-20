from __future__ import annotations
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from services.services import queries
from .factories import create_item_type, create_listing_package, create_user


class QueriesGetSlotSummaryTests(TestCase):
    @patch("services.services.commands.slot_summary_for_user")
    def test_get_slot_summary_delegates_to_commands(self, mock_slot_summary):
        user = create_user()
        mock_slot_summary.return_value = [{"item_type": {"name": "X"}}]
        result = queries.get_slot_summary(user)
        mock_slot_summary.assert_called_once_with(user)
        self.assertEqual(result, [{"item_type": {"name": "X"}}])


class QueriesGetAvailablePackagesTests(TestCase):
    def test_get_available_packages_for_type_orders_by_price_and_points(self):
        itype = create_item_type()
        pkg_free = create_listing_package(item_type=itype, listings_free=5, price_amount=None, points=0)
        pkg_points = create_listing_package(item_type=itype, listings_free=0, price_amount=None, points=10)
        pkg_money = create_listing_package(item_type=itype, listings_free=0, price_amount=Decimal("5.00"), points=0)

        other_type = create_item_type()
        create_listing_package(item_type=other_type, listings_free=1, price_amount=Decimal("1.00"), points=0)

        qs = queries.get_available_packages_for_type(itype)
        pks = [p.id for p in qs]
        self.assertEqual(set(pks), {pkg_free.id, pkg_points.id, pkg_money.id})
