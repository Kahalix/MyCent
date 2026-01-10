from __future__ import annotations
from importlib import import_module
from typing import Callable, Optional

from django.conf import settings
from django.db import transaction
from django.db.models import F


class PointsError(Exception):
    pass

def spend_points(user, amount: int, reason: str = "") -> None:
    """
    Zabezpieczony na wyścigi (select_for_update + F()).
    """
    if amount <= 0:
        return

    if not hasattr(user, "points"):
        raise PointsError("Konto punktowe nie jest dostępne (brak pola 'points' lub niestandardowego backendu).")

    with transaction.atomic():
        # zablokuj wiersz, żeby uniknąć race condition
        u = user.__class__.objects.select_for_update().get(pk=user.pk)
        if int(u.points) < int(amount):
            raise PointsError("Niewystarczająca liczba punktów.")
        # atomowa dekrementacja
        u.points = F("points") - int(amount)
        u.save(update_fields=["points"])
        # odśwież lokalny obiekt
        u.refresh_from_db(fields=["points"])
        user.points = u.points


def add_points(user, amount: int, reason: str = "") -> None:
    """
    Opcjonalny helper do przyznawania punktów (np. za zakupy).
    """
    if amount <= 0:
        return
    if not hasattr(user, "points"):
        raise PointsError("Konto punktowe nie jest dostępne (brak pola 'points').")
    with transaction.atomic():
        u = user.__class__.objects.select_for_update().get(pk=user.pk)
        u.points = F("points") + int(amount)
        u.save(update_fields=["points"])
        u.refresh_from_db(fields=["points"])
        user.points = u.points
