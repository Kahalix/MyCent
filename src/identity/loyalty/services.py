from __future__ import annotations
from decimal import Decimal
from math import floor
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from djmoney.money import Money

User = get_user_model()

# Domyślne wartości
DEFAULT_RATE_BPS = getattr(settings, "LOYALTY_RATE_BPS", 200)               # 2% w punktach (1 PLN = 1 pkt przy 100%)
DEFAULT_POINT_VALUE_PLN = Decimal(str(getattr(settings, "LOYALTY_POINT_VALUE_PLN", "0.01")))  # 1 pkt = 0.01 PLN

def calc_points_for_amount(amount: Money) -> int:
    """
    Liczba punktów za daną kwotę (waluta ignorowana - liczymy po nominale).
    Jeśli RATE_BPS=200 (2%), to za 123.45 PLN dostaniesz (123.45 * 0.02) = 2 pkt.
    """
    rate = Decimal(DEFAULT_RATE_BPS) / Decimal("10000")
    pts = int(Decimal(amount.amount) * rate)
    return max(pts, 0)

def point_value_money(points: int, currency: str = "PLN") -> Money:
    """
    Ile warte jest N punktów w pieniądzu. Domyślnie 1 pkt = 0.01 PLN.
    """
    if points <= 0:
        return Money(0, currency)
    return Money((Decimal(points) * DEFAULT_POINT_VALUE_PLN).quantize(Decimal("0.01")), currency)

def add_points(user: User, points: int) -> None:
    if points <= 0:
        return
    user.points = int(user.points) + int(points)
    user.save(update_fields=["points"])

def take_points(user: User, points: int) -> int:
    """
    Pobiera do 'points' punktów, ale nie więcej niż user posiada. Zwraca faktycznie pobraną liczbę.
    """
    want = max(int(points), 0)
    have = int(getattr(user, "points", 0))
    used = min(want, have)
    if used > 0:
        user.points = have - used
        user.save(update_fields=["points"])
    return used
