from __future__ import annotations
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from catalog.models import ItemType
from listings.models import ItemSet
from saved.models import SavedSearch, SavedSearchItem, SavedListing
from saved.services.notifications import notify_price_drop
from saved.services.queries import run_saved_query  # <<- używamy filtra opartego o query_string


def _descendants_types(category_path: str):
    if not (category_path or "").strip():
        return ItemType.objects.none()
    return ItemType.objects.filter(path__startswith=category_path)

def _since(ss: SavedSearch):
    # skąd zaczynamy liczenie „nowych” - domyślnie data utworzenia
    return ss.since_at or ss.created_at

def _query_for_search(ss: SavedSearch):
    """
    Zwraca queryset NOWYCH ofert (created_at > since) - lekki, bez select_related/prefetch.
    Używany wyłącznie do budowania snapshota (wystarczy PK).
    """
    qstr = (ss.query_string or "").strip()
    if qstr:
        base = run_saved_query(qstr)
    else:
        qs = ItemSet.objects.filter(status="AVAILABLE")
        cat = (ss.category_path or "").strip()
        if cat:
            types = _descendants_types(cat)
            qs = qs.filter(type__in=types)
        phrase = (ss.search_phrase or "").strip()
        if phrase:
            qs = qs.filter(Q(set_name__icontains=phrase) | Q(description__icontains=phrase))
        base = qs

    # Zbij wszystkie wcześniejsze select_related/prefetch z public_itemsets_qs()
    base = base.select_related(None).prefetch_related(None)

    # Tylko nowe
    base = base.filter(created_at__gt=_since(ss))

    return base.only("id").order_by("-created_at")

@transaction.atomic
def refresh_saved_searches(*, limit: int | None = None, prune: bool = False) -> dict:
    """
    Buduje snapshot „nieprzeczytanych” wyników (SavedSearchItem) tylko dla NOWYCH ogłoszeń.
    Nie czyści niczego – czyszczenie następuje dopiero po obejrzeniu wyników (mark-seen).
    """
    qs = SavedSearch.objects.all().order_by("id")
    if limit:
        qs = qs[:limit]
    added = removed = scanned = 0
    for ss in qs:
        scanned += 1
        matches = list(_query_for_search(ss).values_list("id", flat=True))

        existing = set(SavedSearchItem.objects
                       .filter(saved_search=ss)
                       .values_list("item_set_id", flat=True))

        new_ids = [iid for iid in matches if iid not in existing]
        if new_ids:
            SavedSearchItem.objects.bulk_create(
                [SavedSearchItem(saved_search=ss, item_set_id=iid) for iid in new_ids],
                ignore_conflicts=True,
            )
        added += len(new_ids)

        # „prune” nie ma już znaczenia (trzymamy tylko nowe), ale zostawiamy zgodność:
        if prune:
            # nic do prunowania – snapshot to tylko nieprzeczytane
            pass

    return {"scanned": scanned, "added": added, "removed": removed}


@transaction.atomic
def check_price_drops(*, limit: int | None = None, notify: bool = True) -> dict:
    qs = SavedListing.objects.select_related("user", "item_set").order_by("id")
    if limit:
        qs = qs[:limit]

    notified = initialized = scanned = 0
    now = timezone.now()

    for sl in qs:
        scanned += 1
        it = sl.item_set
        if not it or it.status != "AVAILABLE" or it.price is None:
            sl.last_price_checked_at = now
            sl.save(update_fields=["last_price_checked_at"])
            continue

        cur_amount = it.price.amount
        cur_currency = str(it.price.currency)

        if sl.saved_price_amount is None:
            sl.saved_price_amount = cur_amount
            sl.saved_price_currency = cur_currency
            sl.last_price_checked_at = now
            sl.price_drop_notification_sent = False
            sl.save(update_fields=[
                "saved_price_amount", "saved_price_currency",
                "last_price_checked_at", "price_drop_notification_sent"
            ])
            initialized += 1
            continue

        if cur_amount < sl.saved_price_amount and not sl.price_drop_notification_sent:
            if notify:
                notify_price_drop(
                    user=sl.user, item_set=it,
                    old_amount=sl.saved_price_amount, new_amount=cur_amount, currency=cur_currency
                )
            sl.saved_price_amount = cur_amount
            sl.saved_price_currency = cur_currency
            sl.price_drop_notification_sent = True
            sl.last_price_checked_at = now
            sl.save(update_fields=[
                "saved_price_amount", "saved_price_currency",
                "price_drop_notification_sent", "last_price_checked_at"
            ])
            notified += 1
        else:
            # jeśli cena wzrosła – znów pozwól powiadomić przy kolejnym spadku
            if sl.price_drop_notification_sent and cur_amount > sl.saved_price_amount:
                sl.price_drop_notification_sent = False
            sl.last_price_checked_at = now
            sl.save(update_fields=["price_drop_notification_sent", "last_price_checked_at"])

    return {"scanned": scanned, "initialized": initialized, "notified": notified}
