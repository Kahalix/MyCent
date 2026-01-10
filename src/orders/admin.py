from __future__ import annotations

import io
import zipfile

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils import timezone

from orders.models import Order, OrderLine, OrderShipping, ItemReservation
from orders.forms import OrderAdminForm, OrderLineAdminForm
from orders.services.commands import build_receipt_pdf, build_receipt_csv, set_order_status
from orders.services.printing_csv import export_orders_csv, export_orders_summary_csv
from orders.services.exceptions import DomainError, Conflict


def _zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(name, data or b"")
    return buf.getvalue()

class OrderLineInline(admin.TabularInline):
    model = OrderLine
    form = OrderLineAdminForm
    extra = 0
    fields = ("item_set", "quantity", "unit_price", "line_total", "item_snapshot")
    readonly_fields = ("line_total", "item_snapshot")


class OrderShippingInline(admin.TabularInline):
    model = OrderShipping
    extra = 0
    fields = ("order_line", "package_type", "price", "tracking_number", "shipping_status", "package_label")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm

    list_display = (
        "public_id",
        "order_name",
        "seller_profile",
        "buyer",
        "order_status",
        "payment_method",
        "items_total",
        "shipping_total",
        "purchase_cost",
        "purchase_date",
        "created_at",
    )
    list_filter = ("order_status", "payment_method", "seller_profile", "purchase_date")
    search_fields = ("public_id", "order_name", "description", "buyer__email", "seller_profile__slug")
    inlines = [OrderLineInline, OrderShippingInline]
    readonly_fields = ("public_id", "created_at", "updated_at", "items_total", "shipping_total", "purchase_cost")
    list_select_related = ("seller_profile", "buyer", "transaction")
    date_hierarchy = "created_at"
    show_full_result_count = False

    actions = [
        "recalc_totals_action",
        "mark_completed_action",
        "mark_cancelled_action",
        "mark_refunded_action",
        "export_selected_orders_csv_action",
        "export_selected_orders_summary_csv_action",
        "download_receipts_pdf_action",
        "download_receipts_csv_action",
    ]

    @admin.action(description="Przelicz sumy zamówienia")
    def recalc_totals_action(self, request, queryset):
        for o in queryset.iterator():
            try:
                o.recalc_totals(save=True)
            except Exception as e:
                self.message_user(request, f"{o.public_id}: błąd przeliczania: {e}", level=messages.ERROR)
        self.message_user(request, "Zakończono przeliczanie sum.", level=messages.SUCCESS)

    def _bulk_set_status(self, request, queryset, to_status: str):
        ok = 0
        failed = 0
        for o in queryset.select_related("transaction").iterator():
            try:
                set_order_status(order=o, to_status=to_status)
                ok += 1
            except (DomainError, Conflict) as e:
                failed += 1
                self.message_user(request, f"{o.public_id}: {e.detail if hasattr(e, 'detail') else str(e)}", level=messages.ERROR)
            except Exception as e:
                failed += 1
                self.message_user(request, f"{o.public_id}: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Zmieniono status dla {ok} zamówień.", level=messages.SUCCESS)
        if failed:
            self.message_user(request, f"Nie udało się zmienić statusu dla {failed} zamówień.", level=messages.WARNING)

    @admin.action(description="Ustaw status: COMPLETED")
    def mark_completed_action(self, request, queryset):
        self._bulk_set_status(request, queryset, "COMPLETED")

    @admin.action(description="Ustaw status: CANCELLED")
    def mark_cancelled_action(self, request, queryset):
        self._bulk_set_status(request, queryset, "CANCELLED")

    @admin.action(description="Ustaw status: REFUNDED")
    def mark_refunded_action(self, request, queryset):
        self._bulk_set_status(request, queryset, "REFUNDED")

    @admin.action(description="Eksport zaznaczonych: CSV (lista)")
    def export_selected_orders_csv_action(self, request, queryset):
        qs = queryset.select_related("seller_profile", "buyer", "transaction").order_by("-created_at")
        data = export_orders_csv(qs)
        filename = f"orders_export_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')}.csv"
        resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @admin.action(description="Eksport zaznaczonych: CSV (zestawienie)")
    def export_selected_orders_summary_csv_action(self, request, queryset):
        qs = queryset.select_related("transaction").order_by("-created_at")
        data = export_orders_summary_csv(qs)
        filename = f"orders_summary_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')}.csv"
        resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @admin.action(description="Dokumenty: pobierz receipt PDF (1 szt. lub ZIP)")
    def download_receipts_pdf_action(self, request, queryset):
        files: list[tuple[str, bytes]] = []
        qs = (
            queryset
            .select_related("transaction", "seller_profile")
            .prefetch_related("order_lines", "shippings")
        )
        for o in qs.iterator(chunk_size=2000):
            try:
                pdf = build_receipt_pdf(o)
                files.append((f"receipt_{o.public_id}.pdf", pdf))
            except RuntimeError as e:
                self.message_user(request, f"{o.public_id}: {e}", level=messages.ERROR)
            except Exception as e:
                self.message_user(request, f"{o.public_id}: błąd generowania PDF: {e}", level=messages.ERROR)

        if not files:
            self.message_user(request, "Brak dokumentów do pobrania.", level=messages.WARNING)
            return None

        if len(files) == 1:
            name, data = files[0]
            resp = HttpResponse(data, content_type="application/pdf")
            resp["Content-Disposition"] = f'attachment; filename="{name}"'
            resp["Content-Length"] = str(len(data))
            return resp

        zdata = _zip_bytes(files)
        filename = f"receipts_orders_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')}.zip"
        resp = HttpResponse(zdata, content_type="application/zip")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp["Content-Length"] = str(len(zdata))
        return resp

    @admin.action(description="Dokumenty: pobierz receipt CSV (1 szt. lub ZIP)")
    def download_receipts_csv_action(self, request, queryset):
        files: list[tuple[str, bytes]] = []
        qs = (
            queryset
            .select_related("transaction", "seller_profile")
            .prefetch_related("order_lines", "shippings")
        )
        for o in qs.iterator(chunk_size=2000):
            try:
                csvb = build_receipt_csv(o)
                files.append((f"receipt_{o.public_id}.csv", csvb))
            except Exception as e:
                self.message_user(request, f"{o.public_id}: błąd generowania CSV: {e}", level=messages.ERROR)

        if not files:
            self.message_user(request, "Brak dokumentów do pobrania.", level=messages.WARNING)
            return None

        if len(files) == 1:
            name, data = files[0]
            resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
            resp["Content-Disposition"] = f'attachment; filename="{name}"'
            return resp

        zdata = _zip_bytes(files)
        filename = f"receipts_orders_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')}.zip"
        resp = HttpResponse(zdata, content_type="application/zip")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp["Content-Length"] = str(len(zdata))
        return resp


@admin.register(ItemReservation)
class ItemReservationAdmin(admin.ModelAdmin):
    list_display = ("item_set", "transaction", "order_line", "user", "quantity", "expires_at", "released_at", "created_at")
    list_filter = ("released_at",)
    search_fields = ("item_set__set_name", "transaction__public_id", "order_line__public_id", "user__email")
    list_select_related = ("item_set", "transaction", "order_line", "user")
    show_full_result_count = False
