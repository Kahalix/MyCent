# src/orders/services/printing.py
from __future__ import annotations
import io
from pathlib import Path
from urllib.parse import urljoin
from django.conf import settings
from django.template.loader import render_to_string
from djmoney.money import Money
from django.utils import timezone

from catalog.models import ItemType
from orders.models import Order
from common.attrs_display import attrs_pairs

COND_PL = {"NEW": "Nowy", "USED": "Używany", "DAMAGED": "Uszkodzony"}

def _ui_for_snapshot(snap: dict) -> dict:
    """
    Pobierz ui_schema z ItemType po type_path (jeśli jest).
    """
    if not isinstance(snap, dict):
        return {}
    tpath = snap.get("type_path")
    if not tpath:
        return {}
    it = ItemType.objects.filter(path=tpath).only("ui_schema_json").first()
    return (it.ui_schema_json or {}) if it else {}

def _canonical_pairs(snap: dict) -> list[tuple[str,str]]:
    """
    Z kanonicznych pól ItemSet (poza attributes) zrób czytelne pary do PDF.
    """
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

def _ctx(order: Order) -> dict:
    cust = order.customer_snapshot or {}

    lines = []
    for l in order.order_lines.all():
        snap = l.item_snapshot or {}
        ui = _ui_for_snapshot(snap)
        pairs = _canonical_pairs(snap) + attrs_pairs(snap.get("attributes") or {}, ui)
        lines.append({
            "title": (snap.get("title")
                      or snap.get("set_name")
                      or getattr(l.item_set, "set_name", "")
                      or "Pozycja"),
            "qty": l.quantity,
            "unit": l.unit_price,
            "total": l.line_total,
            "attrs_pairs": pairs,           # NEW: gotowe pary do PDF
            "notes": snap.get("notes",""),
        })

    seller_logo_src = None
    try:
        if order.seller_profile and order.seller_profile.logo_image:
            seller_logo_src = Path(order.seller_profile.logo_image.path).absolute().as_uri()
    except Exception:
        pass

    return {
        "order": order,
        "order_id": order.public_id,
        "seller_name": getattr(order.seller_profile, "company_name", ""),
        "seller_logo_src": seller_logo_src,
        "purchase_date": order.purchase_date,
        "customer": cust,
        "lines": lines,
        "items_total": order.items_total or Money(0, "PLN"),
        "shipping_total": order.shipping_total or Money(0, "PLN"),
        "grand_total": order.purchase_cost or Money(0, "PLN"),
        "created_at": order.created_at,
        "printed_at": timezone.localtime(timezone.now()),
    }

def render_receipt_csv(order: Order) -> bytes:
    from .printing_csv import render_receipt_csv as _csv
    return _csv(order)

def render_receipt_pdf(order: Order, *, template_name: str | None = None) -> bytes:
    try:
        from weasyprint import HTML
    except Exception as e:
        raise RuntimeError("Brak zależności 'weasyprint'. Zainstaluj: pip install weasyprint") from e

    if template_name is None:
        tx_type = getattr(getattr(order, "transaction", None), "type", None)
        template_name = "receipt_pawn.html" if tx_type == "PAWN_PURCHASE" else "receipt_sale.html"

    ctx = _ctx(order)
    html = render_to_string(template_name, ctx)
    base_url = str(Path(settings.BASE_DIR).absolute())
    return HTML(string=html, base_url=base_url).write_pdf()

