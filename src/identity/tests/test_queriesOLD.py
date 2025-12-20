# src/identity/tests/test_queriesOLD.py

from datetime import timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from identity.models import SellerProfile, SellerMembership, SellerBankAccount
from identity.services import queries


User = get_user_model()


def make_user(email: str, **extra) -> User:
    """
    Mały helper, żeby nie powielać create_user w każdym teście.
    Pozwala nadpisać first_name / last_name / password przez **extra.
    """
    defaults = {
        "password": "testpass123",
        "first_name": "",
        "last_name": "",
    }
    defaults.update(extra)
    return User.objects.create_user(email=email, **defaults)


# =========================
# LISTY SKLEPÓW / KONT
# =========================

class QueriesSellerListsTests(TestCase):
    def test_sellers_for_user_returns_only_active_memberships(self):
        member = make_user("member@example.com")
        owner1 = make_user("owner1@example.com")
        owner2 = make_user("owner2@example.com")

        seller1 = SellerProfile.objects.create(owner=owner1, company_name="Active Shop", slug="active-shop")
        seller2 = SellerProfile.objects.create(owner=owner2, company_name="Inactive Shop", slug="inactive-shop")

        SellerMembership.objects.create(
            seller_profile=seller1, user=member, role="EMPLOYEE", is_active=True
        )
        SellerMembership.objects.create(
            seller_profile=seller2, user=member, role="EMPLOYEE", is_active=False
        )

        qs = queries.sellers_for_user(member)
        self.assertEqual(list(qs.values_list("slug", flat=True)), ["active-shop"])

    def test_sellers_for_user_is_ordered_by_company_name(self):
        member = make_user("member@example.com")
        owner1 = make_user("owner1@example.com")
        owner2 = make_user("owner2@example.com")

        seller_b = SellerProfile.objects.create(owner=owner1, company_name="Zebra Shop", slug="zebra")
        seller_a = SellerProfile.objects.create(owner=owner2, company_name="Alpha Shop", slug="alpha")

        SellerMembership.objects.create(
            seller_profile=seller_b, user=member, role="EMPLOYEE", is_active=True
        )
        SellerMembership.objects.create(
            seller_profile=seller_a, user=member, role="EMPLOYEE", is_active=True
        )

        qs = queries.sellers_for_user(member)
        self.assertEqual(list(qs.values_list("company_name", flat=True)), ["Alpha Shop", "Zebra Shop"])

    def test_bank_accounts_for_user_returns_only_for_active_memberships(self):
        member = make_user("member@example.com")
        owner1 = make_user("owner1@example.com")
        owner2 = make_user("owner2@example.com")

        seller1 = SellerProfile.objects.create(owner=owner1, company_name="Active Shop", slug="active-shop")
        seller2 = SellerProfile.objects.create(owner=owner2, company_name="Inactive Shop", slug="inactive-shop")

        # memberships
        SellerMembership.objects.create(
            seller_profile=seller1, user=member, role="EMPLOYEE", is_active=True
        )
        SellerMembership.objects.create(
            seller_profile=seller2, user=member, role="EMPLOYEE", is_active=False
        )

        acc1 = SellerBankAccount.objects.create(
            seller_profile=seller1,
            iban="PL12123456789012345678901234",
            bank_name="Bank 1",
            account_holder="Holder 1",
            is_active=True,
        )
        SellerBankAccount.objects.create(
            seller_profile=seller2,
            iban="PL34123456789012345678901234",
            bank_name="Bank 2",
            account_holder="Holder 2",
            is_active=True,
        )

        qs = queries.bank_accounts_for_user(member)
        self.assertEqual(list(qs.values_list("public_id", flat=True)), [acc1.public_id])


# =========================
# LISTY MEMBERSHIPÓW
# =========================

class QueriesMembershipListsTests(TestCase):
    def test_memberships_for_seller_returns_only_active_and_sorted_by_created_desc(self):
        seller_owner = make_user("owner@example.com")
        seller = SellerProfile.objects.create(owner=seller_owner, company_name="Shop", slug="shop")

        # Membership OWNERA powstaje z sygnału post_save
        owner_membership = SellerMembership.objects.get(
            seller_profile=seller, user=seller_owner
        )

        u1 = make_user("u1@example.com")
        u2 = make_user("u2@example.com")

        m1 = SellerMembership.objects.create(
            seller_profile=seller, user=u1, role="EMPLOYEE", is_active=True
        )
        m2 = SellerMembership.objects.create(
            seller_profile=seller, user=u2, role="EMPLOYEE", is_active=True
        )
        SellerMembership.objects.create(
            seller_profile=seller, user=make_user("u3@example.com"), role="EMPLOYEE", is_active=False
        )

        # Wymuś różne created_at, żeby sortowanie było deterministyczne
        now = timezone.now()
        owner_membership.created_at = now - timedelta(minutes=2)
        owner_membership.save(update_fields=["created_at"])
        m1.created_at = now - timedelta(minutes=1)
        m1.save(update_fields=["created_at"])
        m2.created_at = now
        m2.save(update_fields=["created_at"])

        qs = queries.memberships_for_seller(seller)
        ids = list(qs.values_list("public_id", flat=True))

        # tylko aktywne i w kolejności: najnowszy -> najstarszy
        self.assertEqual(ids, [m2.public_id, m1.public_id, owner_membership.public_id])

    def test_memberships_for_user_returns_only_active_and_sorted_by_created_desc(self):
        member = make_user("member@example.com")
        owner1 = make_user("owner1@example.com")
        owner2 = make_user("owner2@example.com")

        seller1 = SellerProfile.objects.create(owner=owner1, company_name="Shop1", slug="shop1")
        seller2 = SellerProfile.objects.create(owner=owner2, company_name="Shop2", slug="shop2")

        m1 = SellerMembership.objects.create(
            seller_profile=seller1, user=member, role="EMPLOYEE", is_active=True
        )
        m2 = SellerMembership.objects.create(
            seller_profile=seller2, user=member, role="EMPLOYEE", is_active=True
        )

        # inactive membership dla tego samego usera
        seller3 = SellerProfile.objects.create(
            owner=make_user("owner3@example.com"), company_name="Shop3", slug="shop3"
        )
        SellerMembership.objects.create(
            seller_profile=seller3, user=member, role="EMPLOYEE", is_active=False
        )

        # znowu wymuszamy kolejność po created_at
        now = timezone.now()
        m1.created_at = now - timedelta(minutes=1)
        m1.save(update_fields=["created_at"])
        m2.created_at = now
        m2.save(update_fields=["created_at"])

        qs = queries.memberships_for_user(member)
        ids = list(qs.values_list("public_id", flat=True))
        self.assertEqual(ids, [m2.public_id, m1.public_id])

    def test_members_for_seller_orders_by_role_then_created_desc(self):
        seller_owner = make_user("owner@example.com")
        seller = SellerProfile.objects.create(owner=seller_owner, company_name="Shop", slug="shop")

        # owner membership z sygnału
        owner_membership = SellerMembership.objects.get(
            seller_profile=seller, user=seller_owner
        )

        u_emp = make_user("emp@example.com")
        u_mod = make_user("mod@example.com")
        u_mgr = make_user("mgr@example.com")

        m_emp = SellerMembership.objects.create(
            seller_profile=seller, user=u_emp, role="EMPLOYEE", is_active=True
        )
        m_mod = SellerMembership.objects.create(
            seller_profile=seller, user=u_mod, role="MODERATOR", is_active=True
        )
        m_mgr = SellerMembership.objects.create(
            seller_profile=seller, user=u_mgr, role="MANAGER", is_active=True
        )

        qs = queries.members_for_seller(seller)
        roles = list(qs.values_list("role", flat=True))
        self.assertEqual(
            roles,
            ["OWNER", "MANAGER", "MODERATOR", "EMPLOYEE"],
        )
        self.assertIn(owner_membership.public_id, qs.values_list("public_id", flat=True))
        self.assertIn(m_mgr.public_id, qs.values_list("public_id", flat=True))
        self.assertIn(m_mod.public_id, qs.values_list("public_id", flat=True))
        self.assertIn(m_emp.public_id, qs.values_list("public_id", flat=True))


# =========================
# UPRAWNIENIA
# =========================

class QueriesPermissionsTests(TestCase):
    def test_user_role_in_seller_owner_membership(self):
        owner = make_user("owner@example.com")
        seller = SellerProfile.objects.create(owner=owner, company_name="Shop", slug="shop")

        role = queries.user_role_in_seller(owner, seller)
        self.assertEqual(role, "OWNER")

    def test_user_role_in_seller_membership_and_inactive_ignored(self):
        owner = make_user("owner@example.com")
        seller = SellerProfile.objects.create(owner=owner, company_name="Shop", slug="shop")

        member = make_user("member@example.com")
        SellerMembership.objects.create(
            seller_profile=seller, user=member, role="MANAGER", is_active=True
        )

        other = make_user("other@example.com")
        SellerMembership.objects.create(
            seller_profile=seller, user=other, role="EMPLOYEE", is_active=False
        )

        self.assertEqual(queries.user_role_in_seller(member, seller), "MANAGER")
        self.assertIsNone(queries.user_role_in_seller(other, seller))

    def test_can_manage_members_for_owner_and_manager_only(self):
        owner = make_user("owner@example.com")
        seller = SellerProfile.objects.create(owner=owner, company_name="Shop", slug="shop")

        manager = make_user("manager@example.com")
        employee = make_user("employee@example.com")
        mod = make_user("mod@example.com")

        SellerMembership.objects.create(
            seller_profile=seller, user=manager, role="MANAGER", is_active=True
        )
        SellerMembership.objects.create(
            seller_profile=seller, user=employee, role="EMPLOYEE", is_active=True
        )
        SellerMembership.objects.create(
            seller_profile=seller, user=mod, role="MODERATOR", is_active=True
        )

        superuser = User.objects.create_superuser(
            email="admin@example.com", password="adminpass"
        )

        self.assertTrue(queries.can_manage_members(owner, seller))
        self.assertTrue(queries.can_manage_members(manager, seller))
        self.assertFalse(queries.can_manage_members(employee, seller))
        self.assertFalse(queries.can_manage_members(mod, seller))
        self.assertTrue(queries.can_manage_members(superuser, seller))

    def test_best_membership_for_user_prefers_stronger_role_over_newer(self):
        """
        Jeśli użytkownik ma starsze członkostwo z silniejszą rolą i nowsze z
        słabszą rolą, to wybierane jest silniejsze (role_rank).
        """
        member = make_user("member@example.com")
        owner1 = make_user("owner1@example.com")
        owner2 = make_user("owner2@example.com")

        seller_manager = SellerProfile.objects.create(
            owner=owner1, company_name="Manager Shop", slug="manager-shop"
        )
        seller_employee = SellerProfile.objects.create(
            owner=owner2, company_name="Employee Shop", slug="employee-shop"
        )

        m_manager = SellerMembership.objects.create(
            seller_profile=seller_manager, user=member, role="MANAGER", is_active=True
        )
        SellerMembership.objects.create(
            seller_profile=seller_employee, user=member, role="EMPLOYEE", is_active=True
        )

        best = queries.best_membership_for_user(member)
        self.assertIsNotNone(best)
        self.assertEqual(best.public_id, m_manager.public_id)
        self.assertEqual(best.role, "MANAGER")


# =========================
# HELPERY
# =========================

class QueriesHelpersTests(TestCase):
    def test_get_membership_by_public_id_for_seller(self):
        owner = make_user("owner@example.com")
        seller1 = SellerProfile.objects.create(owner=owner, company_name="Shop1", slug="shop1")
        seller2 = SellerProfile.objects.create(
            owner=make_user("owner2@example.com"),
            company_name="Shop2",
            slug="shop2",
        )

        member = make_user("member@example.com")
        m = SellerMembership.objects.create(
            seller_profile=seller1, user=member, role="EMPLOYEE", is_active=True
        )

        found = queries.get_membership_by_public_id_for_seller(m.public_id, seller1)
        self.assertIsNotNone(found)
        self.assertEqual(found.public_id, m.public_id)

        not_found = queries.get_membership_by_public_id_for_seller(m.public_id, seller2)
        self.assertIsNone(not_found)

    def test_get_seller_by_public_id_and_me_payload_and_email_helpers(self):
        user = make_user("user@example.com", first_name="Jan", last_name="Kowalski")
        seller = SellerProfile.objects.create(owner=user, company_name="Shop", slug="shop")

        # get_seller_by_public_id
        found_seller = queries.get_seller_by_public_id(seller.public_id)
        self.assertIsNotNone(found_seller)
        self.assertEqual(found_seller.public_id, seller.public_id)

        # me_payload
        payload = queries.me_payload(user)
        self.assertEqual(payload["public_id"], user.public_id)
        self.assertEqual(payload["email"], "user@example.com")

        # find_user_by_email_ci i get_user_by_public_id
        u1 = queries.find_user_by_email_ci("USER@example.com")
        self.assertIsNotNone(u1)
        self.assertEqual(u1.public_id, user.public_id)

        u2 = queries.get_user_by_public_id(user.public_id)
        self.assertIsNotNone(u2)
        self.assertEqual(u2.email, "user@example.com")
