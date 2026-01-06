from __future__ import annotations
from typing import Optional, Iterable
from datetime import timedelta
from django.db import transaction as dbtx
from django.utils import timezone
from djmoney.money import Money

from catalog.models import ItemType
from pawns.models import Pawn, PawnExtension
from pawns.services import repositories as repo
from pawns.services.fees import calc_extension_fee
from pawns.services.exceptions import DomainError, Conflict
from orders.services._party import snapshot_from_customer, snapshot_from_user, snapshot_from_customer, make_customer_snapshot
from listings.models import ItemSet
from transactions.models import Transaction
from customers.models import Customer

def _snapshot_from_itemset(it: ItemSet, unit_price: Optional[Money]) -> dict:
    price_money = unit_price or getattr(it, "price", None)
    price_amount = str(price_money.amount) if (price_money and price_money.amount is not None) else None
    price_currency = str(price_money.currency) if price_money else None

    return {
        "public_id": it.public_id,
        "set_name": it.set_name,
        "slug": it.slug,
        "description": it.description,
        "price": price_amount,
        "currency": price_currency,
        "condition": it.condition,
        "length_cm": it.length_cm, "width_cm": it.width_cm, "height_cm": it.height_cm,
        "weight_kg": (str(it.weight_kg) if it.weight_kg is not None else None),
        "type_path": (it.type.path if it.type_id else None),
        "catalog_item_public_id": (it.catalog_item.public_id if getattr(it, "catalog_item_id", None) else None),
        "attributes": (it.attributes or {}),
        "seller_slug": (it.seller_profile.slug if it.seller_profile_id else None),
    }



def pawn_is_expired(pawn: Pawn) -> bool:
    return timezone.now().date() > pawn.due_date and pawn.status == "ACTIVE"


def _is_leaf_itemtype(itype: ItemType) -> bool:
    return not ItemType.objects.filter(parent_id=itype.id).exists()


def _pick_itemtype_for_listing(pawn: Pawn) -> Optional[ItemType]:
    lines = list(pawn.lines.select_related("item_set__type").all())
    for ln in lines:
        if ln.item_set_id and getattr(ln.item_set, "type_id", None):
            itype = ln.item_set.type
            if itype and _is_leaf_itemtype(itype):
                return itype
    for ln in lines:
        snap = ln.item_snapshot or {}
        path = (snap.get("type_path") or "").strip()
        if not path:
            continue
        itype = ItemType.objects.filter(path=path).first()
        if itype and _is_leaf_itemtype(itype):
            return itype
    return None


@dbtx.atomic
def create_pawn(
    *,
    operator,
    seller,
    principal: Money,
    due_in_days: int = 30,
    customer=None,
    customer_snapshot_override: Optional[dict] = None,
    lines: Iterable[dict],  # [{"title","description","quantity","appraisal_value":Money,"item_set":ItemSet|None}]
) -> Pawn:
    """
    Tworzy transakcję PLEDGE + Pawn + linie. Zastaw jest ACTIVE.
    """
    # 1) TX (offline, natychmiast)
    tx = repo.create_transaction(
        user=operator, type="PLEDGE", status="COMPLETED",
        expected_total_amount=0, expected_total_currency=str(principal.currency)
    )

    # 2) Snapshot klienta
    if customer:
        cust_snapshot = snapshot_from_customer(customer)
    elif customer_snapshot_override:
        cust_snapshot = customer_snapshot_override
    else:
        cust_snapshot = snapshot_from_user(operator)

    pawn = repo.create_pawn(
        tx=tx, seller=seller, operator=operator,
        customer=customer, customer_snapshot=cust_snapshot,
        principal=principal, start_date=timezone.now().date(),
        due_date=(timezone.now().date() + timedelta(days=due_in_days)),
    )

    # 3) Linie
    for row in lines:
        iset = row.get("item_set")
        title = row.get("title") or (iset.set_name if iset else "Pozycja")
        snap = _snapshot_from_itemset(iset, unit_price=row.get("appraisal_value")) if iset else (row.get("item_snapshot") or {})
        repo.add_pawn_line(
            pawn=pawn, item_set=iset, title=title,
            description=row.get("description",""), quantity=int(row.get("quantity", 1)),
            appraisal_value=row.get("appraisal_value"), item_snapshot=snap
        )

    pawn.recalc_appraisal(save=True)
    return pawn


@dbtx.atomic
def extend_pawn(*, pawn: Pawn, days: int, operator) -> None:
    """
    Przedłuża aktywny zastaw o 7/14/30 dni. Księguje opłatę.
    """
    if pawn.status != "ACTIVE":
        raise Conflict("Nie można przedłużyć nieaktywnego zastawu.")
    if pawn_is_expired(pawn):
        raise Conflict("Zastaw wygasł - nie można przedłużyć.")
    if days not in (7, 14, 30):
        raise DomainError("Dozwolone przedłużenia: 7/14/30 dni.")

    fee = calc_extension_fee(principal=pawn.principal, days=days)

    # transakcja opłaty
    tx = repo.create_transaction(
        user=operator, type="PAWN_EXTENSION", status="COMPLETED",
        expected_total_amount=fee.amount, expected_total_currency=str(fee.currency)
    )

    prev = pawn.due_date
    pawn.due_date = pawn.due_date + timedelta(days=days)
    pawn.save(update_fields=["due_date","updated_at"])

    repo.create_extension(
        pawn=pawn, days=days, fee=fee,
        previous_due=prev, new_due=pawn.due_date,
        tx=tx, operator=operator
    )


@dbtx.atomic
def redeem_pawn(*, pawn: Pawn, operator) -> Pawn:
    """
    Wykup: klient spłaca kapitał (procenty w extension fee).
    """
    if pawn.status != "ACTIVE":
        raise Conflict("Zastaw nie jest aktywny.")
    principal = pawn.principal
    repo.create_transaction(
        user=operator, type="PAWN_REDEEM", status="COMPLETED",
        expected_total_amount=principal.amount, expected_total_currency=str(principal.currency)
    )
    pawn.status = "REDEEMED"
    pawn.redeemed_at = timezone.now()
    pawn.save(update_fields=["status","redeemed_at","updated_at"])
    return pawn


@dbtx.atomic
def forfeit_pawn(*, pawn: Pawn, operator, create_listing: bool = True) -> Pawn:
    if pawn.status != "ACTIVE":
        raise Conflict("Zastaw nie jest aktywny.")
    if not pawn_is_expired(pawn):
        raise Conflict("Zastaw jeszcze nie wygasł.")

    pawn.status = "FORFEITED"
    pawn.forfeited_at = timezone.now()
    pawn.save(update_fields=["status", "forfeited_at", "updated_at"])

    if not create_listing:
        return pawn

    if pawn.forfeited_item_id:
        return pawn

    itype = _pick_itemtype_for_listing(pawn)
    if not itype:
        raise Conflict("Brak kategorii (ItemType) w liniach zastawu. Nie można utworzyć ogłoszenia. Użyj create_listing=false.")

    first_line = pawn.lines.select_related("item_set__type").first()

    item = ItemSet.objects.create(
        set_name=(first_line.title if first_line else "Towar z zastawu"),
        description="Wystawione z zastawu.",
        price=pawn.appraisal_total,
        stock_quantity=1,
        condition="USED",
        status="RESERVED",
        listing_type="BUY",
        allow_online_checkout=False,
        added_by="STAFF",
        seller_profile=pawn.seller_profile,
        type=itype,
        attributes={},
    )

    pawn.forfeited_item = item
    pawn.save(update_fields=["forfeited_item", "updated_at"])
    return pawn

@dbtx.atomic
def create_extension_transaction(*, pawn: Pawn, days: int, operator) -> Transaction:
    """
    Tworzy PENDING Transaction (PAWN_EXTENSION) dla online płatności.
    Nie zmienia jeszcze Pawn.due_date - to nastąpi po SUCCEEDED płatności.
    """
    if pawn.status != "ACTIVE":
        raise Conflict("Zastaw nie jest aktywny.")
    if pawn_is_expired(pawn):
        raise Conflict("Zastaw wygasł - nie można przedłużyć.")
    if days not in (7, 14, 30):
        raise DomainError("Dozwolone przedłużenia: 7/14/30 dni.")

    fee = calc_extension_fee(principal=pawn.principal, days=days)

    tx = repo.create_transaction(
        user=operator, type="PAWN_EXTENSION", status="PENDING",
        expected_total_amount=fee.amount, expected_total_currency=str(fee.currency)
    )


    # zapisz kontekst w tx.notes (lekki i bez nowej tabeli)
    tx.customer = pawn.customer
    tx.customer_snapshot = pawn.customer_snapshot
    tx.notes = f"PAWN_EXT:{pawn.public_id}:{int(days)}"
    tx.save(update_fields=["notes", "updated_at"])
    tx.save(update_fields=["customer","customer_snapshot","notes","updated_at"])
    return tx


@dbtx.atomic
def finalize_extension_after_payment(*, tx: Transaction) -> Optional[Pawn]:
    """
    Idempotentnie finalizuje przedłużenie po COMPLETED transakcji PAWN_EXTENSION.
    Tworzy PawnExtension i przesuwa due_date.
    """
    if tx.type != "PAWN_EXTENSION" or tx.status != "COMPLETED":
        return None

    # idempotencja – jeśli Extension już istnieje dla tej TX, nic nie rób
    existing = PawnExtension.objects.filter(transaction=tx).select_related("pawn").first()
    if existing:
        return existing.pawn

    # z parsowanego notes odczytujemy kontekst
    note = (tx.notes or "").strip()
    try:
        prefix, pawn_pid, days_s = note.split(":", 2)
    except Exception:
        return None
    if prefix != "PAWN_EXT":
        return None

    pawn = Pawn.objects.select_for_update().filter(public_id=pawn_pid).first()
    if not pawn:
        return None
    if pawn.status != "ACTIVE" or pawn_is_expired(pawn):
        # nic nie robimy – wedle polityki biznesowej można tu dodać zwrot/alert
        return None

    days = int(days_s)
    fee = calc_extension_fee(principal=pawn.principal, days=days)

    prev = pawn.due_date
    pawn.due_date = pawn.due_date + timedelta(days=days)
    pawn.save(update_fields=["due_date", "updated_at"])

    repo.create_extension(
        pawn=pawn, days=days, fee=fee,
        previous_due=prev, new_due=pawn.due_date,
        tx=tx, operator=tx.user
    )
    return pawn

@dbtx.atomic
def attach_customer_to_pawn(*, pawn: Pawn, customer: Customer, update_snapshot: bool = True) -> Pawn:
    pawn.customer = customer
    if update_snapshot:
        pawn.customer_snapshot = snapshot_from_customer(customer)
    pawn.save(update_fields=["customer", "customer_snapshot", "updated_at"])
    return pawn

@dbtx.atomic
def detach_customer_from_pawn(*, pawn: Pawn) -> Pawn:
    pawn.customer = None
    pawn.save(update_fields=["customer", "updated_at"])
    return pawn

@dbtx.atomic
def ensure_customer_for_pawn(
    *,
    pawn: Pawn,
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    phone: str = "",
    address: dict | None = None,
    document_type: str = "",
    document_number: str = "",
    birth_date = None,
    allow_update_email: bool = False,
    allow_update_phone: bool = False,
):
    """
    Heurystyka
    - match po email/telefonie -> attach
    - konflikt (dwa różne) -> 409 + candidates
    - brak -> create + attach
    - uzupełniamy TYLKO puste pola (chyba że allow_update_* = True)
    """
    email = (email or "").strip()
    phone = (phone or "").strip()

    c_by_email = Customer.objects.filter(email__iexact=email).first() if email else None
    c_by_phone = Customer.objects.filter(phone=phone).first() if phone else None

    cand = None
    if c_by_email and c_by_phone and c_by_email.id != c_by_phone.id:
        # konflikt
        return {"result": "conflict", "candidates": [
            {"public_id": c_by_email.public_id, "first_name": c_by_email.first_name, "last_name": c_by_email.last_name,
             "email": c_by_email.email, "phone": c_by_email.phone, "city": c_by_email.city},
            {"public_id": c_by_phone.public_id, "first_name": c_by_phone.first_name, "last_name": c_by_phone.last_name,
             "email": c_by_phone.email, "phone": c_by_phone.phone, "city": c_by_phone.city},
        ]}
    cand = c_by_email or c_by_phone

    if cand:
        dirty = False
        if not cand.first_name and first_name:
            cand.first_name = first_name; dirty = True
        if not cand.last_name and last_name:
            cand.last_name = last_name; dirty = True
        if allow_update_email and email and (cand.email or "").lower() != email.lower():
            cand.email = email; dirty = True
        if allow_update_phone and phone and cand.phone != phone:
            cand.phone = phone; dirty = True

        if address:
            if not cand.address_line1 and address.get("line1"): cand.address_line1 = address["line1"]; dirty = True
            if not cand.address_line2 and address.get("line2"): cand.address_line2 = address["line2"]; dirty = True
            if not cand.postal_code and address.get("postal_code"): cand.postal_code = address["postal_code"]; dirty = True
            if not cand.city and address.get("city"): cand.city = address["city"]; dirty = True
            if not cand.country and address.get("country"): cand.country = address["country"]; dirty = True
        if not cand.document_type and document_type: cand.document_type = document_type; dirty = True
        if not cand.document_number and document_number: cand.document_number = document_number; dirty = True
        if not cand.birth_date and birth_date: cand.birth_date = birth_date; dirty = True
        if dirty: cand.save()

        attach_customer_to_pawn(pawn=pawn, customer=cand, update_snapshot=True)
        return {"result": "attached", "customer_public_id": cand.public_id}

    # brak dopasowania -> create
    newc = Customer.objects.create(
        first_name=first_name, last_name=last_name, email=email, phone=phone,
        address_line1=(address or {}).get("line1",""),
        address_line2=(address or {}).get("line2",""),
        postal_code=(address or {}).get("postal_code",""),
        city=(address or {}).get("city",""),
        country=(address or {}).get("country",""),
        document_type=document_type, document_number=document_number, birth_date=birth_date,
    )
    attach_customer_to_pawn(pawn=pawn, customer=newc, update_snapshot=True)
    return {"result": "created", "customer_public_id": newc.public_id}