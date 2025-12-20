from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from identity.models import SellerMembership
from identity.services import queries
from .factories import (
    create_user,
    create_seller_profile,
    create_seller_membership,
    create_seller_bank_account,
)


class MePayloadTests(TestCase):
    def test_me_payload_returns_public_user_data(self):
        user = create_user(
            email="me@example.com",
            first_name="Jan",
            last_name="Kowalski",
        )
        data = queries.me_payload(user)
        self.assertEqual(data["email"], "me@example.com")
        self.assertEqual(data["public_id"], str(user.public_id))
        self.assertEqual(data["first_name"], "Jan")
        self.assertEqual(data["last_name"], "Kowalski")


class UserQueriesTests(TestCase):
    def test_get_user_by_public_id_returns_user(self):
        user = create_user()
        found = queries.get_user_by_public_id(str(user.public_id))
        self.assertIsNotNone(found)
        self.assertEqual(found.id, user.id)

    def test_find_user_by_email_ci_is_case_insensitive(self):
        user = create_user(email="QueryUser@example.com")
        found = queries.find_user_by_email_ci("queryuser@example.com")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, user.id)


class SellerQueriesTests(TestCase):
    def test_sellers_for_user_returns_only_active_memberships(self):
        user = create_user()
        other_user = create_user()
        seller1 = create_seller_profile(company_name="Shop A")
        seller2 = create_seller_profile(company_name="Shop B")
        create_seller_membership(seller_profile=seller1, user=user, is_active=True)
        create_seller_membership(seller_profile=seller2, user=user, is_active=False)
        create_seller_membership(seller_profile=seller2, user=other_user, is_active=True)
        qs = queries.sellers_for_user(user)
        self.assertEqual(list(qs.values_list("id", flat=True)), [seller1.id])

    def test_sellers_for_user_is_ordered_by_company_name(self):
        member = create_user("member@example.com")
        owner1 = create_user("owner1@example.com")
        owner2 = create_user("owner2@example.com")
        seller_b = create_seller_profile(owner=owner1, company_name="Zebra Shop", slug="zebra")
        seller_a = create_seller_profile(owner=owner2, company_name="Alpha Shop", slug="alpha")
        create_seller_membership(
            seller_profile=seller_b,
            user=member,
            role="EMPLOYEE",
            is_active=True,
        )
        create_seller_membership(
            seller_profile=seller_a,
            user=member,
            role="EMPLOYEE",
            is_active=True,
        )
        qs = queries.sellers_for_user(member)
        self.assertEqual(list(qs.values_list("company_name", flat=True)), ["Alpha Shop", "Zebra Shop"])

    def test_bank_accounts_for_user_returns_accounts_for_memberships(self):
        user = create_user()
        seller = create_seller_profile()
        create_seller_membership(seller_profile=seller, user=user, is_active=True)
        acc = create_seller_bank_account(seller_profile=seller)
        qs = queries.bank_accounts_for_user(user)
        self.assertEqual(list(qs.values_list("id", flat=True)), [acc.id])

    def test_bank_accounts_for_user_returns_only_for_active_memberships(self):
        member = create_user("member@example.com")
        owner1 = create_user("owner1@example.com")
        owner2 = create_user("owner2@example.com")
        seller1 = create_seller_profile(owner=owner1, company_name="Active Shop", slug="active-shop")
        seller2 = create_seller_profile(owner=owner2, company_name="Inactive Shop", slug="inactive-shop")
        create_seller_membership(
            seller_profile=seller1,
            user=member,
            role="EMPLOYEE",
            is_active=True,
        )
        create_seller_membership(
            seller_profile=seller2,
            user=member,
            role="EMPLOYEE",
            is_active=False,
        )
        acc1 = create_seller_bank_account(
            seller_profile=seller1,
            bank_name="Bank 1",
            account_holder="Holder 1",
            is_active=True,
        )
        create_seller_bank_account(
            seller_profile=seller2,
            bank_name="Bank 2",
            account_holder="Holder 2",
            is_active=True,
        )
        qs = queries.bank_accounts_for_user(member)
        self.assertEqual(list(qs.values_list("public_id", flat=True)), [acc1.public_id])


class MembershipListQueriesTests(TestCase):
    def test_memberships_for_seller_returns_only_active_and_sorted_by_created_desc(self):
        owner = create_user("owner@example.com")
        seller = create_seller_profile(owner=owner, company_name="Shop", slug="shop")
        owner_membership = SellerMembership.objects.get(
            seller_profile=seller,
            user=owner,
        )
        u1 = create_user("u1@example.com")
        u2 = create_user("u2@example.com")
        m1 = create_seller_membership(
            seller_profile=seller,
            user=u1,
            role="EMPLOYEE",
            is_active=True,
        )
        m2 = create_seller_membership(
            seller_profile=seller,
            user=u2,
            role="EMPLOYEE",
            is_active=True,
        )
        create_seller_membership(
            seller_profile=seller,
            user=create_user("u3@example.com"),
            role="EMPLOYEE",
            is_active=False,
        )
        now = timezone.now()
        owner_membership.created_at = now - timedelta(minutes=2)
        owner_membership.save(update_fields=["created_at"])
        m1.created_at = now - timedelta(minutes=1)
        m1.save(update_fields=["created_at"])
        m2.created_at = now
        m2.save(update_fields=["created_at"])
        qs = queries.memberships_for_seller(seller)
        ids = list(qs.values_list("public_id", flat=True))
        self.assertEqual(ids, [m2.public_id, m1.public_id, owner_membership.public_id])

    def test_memberships_for_user_returns_only_active_and_sorted_by_created_desc(self):
        member = create_user("member@example.com")
        owner1 = create_user("owner1@example.com")
        owner2 = create_user("owner2@example.com")
        seller1 = create_seller_profile(owner=owner1, company_name="Shop1", slug="shop1")
        seller2 = create_seller_profile(owner=owner2, company_name="Shop2", slug="shop2")
        m1 = create_seller_membership(
            seller_profile=seller1,
            user=member,
            role="EMPLOYEE",
            is_active=True,
        )
        m2 = create_seller_membership(
            seller_profile=seller2,
            user=member,
            role="EMPLOYEE",
            is_active=True,
        )
        seller3 = create_seller_profile(
            owner=create_user("owner3@example.com"),
            company_name="Shop3",
            slug="shop3",
        )
        create_seller_membership(
            seller_profile=seller3,
            user=member,
            role="EMPLOYEE",
            is_active=False,
        )
        now = timezone.now()
        m1.created_at = now - timedelta(minutes=1)
        m1.save(update_fields=["created_at"])
        m2.created_at = now
        m2.save(update_fields=["created_at"])
        qs = queries.memberships_for_user(member)
        ids = list(qs.values_list("public_id", flat=True))
        self.assertEqual(ids, [m2.public_id, m1.public_id])


class MembershipQueriesTests(TestCase):
    def test_members_for_seller_orders_by_role_rank(self):
        owner = create_user(email="owner@example.com")
        seller = create_seller_profile(owner=owner)
        manager = create_user(email="manager@example.com")
        moderator = create_user(email="mod@example.com")
        employee = create_user(email="emp@example.com")
        create_seller_membership(
            seller_profile=seller,
            user=manager,
            role="MANAGER",
        )
        create_seller_membership(
            seller_profile=seller,
            user=moderator,
            role="MODERATOR",
        )
        create_seller_membership(
            seller_profile=seller,
            user=employee,
            role="EMPLOYEE",
        )
        members = list(queries.members_for_seller(seller))
        roles = [m.role for m in members]
        self.assertIn("OWNER", roles[0])
        self.assertEqual(set(roles), {"OWNER", "MANAGER", "MODERATOR", "EMPLOYEE"})

    def test_members_for_seller_orders_by_role_then_created_desc(self):
        seller_owner = create_user("owner@example.com")
        seller = create_seller_profile(owner=seller_owner, company_name="Shop", slug="shop")
        owner_membership = SellerMembership.objects.get(
            seller_profile=seller,
            user=seller_owner,
        )
        u_emp = create_user("emp@example.com")
        u_mod = create_user("mod@example.com")
        u_mgr = create_user("mgr@example.com")
        m_emp = create_seller_membership(
            seller_profile=seller,
            user=u_emp,
            role="EMPLOYEE",
            is_active=True,
        )
        m_mod = create_seller_membership(
            seller_profile=seller,
            user=u_mod,
            role="MODERATOR",
            is_active=True,
        )
        m_mgr = create_seller_membership(
            seller_profile=seller,
            user=u_mgr,
            role="MANAGER",
            is_active=True,
        )
        qs = queries.members_for_seller(seller)
        roles = list(qs.values_list("role", flat=True))
        self.assertEqual(
            roles,
            ["OWNER", "MANAGER", "MODERATOR", "EMPLOYEE"],
        )
        ids = list(qs.values_list("public_id", flat=True))
        self.assertIn(owner_membership.public_id, ids)
        self.assertIn(m_mgr.public_id, ids)
        self.assertIn(m_mod.public_id, ids)
        self.assertIn(m_emp.public_id, ids)

    def test_user_role_in_seller_and_can_manage_members(self):
        owner = create_user(email="o@example.com")
        seller = create_seller_profile(owner=owner)
        manager_user = create_user(email="m@example.com")
        emp_user = create_user(email="e@example.com")
        create_seller_membership(
            seller_profile=seller,
            user=manager_user,
            role="MANAGER",
        )
        create_seller_membership(
            seller_profile=seller,
            user=emp_user,
            role="EMPLOYEE",
        )
        self.assertEqual(queries.user_role_in_seller(owner, seller), "OWNER")
        self.assertEqual(queries.user_role_in_seller(manager_user, seller), "MANAGER")
        self.assertEqual(queries.user_role_in_seller(emp_user, seller), "EMPLOYEE")
        self.assertTrue(queries.can_manage_members(owner, seller))
        self.assertTrue(queries.can_manage_members(manager_user, seller))
        self.assertFalse(queries.can_manage_members(emp_user, seller))

    def test_user_role_in_seller_membership_and_inactive_ignored(self):
        owner = create_user("owner@example.com")
        seller = create_seller_profile(owner=owner, company_name="Shop", slug="shop")
        member = create_user("member@example.com")
        other = create_user("other@example.com")
        create_seller_membership(
            seller_profile=seller,
            user=member,
            role="MANAGER",
            is_active=True,
        )
        create_seller_membership(
            seller_profile=seller,
            user=other,
            role="EMPLOYEE",
            is_active=False,
        )
        self.assertEqual(queries.user_role_in_seller(member, seller), "MANAGER")
        self.assertIsNone(queries.user_role_in_seller(other, seller))

    def test_can_manage_members_for_owner_manager_and_superuser(self):
        owner = create_user("owner@example.com")
        seller = create_seller_profile(owner=owner, company_name="Shop", slug="shop")
        manager = create_user("manager@example.com")
        employee = create_user("employee@example.com")
        moderator = create_user("mod@example.com")
        create_seller_membership(
            seller_profile=seller,
            user=manager,
            role="MANAGER",
            is_active=True,
        )
        create_seller_membership(
            seller_profile=seller,
            user=employee,
            role="EMPLOYEE",
            is_active=True,
        )
        create_seller_membership(
            seller_profile=seller,
            user=moderator,
            role="MODERATOR",
            is_active=True,
        )
        superuser = create_user("admin@example.com", is_superuser=True, is_staff=True)
        self.assertTrue(queries.can_manage_members(owner, seller))
        self.assertTrue(queries.can_manage_members(manager, seller))
        self.assertFalse(queries.can_manage_members(employee, seller))
        self.assertFalse(queries.can_manage_members(moderator, seller))
        self.assertTrue(queries.can_manage_members(superuser, seller))

    def test_best_membership_for_user_returns_highest_priority(self):
        user = create_user()
        seller_emp = create_seller_profile()
        seller_mgr = create_seller_profile()
        create_seller_membership(
            seller_profile=seller_emp,
            user=user,
            role="EMPLOYEE",
        )
        create_seller_membership(
            seller_profile=seller_mgr,
            user=user,
            role="MANAGER",
        )
        best = queries.best_membership_for_user(user)
        self.assertIsNotNone(best)
        self.assertEqual(best.role, "MANAGER")


class HelperQueriesTests(TestCase):
    def test_get_membership_by_public_id_for_seller(self):
        owner = create_user("owner@example.com")
        seller1 = create_seller_profile(owner=owner, company_name="Shop1", slug="shop1")
        seller2 = create_seller_profile(
            owner=create_user("owner2@example.com"),
            company_name="Shop2",
            slug="shop2",
        )
        member = create_user("member@example.com")
        m = create_seller_membership(
            seller_profile=seller1,
            user=member,
            role="EMPLOYEE",
            is_active=True,
        )
        found = queries.get_membership_by_public_id_for_seller(m.public_id, seller1)
        self.assertIsNotNone(found)
        self.assertEqual(found.public_id, m.public_id)
        not_found = queries.get_membership_by_public_id_for_seller(m.public_id, seller2)
        self.assertIsNone(not_found)

    def test_get_seller_by_public_id_returns_seller(self):
        owner = create_user("owner@example.com")
        seller = create_seller_profile(owner=owner, company_name="Shop", slug="shop")
        found = queries.get_seller_by_public_id(seller.public_id)
        self.assertIsNotNone(found)
        self.assertEqual(found.public_id, seller.public_id)
