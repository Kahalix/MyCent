from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from pawns.models import Pawn
from .factories import create_user, create_seller_profile, create_transaction, create_pawn, create_pawn_line


class PawnModelTests(TestCase):
    def setUp(self):
        self.operator = create_user(email="pawn-operator@example.com")
        self.seller = create_seller_profile(owner=self.operator, slug="pawn-shop")
        self.tx = create_transaction(user=self.operator, type="PLEDGE", status="COMPLETED", expected_total_amount=0)
        self.pawn = create_pawn(transaction=self.tx, seller_profile=self.seller, operator=self.operator, status="ACTIVE")

    def test_is_active_true_for_active_not_redeemed_not_forfeited(self):
        self.pawn.status = "ACTIVE"
        self.pawn.redeemed_at = None
        self.pawn.forfeited_at = None
        self.pawn.save(update_fields=["status", "redeemed_at", "forfeited_at", "updated_at"])
        self.assertTrue(self.pawn.is_active)

    def test_is_active_false_for_non_active_status(self):
        for status in ["REDEEMED", "FORFEITED", "CANCELLED"]:
            self.pawn.status = status
            self.pawn.redeemed_at = None
            self.pawn.forfeited_at = None
            self.pawn.save(update_fields=["status", "redeemed_at", "forfeited_at", "updated_at"])
            self.assertFalse(self.pawn.is_active)

    def test_is_active_false_when_redeemed_or_forfeited(self):
        self.pawn.status = "ACTIVE"
        self.pawn.redeemed_at = timezone.now()
        self.pawn.forfeited_at = None
        self.pawn.save(update_fields=["status", "redeemed_at", "forfeited_at", "updated_at"])
        self.assertFalse(self.pawn.is_active)
        self.pawn.redeemed_at = None
        self.pawn.forfeited_at = timezone.now()
        self.pawn.save(update_fields=["redeemed_at", "forfeited_at", "updated_at"])
        self.assertFalse(self.pawn.is_active)

    def test_recalc_appraisal_sums_line_values(self):
        create_pawn_line(self.pawn, appraisal_value=Money(100, "PLN"))
        create_pawn_line(self.pawn, appraisal_value=Money(50, "PLN"))
        self.pawn.recalc_appraisal(save=True)
        self.pawn.refresh_from_db()
        self.assertEqual(self.pawn.appraisal_total, Money(150, "PLN"))

    def test_recalc_appraisal_converts_different_currencies_by_amount(self):
        create_pawn_line(self.pawn, appraisal_value=Money(10, "PLN"))
        create_pawn_line(self.pawn, appraisal_value=Money(5, "EUR"))
        self.pawn.recalc_appraisal(save=True)
        self.pawn.refresh_from_db()
        self.assertEqual(self.pawn.appraisal_total, Money(15, "PLN"))
