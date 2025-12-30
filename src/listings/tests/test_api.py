from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from listings.api_views import (
    PublicItemSetViewSet,
    SellerItemSetViewSet,
    UserItemSetViewSet,
    AdminItemSetViewSet,
)
from .factories import (
    create_user,
    create_seller_profile,
    create_item_type,
    create_item_set,
)


def get_results(resp):
    data = resp.data
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


class PublicItemSetApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_by_slug_returns_item(self):
        item = create_item_set(status="AVAILABLE")
        view = PublicItemSetViewSet.as_view({"get": "by_slug"})
        request = self.factory.get(f"/public/item-sets/by-slug/{item.slug}/")
        response = view(request, slug=item.slug)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["public_id"], str(item.public_id))

    def test_start_chat_creates_thread(self):
        user = create_user(email="u@example.com")
        item = create_item_set(status="AVAILABLE")

        view = PublicItemSetViewSet.as_view({"post": "start_chat"})
        request = self.factory.post(
            f"/public/item-sets/{item.public_id}/start-chat/", {}
        )
        force_authenticate(request, user=user)

        # Uwaga: w api_views import jest:
        # from chat.services import commands as chat_cmd
        # from chat.serializers import ChatThreadResponse
        with patch(
            "listings.api_views.chat_cmd.start_dm"
        ) as mock_start_dm, patch(
            "listings.api_views.ChatThreadResponse"
        ) as MockThreadResponse:
            thread_obj = object()
            mock_start_dm.return_value = thread_obj
            MockThreadResponse.return_value.data = {"id": "thread1"}

            response = view(request, public_id=str(item.public_id))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_start_dm.assert_called_once()
        _, kwargs = mock_start_dm.call_args
        self.assertEqual(kwargs["initiator"], user)
        self.assertIsNone(kwargs["other_user"])
        self.assertEqual(kwargs["item"].id, item.id)
        MockThreadResponse.assert_called_once_with(thread_obj)


class SellerItemSetApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = create_user(email="seller@example.com")
        # sygnał na SellerProfile sam zrobi membership OWNER
        self.seller = create_seller_profile(owner=self.user)
        self.item_type = create_item_type()

    def test_list_returns_only_member_seller_items(self):
        own_item = create_item_set(
            item_type=self.item_type,
            seller_profile=self.seller,
            added_by="STAFF",
        )
        other_seller = create_seller_profile()
        other_item = create_item_set(
            item_type=self.item_type,
            seller_profile=other_seller,
            added_by="STAFF",
        )

        view = SellerItemSetViewSet.as_view({"get": "list"})
        request = self.factory.get("/api/sellers/mine/item-sets/")
        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_results(response)
        ids = {row["public_id"] for row in results}
        self.assertIn(str(own_item.public_id), ids)
        self.assertNotIn(str(other_item.public_id), ids)

    def test_create_without_seller_public_id_returns_400(self):
        view = SellerItemSetViewSet.as_view({"post": "create"})
        payload = {
            "set_name": "Test item",
            "price": "10.00",
            "stock_quantity": 1,
            "condition": "USED",
            "status": "AVAILABLE",
            "listing_type": "LISTING",
            "type": str(self.item_type.id),
        }
        request = self.factory.post(
            "/api/sellers/mine/item-sets/", payload, format="json"
        )
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_create_with_seller_public_id_uses_command(self):
        view = SellerItemSetViewSet.as_view({"post": "create"})
        payload = {
            "set_name": "Test item",
            "price": "10.00",
            "stock_quantity": 1,
            "condition": "USED",
            "status": "AVAILABLE",
            "listing_type": "LISTING",
            "type": str(self.item_type.id),
            "seller_public_id": str(self.seller.public_id),
        }
        created_item = create_item_set(
            item_type=self.item_type,
            seller_profile=self.seller,
            added_by="STAFF",
        )

        # w api_views używany jest alias modułu `commands`
        with patch(
            "listings.api_views.commands.seller_member_create_itemset"
        ) as mock_cmd:
            mock_cmd.return_value = created_item
            request = self.factory.post(
                "/api/sellers/mine/item-sets/", payload, format="json"
            )
            force_authenticate(request, user=self.user)
            response = view(request)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_cmd.assert_called_once()
        _, kwargs = mock_cmd.call_args
        self.assertEqual(kwargs["user"], self.user)
        self.assertEqual(kwargs["seller"], self.seller)


class UserItemSetApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = create_user(email="user@example.com")
        self.item_type = create_item_type()

    def test_create_user_itemset_uses_command(self):
        view = UserItemSetViewSet.as_view({"post": "create"})
        payload = {
            "set_name": "User item",
            "price": "5.00",
            "stock_quantity": 1,
            "condition": "USED",
            "status": "AVAILABLE",
            "listing_type": "LISTING",
            "type": str(self.item_type.id),
        }
        created_item = create_item_set(
            item_type=self.item_type,
            added_by="USER",
            seller_profile=None,
            owner_user=self.user,
        )

        with patch(
            "listings.api_views.commands.user_create_itemset"
        ) as mock_cmd:
            mock_cmd.return_value = created_item
            request = self.factory.post(
                "/api/users/me/item-sets/", payload, format="json"
            )
            force_authenticate(request, user=self.user)
            response = view(request)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_cmd.assert_called_once()
        _, kwargs = mock_cmd.call_args
        self.assertEqual(kwargs["owner"], self.user)


class AdminItemSetApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        # IsAdmin wymaga is_superuser
        self.admin = create_user(
            email="admin@example.com",
            is_staff=True,
            is_superuser=True,
            role="ADMIN",
        )

    def test_non_admin_cannot_access_admin_list(self):
        user = create_user(email="user@example.com", role="EMPLOYEE", is_staff=False)
        view = AdminItemSetViewSet.as_view({"get": "list"})
        request = self.factory.get("/api/admin/item-sets/")
        force_authenticate(request, user=user)
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_for_user(self):
        owner = create_user(email="owner@example.com")
        item_type = create_item_type()
        view = AdminItemSetViewSet.as_view({"post": "create"})
        payload = {
            "set_name": "Admin created",
            "price": "20.00",
            "stock_quantity": 1,
            "condition": "NEW",
            "status": "AVAILABLE",
            "listing_type": "LISTING",
            "type": str(item_type.id),
            "owner_public_id": str(owner.public_id),
        }
        created_item = create_item_set(
            item_type=item_type,
            added_by="USER",
            seller_profile=None,
            owner_user=owner,
        )

        with patch(
            "listings.api_views.commands.user_create_itemset"
        ) as mock_cmd:
            mock_cmd.return_value = created_item
            request = self.factory.post(
                "/api/admin/item-sets/", payload, format="json"
            )
            force_authenticate(request, user=self.admin)
            response = view(request)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_cmd.assert_called_once()
        _, kwargs = mock_cmd.call_args
        self.assertEqual(kwargs["owner"], owner)

    def test_admin_destroy_uses_hard_delete_command(self):
        item = create_item_set()
        view = AdminItemSetViewSet.as_view({"delete": "destroy"})
        with patch(
            "listings.api_views.commands.hard_delete_itemset"
        ) as mock_cmd:
            request = self.factory.delete(f"/api/admin/item-sets/{item.public_id}/")
            force_authenticate(request, user=self.admin)
            response = view(request, public_id=str(item.public_id))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        mock_cmd.assert_called_once()
        _, kwargs = mock_cmd.call_args
        self.assertEqual(kwargs["itemset"].id, item.id)
