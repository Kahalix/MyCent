from __future__ import annotations

import io
import zipfile

from django.contrib import admin, messages
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone

from transactions.models import Transaction
from pawns.models import Pawn, PawnLine, PawnExtension
from pawns.forms import PawnAdminForm, PawnLineAdminForm, PawnExtensionAdminForm
from pawns.services.commands import redeem_pawn, forfeit_pawn, extend_pawn
from pawns.services.printing import render_receipt_pdf as build_pawn_receipt_pdf
from pawns.services.printing import render_receipt_csv as build_pawn_receipt_csv
from pawns.services.printing import export_pawns_csv, export_pawns_summary_csv
from pawns.services.exceptions import Conflict, DomainError
from pawns.services.fees import calc_extension_fee


def _zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(name, data or b"")
    return buf.getvalue()


class PawnLineInline(admin.TabularInline):
    model = PawnLine
    form = PawnLineAdminForm
    extra = 0
    fields = ("title", "description", "quantity", "appraisal_value", "item_snapshot")
    readonly_fields = ("item_snapshot",)


class PawnExtensionInline(admin.TabularInline):
    model = PawnExtension
    form = PawnExtensionAdminForm
    extra = 0
    fields = ("days", "fee", "previous_due", "new_due", "created_at")
    readonly_fields = ("fee", "previous_due", "new_due", "created_at")


@admin.register(Pawn)
class PawnAdmin(admin.ModelAdmin):
    form = PawnAdminForm

    list_display = ("public_id", "seller_profile", "status", "principal", "appraisal_total", "start_date", "due_date", "customer")
    list_filter = ("status", "seller_profile", "due_date")
    search_fields = ("public_id", "customer__first_name", "customer__last_name", "customer_snapshot")
    inlines = [PawnLineInline, PawnExtensionInline]
    readonly_fields = ("public_id", "created_at", "updated_at", "appraisal_total")
    show_full_result_count = False
    date_hierarchy = "created_at"

    actions = [
        "recalc_appraisal_action",
        "redeem_selected_action",
        "forfeit_selected_action",
        "extend_7d_selected_action",
        "extend_14d_selected_action",
        "extend_30d_selected_action",
        "export_selected_pawns_csv_action",
        "export_selected_pawns_summary_csv_action",
        "download_receipts_pdf_action",
        "download_receipts_csv_action",
    ]

    @admin.action(description="Przelicz sumę wycen (appraisal_total)")
    def recalc_appraisal_action(self, request, queryset):
        for p in queryset.prefetch_related("lines").iterator():
            try:
                p.recalc_appraisal(save=True)
            except Exception as e:
                self.message_user(request, f"{p.public_id}: błąd przeliczania: {e}", level=messages.ERROR)
        self.message_user(request, "Zakończono przeliczanie wycen.", level=messages.SUCCESS)

    @admin.action(description="Wykup (REDEEMED) przez operatora")
    def redeem_selected_action(self, request, queryset):
        ok = 0
        failed = 0
        for p in queryset.iterator():
            try:
                redeem_pawn(pawn=p, operator=request.user)
                ok += 1
            except (Conflict, DomainError) as e:
                failed += 1
                self.message_user(request, f"{p.public_id}: {e.detail if hasattr(e, 'detail') else str(e)}", level=messages.ERROR)
            except Exception as e:
                failed += 1
                self.message_user(request, f"{p.public_id}: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Wykupiono {ok} zastawów.", level=messages.SUCCESS)
        if failed:
            self.message_user(request, f"Niepowodzenia: {failed}.", level=messages.WARNING)

    @admin.action(description="Przepadek (FORFEITED) jeśli po terminie")
    def forfeit_selected_action(self, request, queryset):
        ok = 0
        failed = 0
        for p in queryset.prefetch_related("lines").iterator():
            try:
                forfeit_pawn(pawn=p, operator=request.user, create_listing=True)
                ok += 1
            except (Conflict, DomainError) as e:
                failed += 1
                self.message_user(request, f"{p.public_id}: {e.detail if hasattr(e, 'detail') else str(e)}", level=messages.ERROR)
            except Exception as e:
                failed += 1
                self.message_user(request, f"{p.public_id}: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Oznaczono jako FORFEITED: {ok}.", level=messages.SUCCESS)
        if failed:
            self.message_user(request, f"Niepowodzenia: {failed}.", level=messages.WARNING)

    def _extend_selected(self, request, queryset, days: int):
        ok = 0
        failed = 0
        for p in queryset.iterator():
            try:
                extend_pawn(pawn=p, days=days, operator=request.user)
                ok += 1
            except (Conflict, DomainError) as e:
                failed += 1
                self.message_user(request, f"{p.public_id}: {e.detail if hasattr(e, 'detail') else str(e)}", level=messages.ERROR)
            except Exception as e:
                failed += 1
                self.message_user(request, f"{p.public_id}: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Przedłużono {ok} zastawów o {days} dni.", level=messages.SUCCESS)
        if failed:
            self.message_user(request, f"Niepowodzenia: {failed}.", level=messages.WARNING)

    @admin.action(description="Przedłuż o 7 dni (nalicza opłatę)")
    def extend_7d_selected_action(self, request, queryset):
        self._extend_selected(request, queryset, 7)

    @admin.action(description="Przedłuż o 14 dni (nalicza opłatę)")
    def extend_14d_selected_action(self, request, queryset):
        self._extend_selected(request, queryset, 14)

    @admin.action(description="Przedłuż o 30 dni (nalicza opłatę)")
    def extend_30d_selected_action(self, request, queryset):
        self._extend_selected(request, queryset, 30)

    @admin.action(description="Eksport zaznaczonych: CSV (lista)")
    def export_selected_pawns_csv_action(self, request, queryset):
        qs = queryset.select_related("seller_profile", "operator", "customer", "transaction").order_by("-created_at")
        data = export_pawns_csv(qs)
        filename = f"pawns_export_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')}.csv"
        resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @admin.action(description="Eksport zaznaczonych: CSV (zestawienie)")
    def export_selected_pawns_summary_csv_action(self, request, queryset):
        qs = queryset.select_related("seller_profile", "operator", "customer", "transaction").order_by("-created_at")
        data = export_pawns_summary_csv(qs)
        filename = f"pawns_summary_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')}.csv"
        resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @admin.action(description="Dokumenty: pobierz umowę PDF (1 szt. lub ZIP)")
    def download_receipts_pdf_action(self, request, queryset):
        files: list[tuple[str, bytes]] = []
        qs = (
            queryset
            .select_related("seller_profile", "operator")
            .prefetch_related("lines", "extensions")
        )
        for p in qs.iterator(chunk_size=2000):
            try:
                pdf = build_pawn_receipt_pdf(p)
                files.append((f"pawn_{p.public_id}.pdf", pdf))
            except RuntimeError as e:
                self.message_user(request, f"{p.public_id}: {e}", level=messages.ERROR)
            except Exception as e:
                self.message_user(request, f"{p.public_id}: błąd generowania PDF: {e}", level=messages.ERROR)

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
        filename = f"pawns_docs_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')}.zip"
        resp = HttpResponse(zdata, content_type="application/zip")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp["Content-Length"] = str(len(zdata))
        return resp

    @admin.action(description="Dokumenty: pobierz umowę CSV (1 szt. lub ZIP)")
    def download_receipts_csv_action(self, request, queryset):
        files: list[tuple[str, bytes]] = []
        qs = (
            queryset
            .select_related("seller_profile", "operator")
            .prefetch_related("lines", "extensions")
        )
        for p in qs.iterator(chunk_size=2000):
            try:
                csvb = build_pawn_receipt_csv(p)
                files.append((f"pawn_{p.public_id}.csv", csvb))
            except Exception as e:
                self.message_user(request, f"{p.public_id}: błąd generowania CSV: {e}", level=messages.ERROR)

        if not files:
            self.message_user(request, "Brak dokumentów do pobrania.", level=messages.WARNING)
            return None

        if len(files) == 1:
            name, data = files[0]
            resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
            resp["Content-Disposition"] = f'attachment; filename="{name}"'
            return resp

        zdata = _zip_bytes(files)
        filename = f"pawns_docs_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')}.zip"
        resp = HttpResponse(zdata, content_type="application/zip")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp["Content-Length"] = str(len(zdata))
        return resp

    @transaction.atomic
    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)

        for obj in formset.deleted_objects:
            obj.delete()

        for obj in instances:
            if isinstance(obj, PawnExtension) and obj.pk is None:
                pawn = obj.pawn
                days = int(obj.days or 0)
                fee = calc_extension_fee(principal=pawn.principal, days=days)

                tx = Transaction.objects.create(
                    user=request.user,
                    type="PAWN_EXTENSION",
                    status="COMPLETED",
                    expected_total_amount=(fee.amount if fee else 0),
                    expected_total_currency=(str(fee.currency) if fee else "PLN"),
                )

                obj.transaction = tx
                obj.created_by = request.user
                obj.fee = fee
                obj.previous_due = pawn.due_date
                obj.new_due = pawn.due_date + timezone.timedelta(days=days)

                if obj.new_due and pawn.due_date != obj.new_due:
                    pawn.due_date = obj.new_due
                    pawn.save(update_fields=["due_date", "updated_at"])

            obj.save()

        formset.save_m2m()

        if formset.model is PawnLine:
            form.instance.recalc_appraisal(save=True)
