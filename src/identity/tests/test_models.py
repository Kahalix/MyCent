from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase

from identity.models import User, SellerProfile, SellerMembership, SellerBankAccount, UserToken
from .factories import (
    create_user,
    create_seller_profile,
    create_seller_membership,
    create_seller_bank_account,
)


class UserModelTests(TestCase):
    def test_email_normalized_and_str_returns_email(self):
        user = create_user(email="User.TEST@Example.COM")
        self.assertEqual(user.email, "user.test@example.com")
        self.assertEqual(str(user), "user.test@example.com")

    def test_case_insensitive_email_unique_constraint(self):
        create_user(email="dup@example.com")
        with self.assertRaises(IntegrityError):
            create_user(email="DUP@example.com")


class SellerProfileModelTests(TestCase):
    def test_str_returns_company_name(self):
        sp = create_seller_profile(company_name="Firma X")
        self.assertEqual(str(sp), "Firma X")


class SellerMembershipModelTests(TestCase):
    def test_str_contains_slug_email_and_role(self):
        seller = create_seller_profile(slug="test-shop")
        user = create_user(email="member@example.com")
        membership = create_seller_membership(
            seller_profile=seller,
            user=user,
            role="MANAGER",
        )
        s = str(membership)
        self.assertIn("test-shop", s)
        self.assertIn("member@example.com", s)
        self.assertIn("MANAGER", s)


class SellerBankAccountModelTests(TestCase):
    def test_save_normalizes_iban(self):
        seller = create_seller_profile()
        acc = SellerBankAccount(
            seller_profile=seller,
            iban="pl12 1234 5678 90123",
            bank_name="Bank",
            account_holder="Holder",
        )
        acc.save()
        self.assertEqual(acc.iban, "PL121234567890123")

    def test_unique_default_per_seller_enforced(self):
        seller = create_seller_profile()
        create_seller_bank_account(seller_profile=seller, is_default=True)
        with self.assertRaises(IntegrityError):
            create_seller_bank_account(seller_profile=seller, is_default=True)


class UserTokenModelTests(TestCase):
    def test_issue_and_consume_ephemeral_token(self):
        user = create_user()
        raw = UserToken.issue_ephemeral(user, "EMAIL_CONFIRMATION", minutes_valid=5)
        self.assertTrue(
            UserToken.objects.filter(user=user, type="EMAIL_CONFIRMATION").exists()
        )
        tok = UserToken.consume_ephemeral(raw, "EMAIL_CONFIRMATION")
        self.assertIsNotNone(tok)
        self.assertFalse(
            UserToken.objects.filter(user=user, type="EMAIL_CONFIRMATION").exists()
        )
        tok2 = UserToken.consume_ephemeral(raw, "EMAIL_CONFIRMATION")
        self.assertIsNone(tok2)

    def test_refresh_token_lifecycle(self):
        user = create_user()
        raw = "raw-refresh-token"
        tok = UserToken.save_refresh(user, raw)
        self.assertEqual(tok.type, "REFRESH_TOKEN")
        self.assertTrue(UserToken.exists_refresh(user, raw))
        deleted = UserToken.delete_refresh(user, raw)
        self.assertEqual(deleted, 1)
        self.assertFalse(UserToken.exists_refresh(user, raw))
        UserToken.save_refresh(user, "x1")
        UserToken.save_refresh(user, "x2")
        deleted_all = UserToken.delete_all_refreshes(user)
        self.assertEqual(deleted_all, 2)
        self.assertFalse(
            UserToken.objects.filter(user=user, type="REFRESH_TOKEN").exists()
        )
