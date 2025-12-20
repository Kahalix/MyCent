from __future__ import annotations

from django.test import TestCase

from identity.models import UserToken
from identity.services import repositories as repo
from .factories import (
    create_user,
    create_seller_profile,
    create_seller_bank_account,
    create_seller_membership,
)


class UserRepositoryTests(TestCase):
    def test_find_user_by_email_ci_and_is_email_taken_ci(self):
        user = create_user(email="repo@example.com")
        found = repo.find_user_by_email_ci("Repo@Example.com")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, user.id)
        self.assertTrue(repo.is_email_taken_ci("repo@example.com"))
        self.assertFalse(repo.is_email_taken_ci("other@example.com"))
        self.assertFalse(
            repo.is_email_taken_ci("repo@example.com", exclude_user_id=user.id)
        )

    def test_create_and_get_user(self):
        user = repo.create_user(
            email="created@example.com",
            password="StrongPass123!",
            first_name="A",
            last_name="B",
            active=False,
        )
        self.assertFalse(user.is_active)
        by_id = repo.get_user_by_id(user.id)
        by_public = repo.get_user_by_public_id(str(user.public_id))
        self.assertIsNotNone(by_id)
        self.assertIsNotNone(by_public)
        self.assertEqual(by_id.id, user.id)
        self.assertEqual(by_public.id, user.id)


class TokenRepositoryTests(TestCase):
    def test_issue_and_consume_ephemeral(self):
        user = create_user()
        raw = repo.issue_ephemeral(user, "EMAIL_CONFIRMATION", minutes=5)
        self.assertTrue(
            UserToken.objects.filter(user=user, type="EMAIL_CONFIRMATION").exists()
        )
        tok = repo.consume_ephemeral(raw, "EMAIL_CONFIRMATION")
        self.assertIsNotNone(tok)
        self.assertFalse(
            UserToken.objects.filter(user=user, type="EMAIL_CONFIRMATION").exists()
        )

    def test_refresh_lifecycle(self):
        user = create_user()
        raw = "repo-refresh"
        tok = repo.save_refresh(user, raw)
        self.assertEqual(tok.type, "REFRESH_TOKEN")
        self.assertTrue(repo.exists_refresh(user, raw))
        deleted = repo.delete_refresh(user, raw)
        self.assertEqual(deleted, 1)
        self.assertFalse(repo.exists_refresh(user, raw))
        repo.save_refresh(user, "a")
        repo.save_refresh(user, "b")
        deleted_all = repo.delete_all_refreshes(user)
        self.assertEqual(deleted_all, 2)
        self.assertFalse(
            UserToken.objects.filter(user=user, type="REFRESH_TOKEN").exists()
        )


class SellerRepositoryTests(TestCase):
    def test_get_seller_by_public_id_and_slug_and_for_owner(self):
        owner = create_user()
        seller = create_seller_profile(owner=owner, slug="repo-shop")
        by_public = repo.get_seller_by_public_id(str(seller.public_id))
        by_slug = repo.get_seller_by_slug("repo-shop")
        by_owner = repo.get_seller_for_owner(owner)
        self.assertEqual(by_public.id, seller.id)
        self.assertEqual(by_slug.id, seller.id)
        self.assertEqual(by_owner.id, seller.id)


class BankAccountRepositoryTests(TestCase):
    def test_bank_account_lookup_and_list_and_default(self):
        owner = create_user()
        seller = create_seller_profile(owner=owner)
        acc1 = create_seller_bank_account(seller_profile=seller, is_default=True)
        acc2 = create_seller_bank_account(seller_profile=seller, is_default=False)
        found = repo.get_bank_account_by_public_id(str(acc1.public_id))
        self.assertEqual(found.id, acc1.id)
        qs_owner = repo.list_bank_accounts_for_owner(owner)
        ids = list(qs_owner.values_list("id", flat=True))
        self.assertEqual(set(ids), {acc1.id, acc2.id})
        repo.set_default_for_seller(seller, acc2)
        acc1.refresh_from_db()
        acc2.refresh_from_db()
        self.assertFalse(acc1.is_default)
        self.assertTrue(acc2.is_default)


class MembershipRepositoryTests(TestCase):
    def test_is_member_and_lists(self):
        user = create_user()
        other = create_user()
        seller1 = create_seller_profile()
        seller2 = create_seller_profile()
        create_seller_membership(
            seller_profile=seller1,
            user=user,
            role="EMPLOYEE",
            is_active=True,
        )
        create_seller_membership(
            seller_profile=seller2,
            user=user,
            role="MANAGER",
            is_active=False,
        )
        create_seller_membership(
            seller_profile=seller2,
            user=other,
            role="OWNER",
            is_active=True,
        )
        self.assertTrue(repo.is_member(user, str(seller1.public_id), roles=None))
        self.assertTrue(
            repo.is_member(user, str(seller1.public_id), roles={"EMPLOYEE"})
        )
        self.assertFalse(
            repo.is_member(user, str(seller2.public_id), roles={"OWNER"})
        )
        sellers_for_user = list(repo.list_sellers_for_user(user))
        self.assertEqual([s.id for s in sellers_for_user], [seller1.id])
        acc = create_seller_bank_account(seller_profile=seller1)
        accs_for_user = list(repo.list_bank_accounts_for_user(user))
        self.assertEqual([a.id for a in accs_for_user], [acc.id])
