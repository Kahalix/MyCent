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
# from orders.models import Order, OrderShipping
# from orders.services import commands
# from shipping.models import PackageType
# from customers.models import Customer
#
#
# @override_settings(SECURE_SSL_REDIRECT=False)
# class SellerOrdersApiTests(APITestCase):
#     def setUp(self):
#         self.seller_user = User.objects.create_user(email="seller@example.com", password="pass1234")
#         self.seller = SellerProfile.objects.create(
#             owner=self.seller_user,
#             company_name="Main Seller",
#             slug="main-seller",
#         )
#         SellerMembership.objects.create(
#             seller_profile=self.seller,
#             user=self.seller_user,
#             role="OWNER",
#             is_active=True,
#         )
#         self.buyer = User.objects.create_user(email="buyer@example.com", password="pass1234")
#         self.item_type = ItemType.objects.create(name="Category")
#         self.item = ItemSet.objects.create(
#             set_name="Laptop",
#             description="Nice laptop",
#             price=Money(200, "PLN"),
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
#             price=Money(15, "PLN"),
#             points=0,
#         )
#         self.client.force_authenticate(user=self.seller_user)
#         self.order = commands.checkout_single_item(
#             buyer=self.buyer,
#             item_public_id=self.item.public_id,
#             quantity=1,
#             payment_method="CREDIT_CARD",
#         )
#
#     def test_list_returns_only_orders_for_seller_member(self):
#         other_seller_user = User.objects.create_user(email="seller2@example.com", password="pass1234")
#         other_seller = SellerProfile.objects.create(
#             owner=other_seller_user,
#             company_name="Other Seller",
#             slug="other-seller",
#         )
#         SellerMembership.objects.create(
#             seller_profile=other_seller,
#             user=other_seller_user,
#             role="OWNER",
#             is_active=True,
#         )
#         item2 = ItemSet.objects.create(
#             set_name="Phone",
#             description="Phone",
#             price=Money(100, "PLN"),
#             stock_quantity=3,
#             condition="USED",
#             status="AVAILABLE",
#             listing_type="BUY",
#             allow_online_checkout=True,
#             seller_profile=other_seller,
#             owner_user=None,
#             type=self.item_type,
#         )
#         commands.checkout_single_item(
#             buyer=self.buyer,
#             item_public_id=item2.public_id,
#             quantity=1,
#             payment_method="CREDIT_CARD",
#         )
#         url = reverse("orders:seller-orders-list")
#         resp = self.client.get(url, format="json")
#         self.assertEqual(resp.status_code, status.HTTP_200_OK)
#         pids = [row["public_id"] for row in resp.data["results"]]
#         self.assertIn(self.order.public_id, pids)
#         self.assertTrue(all(pid == self.order.public_id for pid in pids))
#
#     def test_offline_checkout_creates_new_order(self):
#         url = reverse("orders:seller-orders-offline-checkout")
#         payload = {
#             "item_public_id": self.item.public_id,
#             "quantity": 2,
#             "payment_method": "CASH",
#             "customer": {
#                 "first_name": "Jan",
#                 "last_name": "Kowalski",
#                 "email": "jan@example.com",
#             },
#         }
#         resp = self.client.post(url, payload, format="json")
#         self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
#         data = resp.data
#         self.assertEqual(data["payment_method"], "CASH")
#         self.assertEqual(data["order_status"], "COMPLETED")
#         self.assertEqual(data["seller_profile"], self.seller.id)
#
#     def test_add_line_shipping_creates_shipping(self):
#         line = self.order.order_lines.first()
#         url = reverse(
#             "orders:seller-orders-add-line-shipping",
#             kwargs={"public_id": self.order.public_id, "line_public_id": line.public_id},
#         )
#         payload = {
#             "tracking_number": "TRACK123",
#             "package_type_public_id": self.package.public_id,
#             "price": "20.00",
#         }
#         resp = self.client.post(url, payload, format="json")
#         self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
#         shipping = OrderShipping.objects.get(order=self.order, order_line=line)
#         self.assertEqual(shipping.tracking_number, "TRACK123")
#         self.assertEqual(shipping.package_type, self.package)
#
#     def test_update_line_shipping_status_and_tracking(self):
#         line = self.order.order_lines.first()
#         url_create = reverse(
#             "orders:seller-orders-add-line-shipping",
#             kwargs={"public_id": self.order.public_id, "line_public_id": line.public_id},
#         )
#         self.client.post(
#             url_create,
#             {"tracking_number": "OLD", "package_type_public_id": self.package.public_id, "price": "10.00"},
#             format="json",
#         )
#         shipping = OrderShipping.objects.get(order=self.order, order_line=line)
#         url = reverse(
#             "orders:seller-orders-update-line-shipping-status",
#             kwargs={
#                 "public_id": self.order.public_id,
#                 "line_public_id": line.public_id,
#                 "shipping_public_id": shipping.public_id,
#             },
#         )
#         payload = {
#             "shipping_status": "SHIPPED",
#             "tracking_number": "NEWTRACK",
#         }
#         resp = self.client.patch(url, payload, format="json")
#         self.assertEqual(resp.status_code, status.HTTP_200_OK)
#         shipping.refresh_from_db()
#         self.assertEqual(shipping.shipping_status, "SHIPPED")
#         self.assertEqual(shipping.tracking_number, "NEWTRACK")
#
#     def test_receipt_csv_returns_attachment(self):
#         url = reverse("orders:seller-orders-receipt-csv", kwargs={"public_id": self.order.public_id})
#         resp = self.client.get(url)
#         self.assertEqual(resp.status_code, status.HTTP_200_OK)
#         self.assertIn("attachment;", resp["Content-Disposition"])
#         self.assertTrue(resp.content)
#
#     @mock.patch("orders.services.commands.build_receipt_pdf", return_value=b"%PDF-1.4")
#     def test_receipt_pdf_uses_stubbed_builder(self, mock_pdf):
#         url = reverse("orders:seller-orders-receipt-pdf", kwargs={"public_id": self.order.public_id})
#         resp = self.client.get(url)
#         self.assertEqual(resp.status_code, status.HTTP_200_OK)
#         self.assertEqual(resp["Content-Type"], "application/pdf")
#         self.assertTrue(resp.content)
#         mock_pdf.assert_called_once()
#
#     def test_export_csv_returns_attachment(self):
#         url = reverse("orders:seller-orders-export-csv")
#         resp = self.client.get(url)
#         self.assertEqual(resp.status_code, status.HTTP_200_OK)
#         self.assertIn("attachment;", resp["Content-Disposition"])
#         self.assertTrue(resp.content)
#
#     def test_attach_and_detach_customer(self):
#         customer = Customer.objects.create(
#             first_name="Adam",
#             last_name="Nowak",
#             email="adam@example.com",
#             phone="123456789",
#         )
#         url_attach = reverse("orders:seller-orders-attach-customer", kwargs={"public_id": self.order.public_id})
#         resp_attach = self.client.post(url_attach, {"customer_public_id": customer.public_id}, format="json")
#         self.assertEqual(resp_attach.status_code, status.HTTP_200_OK)
#         self.order.refresh_from_db()
#         self.assertEqual(self.order.customer, customer)
#         url_detach = reverse("orders:seller-orders-detach-customer", kwargs={"public_id": self.order.public_id})
#         resp_detach = self.client.post(url_detach, {}, format="json")
#         self.assertEqual(resp_detach.status_code, status.HTTP_200_OK)
#         self.order.refresh_from_db()
#         self.assertIsNone(self.order.customer)
#
#     def test_ensure_customer_created_when_not_exists(self):
#         url = reverse("orders:seller-orders-ensure-customer", kwargs={"public_id": self.order.public_id})
#         payload = {
#             "first_name": "Ewa",
#             "last_name": "Kowalska",
#             "email": "ewa@example.com",
#             "phone": "987654321",
#             "address": {
#                 "line1": "Ulica 1",
#                 "postal_code": "00-001",
#                 "city": "Warszawa",
#                 "country": "PL",
#             },
#         }
#         resp = self.client.post(url, payload, format="json")
#         self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
#         self.assertIn(resp.data["result"], ("attached", "created"))
#         self.assertTrue(resp.data.get("customer_public_id"))
