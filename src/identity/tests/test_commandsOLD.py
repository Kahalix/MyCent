from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from unittest.mock import patch
from rest_framework_simplejwt.tokens import RefreshToken

from identity.services import commands
from identity.services.exceptions import (
    EmailAlreadyUsed,
    InvalidCredentials,
    AccountNotActive,
    TokenInvalid,
    RefreshMissing,
)
from identity.models import SellerProfile, SellerBankAccount, SellerMembership


class DummyRequest:
    def __init__(self):
        self.META = {}
        self.COOKIES = {}

    def build_absolute_uri(self, path):
        return "http://testserver" + path


User = get_user_model()


class CommandsAuthTests(TestCase):
    def test_register_user_creates_inactive_user_and_sends_email(self):
        request = DummyRequest()
        with patch("identity.services.commands._send_registration_confirmation_email") as mock_send:
            data = commands.register_user(
                request,
                email="NewUser@Example.com",
                password="Secret12345!",
                first_name="John",
                last_name="Doe",
            )
        self.assertEqual(data["message"], "Sprawdź e-mail w celu aktywacji.")
        user = User.objects.get(email="newuser@example.com")
        self.assertFalse(user.is_active)
        mock_send.assert_called_once()
        called_user = mock_send.call_args.kwargs["user"]
        self.assertEqual(called_user, user)

    def test_register_user_raises_when_email_taken(self):
        User.objects.create_user(email="taken@example.com", password="Secret12345!", first_name="A", last_name="B")
        request = DummyRequest()
        with self.assertRaises(EmailAlreadyUsed):
            commands.register_user(
                request,
                email="taken@example.com",
                password="Secret12345!",
                first_name="John",
                last_name="Doe",
            )

    def test_confirm_registration_activates_user(self):
        user = User.objects.create_user(email="user@example.com", password="Secret12345!", first_name="A", last_name="B")
        user.is_active = False
        user.save(update_fields=["is_active"])
        token = commands.issue_ephemeral(user, "EMAIL_CONFIRMATION", minutes=60)
        data = commands.confirm_registration(token=token)
        self.assertEqual(data["message"], "Konto aktywowane.")
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_confirm_registration_invalid_token_raises(self):
        with self.assertRaises(TokenInvalid):
            commands.confirm_registration(token="invalid-token")

    def test_login_user_success(self):
        user = User.objects.create_user(email="user@example.com", password="Secret12345!", first_name="A", last_name="B")
        request = DummyRequest()
        request.META["HTTP_USER_AGENT"] = "test-agent"
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        payload = commands.login_user(request, email="User@Example.com", password="Secret12345!")
        self.assertIn("access", payload)
        self.assertIn("refresh", payload)
        self.assertIn("user", payload)
        self.assertEqual(payload["user"]["email"], "user@example.com")

    def test_login_user_invalid_credentials_raise(self):
        User.objects.create_user(email="user@example.com", password="Secret12345!", first_name="A", last_name="B")
        request = DummyRequest()
        with self.assertRaises(InvalidCredentials):
            commands.login_user(request, email="user@example.com", password="WrongPass123!")

    def test_login_user_inactive_status_active_resends_activation(self):
        user = User.objects.create_user(email="user@example.com", password="Secret12345!", first_name="A", last_name="B")
        user.is_active = False
        user.user_status = "ACTIVE"
        user.save(update_fields=["is_active", "user_status"])
        request = DummyRequest()
        with patch("identity.services.commands._send_registration_confirmation_email") as mock_send:
            with self.assertRaises(AccountNotActive) as ctx:
                commands.login_user(request, email="user@example.com", password="Secret12345!")
        self.assertIn("Konto nie zostało jeszcze aktywowane", str(ctx.exception))
        mock_send.assert_called_once()

    def test_login_user_inactive_suspended_does_not_resend_activation(self):
        user = User.objects.create_user(email="user@example.com", password="Secret12345!", first_name="A", last_name="B")
        user.is_active = False
        user.user_status = "SUSPENDED"
        user.save(update_fields=["is_active", "user_status"])
        request = DummyRequest()
        with patch("identity.services.commands._send_registration_confirmation_email") as mock_send:
            with self.assertRaises(AccountNotActive) as ctx:
                commands.login_user(request, email="user@example.com", password="Secret12345!")
        self.assertIn("Konto jest nieaktywne lub zablokowane", str(ctx.exception))
        mock_send.assert_not_called()

    def test_refresh_tokens_rotates_refresh_and_persists_in_db(self):
        user = User.objects.create_user(email="user@example.com", password="Secret12345!", first_name="A", last_name="B")
        request = DummyRequest()
        request.META["HTTP_USER_AGENT"] = "test-agent"
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        old_refresh = str(RefreshToken.for_user(user))
        commands.save_refresh(user, old_refresh, data={"source": "test"})
        payload = commands.refresh_tokens(request, refresh_jwt=old_refresh)
        self.assertIn("access", payload)
        self.assertIn("refresh", payload)
        new_refresh = payload["refresh"]
        self.assertNotEqual(old_refresh, new_refresh)
        self.assertFalse(commands.exists_refresh(user, old_refresh))
        self.assertTrue(commands.exists_refresh(user, new_refresh))

    @override_settings(JWT_REFRESH_IN_COOKIE=False)
    def test_refresh_tokens_missing_raises(self):
        DummyRequest()
        request = DummyRequest()
        with self.assertRaises(RefreshMissing):
            commands.refresh_tokens(request, refresh_jwt=None)

    def test_reset_password_changes_password(self):
        user = User.objects.create_user(email="user@example.com", password="OldPass123!", first_name="A", last_name="B")
        token = commands.issue_ephemeral(user, "PASSWORD_RESET", minutes=30)
        commands.reset_password(token=token, new_password="NewPass123!")
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewPass123!"))

    def test_reset_password_invalid_token_raises(self):
        with self.assertRaises(TokenInvalid):
            commands.reset_password(token="invalid", new_password="NewPass123!")

    def test_forgot_password_returns_generic_message_and_sends_email_for_active_user(self):
        user = User.objects.create_user(email="user@example.com", password="x", first_name="A", last_name="B")
        request = DummyRequest()
        with patch("identity.services.commands.issue_ephemeral") as mock_issue, patch(
            "identity.services.commands.emails.send_templated_email"
        ) as mock_email:
            data = commands.forgot_password(request, email=user.email)
        self.assertEqual(data["message"], "Jeśli konto istnieje, wysłaliśmy instrukcje.")
        mock_issue.assert_called_once()
        mock_email.assert_called_once()

    def test_forgot_password_inactive_user_does_not_send_email(self):
        user = User.objects.create_user(email="user@example.com", password="x", first_name="A", last_name="B")
        user.is_active = False
        user.save(update_fields=["is_active"])
        request = DummyRequest()
        with patch("identity.services.commands.issue_ephemeral") as mock_issue, patch(
            "identity.services.commands.emails.send_templated_email"
        ) as mock_email:
            data = commands.forgot_password(request, email=user.email)
        self.assertEqual(data["message"], "Jeśli konto istnieje, wysłaliśmy instrukcje.")
        mock_issue.assert_not_called()
        mock_email.assert_not_called()

    def test_request_email_change_validates_uniqueness_and_sends_email(self):
        user = User.objects.create_user(email="user@example.com", password="x", first_name="A", last_name="B")
        User.objects.create_user(email="other@example.com", password="x", first_name="C", last_name="D")
        request = DummyRequest()
        with self.assertRaises(EmailAlreadyUsed):
            commands.request_email_change(request, user=user, new_email="other@example.com")
        with patch("identity.services.commands.issue_ephemeral") as mock_issue, patch(
            "identity.services.commands.emails.send_templated_email"
        ) as mock_email:
            data = commands.request_email_change(request, user=user, new_email="NewEmail@example.com")
        self.assertEqual(data["message"], "Wysłano link potwierdzający na nowy e-mail.")
        mock_issue.assert_called_once()
        mock_email.assert_called_once()

    def test_confirm_email_change_updates_email(self):
        user = User.objects.create_user(email="user@example.com", password="x", first_name="A", last_name="B")
        new_email = "new@example.com"
        token = commands.issue_ephemeral(user, "EMAIL_CHANGE", minutes=60, data={"new_email": new_email})
        data = commands.confirm_email_change(token=token)
        self.assertEqual(data["message"], "Email zmieniony.")
        user.refresh_from_db()
        self.assertEqual(user.email, new_email)

    def test_update_user_self_updates_fields(self):
        user = User.objects.create_user(email="user@example.com", password="x", first_name="", last_name="", phone_number="")
        result = commands.update_user_self(
            user=user,
            first_name="John",
            last_name="Doe",
            phone_number="+48123456789",
        )
        self.assertEqual(result["message"], "Zaktualizowano profil.")
        user.refresh_from_db()
        self.assertEqual(user.first_name, "John")
        self.assertEqual(user.last_name, "Doe")
        self.assertEqual(user.phone_number, "+48123456789")

    def test_change_password_success(self):
        user = User.objects.create_user(email="user@example.com", password="OldPass123!", first_name="A", last_name="B")
        with patch("identity.services.commands.delete_all_refreshes") as mock_delete:
            data = commands.change_password(
                user=user,
                old_password="OldPass123!",
                new_password="NewPass123!",
            )
        self.assertEqual(data["message"], "Hasło zmienione. Zaloguj się ponownie.")
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewPass123!"))
        mock_delete.assert_called_once_with(user)

    def test_change_password_wrong_old_raises(self):
        user = User.objects.create_user(email="user@example.com", password="OldPass123!", first_name="A", last_name="B")
        with self.assertRaises(InvalidCredentials):
            commands.change_password(
                user=user,
                old_password="WrongOld",
                new_password="NewPass123!",
            )


class CommandsAdminUserTests(TestCase):
    def test_admin_create_user_sets_fields(self):
        user = commands.admin_create_user(
            email="AdminUser@example.com",
            password="Secret12345!",
            first_name="Admin",
            last_name="User",
            role="MANAGER",
            user_status="ACTIVE",
            is_staff=True,
            is_active=True,
        )
        self.assertEqual(user.email, "adminuser@example.com")
        self.assertEqual(user.first_name, "Admin")
        self.assertEqual(user.role, "MANAGER")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_active)

    def test_admin_create_user_raises_if_email_taken(self):
        User.objects.create_user(email="taken@example.com", password="x", first_name="A", last_name="B")
        with self.assertRaises(EmailAlreadyUsed):
            commands.admin_create_user(
                email="taken@example.com",
                password="Secret12345!",
                first_name="Admin",
                last_name="User",
            )

    def test_admin_update_user_updates_allowed_fields(self):
        user = User.objects.create_user(email="user@example.com", password="x", first_name="Old", last_name="Name")
        updated = commands.admin_update_user(
            public_id=str(user.public_id),
            first_name="New",
            last_name="Name",
            phone_number="+48123456789",
            role="EMPLOYEE",
            user_status="INACTIVE",
            is_staff=True,
            is_active=False,
        )
        self.assertEqual(updated.first_name, "New")
        self.assertEqual(updated.phone_number, "+48123456789")
        self.assertEqual(updated.role, "EMPLOYEE")
        self.assertEqual(updated.user_status, "INACTIVE")
        self.assertTrue(updated.is_staff)
        self.assertFalse(updated.is_active)

    def test_admin_delete_user_deletes_user(self):
        user = User.objects.create_user(email="user@example.com", password="x", first_name="A", last_name="B")
        commands.admin_delete_user(public_id=str(user.public_id))
        self.assertFalse(User.objects.filter(id=user.id).exists())

    def test_admin_set_user_status_maps_is_active_and_revokes_tokens(self):
        user = User.objects.create_user(email="user@example.com", password="x", first_name="A", last_name="B")
        with patch("identity.services.commands._revoke_all_tokens") as mock_revoke:
            updated = commands.admin_set_user_status(public_id=str(user.public_id), user_status="SUSPENDED", is_active=None)
        self.assertEqual(updated.user_status, "SUSPENDED")
        self.assertFalse(updated.is_active)
        mock_revoke.assert_called_once_with(updated)

    def test_admin_set_user_status_explicit_is_active_preserved(self):
        user = User.objects.create_user(email="user@example.com", password="x", first_name="A", last_name="B")
        updated = commands.admin_set_user_status(public_id=str(user.public_id), user_status="SUSPENDED", is_active=True)
        self.assertEqual(updated.user_status, "SUSPENDED")
        self.assertTrue(updated.is_active)


class CommandsSellerTests(TestCase):
    def create_owner(self, email="owner@example.com"):
        return User.objects.create_user(email=email, password="x", first_name="Owner", last_name="User")

    def test_create_seller_for_owner_creates_profile_and_membership(self):
        owner = self.create_owner()
        data = {
            "company_name": "Test Company",
            "legal_name": "",
            "slug": "test-company",
            "description": "",
            "contact_email": "",
            "contact_phone": "",
            "website_url": "",
        }
        seller = commands.create_seller_for_owner(owner=owner, data=data)
        self.assertEqual(seller.owner, owner)
        self.assertTrue(
            SellerMembership.objects.filter(
                seller_profile=seller, user=owner, role="OWNER", is_active=True
            ).exists()
        )

    def test_create_seller_for_owner_raises_when_already_exists(self):
        owner = self.create_owner()
        SellerProfile.objects.create(
            owner=owner,
            company_name="Existing",
            legal_name="",
            slug="existing",
            description="",
            contact_email="",
            contact_phone="",
            website_url="",
        )
        data = {
            "company_name": "Another",
            "legal_name": "",
            "slug": "another",
            "description": "",
            "contact_email": "",
            "contact_phone": "",
            "website_url": "",
        }
        with self.assertRaises(TokenInvalid):
            commands.create_seller_for_owner(owner=owner, data=data)

    def test_update_seller_owned_updates_allowed_fields(self):
        owner = self.create_owner()
        seller = SellerProfile.objects.create(
            owner=owner,
            company_name="Old",
            legal_name="Old Legal",
            slug="seller",
            description="Old",
            contact_email="old@example.com",
            contact_phone="123",
            website_url="http://old.example.com",
        )
        data = {
            "company_name": "New",
            "legal_name": "New Legal",
            "description": "New",
            "contact_email": "new@example.com",
            "contact_phone": "456",
            "website_url": "http://new.example.com",
        }
        updated = commands.update_seller_owned(seller=seller, data=data)
        self.assertEqual(updated.company_name, "New")
        self.assertEqual(updated.legal_name, "New Legal")
        self.assertEqual(updated.contact_email, "new@example.com")

    def test_owner_create_bank_account_sets_default(self):
        owner = self.create_owner()
        seller = commands.create_seller_for_owner(
            owner=owner,
            data={
                "company_name": "Test Company",
                "legal_name": "",
                "slug": "test-company",
                "description": "",
                "contact_email": "",
                "contact_phone": "",
                "website_url": "",
            },
        )
        acc = commands.owner_create_bank_account(
            owner=owner,
            data={
                "iban": "PL30102010260000042270201111",
                "bank_name": "Bank",
                "account_holder": "Holder",
                "is_active": True,
                "is_default": True,
            },
        )
        self.assertEqual(acc.seller_profile, seller)
        self.assertTrue(acc.is_default)

    def test_owner_cannot_manage_foreign_bank_account(self):
        owner = self.create_owner("owner1@example.com")
        foreign_owner = self.create_owner("owner2@example.com")
        foreign_seller = commands.create_seller_for_owner(
            owner=foreign_owner,
            data={
                "company_name": "Foreign",
                "legal_name": "",
                "slug": "foreign",
                "description": "",
                "contact_email": "",
                "contact_phone": "",
                "website_url": "",
            },
        )
        acc = SellerBankAccount.objects.create(
            seller_profile=foreign_seller,
            iban="PL30102010260000042270202222",
            bank_name="Bank",
            account_holder="Holder",
            is_active=True,
            is_default=False,
        )
        with self.assertRaises(TokenInvalid):
            commands.owner_update_bank_account(owner=owner, public_id=str(acc.public_id), data={"bank_name": "X"})
        with self.assertRaises(TokenInvalid):
            commands.owner_delete_bank_account(owner=owner, public_id=str(acc.public_id))
        with self.assertRaises(TokenInvalid):
            commands.owner_set_default_bank_account(owner=owner, public_id=str(acc.public_id))


class CommandsMembershipTests(TestCase):
    def create_seller_with_owner(self):
        owner = User.objects.create_user(email="owner@example.com", password="x", first_name="Owner", last_name="User")
        seller = SellerProfile.objects.create(
            owner=owner,
            company_name="Shop",
            legal_name="",
            slug="shop",
            description="",
            contact_email="",
            contact_phone="",
            website_url="",
        )
        return owner, seller

    def test_owner_can_add_employee_member(self):
        owner, seller = self.create_seller_with_owner()
        target = User.objects.create_user(
            email="emp@example.com",
            password="x",
            first_name="Emp",
            last_name="User",
            role="EMPLOYEE",
        )
        member = commands.add_member(actor=owner, seller=seller, target_user=target, role="EMPLOYEE")
        self.assertEqual(member.role, "EMPLOYEE")
        self.assertTrue(member.is_active)

    def test_manager_cannot_add_manager_or_moderator(self):
        owner, seller = self.create_seller_with_owner()
        manager = User.objects.create_user(
            email="mgr@example.com",
            password="x",
            first_name="Mgr",
            last_name="User",
            role="EMPLOYEE",
        )
        SellerMembership.objects.create(seller_profile=seller, user=manager, role="MANAGER", is_active=True)
        target = User.objects.create_user(
            email="emp@example.com",
            password="x",
            first_name="Emp",
            last_name="User",
            role="EMPLOYEE",
        )
        with self.assertRaises(PermissionError):
            commands.add_member(actor=manager, seller=seller, target_user=target, role="MANAGER")
        with self.assertRaises(PermissionError):
            commands.add_member(actor=manager, seller=seller, target_user=target, role="MODERATOR")

    def test_add_member_rejects_client_role(self):
        owner, seller = self.create_seller_with_owner()
        target = User.objects.create_user(
            email="client@example.com",
            password="x",
            first_name="Cli",
            last_name="User",
            role="CLIENT",
        )
        with self.assertRaises(TokenInvalid):
            commands.add_member(actor=owner, seller=seller, target_user=target, role="EMPLOYEE")

    def test_update_member_role_enforces_rules(self):
        owner, seller = self.create_seller_with_owner()
        manager_user = User.objects.create_user(
            email="mgr@example.com",
            password="x",
            first_name="Mgr",
            last_name="User",
            role="EMPLOYEE",
        )
        manager_membership = SellerMembership.objects.create(
            seller_profile=seller,
            user=manager_user,
            role="MANAGER",
            is_active=True,
        )
        employee_user = User.objects.create_user(
            email="emp@example.com",
            password="x",
            first_name="Emp",
            last_name="User",
            role="EMPLOYEE",
        )
        employee_membership = SellerMembership.objects.create(
            seller_profile=seller,
            user=employee_user,
            role="EMPLOYEE",
            is_active=True,
        )
        with self.assertRaises(PermissionError):
            commands.update_member_role(actor=manager_user, seller=seller, member=manager_membership, new_role="EMPLOYEE")
        updated = commands.update_member_role(actor=owner, seller=seller, member=employee_membership, new_role="MODERATOR")
        self.assertEqual(updated.role, "MODERATOR")

    def test_remove_member_marks_inactive_and_respects_permissions(self):
        owner, seller = self.create_seller_with_owner()
        manager_user = User.objects.create_user(
            email="mgr@example.com",
            password="x",
            first_name="Mgr",
            last_name="User",
            role="EMPLOYEE",
        )
        SellerMembership.objects.create(seller_profile=seller, user=manager_user, role="MANAGER", is_active=True)
        mod_user = User.objects.create_user(
            email="mod@example.com",
            password="x",
            first_name="Mod",
            last_name="User",
            role="EMPLOYEE",
        )
        mod_membership = SellerMembership.objects.create(
            seller_profile=seller,
            user=mod_user,
            role="MODERATOR",
            is_active=True,
        )
        emp_user = User.objects.create_user(
            email="emp@example.com",
            password="x",
            first_name="Emp",
            last_name="User",
            role="EMPLOYEE",
        )
        emp_membership = SellerMembership.objects.create(
            seller_profile=seller,
            user=emp_user,
            role="EMPLOYEE",
            is_active=True,
        )
        with self.assertRaises(PermissionError):
            commands.remove_member(actor=manager_user, seller=seller, member=mod_membership)
        commands.remove_member(actor=manager_user, seller=seller, member=emp_membership)
        emp_membership.refresh_from_db()
        self.assertFalse(emp_membership.is_active)
