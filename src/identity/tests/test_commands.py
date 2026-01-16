from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from identity.models import User, SellerBankAccount, SellerMembership, UserToken
from identity.services import commands
from identity.services import queries
from identity.services.exceptions import (
    EmailAlreadyUsed,
    InvalidCredentials,
    AccountNotActive,
    TokenInvalid,
    RefreshMissing,
    RefreshInvalid,
    RefreshNotRecognized,
)
from .factories import (
    create_user,
    create_seller_profile,
    create_seller_membership,
    issue_ephemeral_token,
)


@override_settings(JWT_REFRESH_IN_COOKIE=False)
class AuthCommandsTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_register_user_creates_inactive_user(self):
        request = self.factory.post("/api/auth/register/", {})
        data = commands.register_user(
            request,
            email="new@example.com",
            password="StrongPass123!",
            first_name="Jan",
            last_name="Kowalski",
        )
        self.assertIn("message", data)
        user = User.objects.get(email="new@example.com")
        self.assertFalse(user.is_active)
        self.assertEqual(user.first_name, "Jan")
        self.assertEqual(user.last_name, "Kowalski")

    def test_register_user_existing_email_raises(self):
        create_user(email="dup@example.com")
        request = self.factory.post("/api/auth/register/", {})
        with self.assertRaises(EmailAlreadyUsed):
            commands.register_user(
                request,
                email="dup@example.com",
                password="StrongPass123!",
                first_name="A",
                last_name="B",
            )

    def test_confirm_registration_activates_user(self):
        user = create_user(email="conf@example.com", is_active=False)
        raw = issue_ephemeral_token(user=user, typ="EMAIL_CONFIRMATION")
        data = commands.confirm_registration(token=raw)
        self.assertEqual(data["message"], "Konto aktywowane.")
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_confirm_registration_invalid_token_raises(self):
        with self.assertRaises(TokenInvalid):
            commands.confirm_registration(token="invalid-token")

    def test_login_user_success_returns_payload_and_saves_refresh(self):
        user = create_user(email="login@example.com")
        request = self.factory.post(
            "/api/auth/login/",
            {},
            HTTP_USER_AGENT="ua",
            REMOTE_ADDR="127.0.0.1",
        )
        payload, refresh_jwt = commands.login_user(
            request,
            email="login@example.com",
            password="pass1234",
        )
        self.assertIn("access", payload)
        self.assertIn("user", payload)
        self.assertEqual(payload["user"]["email"], "login@example.com")
        self.assertTrue(UserToken.exists_refresh(user, refresh_jwt))

    def test_login_user_invalid_credentials_raises(self):
        create_user(email="bad@example.com")
        request = self.factory.post("/api/auth/login/", {})
        with self.assertRaises(InvalidCredentials):
            commands.login_user(
                request,
                email="bad@example.com",
                password="wrong",
            )

    def test_login_inactive_status_active_raises_account_not_active(self):
        create_user(
            email="inactive@example.com",
            is_active=False,
            user_status="ACTIVE",
        )
        request = self.factory.post("/api/auth/login/", {})
        with self.assertRaises(AccountNotActive):
            commands.login_user(
                request,
                email="inactive@example.com",
                password="pass1234",
            )

    def test_refresh_tokens_success_rotates_refresh(self):
        user = create_user(email="refresh@example.com")
        request = self.factory.post(
            "/api/auth/refresh/",
            {},
            HTTP_USER_AGENT="ua2",
            REMOTE_ADDR="10.0.0.1",
        )
        original = RefreshToken.for_user(user)
        UserToken.save_refresh(user, str(original))

        payload, new_refresh_jwt = commands.refresh_tokens(request, refresh_jwt=str(original))

        self.assertIn("access", payload)
        self.assertNotEqual(new_refresh_jwt, str(original))
        self.assertFalse(UserToken.exists_refresh(user, str(original)))
        self.assertTrue(UserToken.exists_refresh(user, new_refresh_jwt))

    def test_refresh_tokens_missing_raises(self):
        request = self.factory.post("/api/auth/refresh/", {})
        with self.assertRaises(RefreshMissing):
            commands.refresh_tokens(request, refresh_jwt=None)

    def test_refresh_tokens_invalid_string_raises(self):
        user = create_user(email="inv@example.com")
        self.assertIsNotNone(user)
        request = self.factory.post("/api/auth/refresh/", {})
        with self.assertRaises(RefreshInvalid):
            commands.refresh_tokens(request, refresh_jwt="not-a-token")

    def test_refresh_tokens_not_recognized_raises(self):
        user = create_user(email="nr@example.com")
        token = RefreshToken.for_user(user)
        request = self.factory.post("/api/auth/refresh/", {})
        with self.assertRaises(RefreshNotRecognized):
            commands.refresh_tokens(request, refresh_jwt=str(token))

    def test_logout_user_deletes_refreshes_and_blacklists_tokens(self):
        user = create_user(email="logout@example.com")
        refresh = RefreshToken.for_user(user)
        UserToken.save_refresh(user, str(refresh))
        request = self.factory.post("/api/auth/logout/", {})
        commands.logout_user(request, user=user)
        self.assertFalse(UserToken.objects.filter(user=user, type="REFRESH_TOKEN").exists())
        self.assertTrue(BlacklistedToken.objects.filter(token__user=user).exists())

    def test_reset_password_changes_password(self):
        user = create_user(email="reset@example.com")
        raw = issue_ephemeral_token(user=user, typ="PASSWORD_RESET")
        commands.reset_password(token=raw, new_password="NewPass123!")
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewPass123!"))

    def test_reset_password_invalid_token_raises(self):
        with self.assertRaises(TokenInvalid):
            commands.reset_password(token="invalid", new_password="NewPass123!")

    def test_forgot_password_sends_email_for_active_user(self):
        user = create_user(email="user@example.com")
        request = self.factory.post("/api/auth/forgot-password/", {})
        with patch("identity.services.commands.emails.send_templated_email") as mock_email:
            data = commands.forgot_password(request, email=user.email)
        self.assertIn("message", data)
        self.assertTrue(UserToken.objects.filter(user=user, type="PASSWORD_RESET").exists())
        mock_email.assert_called_once()

    def test_forgot_password_does_not_send_email_for_inactive_user(self):
        user = create_user(email="user@example.com", is_active=False)
        request = self.factory.post("/api/auth/forgot-password/", {})
        with patch("identity.services.commands.emails.send_templated_email") as mock_email:
            data = commands.forgot_password(request, email=user.email)
        self.assertIn("message", data)
        self.assertFalse(UserToken.objects.filter(user=user, type="PASSWORD_RESET").exists())
        mock_email.assert_not_called()

    def test_request_email_change_validates_uniqueness_and_sends_email(self):
        user = create_user(email="user@example.com")
        other = create_user(email="other@example.com")
        request = self.factory.post("/api/auth/request-email-change/", {})
        with self.assertRaises(EmailAlreadyUsed):
            commands.request_email_change(
                request,
                user=user,
                new_email=other.email,
            )
        with patch("identity.services.commands.emails.send_templated_email") as mock_email:
            data = commands.request_email_change(
                request,
                user=user,
                new_email="NewEmail@example.com",
            )
        self.assertIn("message", data)
        mock_email.assert_called_once()

    def test_confirm_email_change_updates_email(self):
        user = create_user(email="user@example.com")
        new_email = "new@example.com"
        raw = issue_ephemeral_token(
            user=user,
            typ="EMAIL_CHANGE",
            data={"new_email": new_email},
        )
        data = commands.confirm_email_change(token=raw)
        self.assertIn("message", data)
        user.refresh_from_db()
        self.assertEqual(user.email, new_email)


class UserCommandsTests(TestCase):
    def test_update_user_self_changes_fields(self):
        user = create_user(
            email="self@example.com",
            first_name="Old",
            last_name="Name",
            phone_number="123",
        )
        result = commands.update_user_self(
            user=user,
            first_name="New",
            last_name="Surname",
            phone_number="555",
        )
        self.assertIn("message", result)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "Surname")
        self.assertEqual(user.phone_number, "555")

    def test_change_password_with_wrong_old_raises(self):
        user = create_user(email="cp@example.com")
        with self.assertRaises(InvalidCredentials):
            commands.change_password(
                user=user,
                old_password="wrong",
                new_password="NewStrongPass123!",
            )

    def test_change_password_success_deletes_refreshes(self):
        user = create_user(email="cp2@example.com")
        UserToken.save_refresh(user, "old-refresh")
        commands.change_password(
            user=user,
            old_password="pass1234",
            new_password="NewStrongPass123!",
        )
        self.assertFalse(UserToken.objects.filter(user=user, type="REFRESH_TOKEN").exists())

    def test_admin_create_update_delete_user(self):
        u = commands.admin_create_user(
            email="admin-created@example.com",
            password="StrongPass123!",
            first_name="AA",
            last_name="BB",
            role="EMPLOYEE",
            user_status="ACTIVE",
            is_staff=True,
            is_active=True,
        )
        self.assertTrue(u.is_staff)
        self.assertEqual(u.role, "EMPLOYEE")
        with self.assertRaises(EmailAlreadyUsed):
            commands.admin_create_user(
                email="admin-created@example.com",
                password="StrongPass123!",
                first_name="X",
                last_name="Y",
            )
        updated = commands.admin_update_user(
            public_id=str(u.public_id),
            first_name="NewName",
            is_active=False,
        )
        self.assertEqual(updated.first_name, "NewName")
        self.assertFalse(updated.is_active)
        commands.admin_delete_user(public_id=str(u.public_id))
        self.assertFalse(User.objects.filter(email="admin-created@example.com").exists())

    def test_admin_set_user_status_deactivates_and_revokes_tokens(self):
        user = create_user(email="status@example.com")
        refresh = RefreshToken.for_user(user)
        UserToken.save_refresh(user, str(refresh))
        commands.admin_set_user_status(
            public_id=str(user.public_id),
            user_status="SUSPENDED",
            is_active=None,
        )
        user.refresh_from_db()
        self.assertEqual(user.user_status, "SUSPENDED")
        self.assertFalse(user.is_active)
        self.assertFalse(UserToken.objects.filter(user=user, type="REFRESH_TOKEN").exists())
        self.assertTrue(BlacklistedToken.objects.filter(token__user=user).exists())


class SellerCommandsTests(TestCase):
    def test_create_seller_for_owner_creates_profile_and_membership(self):
        owner = create_user(email="owner@example.com", role="OWNER")
        data = {
            "company_name": "Moja Firma",
            "legal_name": "",
            "slug": "moja-firma",
            "description": "",
            "contact_email": "",
            "contact_phone": "",
            "website_url": "",
        }
        sp = commands.create_seller_for_owner(owner=owner, data=data)
        self.assertEqual(sp.owner_id, owner.id)
        membership = SellerMembership.objects.filter(
            seller_profile=sp,
            user=owner,
            role="OWNER",
            is_active=True,
        ).first()
        self.assertIsNotNone(membership)

    def test_create_seller_for_owner_when_exists_raises(self):
        owner = create_user(email="owner2@example.com", role="OWNER")
        create_seller_profile(owner=owner)
        with self.assertRaises(TokenInvalid):
            commands.create_seller_for_owner(
                owner=owner,
                data={
                    "company_name": "Inna",
                    "legal_name": "",
                    "slug": "inna",
                    "description": "",
                    "contact_email": "",
                    "contact_phone": "",
                    "website_url": "",
                },
            )

    def test_update_seller_owned_updates_allowed_fields(self):
        owner = create_user(email="owner3@example.com", role="OWNER")
        sp = create_seller_profile(owner=owner, company_name="Old", slug="old-slug")
        updated = commands.update_seller_owned(
            seller=sp,
            data={"company_name": "New Name", "description": "Desc"},
        )
        self.assertEqual(updated.company_name, "New Name")
        self.assertEqual(updated.description, "Desc")


class BankAccountCommandsTests(TestCase):
    def test_owner_bank_account_crud_and_default(self):
        owner = create_user(email="bank-owner@example.com", role="OWNER")
        seller = create_seller_profile(owner=owner)
        acc = commands.owner_create_bank_account(
            owner=owner,
            data={
                "iban": "PL00123456789012345",
                "bank_name": "Bank",
                "account_holder": "Holder",
                "is_active": True,
                "is_default": True,
            },
        )
        self.assertEqual(acc.seller_profile_id, seller.id)
        self.assertTrue(acc.is_default)
        updated = commands.owner_update_bank_account(
            owner=owner,
            public_id=str(acc.public_id),
            data={"bank_name": "NewBank"},
        )
        self.assertEqual(updated.bank_name, "NewBank")
        acc2 = commands.owner_create_bank_account(
            owner=owner,
            data={
                "iban": "PL00999999999999999",
                "bank_name": "B2",
                "account_holder": "H2",
                "is_active": True,
                "is_default": False,
            },
        )
        commands.owner_set_default_bank_account(
            owner=owner,
            public_id=str(acc2.public_id),
        )
        acc.refresh_from_db()
        acc2.refresh_from_db()
        self.assertFalse(acc.is_default)
        self.assertTrue(acc2.is_default)
        commands.owner_delete_bank_account(
            owner=owner,
            public_id=str(acc2.public_id),
        )
        self.assertFalse(SellerBankAccount.objects.filter(public_id=acc2.public_id).exists())

    def test_member_bank_account_requires_member_with_owner_role(self):
        owner = create_user(email="shopowner@example.com", role="OWNER")
        seller = create_seller_profile(owner=owner)
        member = create_user(email="member@example.com", role="EMPLOYEE")
        create_seller_membership(
            seller_profile=seller,
            user=member,
            role="EMPLOYEE",
            is_active=True,
        )
        with self.assertRaises(TokenInvalid):
            commands.member_create_bank_account(
                user=member,
                seller_public_id=str(seller.public_id),
                data={
                    "iban": "PL00333333333333333",
                    "bank_name": "Bank",
                    "account_holder": "Holder",
                    "is_active": True,
                    "is_default": False,
                },
            )


class MembershipCommandsTests(TestCase):
    def test_add_member_owner_can_add_non_client_and_forbids_owner_role(self):
        owner = create_user(email="own@example.com", role="OWNER")
        seller = create_seller_profile(owner=owner)
        target_emp = create_user(email="emp@example.com", role="EMPLOYEE")
        m = commands.add_member(
            actor=owner,
            seller=seller,
            target_user=target_emp,
            role="EMPLOYEE",
        )
        self.assertEqual(m.role, "EMPLOYEE")
        client = create_user(email="client@example.com", role="CLIENT")
        with self.assertRaises(TokenInvalid):
            commands.add_member(
                actor=owner,
                seller=seller,
                target_user=client,
                role="EMPLOYEE",
            )
        other = create_user(email="other@example.com", role="EMPLOYEE")
        with self.assertRaises(TokenInvalid):
            commands.add_member(
                actor=owner,
                seller=seller,
                target_user=other,
                role="OWNER",
            )

    def test_manager_add_member_and_update_role_constraints(self):
        owner = create_user(email="own2@example.com", role="OWNER")
        seller = create_seller_profile(owner=owner)
        manager_user = create_user(email="mgr@example.com", role="EMPLOYEE")
        emp_user = create_user(email="emp2@example.com", role="EMPLOYEE")
        create_seller_membership(
            seller_profile=seller,
            user=manager_user,
            role="MANAGER",
            is_active=True,
        )
        m = commands.add_member(
            actor=manager_user,
            seller=seller,
            target_user=emp_user,
            role="EMPLOYEE",
        )
        self.assertEqual(m.role, "EMPLOYEE")
        with self.assertRaises(PermissionError):
            commands.add_member(
                actor=manager_user,
                seller=seller,
                target_user=create_user(email="mod@example.com", role="EMPLOYEE"),
                role="MODERATOR",
            )
        member = queries.get_membership_by_public_id(str(m.public_id))
        with self.assertRaises(PermissionError):
            commands.update_member_role(
                actor=manager_user,
                seller=seller,
                member=member,
                new_role="MODERATOR",
            )

    def test_remove_member_marks_inactive_and_respects_permissions(self):
        owner = create_user(email="own3@example.com", role="OWNER")
        seller = create_seller_profile(owner=owner)
        manager = create_user(email="mgr2@example.com", role="EMPLOYEE")
        emp = create_user(email="emp3@example.com", role="EMPLOYEE")
        create_seller_membership(
            seller_profile=seller,
            user=manager,
            role="MANAGER",
            is_active=True,
        )
        mem_emp = create_seller_membership(
            seller_profile=seller,
            user=emp,
            role="EMPLOYEE",
            is_active=True,
        )
        commands.remove_member(actor=manager, seller=seller, member=mem_emp)
        mem_emp.refresh_from_db()
        self.assertFalse(mem_emp.is_active)
        owner_membership = SellerMembership.objects.filter(
            seller_profile=seller,
            user=owner,
        ).first()
        self.assertIsNotNone(owner_membership)
        with self.assertRaises(TokenInvalid):
            commands.remove_member(
                actor=owner,
                seller=seller,
                member=owner_membership,
            )
