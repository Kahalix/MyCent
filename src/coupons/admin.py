from __future__ import annotations

import csv
from decimal import Decimal
from io import BytesIO
from typing import Any

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils import timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from coupons.forms import CouponAdminForm
from coupons.models import Coupon, UserCoupon


def _now_stamp() -> str:
    return timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M%S")


def _csv_response(filename: str) -> HttpResponse:
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.write("\ufeff")
    return resp


def _safe_iso(dt) -> str:
    if not dt:
        return ""
    return timezone.localtime(dt).isoformat()


def _money_amount(m) -> str:
    if m is None:
        return ""
    try:
        return str(Decimal(str(m.amount)).quantize(Decimal("0.01")))
    except Exception:
        try:
            return str(m.amount)
        except Exception:
            return ""


def _money_currency(m) -> str:
    if m is None:
        return ""
    try:
        return str(m.currency)
    except Exception:
        return ""


def _ids(queryset) -> list[int]:
    return list(queryset.values_list("pk", flat=True))


def _fresh_coupon_qs(ids: list[int]):
    return Coupon.objects.filter(pk__in=ids).order_by("-created_at")


def _fresh_user_coupon_qs(ids: list[int]):
    return (
        UserCoupon.objects.filter(pk__in=ids)
        .select_related("user", "coupon")
        .order_by("-created_at")
    )


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    form = CouponAdminForm
    list_display = (
        "public_id",
        "code",
        "discount_type",
        "discount_value",
        "active",
        "expiration_date",
        "quantity",
        "points_cost",
    )
    list_filter = ("discount_type", "active")
    search_fields = ("public_id", "code")
    readonly_fields = ("public_id", "created_at", "updated_at")
    date_hierarchy = "created_at"
    show_full_result_count = False
    list_per_page = 50

    actions = [
        "deactivate_selected",
        "activate_selected",
        "service_deactivate_expired",
        "export_selected_csv",
        "export_summary_csv",
        "generate_catalog_pdf",
    ]

    def deactivate_selected(self, request, queryset):
        ids = _ids(queryset)
        now = timezone.now()
        updated = Coupon.objects.filter(pk__in=ids).update(active=False, updated_at=now)
        self.message_user(request, f"Dezaktywowano kupony: {updated}", level=messages.SUCCESS)

    deactivate_selected.short_description = "Dezaktywuj: zaznaczone kupony (active=False)"

    def activate_selected(self, request, queryset):
        ids = _ids(queryset)
        now = timezone.now()
        updated = Coupon.objects.filter(pk__in=ids).update(active=True, updated_at=now)
        self.message_user(request, f"Aktywowano kupony: {updated}", level=messages.SUCCESS)

    activate_selected.short_description = "Aktywuj: zaznaczone kupony (active=True)"

    def service_deactivate_expired(self, request, queryset):
        now = timezone.now()
        updated = Coupon.objects.filter(active=True, expiration_date__isnull=False, expiration_date__lte=now).update(
            active=False,
            updated_at=now,
        )
        self.message_user(request, f"Dezaktywowano wygasłe kupony: {updated}", level=messages.SUCCESS)

    service_deactivate_expired.short_description = "Serwis: dezaktywuj wszystkie wygasłe kupony (active=False)"

    def export_selected_csv(self, request, queryset):
        resp = _csv_response(f"kupony_{_now_stamp()}.csv")
        w = csv.writer(resp)
        w.writerow(
            [
                "public_id",
                "kod",
                "typ_znizki",
                "znizka_wartosc_kwota",
                "znizka_wartosc_waluta",
                "maks_znizka_kwota",
                "maks_znizka_waluta",
                "min_zakup_kwota",
                "min_zakup_waluta",
                "aktywny",
                "wazny_do",
                "ilosc",
                "koszt_punkty",
                "limit_uzyc",
                "limit_na_uzytkownika",
                "utworzono",
                "zaktualizowano",
            ]
        )

        ids = _ids(queryset)
        qs = _fresh_coupon_qs(ids)

        for c in qs.iterator(chunk_size=5000):
            w.writerow(
                [
                    c.public_id,
                    c.code or "",
                    c.discount_type,
                    _money_amount(c.discount_value),
                    _money_currency(c.discount_value),
                    _money_amount(c.max_discount_value),
                    _money_currency(c.max_discount_value),
                    _money_amount(c.min_purchase_value),
                    _money_currency(c.min_purchase_value),
                    bool(c.active),
                    _safe_iso(c.expiration_date),
                    "" if c.quantity is None else int(c.quantity),
                    "" if c.points_cost is None else int(c.points_cost),
                    "" if c.max_redemptions is None else int(c.max_redemptions),
                    "" if c.max_per_user is None else int(c.max_per_user),
                    _safe_iso(c.created_at),
                    _safe_iso(c.updated_at),
                ]
            )
        return resp

    export_selected_csv.short_description = "Eksport: zaznaczone kupony → CSV"

    def export_summary_csv(self, request, queryset):
        resp = _csv_response(f"kupony_zestawienie_{_now_stamp()}.csv")
        w = csv.writer(resp)
        w.writerow(
            [
                "typ_znizki",
                "aktywny",
                "waluta_znizki",
                "czy_za_punkty",
                "liczba",
                "suma_koszt_punkty",
                "suma_ilosc",
            ]
        )

        ids = _ids(queryset)
        qs = (
            Coupon.objects.filter(pk__in=ids)
            .only("discount_type", "active", "discount_value", "discount_value_currency", "points_cost", "quantity")
            .iterator(chunk_size=5000)
        )

        buckets: dict[tuple[str, bool, str, bool], dict[str, Any]] = {}
        for c in qs:
            cur = getattr(c, "discount_value_currency", "") or "PLN"
            purch = c.points_cost is not None
            key = (c.discount_type, bool(c.active), cur, purch)
            if key not in buckets:
                buckets[key] = {"count": 0, "sum_points": 0, "sum_qty": 0}
            buckets[key]["count"] += 1
            if c.points_cost is not None:
                buckets[key]["sum_points"] += int(c.points_cost or 0)
            if c.quantity is not None:
                buckets[key]["sum_qty"] += int(c.quantity or 0)

        for (dtype, active, cur, purch), agg in sorted(
            buckets.items(),
            key=lambda x: (x[0][0], x[0][1], x[0][2], x[0][3]),
        ):
            w.writerow([dtype, active, cur, purch, agg["count"], agg["sum_points"], agg["sum_qty"]])
        return resp

    export_summary_csv.short_description = "Zestawienie: zaznaczone kupony → CSV"

    def generate_catalog_pdf(self, request, queryset):
        resp = HttpResponse(content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="katalog_kuponow_{_now_stamp()}.pdf"'

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        page_w, page_h = A4

        ids = _ids(queryset)
        qs = _fresh_coupon_qs(ids)

        def draw_kv(y, k, v):
            c.setFont("Helvetica-Bold", 10)
            c.drawString(15 * mm, y, str(k))
            c.setFont("Helvetica", 10)
            c.drawString(60 * mm, y, str(v)[:110])

        for cp in qs.iterator(chunk_size=500):
            c.setFont("Helvetica-Bold", 14)
            title = (cp.code or "").strip() or f"Kupon {cp.public_id}"
            c.drawString(15 * mm, page_h - 20 * mm, title)

            c.setFont("Helvetica", 10)
            c.drawString(15 * mm, page_h - 27 * mm, f"public_id: {cp.public_id}")

            y = page_h - 40 * mm
            draw_kv(y, "Aktywny", bool(cp.active))
            y -= 6 * mm
            draw_kv(y, "Ważny do", _safe_iso(cp.expiration_date))
            y -= 6 * mm
            draw_kv(y, "Typ zniżki", cp.discount_type)
            y -= 6 * mm

            dv = cp.discount_value
            if cp.discount_type == "PERCENTAGE":
                dv_txt = f"{_money_amount(dv)}%"
            else:
                dv_txt = f"{_money_amount(dv)} {_money_currency(dv)}".strip()
            draw_kv(y, "Wartość zniżki", dv_txt)
            y -= 6 * mm

            mdv = cp.max_discount_value
            draw_kv(y, "Maks. zniżka", f"{_money_amount(mdv)} {_money_currency(mdv)}".strip())
            y -= 6 * mm

            mpv = cp.min_purchase_value
            draw_kv(y, "Min. zakup", f"{_money_amount(mpv)} {_money_currency(mpv)}".strip())
            y -= 6 * mm

            draw_kv(y, "Ilość", "bez limitu" if cp.quantity is None else int(cp.quantity))
            y -= 6 * mm
            draw_kv(y, "Koszt (punkty)", "" if cp.points_cost is None else int(cp.points_cost))
            y -= 6 * mm
            draw_kv(y, "Limit użyć", "" if cp.max_redemptions is None else int(cp.max_redemptions))
            y -= 6 * mm
            draw_kv(y, "Limit na użytkownika", "" if cp.max_per_user is None else int(cp.max_per_user))
            y -= 6 * mm

            c.setFont("Helvetica", 8)
            c.drawString(
                15 * mm,
                12 * mm,
                f"utworzono: {_safe_iso(cp.created_at)}   zaktualizowano: {_safe_iso(cp.updated_at)}",
            )
            c.showPage()

        c.save()
        pdf = buf.getvalue()
        buf.close()
        resp.write(pdf)
        return resp

    generate_catalog_pdf.short_description = "Dokument: katalog PDF (zaznaczone kupony)"


@admin.register(UserCoupon)
class UserCouponAdmin(admin.ModelAdmin):
    list_display = ("public_id", "user", "coupon", "redeemed", "purchased_at", "redeemed_at", "points_paid")
    list_filter = ("redeemed",)
    search_fields = ("public_id", "user__email", "coupon__code")
    readonly_fields = ("public_id", "created_at", "updated_at")
    date_hierarchy = "created_at"
    show_full_result_count = False
    list_per_page = 50

    actions = [
        "export_selected_csv",
        "export_summary_csv",
    ]

    def export_selected_csv(self, request, queryset):
        resp = _csv_response(f"kupony_uzytkownikow_{_now_stamp()}.csv")
        w = csv.writer(resp)
        w.writerow(
            [
                "public_id",
                "user_public_id",
                "user_email",
                "coupon_public_id",
                "coupon_code",
                "redeemed",
                "purchased_at",
                "redeemed_at",
                "points_paid",
                "created_at",
                "updated_at",
            ]
        )

        ids = _ids(queryset)
        qs = _fresh_user_coupon_qs(ids)

        for uc in qs.iterator(chunk_size=5000):
            u = getattr(uc, "user", None)
            cp = getattr(uc, "coupon", None)
            w.writerow(
                [
                    uc.public_id,
                    getattr(u, "public_id", "") if u else "",
                    getattr(u, "email", "") if u else "",
                    getattr(cp, "public_id", "") if cp else "",
                    getattr(cp, "code", "") if cp else "",
                    bool(uc.redeemed),
                    _safe_iso(uc.purchased_at),
                    _safe_iso(uc.redeemed_at),
                    "" if uc.points_paid is None else int(uc.points_paid),
                    _safe_iso(uc.created_at),
                    _safe_iso(uc.updated_at),
                ]
            )
        return resp

    export_selected_csv.short_description = "Eksport: zaznaczone kupony użytkowników → CSV"

    def export_summary_csv(self, request, queryset):
        resp = _csv_response(f"kupony_uzytkownikow_zestawienie_{_now_stamp()}.csv")
        w = csv.writer(resp)
        w.writerow(["redeemed", "coupon_code", "liczba", "suma_points_paid"])

        ids = _ids(queryset)
        qs = (
            UserCoupon.objects.filter(pk__in=ids)
            .select_related("coupon")
            .only("redeemed", "points_paid", "coupon__code")
            .iterator(chunk_size=5000)
        )

        buckets: dict[tuple[bool, str], dict[str, Any]] = {}
        for uc in qs:
            code = getattr(getattr(uc, "coupon", None), "code", "") or ""
            key = (bool(uc.redeemed), code)
            if key not in buckets:
                buckets[key] = {"count": 0, "sum_points": 0}
            buckets[key]["count"] += 1
            if uc.points_paid is not None:
                buckets[key]["sum_points"] += int(uc.points_paid or 0)

        for (redeemed, code), agg in sorted(buckets.items(), key=lambda x: (x[0][0], x[0][1])):
            w.writerow([redeemed, code, agg["count"], agg["sum_points"]])
        return resp

    export_summary_csv.short_description = "Zestawienie: zaznaczone kupony użytkowników → CSV"
