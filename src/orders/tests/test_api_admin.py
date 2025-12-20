# from django.urls import reverse
# from django.test import override_settings
# from rest_framework.test import APITestCase
# from rest_framework import status
# from djmoney.money import Money
#
# from identity.models import User, SellerProfile, SellerMembership
# from catalog.models import ItemType
# from listings.models import ItemSet
# from orders.models import Order
# from orders.services import commands
#
#
# @override_settings(SECURE_SSL_REDIRECT=False)
# class AdminOrdersApiTests(APITestCase):
#     def setUp(self):
#         self.admin = User.objects.create_user(
#             email="admin@example.com",
#             password="pass1234",
#             is_staff=True,
#             is_superuser=True,
#         )
#         self.seller_user = User.objects.create_user(email="seller@example.com", password="pass1234")
#         self.seller = SellerProfile.objects.create(
#             owner=self.seller_user,
#             company_name="Test Seller",
#             slug="admin-seller",
#         )
#         SellerMembership.objects.create(
#             seller_profile=self.seller,
#             user=self.seller_user,
#             role="OWNER",
#             is_active=True,
#         )
#         self.buyer1 = User.objects.create_user(email="buyer1@example.com", password="pass1234")
#         self.buyer2 = User.objects.create_user(email="buyer2@example.com", password="pass1234")
#         self.item_type = ItemType.objects.create(name="Category")
#         self.item = ItemSet.objects.create(
#             set_name="TV",
#             description="TV",
#             price=Money(300, "PLN"),
#             stock_quantity=10,
#             condition="USED",
#             status="AVAILABLE",
#             listing_type="BUY",
#             allow_online_checkout=True,
#             seller_profile=self.seller,
#             owner_user=None,
#             type=self.item_type,
#         )
#         self.order1 = commands.checkout_single_item(
#             buyer=self.buyer1,
#             item_public_id=self.item.public_id,
#             quantity=1,
#             payment_method="CREDIT_CARD",
#         )
#         self.order2 = commands.checkout_single_item(
#             buyer=self.buyer2,
#             item_public_id=self.item.public_id,
#             quantity=2,
#             payment_method="CREDIT_CARD",
#         )
#         self.client.force_authenticate(user=self.admin)
#
#     def test_admin_list_returns_orders(self):
#         url = reverse("orders:admin-orders-list")
#         resp = self.client.get(url, format="json")
#         self.assertEqual(resp.status_code, status.HTTP_200_OK)
#         pids = [row["public_id"] for row in resp.data["results"]]
#         self.assertIn(self.order1.public_id, pids)
#         self.assertIn(self.order2.public_id, pids)
#
#     def test_admin_retrieve_single_order(self):
#         url = reverse("orders:admin-orders-detail", kwargs={"public_id": self.order1.public_id})
#         resp = self.client.get(url, format="json")
#         self.assertEqual(resp.status_code, status.HTTP_200_OK)
#         self.assertEqual(resp.data["public_id"], self.order1.public_id)
#         self.assertEqual(resp.data["transaction_public_id"], self.order1.transaction.public_id)
