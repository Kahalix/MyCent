from __future__ import annotations
import csv
import io
from typing import Any, Dict
from djmoney.money import Money
from pawns.models import Pawn

def _money(m: Money | None) -> str:
    if not m: return ""
    return f"{m.amount:.2f} {m.currency}"

def _attr_str(attrs: Dict[str, Any] | None) -> str:
    if not attrs: return ""
    parts = []
    for k, v in attrs.items():
        if v is None: continue
        parts.append(f"{k}={v}")
    return " | ".join(parts)

def render_receipt_csv(pawn: Pawn) -> bytes:
    out = io.StringIO(newline="")
    w = csv.writer(out)

    cust = pawn.customer_snapshot or {}
    addr = cust.get("address", {}) if isinstance(cust.get("address", {}), dict) else {}

    # NAGŁÓWEK
    w.writerow(["Dokument", "Umowa zastawu"])
    w.writerow(["ID", pawn.public_id])
    w.writerow(["Sklep", getattr(pawn.seller_profile, "company_name", "")])
    w.writerow(["Data początku", str(pawn.start_date)])
    w.writerow(["Termin wykupu", str(pawn.due_date)])
    w.writerow(["Status", pawn.status])

    # Klient
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

    # POZYCJE
    w.writerow([])
    w.writerow(["POZYCJE ZASTAWU"])
    w.writerow(["Lp.", "Opis", "Ilość", "Wycena", "Atrybuty / Uwagi"])
    lines = list(pawn.lines.all())
    for i, ln in enumerate(lines, start=1):
        snap = ln.item_snapshot or {}
        attrs = _attr_str(snap.get("attributes") or {})
        notes = (ln.description or snap.get("notes","")).strip()
        extra = " | ".join([p for p in [attrs, notes] if p]).strip(" |")
        w.writerow([i, ln.title or "Pozycja", ln.quantity, _money(ln.appraisal_value), extra])

    # PRZEDŁUŻENIA
    exs = list(pawn.extensions.all())
    if exs:
        w.writerow([])
        w.writerow(["PRZEDŁUŻENIA"])
        w.writerow(["Dni", "Opłata", "Poprzedni termin", "Nowy termin", "Utworzono"])
        for ex in exs:
            w.writerow([ex.days, _money(ex.fee), str(ex.previous_due), str(ex.new_due), str(ex.created_at.date())])

    # PODSUMOWANIE
    w.writerow([])
    w.writerow(["PODSUMOWANIE"])
    w.writerow(["Suma wycen", _money(pawn.appraisal_total)])
    w.writerow(["Kapitał (wypłacony)", _money(pawn.principal)])

    return out.getvalue().encode("utf-8-sig")

def export_pawns_csv(pawns) -> bytes:
    """
    Lista zastawów (np. do eksportu z widoku listy).
    """
    out = io.StringIO(newline="")
    w = csv.writer(out)
    # w.writerow(["ID", "Status", "Kapitał", "Wycena", "Data początku", "Termin wykupu", "Klient"])
    w.writerow(["public_id","status","principal","appraisal_total","start_date","due_date","customer"])
    for p in pawns:
        full_name = (p.customer_snapshot.get("first_name","") + " " + p.customer_snapshot.get("last_name","")).strip()
        w.writerow([
            p.public_id, p.status, _money(p.principal), _money(p.appraisal_total),
            str(p.start_date), str(p.due_date), full_name
        ])
    return out.getvalue().encode("utf-8-sig")
