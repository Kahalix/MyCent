from __future__ import annotations
from pathlib import Path
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from djmoney.money import Money

from pawns.models import Pawn
from common.attrs_display import attrs_pairs
from catalog.models import ItemType

COND_PL = {"NEW": "Nowy", "USED": "Używany", "DAMAGED": "Uszkodzony"}

def _ui_for_snapshot(snap: dict) -> dict:
    if not isinstance(snap, dict):
        return {}
    tpath = snap.get("type_path")
    if not tpath:
        return {}
    it = ItemType.objects.filter(path=tpath).only("ui_schema_json").first()
    return (it.ui_schema_json or {}) if it else {}

def _canonical_pairs(snap: dict) -> list[tuple[str,str]]:
    if not isinstance(snap, dict):
        return []
    out = []
    cond = snap.get("condition")
    if cond:
        out.append(("Stan", COND_PL.get(cond, cond)))
    L, W, H = snap.get("length_cm"), snap.get("width_cm"), snap.get("height_cm")
    if any(v not in (None, "", "None") for v in (L, W, H)):
        out.append(("Wymiary", f"{L or '-'} × {W or '-'} × {H or '-'} cm"))
    weight = snap.get("weight_kg")
    if weight not in (None, "", "None"):
        out.append(("Masa", f"{weight} kg"))
    return out

def _ctx(pawn: Pawn) -> dict:
    cust = pawn.customer_snapshot or {}
    lines = []
    for ln in pawn.lines.all():
        snap = ln.item_snapshot or {}
        ui = _ui_for_snapshot(snap)
        pairs = _canonical_pairs(snap) + attrs_pairs(snap.get("attributes") or {}, ui)
        lines.append({
            "title": ln.title or "Pozycja",
            "qty": ln.quantity,
            "appraisal": ln.appraisal_value,
            "attrs_pairs": pairs,
            "notes": ln.description or snap.get("notes",""),
        })

    seller_logo_src = None
    try:
        if pawn.seller_profile and pawn.seller_profile.logo_image:
            seller_logo_src = Path(pawn.seller_profile.logo_image.path).absolute().as_uri()
    except Exception:
        pass

    return {
        "pawn": pawn,
        "pawn_id": pawn.public_id,
        "seller_name": getattr(pawn.seller_profile, "company_name", ""),
        "seller_logo_src": seller_logo_src,
        "start_date": pawn.start_date,
        "due_date": pawn.due_date,
        "status": pawn.status,
        "customer": cust,
        "lines": lines,
        "appraisal_total": pawn.appraisal_total or Money(0, "PLN"),
        "principal": pawn.principal,
        "created_at": pawn.created_at,
        "printed_at": timezone.localtime(timezone.now()),
        "extensions": list(pawn.extensions.all()),
        "operator": pawn.operator,
    }

def render_receipt_pdf(pawn: Pawn, *, template_name: str = "pawn_receipt.html") -> bytes:
    try:
        from weasyprint import HTML
    except Exception as e:
        raise RuntimeError("Brak zależności 'weasyprint'. Zainstaluj: pip install weasyprint") from e

    ctx = _ctx(pawn)
    html = render_to_string(template_name, ctx)
    base_url = str(Path(settings.BASE_DIR).absolute())
    return HTML(string=html, base_url=base_url).write_pdf()

def render_receipt_csv(pawn: Pawn) -> bytes:
    from .printing_csv import render_receipt_csv as _csv
    return _csv(pawn)

def export_pawns_csv(pawns) -> bytes:
    from .printing_csv import export_pawns_csv as _list_csv
    return _list_csv(pawns)

def export_pawns_summary_csv(pawns) -> bytes:
    from .printing_csv import export_pawns_summary_csv as _sum_csv
    return _sum_csv(pawns)
