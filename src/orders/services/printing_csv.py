from __future__ import annotations
import csv
import io
from typing import Any, Dict
from collections import defaultdict
from django.utils import timezone
from djmoney.money import Money
from orders.models import Order

def _money(m: Money | None) -> str:
    if not m:
        return ""
    return f"{m.amount:.2f} {m.currency}"

def _attr_str(attrs: Dict[str, Any] | None) -> str:
    if not attrs:
        return ""
    pairs = []
    for k, v in attrs.items():
        if v is None:
            continue
        pairs.append(f"{k}={v}")
    return " | ".join(pairs)

def render_receipt_csv(order: Order) -> bytes:
    out = io.StringIO(newline="")
    w = csv.writer(out)

    cust = order.customer_snapshot or {}
    addr = cust.get("address", {}) if isinstance(cust.get("address", {}), dict) else {}

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
        w.writerow([i, title, l.quantity, _money(l.unit_price), _money(l.line_total), extra])

    shippings = list(order.shippings.select_related("package_type", "order_line"))
    if shippings:
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
            w.writerow([line_no, s.tracking_number or "", label, method, _money(s.price), s.shipping_status])

    w.writerow([])
    w.writerow(["PODSUMOWANIE"])
    w.writerow(["Suma pozycji", _money(order.items_total)])
    w.writerow(["Suma wysyłek", _money(order.shipping_total)])
    w.writerow(["Razem", _money(order.purchase_cost)])

    return out.getvalue().encode("utf-8-sig")

def export_orders_csv(orders) -> bytes:
    out = io.StringIO(newline="")
    w = csv.writer(out)
    w.writerow([
        "public_id", "status", "payment_method", "purchase_date",
        "items_total", "shipping_total", "purchase_cost", "tx_type", "customer"
    ])

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

def export_orders_summary_csv(orders) -> bytes:
    out = io.StringIO(newline="")
    w = csv.writer(out)

    total_count = 0
    base_currency = "PLN"

    totals = {
        "items": None,
        "shipping": None,
        "purchase": None,
    }

    by_status = defaultdict(lambda: {"count": 0, "purchase": None})

    qs = orders
    if hasattr(qs, "prefetch_related"):
        qs = qs.prefetch_related(None)

    it = qs.iterator(chunk_size=2000) if hasattr(qs, "iterator") else iter(qs)

    for o in it:
        total_count += 1
        st = str(getattr(o, "order_status", "") or "")

        itv = getattr(o, "items_total", None)
        sh = getattr(o, "shipping_total", None)
        pu = getattr(o, "purchase_cost", None)

        first_money = itv or sh or pu
        if first_money and base_currency == "PLN":
            base_currency = str(first_money.currency)

        if itv:
            it_eff = itv if str(itv.currency) == base_currency else Money(itv.amount, base_currency)
            totals["items"] = it_eff if totals["items"] is None else (totals["items"] + it_eff)

        if sh:
            sh_eff = sh if str(sh.currency) == base_currency else Money(sh.amount, base_currency)
            totals["shipping"] = sh_eff if totals["shipping"] is None else (totals["shipping"] + sh_eff)

        if pu:
            pu_eff = pu if str(pu.currency) == base_currency else Money(pu.amount, base_currency)
            totals["purchase"] = pu_eff if totals["purchase"] is None else (totals["purchase"] + pu_eff)
            s_pu = by_status[st]["purchase"]
            by_status[st]["purchase"] = pu_eff if s_pu is None else (s_pu + pu_eff)

        by_status[st]["count"] += 1

    w.writerow(["report", "orders_summary"])
    w.writerow(["generated_at", str(timezone.localtime(timezone.now()))])
    w.writerow([])
    w.writerow(["total_orders", str(total_count)])
    w.writerow(["items_total_sum", _money(totals["items"] or Money(0, base_currency))])
    w.writerow(["shipping_total_sum", _money(totals["shipping"] or Money(0, base_currency))])
    w.writerow(["purchase_cost_sum", _money(totals["purchase"] or Money(0, base_currency))])
    w.writerow([])
    w.writerow(["status", "count", "purchase_cost_sum"])

    for st in sorted(by_status.keys()):
        row = by_status[st]
        w.writerow([
            st,
            str(row["count"]),
            _money(row["purchase"] or Money(0, base_currency)),
        ])

    return out.getvalue().encode("utf-8-sig")
