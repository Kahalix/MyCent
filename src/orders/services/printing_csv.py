from __future__ import annotations
import csv
import io
from typing import Any, Dict

from djmoney.money import Money
from orders.models import Order


def _money(m: Money | None) -> str:
    if not m:
        return ""
    # 12.34 PLN
    return f"{m.amount:.2f} {m.currency}"


def _attr_str(attrs: Dict[str, Any] | None) -> str:
    if not attrs:
        return ""
    # k1=v1 | k2=v2
    pairs = []
    for k, v in attrs.items():
        if v is None:
            continue
        pairs.append(f"{k}={v}")
    return " | ".join(pairs)


def render_receipt_csv(order: Order) -> bytes:
    """
    Zwraca bytes (UTF-8 z BOM, przyjazne dla Excela).
    Sekcje:
      - nagłówek (dokument, sklep, daty, klient)
      - pozycje
      - wysyłki (jeśli są)
      - podsumowanie
    """
    out = io.StringIO(newline="")
    w = csv.writer(out)

    cust = order.customer_snapshot or {}
    addr = cust.get("address", {}) if isinstance(cust.get("address", {}), dict) else {}

    # ===== NAGŁÓWEK =====
    w.writerow(["Dokument", "Przyjęcie skupu"])
    w.writerow(["ID", order.public_id])
    w.writerow(["Sklep", getattr(order.seller_profile, "company_name", "")])
    w.writerow(["Data przyjęcia", str(order.purchase_date or getattr(order, "created_at", ""))])

    full_name = f"{cust.get('first_name','')} {cust.get('last_name','')}".strip()
    w.writerow([])
    w.writerow(["Klient", full_name])
    w.writerow(["E-mail", cust.get("email", "")])
    w.writerow(["Telefon", cust.get("phone", "")])
    w.writerow(["Adres", f"{addr.get('line1','')} {addr.get('line2','')}".strip()])
    w.writerow(["Kod / Miasto", f"{addr.get('postal_code','')} {addr.get('city','')}".strip()])
    w.writerow(["Kraj", addr.get("country","")])
    doc = cust.get("document", {}) if isinstance(cust.get("document", {}), dict) else {}
    if doc.get("number"):
        w.writerow(["Dokument tożsamości", f"{doc.get('type','')} {doc.get('number','')}".strip()])

    # ===== POZYCJE =====
    w.writerow([])
    w.writerow(["POZYCJE"])
    w.writerow(["Lp.", "Tytuł", "Ilość", "Cena jedn.", "Suma", "Atrybuty / Uwagi"])

    lines = list(order.order_lines.all())
    for i, l in enumerate(lines, start=1):
        snap = l.item_snapshot or {}
        title = snap.get("title") or snap.get("set_name") or getattr(getattr(l, "item_set", None), "set_name", "") or "Pozycja"
        attrs = _attr_str(snap.get("attributes") or {})
        notes = snap.get("notes", "")
        extra = f"{attrs} | {notes}".strip(" |")
        w.writerow([
            i,
            title,
            l.quantity,
            _money(l.unit_price),
            _money(l.line_total),
            extra,
        ])

    # ===== WYSYŁKI (jeśli są) =====
    shippings = list(order.shippings.select_related("package_type", "order_line"))
    if shippings:
        # mapowanie: order_line_id -> lp (żeby w CSV dać numer pozycji)
        pos_by_line_id = {ln.id: i for i, ln in enumerate(lines, start=1)}

        w.writerow([])
        w.writerow(["WYSYŁKI"])
        w.writerow(["Pozycja (Lp.)", "Tracking", "Etykieta", "Metoda", "Cena", "Status"])
        for s in shippings:
            line_no = pos_by_line_id.get(getattr(s.order_line, "id", None), "")
            label = (s.package_label or "").strip()
            if (not s.package_type) or label.upper() == "PICKUP":
                label = "Odbiór osobisty"
            method = str(s.package_type) if s.package_type else "Odbiór osobisty"
            w.writerow([
                line_no,
                s.tracking_number or "",
                label,
                method,
                _money(s.price),
                s.shipping_status,
            ])

    # ===== PODSUMOWANIE =====
    w.writerow([])
    w.writerow(["PODSUMOWANIE"])
    w.writerow(["Suma pozycji", _money(order.items_total)])
    w.writerow(["Suma wysyłek", _money(order.shipping_total)])
    w.writerow(["Razem", _money(order.purchase_cost)])

    # UTF-8 z BOM dla Excela
    csv_text = out.getvalue()
    return csv_text.encode("utf-8-sig")

def export_orders_csv(orders) -> bytes:
    """
    Eksport listy zamówień (UTF-8 z BOM, przyjazne dla Excela).
    Nagłówki po angielsku (PL poniżej w komentarzu).
    """
    out = io.StringIO(newline="")
    w = csv.writer(out)

    # EN headers:
    w.writerow([
        "public_id", "status", "payment_method", "purchase_date",
        "items_total", "shipping_total", "purchase_cost", "tx_type", "customer"
    ])
    # PL:
    # w.writerow(["ID", "Status", "Metoda płatności", "Data zakupu",
    #             "Suma pozycji", "Wysyłka", "Razem", "Typ transakcji", "Klient"])

    for o in orders:
        snap = o.customer_snapshot or {}
        full_name = f"{snap.get('first_name','')} {snap.get('last_name','')}".strip()
        tx_type = getattr(getattr(o, "transaction", None), "type", "") or ""
        w.writerow([
            o.public_id,
            o.order_status,
            o.payment_method,
            str(o.purchase_date or ""),
            _money(o.items_total),
            _money(o.shipping_total),
            _money(o.purchase_cost),
            tx_type,
            full_name,
        ])

    return out.getvalue().encode("utf-8-sig")
