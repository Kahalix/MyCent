from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from orders.services import queries
from .factories import (
    create_user,
    create_seller_profile,
    create_item_type,
    create_itemset,
    create_transaction,
    create_order,
    create_order_line,
)


class OrderQueriesTests(TestCase):
    def setUp(self):
        self.admin = create_user(email="admin@example.com", is_staff=True)
        self.buyer1 = create_user(email="buyer1@example.com")
        self.buyer2 = create_user(email="buyer2@example.com")
        self.owner1 = create_user(email="owner1@example.com")
        self.owner2 = create_user(email="owner2@example.com")
        self.seller1 = create_seller_profile(owner=self.owner1, slug="shop-a")
        self.seller2 = create_seller_profile(owner=self.owner2, slug="shop-b")
        self.item_type = create_item_type()
        self.item1 = create_itemset(self.seller1, self.item_type, price=Money(10, "PLN"))
        self.item2 = create_itemset(self.seller2, self.item_type, price=Money(20, "PLN"))
        tx1 = create_transaction(user=self.buyer1)
        tx2 = create_transaction(user=self.buyer2)
        self.order_b1_s1 = create_order(tx1, self.seller1, buyer=self.buyer1, order_name="B1-S1")
        create_order_line(self.order_b1_s1, self.item1, quantity=1)
        self.order_b1_s2 = create_order(tx1, self.seller2, buyer=self.buyer1, order_name="B1-S2")
        create_order_line(self.order_b1_s2, self.item2, quantity=2)
        self.order_b2_s1 = create_order(tx2, self.seller1, buyer=self.buyer2, order_name="B2-S1")
        create_order_line(self.order_b2_s1, self.item1, quantity=1)

    def test_list_buyer_orders_returns_only_for_buyer(self):
        qs1 = queries.list_buyer_orders(self.buyer1)
        ids1 = {o.public_id for o in qs1}
        self.assertEqual(ids1, {self.order_b1_s1.public_id, self.order_b1_s2.public_id})
        qs2 = queries.list_buyer_orders(self.buyer2)
        ids2 = {o.public_id for o in qs2}
        self.assertEqual(ids2, {self.order_b2_s1.public_id})

    def test_list_seller_orders_returns_only_for_seller(self):
        qs1 = queries.list_seller_orders(self.seller1)
        ids1 = {o.public_id for o in qs1}
        self.assertEqual(ids1, {self.order_b1_s1.public_id, self.order_b2_s1.public_id})
        qs2 = queries.list_seller_orders(self.seller2)
        ids2 = {o.public_id for o in qs2}
        self.assertEqual(ids2, {self.order_b1_s2.public_id})

    def test_list_admin_orders_returns_all(self):
        qs = queries.list_admin_orders()
        ids = {o.public_id for o in qs}
        self.assertEqual(ids, {self.order_b1_s1.public_id, self.order_b1_s2.public_id, self.order_b2_s1.public_id})

    def test_buyer_orders_ordered_by_created_desc(self):
        o1 = self.order_b1_s1
        o2 = self.order_b1_s2
        o1.created_at = timezone.now() - timezone.timedelta(days=1)
        o1.save(update_fields=["created_at"])
        qs = list(queries.list_buyer_orders(self.buyer1))
        self.assertEqual(qs[0].public_id, o2.public_id)
        self.assertEqual(qs[1].public_id, o1.public_id)