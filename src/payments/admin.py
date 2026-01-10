from __future__ import annotations

import csv
import json
from decimal import Decimal
from typing import Any

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils import timezone

from payments.forms import PaymentAdminForm
from payments.models import Payment
from payments.payments_integrations.stripe_client import StripeClient
from payments.services.commands import (
    cancel_active_payment,
    confirm_payment_simulator,
    expire_stale_payments,
)


def _now_stamp() -> str:
    return timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M%S")


def _csv_response(filename: str) -> HttpResponse:
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.write("\ufeff")
    return resp


def _ids(queryset) -> list[int]:
    return list(queryset.values_list("pk", flat=True))


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("public_id", "provider", "status", "amount", "transaction", "created_at")
    list_filter = ("provider", "status")
    search_fields = ("public_id", "transaction__public_id", "provider_payment_id")
    readonly_fields = ("public_id", "created_at", "updated_at")
    form = PaymentAdminForm
    list_select_related = ("transaction",)
    date_hierarchy = "created_at"
    show_full_result_count = False
    list_per_page = 50

    actions = [
        "export_selected_csv",
        "export_summary_csv",
        "mark_succeeded",
        "mark_failed",
        "mark_cancelled",
        "service_cancel_via_provider",
        "service_close_sim_test_payments",
        "service_expire_stale_30m",
    ]

    def export_selected_csv(self, request, queryset):
        resp = _csv_response(f"payments_{_now_stamp()}.csv")
        w = csv.writer(resp)
        w.writerow([
            "public_id",
            "provider",
            "status",
            "amount",
            "currency",
            "transaction_public_id",
            "transaction_type",
            "transaction_status",
            "provider_payment_id",
            "client_secret",
            "metadata_json",
            "created_at",
            "updated_at",
        ])

        ids = _ids(queryset)
        qs = Payment.objects.filter(pk__in=ids).select_related("transaction")

        for p in qs.iterator(chunk_size=2000):
            tx = p.transaction
            w.writerow([
                p.public_id,
                p.provider,
                p.status,
                str(getattr(p.amount, "amount", "")),
                str(getattr(p.amount, "currency", "")),
                getattr(tx, "public_id", ""),
                getattr(tx, "type", ""),
                getattr(tx, "status", ""),
                p.provider_payment_id,
                p.client_secret,
                json.dumps(p.metadata or {}, ensure_ascii=False),
                timezone.localtime(p.created_at).isoformat() if p.created_at else "",
                timezone.localtime(p.updated_at).isoformat() if p.updated_at else "",
            ])
        return resp

    export_selected_csv.short_description = "Eksport: zaznaczone płatności → CSV"

    def export_summary_csv(self, request, queryset):
        resp = _csv_response(f"payments_summary_{_now_stamp()}.csv")
        w = csv.writer(resp)
        w.writerow(["provider", "status", "currency", "count", "sum_amount"])

        ids = _ids(queryset)
        qs = (
            Payment.objects.filter(pk__in=ids)
            .only("provider", "status", "amount", "amount_currency")
            .iterator(chunk_size=5000)
        )

        buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
        for p in qs:
            cur = getattr(p, "amount_currency", "") or "PLN"
            key = (p.provider, p.status, cur)
            if key not in buckets:
                buckets[key] = {"count": 0, "sum": Decimal("0")}
            buckets[key]["count"] += 1
            amt = getattr(p, "amount", None)
            if amt is not None:
                buckets[key]["sum"] += Decimal(str(getattr(amt, "amount", 0) or 0))

        for (provider, status, cur), agg in sorted(buckets.items()):
            w.writerow([provider, status, cur, agg["count"], str(agg["sum"].quantize(Decimal("0.01")))])
        return resp

    export_summary_csv.short_description = "Zestawienie: zaznaczone płatności (provider/status/currency) → CSV"

    def mark_succeeded(self, request, queryset):
        ok = 0
        bad = 0
        ids = _ids(queryset)
        qs = Payment.objects.filter(pk__in=ids).select_related("transaction")
        for p in qs.iterator(chunk_size=2000):
            if p.provider != "SIM":
                bad += 1
                self.message_user(
                    request,
                    f"{p.public_id}: tylko SIM można oznaczać akcją SUCCEEDED/FAILED (Stripe przez webhook).",
                    level=messages.WARNING,
                )
                continue
            confirm_payment_simulator(payment=p, succeed=True)
            ok += 1
        if ok:
            self.message_user(request, f"Oznaczono SUCCEEDED: {ok}", level=messages.SUCCESS)
        if bad:
            self.message_user(request, f"Pominięto (nie-SIM): {bad}", level=messages.WARNING)

    mark_succeeded.short_description = "Oznacz jako SUCCEEDED (tylko SIM)"

    def mark_failed(self, request, queryset):
        ok = 0
        bad = 0
        ids = _ids(queryset)
        qs = Payment.objects.filter(pk__in=ids).select_related("transaction")
        for p in qs.iterator(chunk_size=2000):
            if p.provider != "SIM":
                bad += 1
                self.message_user(
                    request,
                    f"{p.public_id}: tylko SIM można oznaczać akcją SUCCEEDED/FAILED (Stripe przez webhook).",
                    level=messages.WARNING,
                )
                continue
            confirm_payment_simulator(payment=p, succeed=False)
            ok += 1
        if ok:
            self.message_user(request, f"Oznaczono FAILED: {ok}", level=messages.SUCCESS)
        if bad:
            self.message_user(request, f"Pominięto (nie-SIM): {bad}", level=messages.WARNING)

    mark_failed.short_description = "Oznacz jako FAILED (tylko SIM)"

    def mark_cancelled(self, request, queryset):
        ids = _ids(queryset)
        qs = Payment.objects.filter(pk__in=ids)
        cnt = 0
        for p in qs.iterator(chunk_size=2000):
            cancel_active_payment(payment=p, reason="Admin action")
            cnt += 1
        self.message_user(request, f"Oznaczono CANCELLED: {cnt}", level=messages.SUCCESS)

    mark_cancelled.short_description = "Oznacz jako CANCELLED"

    def service_cancel_via_provider(self, request, queryset):
        cnt = 0
        stripe_cnt = 0
        stripe_err = 0

        client = StripeClient()
        ids = _ids(queryset)
        qs = Payment.objects.filter(pk__in=ids)

        for p in qs.iterator(chunk_size=2000):
            if p.status in ("SUCCEEDED", "FAILED", "CANCELLED"):
                continue

            if p.provider == "STRIPE" and p.provider_payment_id:
                try:
                    client.cancel(provider_payment_id=p.provider_payment_id)
                    stripe_cnt += 1
                except Exception as e:
                    stripe_err += 1
                    self.message_user(request, f"{p.public_id}: błąd cancel w Stripe: {e}", level=messages.ERROR)
                    continue

            cancel_active_payment(payment=p, reason="Admin: cancel via provider")
            cnt += 1

        if cnt:
            self.message_user(request, f"Anulowano płatności: {cnt}", level=messages.SUCCESS)
        if stripe_cnt:
            self.message_user(request, f"Stripe: wykonano cancel PI: {stripe_cnt}", level=messages.INFO)
        if stripe_err:
            self.message_user(request, f"Stripe: błędy cancel PI: {stripe_err}", level=messages.ERROR)

    service_cancel_via_provider.short_description = "Serwis: anuluj przez providera (Stripe cancel PI, potem CANCELLED)"

    def service_close_sim_test_payments(self, request, queryset):
        active = ("REQUIRES_CONFIRMATION", "REQUIRES_ACTION", "PROCESSING")
        qs = Payment.objects.filter(provider="SIM", status__in=active).order_by("-created_at")
        cnt = 0
        for p in qs.iterator(chunk_size=5000):
            cancel_active_payment(payment=p, reason="Admin: close SIM test payments")
            cnt += 1
        self.message_user(request, f"Zamknięto (CANCELLED) SIM test payments: {cnt}", level=messages.SUCCESS)

    service_close_sim_test_payments.short_description = "Serwis: zamknij wszystkie testowe SIM (ustaw CANCELLED)"

    def service_expire_stale_30m(self, request, queryset):
        try:
            cnt = expire_stale_payments(minutes=30)
            self.message_user(request, f"Wygaszono przeterminowane płatności: {cnt}", level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Błąd expire_stale_payments: {e}", level=messages.ERROR)

    service_expire_stale_30m.short_description = "Serwis: wygaś przeterminowane płatności (TTL 30 min)"
