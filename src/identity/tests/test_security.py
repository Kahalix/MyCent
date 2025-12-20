from __future__ import annotations

from django.test import override_settings, TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from identity.models import SellerProfile
from identity.services import commands
from identity.services.exceptions import TokenInvalid
from .factories import (
    create_user,
    create_seller_profile,
    create_seller_bank_account,
    create_seller_membership,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class PublicSellerSecurityTests(APITestCase):
    def setUp(self):
        self.seller = create_seller_profile(company_name="Bezpieczny Sklep", slug="bezpieczny")

    def test_search_parameter_is_safe_against_injection_like_input(self):
        before = SellerProfile.objects.count()
        payload = {
            "search": "Bezpieczny'; DROP TABLE identity_sellerprofile;--"
        }
        resp = self.client.get("/api/public/sellers/", payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        after = SellerProfile.objects.count()
        self.assertEqual(before, after)


@override_settings(SECURE_SSL_REDIRECT=False)
class MyBankAccountsSecurityTests(APITestCase):
    def setUp(self):
        self.owner = create_user(email="owner-sec@example.com", role="OWNER")
        self.other = create_user(email="other-sec@example.com")
        self.seller = create_seller_profile(owner=self.owner)
        create_seller_bank_account(seller_profile=self.seller)

    def test_my_bank_accounts_auth_and_role_checks(self):
        resp = self.client.get("/api/sellers/mine/bank-accounts/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(user=self.other)
        resp2 = self.client.get("/api/sellers/mine/bank-accounts/")
        self.assertEqual(resp2.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(user=self.owner)
        resp3 = self.client.get("/api/sellers/mine/bank-accounts/")
        self.assertEqual(resp3.status_code, status.HTTP_200_OK)


@override_settings(SECURE_SSL_REDIRECT=False)
class SellerMembersSecurityTests(APITestCase):
    def setUp(self):
        self.owner = create_user(email="owner-mem@example.com", role="OWNER")
        self.manager = create_user(email="mgr-mem@example.com", role="EMPLOYEE")
        self.other = create_user(email="other-mem@example.com", role="EMPLOYEE")
        self.seller = create_seller_profile(owner=self.owner)
        create_seller_membership(
            seller_profile=self.seller,
            user=self.manager,
            role="MANAGER",
            is_active=True,
        )

    def test_list_members_requires_manage_permission(self):
        url = f"/api/sellers/{self.seller.public_id}/members/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(user=self.other)
        resp2 = self.client.get(url)
        self.assertEqual(resp2.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(user=self.manager)
        resp3 = self.client.get(url)
        self.assertEqual(resp3.status_code, status.HTTP_200_OK)


class CommandsSecurityTests(TestCase):
    def test_member_create_bank_account_requires_owner_membership(self):
        owner = create_user(email="own-sec@example.com", role="OWNER")
        seller = create_seller_profile(owner=owner)
        user = create_user(email="emp-sec@example.com", role="EMPLOYEE")
        create_seller_membership(
            seller_profile=seller,
            user=user,
            role="EMPLOYEE",
            is_active=True,
        )
        with self.assertRaises(TokenInvalid):
            commands.member_create_bank_account(
                user=user,
                seller_public_id=str(seller.public_id),
                data={
                    "iban": "PL00111111111111111",
                    "bank_name": "Bank",
                    "account_holder": "Holder",
                    "is_active": True,
                    "is_default": False,
                },
            )

    def test_add_member_denied_when_actor_cannot_manage(self):
        owner = create_user(email="own-sec2@example.com", role="OWNER")
        seller = create_seller_profile(owner=owner)
        actor = create_user(email="actor-sec@example.com", role="EMPLOYEE")
        target = create_user(email="target-sec@example.com", role="EMPLOYEE")
        with self.assertRaises(PermissionError):
            commands.add_member(
                actor=actor,
                seller=seller,
                target_user=target,
                role="EMPLOYEE",
            )
