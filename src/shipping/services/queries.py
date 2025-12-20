from __future__ import annotations
from typing import Iterable, List, Dict, Any
from ..models import PackageType

def _leq_or_unlimited(actual, limit):
    if limit is None or actual is None:
        return True
    return actual <= limit

def suggest_packages_for_dims(*, length_cm: int|None, width_cm: int|None,
                              height_cm: int|None, weight_kg: float|None) -> List[Dict[str, Any]]:
    """
    Prosta sugestia paczek wyłącznie na podstawie wymiarów/wagi.
    Zwraca listę dictów: {"package_type": PackageType, "fits": bool}
    (tu fits = True zawsze, bo filtrujemy; klucz zgodny z innymi wzorcami).
    """
    out = []
    for pkg in PackageType.objects.all():
        fits = (
            _leq_or_unlimited(length_cm, pkg.max_length_cm) and
            _leq_or_unlimited(width_cm,  pkg.max_width_cm) and
            _leq_or_unlimited(height_cm, pkg.max_height_cm) and
            _leq_or_unlimited(
                float(weight_kg) if weight_kg is not None else None,
                float(pkg.max_weight_kg) if pkg.max_weight_kg is not None else None
            )
        )
        if fits:
            out.append({"package_type": pkg, "fits": True, "price": pkg.price})
    def key(row):
        p = row["price"]
        return (1, 0) if p is None else (0, float(p.amount))
    out.sort(key=key)
    return out