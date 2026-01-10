from __future__ import annotations
from djmoney.money import Money
from decimal import Decimal
from django.conf import settings

# Konfiguracja (domyślna)
DEFAULT_RATE_BPS_PER_30D = getattr(settings, "PAWN_RATE_BPS_PER_30D", 1000)  # 10% per 30 dni
DEFAULT_MIN_FEE_AMOUNT   = getattr(settings, "PAWN_MIN_FEE_AMOUNT", 5)

def calc_extension_fee(*, principal: Money, days: int) -> Money:
    """
    Opłata proporcjonalna do dni (7/14/30). Zawsze w walucie principal.
    """
    assert days in (7, 14, 30)
    base = principal
    bps_30 = Decimal(DEFAULT_RATE_BPS_PER_30D)
    pct_30 = bps_30 / Decimal("10000")  # np. 0.10
    fee_amount = (Decimal(base.amount) * pct_30 * Decimal(days) / Decimal("30")).quantize(Decimal("0.01"))
    fee = Money(fee_amount, base.currency)

    # min fee w tej samej walucie co principal
    min_fee = Money(Decimal(DEFAULT_MIN_FEE_AMOUNT), base.currency)
    return fee if fee >= min_fee else min_fee
