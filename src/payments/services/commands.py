from __future__ import annotations
from decimal import Decimal
import secrets
from collections import defaultdict
from uuid import UUID

from django.conf import settings
from django.db import transaction as dbtx, IntegrityError
from djmoney.money import Money
from django.utils import timezone
from datetime import timedelta

from django.db.models import Sum, Max
from django.db.models.functions import Coalesce

from orders.models import OrderLine, ItemReservation
from orders.services import repositories as order_repo
from listings.models import ItemSet
from payments.models import Payment
from payments.payments_integrations.stripe_client import StripeClient
from payments.services import repositories as repo
from payments.services.exceptions import Conflict, Forbidden, DomainError, NotFound
from transactions.models import Transaction
from transactions.services.commands import set_transaction_status, attach_coupon_and_recalculate

from coupons.services.points_backend import add_points as loyalty_add_points

_ACTIVE = ("REQUIRES_CONFIRMATION", "REQUIRES_ACTION", "PROCESSING")

@dbtx.atomic
def mark_payment_processing(*, payment: Payment, reason: str = "") -> Payment:
    payment = Payment.objects.select_for_update().select_related("transaction").get(pk=payment.pk)

    cancel_active_payments_for_tx(
        tx=payment.transaction,
        reason=reason or "Stripe: processing",
        exclude_payment_id=payment.pk,
    )

    if payment.status not in ("SUCCEEDED", "FAILED", "CANCELLED") and payment.status != "PROCESSING":
        payment.status = "PROCESSING"
        payment.save(update_fields=["status", "updated_at"])

    return payment

@dbtx.atomic
def mark_payment_requires_action(*, payment: Payment, reason: str = "") -> Payment:
    payment = Payment.objects.select_for_update().select_related("transaction").get(pk=payment.pk)

    cancel_active_payments_for_tx(
        tx=payment.transaction,
        reason=reason or "Stripe: requires_action",
        exclude_payment_id=payment.pk,
    )

    if payment.status != "REQUIRES_ACTION":
        payment.status = "REQUIRES_ACTION"
        payment.save(update_fields=["status", "updated_at"])

    return payment

def _assert_item_buyable_for_payment(item: ItemSet) -> None:
    if item.status != "AVAILABLE":
        raise Conflict("Ogłoszenie nie jest dostępne.")
    if item.listing_type != "BUY" or not item.allow_online_checkout:
        raise Forbidden("To ogłoszenie nie obsługuje zakupu online.")
    if not item.seller_profile_id:
        raise Conflict("Oferta nie ma przypisanego sprzedawcy.")


def _purchase_need_by_item_id(tx: Transaction) -> dict[int, int]:
    rows = (
        OrderLine.objects
        .filter(order__transaction=tx, item_set_id__isnull=False)
        .values_list("item_set_id", "quantity")
    )
    out: dict[int, int] = defaultdict(int)
    for item_id, qty in rows:
        if item_id is None or not qty:
            continue
        out[int(item_id)] += int(qty)
    return dict(out)


def _assert_reservation_refresh_window(*, tx: Transaction) -> None:
    now = timezone.now()
    last_exp = (
        ItemReservation.objects
        .filter(transaction=tx)
        .order_by("-expires_at")
        .values_list("expires_at", flat=True)
        .first()
    )
    if last_exp and last_exp <= now and (now - last_exp) > timedelta(hours=1):
        raise Conflict("Rezerwacja wygasła zbyt dawno. Złóż zamówienie ponownie.")


def _ensure_purchase_tx_stock_available_and_reserve(*, tx: Transaction) -> None:
    need_by_item_id = _purchase_need_by_item_id(tx)
    if not need_by_item_id:
        raise DomainError("Brak pozycji w zamówieniu.")

    item_ids = list(need_by_item_id.keys())

    locked_items = order_repo.lock_itemsets_for_update(item_ids)
    locked_by_id = {int(it.id): it for it in locked_items}

    reserved_others = order_repo.active_reserved_qty_by_item_ids(item_ids, exclude_tx_id=tx.id)

    for item_id, need_qty in need_by_item_id.items():
        if need_qty <= 0:
            continue

        item = locked_by_id.get(int(item_id))
        if item is None:
            raise NotFound("Ogłoszenie nie istnieje.")

        _assert_item_buyable_for_payment(item)

        if item.stock_quantity is None:
            raise Conflict("Brak stanu magazynowego dla oferty.")

        stock = int(item.stock_quantity or 0)
        other_reserved = int(reserved_others.get(int(item_id), 0) or 0)
        available = stock - other_reserved
        if available < need_qty:
            raise Conflict(f"Brak dostępnej ilości dla: {item.set_name}.")

    _assert_reservation_refresh_window(tx=tx)

    ttl_seconds = int(getattr(settings, "ORDERS_RESERVATION_TTL_MINUTES", 30)) * 60
    now = timezone.now()
    new_exp = now + timedelta(seconds=ttl_seconds)

    lines = list(
        OrderLine.objects
        .select_for_update()
        .filter(order__transaction=tx, item_set_id__in=item_ids)
        .order_by("id")
    )
    if not lines:
        raise DomainError("Brak pozycji w zamówieniu.")

    line_ids = [ln.id for ln in lines]

    existing = list(
        ItemReservation.objects
        .select_for_update()
        .filter(transaction=tx, order_line_id__in=line_ids, item_set_id__in=item_ids)
        .order_by("-expires_at", "-created_at")
    )
    by_line: dict[int, list[ItemReservation]] = defaultdict(list)
    for r in existing:
        if r.order_line_id:
            by_line[int(r.order_line_id)].append(r)

    keep_ids: set = set()

    for ln in lines:
        if ln.item_set_id is None:
            continue

        qty = int(ln.quantity or 0)
        if qty <= 0:
            raise DomainError("Nieprawidłowa ilość w zamówieniu.")

        item = locked_by_id.get(int(ln.item_set_id))
        if item is None:
            raise NotFound("Ogłoszenie nie istnieje.")

        candidates = by_line.get(int(ln.id), [])
        keep = None

        if candidates:
            active_now = [r for r in candidates if r.released_at is None and r.expires_at and r.expires_at > now]
            if active_now:
                keep = active_now[0]
            else:
                active_any = [r for r in candidates if r.released_at is None]
                keep = active_any[0] if active_any else candidates[0]

            extra_ids = [r.id for r in candidates if r.id != keep.id and r.released_at is None]
            if extra_ids:
                ItemReservation.objects.filter(id__in=extra_ids).update(released_at=now)

            ItemReservation.objects.filter(id=keep.id).update(
                item_set_id=item.id,
                quantity=qty,
                expires_at=new_exp,
                released_at=None,
                user=getattr(tx, "user", None),
            )
            keep_ids.add(keep.id)
        else:
            r = order_repo.create_reservation(
                item=item,
                tx=tx,
                line=ln,
                user=getattr(tx, "user", None),
                quantity=qty,
                ttl_seconds=ttl_seconds,
            )
            keep_ids.add(r.id)

    qs_orphans = ItemReservation.objects.select_for_update().filter(transaction=tx, released_at__isnull=True)
    if keep_ids:
        qs_orphans = qs_orphans.exclude(id__in=list(keep_ids))
    qs_orphans.update(released_at=now)

def _orders_gross(tx: Transaction) -> Money:
    cur = tx.expected_total_currency or "PLN"
    total = Money(0, cur)
    for o in tx.orders.all():
        gt = o.grand_total
        if gt.currency != total.currency:
            gt = Money(gt.amount, total.currency)
        total += gt
    return total


def _calc_points_for_amount(amount: Money) -> int:
    # domyślnie 200 bps (2%)
    bps = int(getattr(settings, "LOYALTY_RATE_BPS", 200))
    rate = Decimal(bps) / Decimal("10000")
    return max(int(Decimal(amount.amount) * rate), 0)


def _award_points_after_success(payment: Payment) -> int:
    # tylko za PURCHASE
    if getattr(payment.transaction, "type", "") != "PURCHASE":
        return 0
    pts = _calc_points_for_amount(payment.amount)
    if pts > 0:
        loyalty_add_points(payment.transaction.user, pts, reason=f"Zakup: {payment.public_id}")
        md = dict(payment.metadata or {})
        md["loyalty_points_awarded"] = pts
        payment.metadata = md
        payment.save(update_fields=["metadata", "updated_at"])
    return pts


def _notify_order_confirmed(payment: Payment) -> None:
    # tylko zakupy online
    if getattr(payment.transaction, "type", "") != "PURCHASE":
        return
    try:
        orders = list(payment.transaction.orders.all())
        if not orders:
            return
        from orders.services.notifications import notify_order_confirmed
        notify_order_confirmed(user=payment.transaction.user, orders=orders)
    except Exception:
        # notyfikacja nie może blokować płatności
        pass


# --------- funkcje domenowe wywoływane z API i z confirm() ---------

@dbtx.atomic
def mark_payment_failed_or_cancelled(*, payment: Payment, status: str, reason: str = "") -> Payment:
    assert status in ("FAILED", "CANCELLED")
    if payment.status != status:
        payment.status = status
        payment.save(update_fields=["status", "updated_at"])
    return payment

# --------- create/confirm/cancel ---------

@dbtx.atomic
def create_payment_for_transaction(
    *,
    tx: Transaction,
    provider: str | None = None,
    coupon_code: str | None = None,
    user_coupon_public_id: str | None = None,
) -> Payment:
    tx = Transaction.objects.select_for_update().get(pk=tx.pk)

    if tx.status != "PENDING":
        raise Forbidden("Nie można inicjować płatności dla transakcji, która nie jest w statusie Oczekująca.")

    ACTIVE = ("REQUIRES_CONFIRMATION", "REQUIRES_ACTION", "PROCESSING")
    existing = (
        Payment.objects
        .select_for_update()
        .filter(transaction=tx, status__in=ACTIVE)
        .order_by("-created_at")
        .first()
    )
    if existing:
        return existing

    if tx.type == "PURCHASE":
        _ensure_purchase_tx_stock_available_and_reserve(tx=tx)

        for o in tx.orders.all():
            for ln in o.order_lines.select_related("shipping"):
                ship = getattr(ln, "shipping", None)
                if ship is None or ship.price is None:
                    raise DomainError("Wybierz formę wysyłki dla wszystkich pozycji zamówienia, zanim przejdziesz do płatności.")

        from orders.services.commands import _addr_ok as _order_addr_ok
        for o in tx.orders.all():
            any_package = any(
                (getattr(getattr(ln, "shipping", None), "package_type_id", None) is not None)
                for ln in o.order_lines.all()
            )
            if any_package and not _order_addr_ok(o.shipping_address):
                raise DomainError("Uzupełnij adres dostawy dla zamówień z wysyłką.")
    else:
        coupon_code = None
        user_coupon_public_id = None

    if tx.type == "PURCHASE" and (coupon_code or user_coupon_public_id):
        tx = attach_coupon_and_recalculate(
            transaction=tx,
            coupon_code=coupon_code or None,
            user_coupon_public_id=user_coupon_public_id or None,
        )

    amount = Money(tx.expected_total_amount or 0, tx.expected_total_currency or "PLN")
    if amount.amount is None or amount.amount <= 0:
        raise DomainError("Kwota płatności musi być dodatnia.")

    cur = tx.expected_total_currency or "PLN"
    gross = Money(0, cur)
    for o in tx.orders.all():
        gt = o.grand_total
        if gt.currency != gross.currency:
            gt = Money(gt.amount, gross.currency)
        gross += gt

    discount = gross - amount if gross.amount > 0 else Money(0, amount.currency)

    coupon_meta = None
    if tx.type == "PURCHASE" and (tx.user_coupon_id or tx.coupon_id):
        mode = "user_coupon" if tx.user_coupon_id else "code"
        coupon_meta = {
            "mode": mode,
            "coupon_public_id": getattr(tx.coupon, "public_id", "") if tx.coupon_id else "",
            "user_coupon_public_id": getattr(tx.user_coupon, "public_id", "") if tx.user_coupon_id else "",
            "code": (tx.coupon.code if (tx.coupon_id and tx.coupon.code) else ""),
            "discount": str(discount.amount),
            "currency": str(discount.currency),
        }

    req = (provider or "").upper()
    if req not in ("SIM", "STRIPE"):
        req = ""

    stripe_possible = bool(getattr(settings, "STRIPE_SECRET_KEY", "")) and bool(getattr(settings, "STRIPE_PUBLISHABLE_KEY", ""))

    if req == "STRIPE" and stripe_possible:
        final_provider = "STRIPE"
    elif req == "SIM":
        final_provider = "SIM"
    else:
        final_provider = "STRIPE" if stripe_possible else "SIM"

    try:
        if final_provider == "STRIPE":
            try:
                client = StripeClient()
                provider_payment_id, client_secret = client.create_intent(tx_public_id=tx.public_id, amount=amount)
                pay = repo.create_payment(
                    tx=tx,
                    provider="STRIPE",
                    amount=amount,
                    status="REQUIRES_CONFIRMATION",
                    provider_payment_id=provider_payment_id,
                    client_secret=client_secret,
                    metadata={"tx_public_id": tx.public_id, "coupon": coupon_meta, "discount_applied": str(discount.amount)},
                )
                return pay
            except Exception:
                final_provider = "SIM"

        pay = repo.create_payment(
            tx=tx,
            provider=final_provider,
            amount=amount,
            status="REQUIRES_CONFIRMATION",
            client_secret=secrets.token_urlsafe(16),
            metadata={"tx_public_id": tx.public_id, "coupon": coupon_meta, "discount_applied": str(discount.amount)},
        )
        return pay
    except IntegrityError as e:
        revived = (
            Payment.objects
            .filter(transaction=tx, status__in=ACTIVE)
            .order_by("-created_at")
            .first()
        )
        if revived:
            return revived
        raise Conflict("Istnieje już aktywna płatność dla tej transakcji.") from e

@dbtx.atomic
def mark_payment_succeeded(*, payment: Payment, reason: str = "") -> Payment:
    if payment.status != "SUCCEEDED":
        payment.status = "SUCCEEDED"
        payment.save(update_fields=["status","updated_at"])
    active_others = (Payment.objects
                     .select_for_update()
                     .filter(transaction=payment.transaction, status__in=("REQUIRES_CONFIRMATION","REQUIRES_ACTION","PROCESSING"))
                     .exclude(pk=payment.pk))
    for p in active_others:
        md = dict(p.metadata or {})
        md["auto_cancelled_due_to_success"] = True
        p.metadata = md
        p.status = "CANCELLED"
        p.save(update_fields=["status","metadata","updated_at"])
    if payment.transaction.status != "COMPLETED":
        set_transaction_status(tx=payment.transaction, to_status="COMPLETED", reason=reason or "Payment succeeded")
    tx_type = getattr(payment.transaction, "type", "")
    if tx_type == "PAWN_EXTENSION":
        try:
            from pawns.services.commands import finalize_extension_after_payment
            finalize_extension_after_payment(tx=payment.transaction)
        except Exception:
            pass
    pts = _calc_points_for_amount(payment.amount) if getattr(payment.transaction, "type", "") == "PURCHASE" else 0
    if getattr(payment.transaction, "type", "") == "PURCHASE":
        if pts > 0:
            loyalty_add_points(payment.transaction.user, pts, reason=f"Zakup: {payment.public_id}")
            md = dict(payment.metadata or {})
            md["loyalty_points_awarded"] = pts
            payment.metadata = md
            payment.save(update_fields=["metadata","updated_at"])
        _notify_order_confirmed(payment)
    return payment

@dbtx.atomic
def confirm_payment_simulator(*, payment: Payment, succeed: bool) -> Payment:
    if payment.status not in ("REQUIRES_CONFIRMATION", "PROCESSING"):
        return payment

    payment.status = "PROCESSING"
    payment.save(update_fields=["status", "updated_at"])

    if succeed:
        return mark_payment_succeeded(payment=payment, reason="Payment succeeded")
    else:
        return mark_payment_failed_or_cancelled(payment=payment, status="FAILED", reason="Payment failed")


@dbtx.atomic
def confirm_payment(*, payment: Payment, succeed: bool | None = None) -> Payment:
    if payment.provider == "SIM":
        return confirm_payment_simulator(payment=payment, succeed=bool(succeed))
    # inni providerzy - czekamy na webhook
    return payment


@dbtx.atomic
def cancel_active_payment(*, payment: Payment, reason: str = "") -> Payment:
    if payment.status in ("SUCCEEDED", "FAILED", "CANCELLED"):
        return payment
    return mark_payment_failed_or_cancelled(payment=payment, status="CANCELLED", reason=reason or "Payment cancelled")


@dbtx.atomic
def expire_stale_payments(*, minutes: int = 30) -> int:
    from django.utils import timezone
    from django.db.models import Q
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(minutes=minutes)
    qs = Payment.objects.select_related("transaction").filter(
        Q(status="REQUIRES_CONFIRMATION") | Q(status="PROCESSING"),
        updated_at__lt=cutoff,
    )
    cnt = 0
    for p in qs:
        cancel_active_payment(payment=p, reason="Expired")
        cnt += 1
    return cnt


@dbtx.atomic
def cancel_active_payments_for_tx(*, tx: Transaction, reason: str = "", exclude_payment_id: UUID | None = None) -> bool:
    qs = Payment.objects.select_for_update().filter(transaction=tx, status__in=_ACTIVE)
    if exclude_payment_id:
        qs = qs.exclude(pk=exclude_payment_id)

    cancelled = False
    for p in qs:
        md = dict(p.metadata or {})
        md["auto_cancelled_due_to_change"] = True
        if reason:
            md["auto_cancel_reason"] = reason
        p.metadata = md
        p.status = "CANCELLED"
        p.save(update_fields=["status", "metadata", "updated_at"])
        cancelled = True

    return cancelled
