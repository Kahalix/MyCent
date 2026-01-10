from __future__ import annotations

import csv
from decimal import Decimal

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils import timezone

from transactions.models import Transaction, TransactionStatusHistory
from transactions.services.commands import set_transaction_status, cancel_stale_pending_transactions


def _now_stamp() -> str:
    return timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M%S")


def _csv_response(filename: str) -> HttpResponse:
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.write("\ufeff")
    return resp


def _ids(queryset) -> list[int]:
    return list(queryset.values_list("pk", flat=True))


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("public_id", "type", "status", "user", "expected_total_amount", "expected_total_currency", "created_at")
    list_filter = ("status", "type")
    search_fields = ("public_id", "user__email", "notes")
    readonly_fields = ("public_id", "created_at", "updated_at")
    list_select_related = ("user", "customer", "coupon", "user_coupon")
    date_hierarchy = "created_at"
    show_full_result_count = False

    actions = [
        "export_selected_csv",
        "export_summary_csv",
        "set_completed",
        "set_cancelled",
        "set_refunded",
        "service_cancel_stale_pending_60m",
    ]

    def export_selected_csv(self, request, queryset):
        resp = _csv_response(f"transactions_{_now_stamp()}.csv")
        w = csv.writer(resp)
        w.writerow([
            "public_id",
            "type",
            "status",
            "user_id",
            "user_email",
            "customer_id",
            "coupon_id",
            "user_coupon_id",
            "expected_total_amount",
            "expected_total_currency",
            "created_at",
            "updated_at",
            "notes",
        ])

        ids = _ids(queryset)
        qs = Transaction.objects.filter(pk__in=ids).select_related("user", "customer", "coupon", "user_coupon")

        for tx in qs.iterator(chunk_size=2000):
            user = getattr(tx, "user", None)
            w.writerow([
                tx.public_id,
                tx.type,
                tx.status,
                getattr(tx, "user_id", "") or "",
                getattr(user, "email", "") if user else "",
                getattr(tx, "customer_id", "") or "",
                getattr(tx, "coupon_id", "") or "",
                getattr(tx, "user_coupon_id", "") or "",
                str(tx.expected_total_amount) if tx.expected_total_amount is not None else "",
                (tx.expected_total_currency or "").upper(),
                timezone.localtime(tx.created_at).isoformat() if tx.created_at else "",
                timezone.localtime(tx.updated_at).isoformat() if tx.updated_at else "",
                tx.notes or "",
            ])
        return resp

    export_selected_csv.short_description = "Eksport: zaznaczone transakcje → CSV"

    def export_summary_csv(self, request, queryset):
        resp = _csv_response(f"transactions_summary_{_now_stamp()}.csv")
        w = csv.writer(resp)
        w.writerow(["type", "status", "currency", "count", "sum_expected_total_amount"])

        ids = _ids(queryset)
        qs = (
            Transaction.objects.filter(pk__in=ids)
            .only("type", "status", "expected_total_amount", "expected_total_currency")
            .iterator(chunk_size=5000)
        )

        buckets: dict[tuple[str, str, str], dict[str, object]] = {}
        for tx in qs:
            cur = (tx.expected_total_currency or "PLN").upper()
            key = (tx.type, tx.status, cur)
            if key not in buckets:
                buckets[key] = {"count": 0, "sum": Decimal("0")}
            buckets[key]["count"] = int(buckets[key]["count"]) + 1
            amt = tx.expected_total_amount
            if amt is not None:
                buckets[key]["sum"] = Decimal(str(buckets[key]["sum"])) + Decimal(str(amt))

        for (typ, status, cur), agg in sorted(buckets.items()):
            s = Decimal(str(agg["sum"])).quantize(Decimal("0.01"))
            w.writerow([typ, status, cur, agg["count"], str(s)])
        return resp

    export_summary_csv.short_description = "Zestawienie: zaznaczone transakcje (type/status/currency) → CSV"

    def _bulk_set_status(self, request, queryset, to_status: str):
        ok = 0
        bad = 0
        ids = _ids(queryset)
        qs = Transaction.objects.filter(pk__in=ids)
        for tx in qs.iterator(chunk_size=2000):
            try:
                set_transaction_status(tx=tx, to_status=to_status, reason="Admin action")
                ok += 1
            except Exception as e:
                bad += 1
                self.message_user(request, f"{tx.public_id}: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Zmieniono status na {to_status}: {ok}", level=messages.SUCCESS)
        if bad:
            self.message_user(request, f"Błędy: {bad}", level=messages.ERROR)

    def set_completed(self, request, queryset):
        self._bulk_set_status(request, queryset, "COMPLETED")

    set_completed.short_description = "Status: ustaw COMPLETED"

    def set_cancelled(self, request, queryset):
        self._bulk_set_status(request, queryset, "CANCELLED")

    set_cancelled.short_description = "Status: ustaw CANCELLED"

    def set_refunded(self, request, queryset):
        self._bulk_set_status(request, queryset, "REFUNDED")

    set_refunded.short_description = "Status: ustaw REFUNDED"

    def service_cancel_stale_pending_60m(self, request, queryset):
        try:
            cnt = cancel_stale_pending_transactions(minutes=60)
            self.message_user(request, f"Auto-cancel PENDING > 60 min: {cnt}", level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Błąd cancel_stale_pending_transactions: {e}", level=messages.ERROR)

    service_cancel_stale_pending_60m.short_description = "Serwis: anuluj przeterminowane PENDING (TTL 60 min)"


@admin.register(TransactionStatusHistory)
class TransactionStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("transaction", "from_status", "to_status", "created_at")
    list_filter = ("from_status", "to_status")
    search_fields = ("transaction__public_id",)
    readonly_fields = ("public_id", "created_at", "updated_at")
