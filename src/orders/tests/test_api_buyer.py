# from django.urls import reverse
# from django.test import override_settings
# from rest_framework.test import APITestCase
# from rest_framework import status
# from djmoney.money import Money
# from unittest import mock
#
# from identity.models import User, SellerProfile, SellerMembership
# from catalog.models import ItemType
# from listings.models import ItemSet
# from shipping.models import PackageType
# from orders.models import Order
# from orders.services import commands
#
#
# @override_settings(SECURE_SSL_REDIRECT=False)
# class BuyerOrdersApiTests(APITestCase):
#     def setUp(self):
#         self.buyer = User.objects.create_user(email="buyer@example.com", password="pass1234")
#         self.seller_user = User.objects.create_user(email="seller@example.com", password="pass1234")
#         self.seller = SellerProfile.objects.create(
#             owner=self.seller_user,
#             company_name="Test Seller",
#             slug="test-seller",
#         )
#         SellerMembership.objects.create(
#             seller_profile=self.seller,
#             user=self.seller_user,
#             role="OWNER",
#             is_active=True,
#         )
#         self.item_type = ItemType.objects.create(name="Electronics")
#         self.item = ItemSet.objects.create(
#             set_name="Phone",
#             description="Smartphone",
#             price=Money(100, "PLN"),
#             stock_quantity=5,
#             condition="USED",
#             status="AVAILABLE",
#             listing_type="BUY",
#             allow_online_checkout=True,
#             seller_profile=self.seller,
#             owner_user=None,
#             type=self.item_type,
#         )
#         self.package = PackageType.objects.create(
#             provider="INPOST",
#             dimensions="A",
#             max_length_cm=100,
#             max_width_cm=100,
#             max_height_cm=100,
#             max_weight_kg="10.000",
#             price=Money(10, "PLN"),
#             points=0,
#         )
#
#     def _auth_buyer(self):
#         self.client.force_authenticate(user=self.buyer)
#
#     def _checkout(self, quantity=1):
#         self._auth_buyer()
#         url = reverse("orders:buyer-orders-checkout")
#         payload = {
#             "item_public_id": self.item.public_id,
#             "quantity": quantity,
#             "payment_method": "CREDIT_CARD",
#         }
#         resp = self.client.post(url, payload, format="json")
#         self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
#         order_pid = resp.data["public_id"]
#         return Order.objects.get(public_id=order_pid)
#
#     def test_checkout_creates_order_for_buyer(self):
#         order = self._checkout(quantity=2)
#         self.assertEqual(order.buyer, self.buyer)
#         self.assertEqual(order.seller_profile, self.seller)
#         self.assertEqual(order.order_lines.count(), 1)
#         line = order.order_lines.first()
#         self.assertEqual(line.quantity, 2)
#         self.assertEqual(order.transaction.type, "PURCHASE")
#         self.assertEqual(order.order_status, "PENDING")
#
#     def test_list_returns_only_orders_of_buyer(self):
#         order1 = self._checkout(quantity=1)
#         other_user = User.objects.create_user(email="other@example.com", password="pass1234")
#         commands.checkout_single_item(
#             buyer=other_user,
#             item_public_id=self.item.public_id,
#             quantity=1,
#             payment_method="CREDIT_CARD",
#         )
#         self._auth_buyer()
#         url = reverse("orders:buyer-orders-list")
#         resp = self.client.get(url, format="json")
#         self.assertEqual(resp.status_code, status.HTTP_200_OK)
#         pids = [row["public_id"] for row in resp.data["results"]]
#         self.assertIn(order1.public_id, pids)
#         self.assertTrue(all(pid == order1.public_id for pid in pids))
#
#     @mock.patch("orders.services.commands.cancel_active_payments_for_tx", return_value=True)
#     def test_select_line_shipping_package_sets_price_and_cancels_payment(self, mock_cancel):
#         order = self._checkout(quantity=1)
#         line = order.order_lines.first()
#         self._auth_buyer()
#         url = reverse(
#             "orders:buyer-orders-select-line-shipping",
#             kwargs={"public_id": order.public_id, "line_public_id": line.public_id},
#         )
#         payload = {
#             "mode": "PACKAGE",
#             "package_type_public_id": self.package.public_id,
#         }
#         resp = self.client.post(url, payload, format="json")
#         self.assertEqual(resp.status_code, status.HTTP_200_OK)
#         self.assertIn("X-Active-Payment-Cancelled", resp)
#         self.assertEqual(resp["X-Active-Payment-Cancelled"], "1")
#         data = resp.data
#         self.assertEqual(data["package_type_public_id"], self.package.public_id)
#         self.assertEqual(str(data["price"]["amount"]), str(self.package.price.amount))
#         mock_cancel.assert_called_once()
#
#     def test_set_shipping_address_partial_when_only_pickup(self):
#         order = self._checkout(quantity=1)
#         self._auth_buyer()
#         url = reverse("orders:buyer-orders-set-shipping-address", kwargs={"public_id": order.public_id})
#         payload = {
#             "first_name": "Jan",
#             "city": "Kraków",
#         }
#         resp = self.client.post(url, payload, format="json")
#         self.assertEqual(resp.status_code, status.HTTP_200_OK)
#         self.assertEqual(resp.data["public_id"], order.public_id)
#
#     def test_set_shipping_address_requires_full_for_package_shipping(self):
#         order = self._checkout(quantity=1)
#         line = order.order_lines.first()
#         self._auth_buyer()
#         sel_url = reverse(
#             "orders:buyer-orders-select-line-shipping",
#             kwargs={"public_id": order.public_id, "line_public_id": line.public_id},
#         )
#         sel_payload = {
#             "mode": "PACKAGE",
#             "package_type_public_id": self.package.public_id,
#         }
#         resp_sel = self.client.post(sel_url, sel_payload, format="json")
#         self.assertEqual(resp_sel.status_code, status.HTTP_200_OK)
#         addr_url = reverse("orders:buyer-orders-set-shipping-address", kwargs={"public_id": order.public_id})
#         bad_payload = {
#             "first_name": "Jan",
#             "city": "Warszawa",
#         }
#         resp = self.client.post(addr_url, bad_payload, format="json")
#         self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
#         self.assertIn("last_name", resp.data)
#         self.assertIn("street", resp.data)
#         self.assertIn("postal_code", resp.data)
#         self.assertIn("country", resp.data)
