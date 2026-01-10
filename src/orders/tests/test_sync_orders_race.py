from __future__ import annotations

from queue import Queue
from threading import Barrier, Thread

from django.db import connection, connections, close_old_connections
from django.test import TransactionTestCase
from django.utils import timezone

from orders.services.commands import sync_orders_with_transaction
from orders.services.exceptions import Conflict
from orders.tests.factories import (
    create_user,
    create_seller_profile,
    create_item_type,
    create_itemset,
    create_transaction,
    create_order,
    create_order_line,
    create_item_reservation,
)
from listings.models import ItemSet
from orders.models import ItemReservation
from transactions.models import Transaction


class SyncOrdersRaceTests(TransactionTestCase):
    serialized_rollback = True

    @classmethod
    def tearDownClass(cls):
        connections.close_all()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        if connection.vendor != "postgresql":
            self.skipTest("Te testy wymagają PostgreSQL (select_for_update + blokady wątków).")

    def _mk_sellable_item(self, *, stock: int) -> ItemSet:
        owner = create_user(email="seller-owner@example.com")
        seller = create_seller_profile(owner=owner, slug="shop-1", company_name="Shop 1")
        itype = create_item_type(name="Category")
        item = create_itemset(
            seller=seller,
            item_type=itype,
            set_name="Item 1",
            stock_quantity=stock,
            status="AVAILABLE",
            listing_type="BUY",
            allow_online_checkout=True,
        )
        return item

    def _mk_purchase_tx_with_line_and_reservation(self, *, item: ItemSet, qty: int, status: str = "COMPLETED") -> Transaction:
        buyer = create_user(email=f"buyer-{timezone.now().timestamp()}@example.com")
        tx = create_transaction(user=buyer, type_="PURCHASE", status=status)
        order = create_order(tx=tx, seller=item.seller_profile, buyer=buyer, status="PENDING", payment_method="ONLINE_PAYMENT")
        line = create_order_line(order=order, item=item, quantity=qty)
        create_item_reservation(
            item=item,
            tx=tx,
            line=line,
            user=buyer,
            quantity=qty,
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
            released_at=None,
        )
        return tx

    def test_sync_orders_completed_purchase_is_idempotent(self):
        item = self._mk_sellable_item(stock=1)
        tx = self._mk_purchase_tx_with_line_and_reservation(item=item, qty=1, status="COMPLETED")

        sync_orders_with_transaction(tx=tx)

        item.refresh_from_db()
        self.assertEqual(int(item.stock_quantity or 0), 0)
        self.assertEqual(item.status, "SOLD")

        active = ItemReservation.objects.filter(transaction=tx, released_at__isnull=True).count()
        self.assertEqual(active, 0)

        sync_orders_with_transaction(tx=tx)

        item.refresh_from_db()
        self.assertEqual(int(item.stock_quantity or 0), 0)
        self.assertEqual(item.status, "SOLD")

    def test_sync_orders_concurrent_calls_for_same_tx_decrement_stock_only_once(self):
        item = self._mk_sellable_item(stock=1)
        tx = self._mk_purchase_tx_with_line_and_reservation(item=item, qty=1, status="COMPLETED")
        tx_id = tx.id

        barrier = Barrier(2)
        errors: Queue[BaseException] = Queue()

        def worker():
            close_old_connections()
            try:
                tx_local = Transaction.objects.get(pk=tx_id)
                barrier.wait()
                sync_orders_with_transaction(tx=tx_local)
            except BaseException as e:
                errors.put(e)
            finally:
                connections.close_all()

        t1 = Thread(target=worker, daemon=True)
        t2 = Thread(target=worker, daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        connections.close_all()

        if not errors.empty():
            raise errors.get()

        item.refresh_from_db()
        self.assertEqual(int(item.stock_quantity or 0), 0)
        self.assertEqual(item.status, "SOLD")

        active = ItemReservation.objects.filter(transaction_id=tx_id, released_at__isnull=True).count()
        self.assertEqual(active, 0)

    def test_sync_orders_blocks_when_other_active_reservation_exists(self):
        item = self._mk_sellable_item(stock=1)

        tx1 = self._mk_purchase_tx_with_line_and_reservation(item=item, qty=1, status="COMPLETED")
        tx2 = self._mk_purchase_tx_with_line_and_reservation(item=item, qty=1, status="PENDING")

        with self.assertRaises(Conflict):
            sync_orders_with_transaction(tx=tx1)

        item.refresh_from_db()
        self.assertEqual(int(item.stock_quantity or 0), 1)
        self.assertEqual(item.status, "AVAILABLE")

        active1 = ItemReservation.objects.filter(transaction=tx1, released_at__isnull=True).count()
        self.assertEqual(active1, 1)
