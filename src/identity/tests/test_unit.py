from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from identity.services import commands
from identity.services.exceptions import (
    EmailAlreadyUsed,
    InvalidCredentials,
    AccountNotActive,
    TokenInvalid,
    RefreshMissing,
    RefreshInvalid,
    RefreshNotRecognized,
)


class UserTokenHelpersUnitTests(SimpleTestCase):
    def test_sha256_is_stable(self):
        from identity.models import UserToken

        self.assertEqual(
            UserToken._sha256("abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )


class AuthCommandsUnitTests(SimpleTestCase):
    def _request(self, *, ua: str = "ua", ip: str = "127.0.0.1", cookies: dict | None = None):
        return SimpleNamespace(
            META={"HTTP_USER_AGENT": ua, "REMOTE_ADDR": ip},
            COOKIES=cookies or {},
            build_absolute_uri=lambda x: f"https://example.com{x}",
        )

    @patch("identity.services.commands._send_registration_confirmation_email")
    @patch("identity.services.commands.create_user")
    @patch("identity.services.commands.is_email_taken_ci")
    def test_register_user_creates_inactive_user_and_sends_confirmation(
        self,
        mock_taken,
        mock_create_user,
        mock_send_confirm,
    ):
        mock_taken.return_value = False
        created = SimpleNamespace(id=1, email="new@example.com")
        mock_create_user.return_value = created

        req = self._request()
        out = commands.register_user(
            req,
            email="New@Example.com",
            password="StrongPass123!",
            first_name="Jan",
            last_name="Kowalski",
        )

        self.assertIn("message", out)
        mock_taken.assert_called_once_with("new@example.com")

        args, kwargs = mock_create_user.call_args
        self.assertEqual(args[0], "new@example.com")
        self.assertEqual(args[1], "StrongPass123!")
        self.assertEqual(args[2], "Jan")
        self.assertEqual(args[3], "Kowalski")
        self.assertEqual(kwargs["active"], False)

        mock_send_confirm.assert_called_once_with(req, user=created, hours_valid=24)

    @patch("identity.services.commands.create_user")
    @patch("identity.services.commands.is_email_taken_ci")
    def test_register_user_existing_email_raises(self, mock_taken, mock_create_user):
        mock_taken.return_value = True
        req = self._request()
        with self.assertRaises(EmailAlreadyUsed):
            commands.register_user(
                req,
                email="dup@example.com",
                password="StrongPass123!",
                first_name="A",
                last_name="B",
            )
        mock_create_user.assert_not_called()

    @patch("identity.services.commands.consume_ephemeral")
    def test_confirm_registration_invalid_token_raises(self, mock_consume):
        mock_consume.return_value = None
        with self.assertRaises(TokenInvalid):
            commands.confirm_registration(token="bad")
        mock_consume.assert_called_once_with("bad", "EMAIL_CONFIRMATION")

    @patch("identity.services.commands.consume_ephemeral")
    def test_confirm_registration_activates_user(self, mock_consume):
        user = SimpleNamespace(is_active=False, save=MagicMock())
        tok = SimpleNamespace(user=user)
        mock_consume.return_value = tok

        out = commands.confirm_registration(token="raw")

        self.assertEqual(out["message"], "Konto aktywowane.")
        self.assertTrue(user.is_active)
        user.save.assert_called_once_with(update_fields=["is_active"])

    @patch("identity.services.commands._auth_payload")
    @patch("identity.services.commands.save_refresh")
    @patch("identity.services.commands.RefreshToken")
    @patch("identity.services.repositories.find_user_by_email_ci")
    def test_login_user_success_saves_refresh_and_returns_payload(
        self,
        mock_find,
        mock_refresh_cls,
        mock_save_refresh,
        mock_payload,
    ):
        user = SimpleNamespace(
            id=10,
            email="login@example.com",
            is_active=True,
            user_status="ACTIVE",
            check_password=MagicMock(return_value=True),
        )
        mock_find.return_value = user

        refresh_obj = SimpleNamespace()
        mock_refresh_cls.for_user.return_value = refresh_obj

        mock_payload.return_value = {"access": "A", "refresh": "R", "user": {"email": "login@example.com"}}

        req = self._request(ua="ua1", ip="10.0.0.1")
        out = commands.login_user(req, email="LOGIN@EXAMPLE.COM", password="pass")

        self.assertEqual(out["refresh"], "R")
        mock_payload.assert_called_once_with(user, refresh_obj)

        args, kwargs = mock_save_refresh.call_args
        self.assertIs(args[0], user)
        self.assertEqual(args[1], "R")
        self.assertEqual(kwargs["data"]["ua"], "ua1")
        self.assertEqual(kwargs["data"]["ip"], "10.0.0.1")

    @patch("identity.services.commands._send_registration_confirmation_email")
    @patch("identity.services.repositories.find_user_by_email_ci")
    def test_login_user_inactive_active_status_resends_confirmation_and_raises(
        self,
        mock_find,
        mock_send_confirm,
    ):
        user = SimpleNamespace(
            id=10,
            email="inactive@example.com",
            is_active=False,
            user_status="ACTIVE",
            check_password=MagicMock(return_value=True),
        )
        mock_find.return_value = user

        req = self._request()
        with self.assertRaises(AccountNotActive):
            commands.login_user(req, email="inactive@example.com", password="pass")

        mock_send_confirm.assert_called_once()

    @patch("identity.services.commands._send_registration_confirmation_email")
    @patch("identity.services.repositories.find_user_by_email_ci")
    def test_login_user_inactive_suspended_raises_without_resend(self, mock_find, mock_send_confirm):
        user = SimpleNamespace(
            id=10,
            email="inactive@example.com",
            is_active=False,
            user_status="SUSPENDED",
            check_password=MagicMock(return_value=True),
        )
        mock_find.return_value = user

        req = self._request()
        with self.assertRaises(AccountNotActive):
            commands.login_user(req, email="inactive@example.com", password="pass")

        mock_send_confirm.assert_not_called()

    @patch("identity.services.repositories.find_user_by_email_ci")
    def test_login_user_invalid_credentials_raises(self, mock_find):
        user = SimpleNamespace(
            id=10,
            email="x@example.com",
            is_active=True,
            user_status="ACTIVE",
            check_password=MagicMock(return_value=False),
        )
        mock_find.return_value = user

        req = self._request()
        with self.assertRaises(InvalidCredentials):
            commands.login_user(req, email="x@example.com", password="bad")


class RefreshAndRevokeUnitTests(SimpleTestCase):
    def _request(self, *, ua: str = "ua", ip: str = "127.0.0.1", cookies: dict | None = None):
        return SimpleNamespace(
            META={"HTTP_USER_AGENT": ua, "REMOTE_ADDR": ip},
            COOKIES=cookies or {},
        )

    @override_settings(JWT_REFRESH_IN_COOKIE=False)
    def test_refresh_tokens_missing_raises(self):
        req = self._request()
        with self.assertRaises(RefreshMissing):
            commands.refresh_tokens(req, refresh_jwt=None)

    @override_settings(JWT_REFRESH_IN_COOKIE=False)
    @patch("identity.services.commands.RefreshToken")
    def test_refresh_tokens_invalid_string_raises(self, mock_refresh_cls):
        mock_refresh_cls.side_effect = Exception("bad token")
        req = self._request()
        with self.assertRaises(RefreshInvalid):
            commands.refresh_tokens(req, refresh_jwt="not-a-token")

    @override_settings(JWT_REFRESH_IN_COOKIE=False)
    @patch("identity.services.commands._auth_payload")
    @patch("identity.services.commands.save_refresh")
    @patch("identity.services.commands.delete_refresh")
    @patch("identity.services.commands.exists_refresh")
    @patch("identity.services.commands.get_user_by_id")
    @patch("identity.services.commands.RefreshToken")
    def test_refresh_tokens_success_rotates_refresh(
        self,
        mock_refresh_cls,
        mock_get_user,
        mock_exists,
        mock_delete,
        mock_save,
        mock_payload,
    ):
        def _old_getitem(k):
            if k == "user_id":
                return 99
            raise KeyError(k)

        old = MagicMock()
        old.__getitem__.side_effect = _old_getitem
        mock_refresh_cls.side_effect = lambda raw: old

        class DummyRefresh:
            def __init__(self, s: str):
                self.s = s

            def __str__(self) -> str:
                return self.s

        user = SimpleNamespace(id=99, is_active=True)
        mock_get_user.return_value = user
        mock_exists.return_value = True

        new_refresh = DummyRefresh("R2")
        mock_refresh_cls.for_user.return_value = new_refresh

        mock_payload.return_value = {"access": "A2", "refresh": "R2", "user": {"id": 99}}

        req = self._request(ua="ua2", ip="10.0.0.2")
        out = commands.refresh_tokens(req, refresh_jwt="OLD")

        self.assertEqual(out["refresh"], "R2")
        mock_delete.assert_called_once_with(user, "OLD")

        args, kwargs = mock_save.call_args
        self.assertIs(args[0], user)
        self.assertEqual(args[1], "R2")
        self.assertEqual(kwargs["data"]["ua"], "ua2")
        self.assertEqual(kwargs["data"]["ip"], "10.0.0.2")

        mock_payload.assert_called_once_with(user, new_refresh)

    @override_settings(JWT_REFRESH_IN_COOKIE=False)
    @patch("identity.services.commands.get_user_by_id")
    @patch("identity.services.commands.RefreshToken")
    def test_refresh_tokens_user_not_found_or_inactive_raises(self, mock_refresh_cls, mock_get_user):
        def _old_getitem(k):
            if k == "user_id":
                return 1
            raise KeyError(k)

        old = MagicMock()
        old.__getitem__.side_effect = _old_getitem
        mock_refresh_cls.side_effect = lambda raw: old

        mock_get_user.return_value = None
        req = self._request()
        with self.assertRaises(RefreshInvalid):
            commands.refresh_tokens(req, refresh_jwt="OLD")

        mock_get_user.return_value = SimpleNamespace(id=1, is_active=False)
        with self.assertRaises(RefreshInvalid):
            commands.refresh_tokens(req, refresh_jwt="OLD")

    @override_settings(JWT_REFRESH_IN_COOKIE=False)
    @patch("identity.services.commands.exists_refresh")
    @patch("identity.services.commands.get_user_by_id")
    @patch("identity.services.commands.RefreshToken")
    def test_refresh_tokens_not_recognized_raises(self, mock_refresh_cls, mock_get_user, mock_exists):
        def _old_getitem(k):
            if k == "user_id":
                return 1
            raise KeyError(k)

        old = MagicMock()
        old.__getitem__.side_effect = _old_getitem
        mock_refresh_cls.side_effect = lambda raw: old

        mock_get_user.return_value = SimpleNamespace(id=1, is_active=True)
        mock_exists.return_value = False

        req = self._request()
        with self.assertRaises(RefreshNotRecognized):
            commands.refresh_tokens(req, refresh_jwt="OLD")

    @patch("identity.services.commands.BlacklistedToken")
    @patch("identity.services.commands.OutstandingToken")
    @patch("identity.services.commands.delete_all_refreshes")
    def test_logout_user_deletes_refreshes_and_blacklists(self, mock_delete_all, mock_outstanding, mock_blacklisted):
        user = SimpleNamespace(id=1)
        req = self._request()

        mock_outstanding.objects.filter.return_value = [SimpleNamespace(id=10), SimpleNamespace(id=11)]

        commands.logout_user(req, user=user)

        mock_delete_all.assert_called_once_with(user)
        self.assertEqual(mock_blacklisted.objects.get_or_create.call_count, 2)

    @patch("identity.services.commands.BlacklistedToken")
    @patch("identity.services.commands.OutstandingToken")
    @patch("identity.services.commands.delete_all_refreshes")
    @patch("identity.services.commands.get_user_by_public_id")
    def test_admin_set_user_status_revokes_tokens_when_suspended(
        self,
        mock_get_user,
        mock_delete_all,
        mock_outstanding,
        mock_blacklisted,
    ):
        user = SimpleNamespace(
            id=1,
            user_status="ACTIVE",
            is_active=True,
            save=MagicMock(),
        )
        mock_get_user.return_value = user
        mock_outstanding.objects.filter.return_value = [SimpleNamespace(id=1)]

        out = commands.admin_set_user_status(public_id="pid", user_status="SUSPENDED", is_active=None)

        self.assertIs(out, user)
        self.assertEqual(user.user_status, "SUSPENDED")
        self.assertFalse(user.is_active)
        user.save.assert_called_once_with(update_fields=["user_status", "is_active"])
        mock_delete_all.assert_called_once_with(user)
        mock_blacklisted.objects.get_or_create.assert_called_once()
