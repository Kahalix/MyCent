from __future__ import annotations

import csv
import json
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from typing import Any

from django.contrib import admin, messages
from django.core.files.storage import default_storage
from django.db.models import Prefetch
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import format_html

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from catalog.models import ItemType, CatalogItem
from listings.forms import ItemSetAdminForm, ItemSetShippingAdminForm, ItemSetImageAdminForm
from listings.models import ItemSet, ItemSetImage, ItemSetShipping
from listings.services import commands as listing_cmd
from listings.services.cache_utils import invalidate_public_itemsets_cache
from services.services.commands import ensure_slot_matches_state


def _now_stamp() -> str:
    return timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M%S")


def _csv_response(filename: str) -> HttpResponse:
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.write("\ufeff")
    return resp


def _ids(queryset) -> list[int]:
    return list(queryset.values_list("pk", flat=True))


def _fresh_itemset_qs(ids: list[int], with_shipping: bool = True, with_images: bool = True):
    qs = (
        ItemSet.objects.filter(pk__in=ids)
        .select_related("seller_profile", "owner_user", "type", "catalog_item")
    )
    if with_images:
        qs = qs.prefetch_related(Prefetch("images", queryset=ItemSetImage.objects.order_by("image_order", "id")))
    if with_shipping:
        qs = qs.prefetch_related(Prefetch("shipping_options", queryset=ItemSetShipping.objects.select_related("package_type")))
    return qs


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


def _open_image_bytes(*, img: ItemSetImage) -> bytes | None:
    try:
        if getattr(img, "image", None):
            try:
                f = img.image.open("rb")
                data = f.read()
                f.close()
                return data
            except Exception:
                try:
                    with default_storage.open(img.image.name, "rb") as f:
                        return f.read()
                except Exception:
                    return None
    except Exception:
        pass

    path = getattr(img, "image_path", "") or ""
    if not path:
        return None
    try:
        with default_storage.open(path, "rb") as f:
            return f.read()
    except Exception:
        return None


def _cover_image(obj: ItemSet) -> ItemSetImage | None:
    cache = getattr(obj, "_prefetched_objects_cache", None)
    if cache is not None and "images" in cache:
        imgs = cache["images"]
        return imgs[0] if imgs else None
    try:
        return obj.images.order_by("image_order", "id").first()
    except Exception:
        return None


class ItemSetImageInline(admin.TabularInline):
    model = ItemSetImage
    extra = 0
    form = ItemSetImageAdminForm
    fields = ("preview", "image", "image_path", "image_order")
    readonly_fields = ("preview",)
    ordering = ("image_order",)

    def preview(self, obj):
        if not obj:
            return "-"
        url = None
        try:
            if obj.image:
                url = obj.image.url
        except Exception:
            url = None
        if not url and obj.image_path:
            try:
                url = default_storage.url(obj.image_path)
            except Exception:
                url = obj.image_path
        if not url:
            return "-"
        return format_html(
            '<img src="{}" style="max-height:80px;max-width:120px;object-fit:contain;border:1px solid #ddd;padding:2px;background:#fff;" />',
            url,
        )

    preview.short_description = "Podgląd"


class ItemSetShippingInline(admin.TabularInline):
    model = ItemSetShipping
    extra = 0
    form = ItemSetShippingAdminForm
    fields = ("package_type", "price_override", "packed_length_cm", "packed_width_cm", "packed_height_cm", "packed_weight_kg")


@admin.register(ItemSet)
class ItemSetAdmin(admin.ModelAdmin):
    form = ItemSetAdminForm

    class Media:
        js = ("catalog/admin_fill_attrs.js",)

    list_display = (
        "cover_thumb",
        "set_name",
        "slug",
        "price",
        "status",
        "listing_type",
        "added_by",
        "seller_profile",
        "owner_user",
        "type",
        "created_at",
    )
    list_filter = ("status", "listing_type", "type", "added_by", "seller_profile")
    search_fields = ("set_name", "slug", "description", "public_id", "owner_user__email")
    inlines = [ItemSetImageInline, ItemSetShippingInline]
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = ("public_id", "created_at", "updated_at")
    show_full_result_count = False

    fieldsets = (
        ("Podstawowe", {"fields": ("set_name", "slug", "description", "price", "stock_quantity", "condition", "status")}),
        ("Atrybuty i typ", {"fields": ("type", "catalog_item", "attributes")}),
        ("Wymiary i waga", {"fields": ("length_cm", "width_cm", "height_cm", "weight_kg")}),
        ("Własność i checkout", {"fields": ("added_by", "listing_type", "allow_online_checkout", "seller_profile", "owner_user")}),
        ("Identyfikatory", {"classes": ("collapse",), "fields": ("public_id", "created_at", "updated_at")}),
    )

    autocomplete_fields = ("type", "catalog_item")
    raw_id_fields = ("type", "catalog_item")

    list_select_related = ("seller_profile", "owner_user", "type", "catalog_item")

    actions = [
        "export_selected_csv",
        "export_summary_csv",
        "generate_catalog_pdf",
        "set_status_available",
        "set_status_closed",
        "set_status_reserved",
        "set_status_sold",
        "set_status_suspended",
        "set_status_deleted",
        "service_expire_stale_user_available_30d",
        "service_invalidate_public_cache",
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.prefetch_related(None)
        qs = qs.select_related("seller_profile", "owner_user", "type", "catalog_item")
        qs = qs.prefetch_related(
            Prefetch("images", queryset=ItemSetImage.objects.order_by("image_order", "id")),
            Prefetch("shipping_options", queryset=ItemSetShipping.objects.select_related("package_type")),
        )
        return qs

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "type":
            kwargs["queryset"] = ItemType.objects.filter(children__isnull=True)

        if db_field.name == "catalog_item":
            posted_type_id = None
            posted_catalog_id = None

            if request.method in ("POST", "PUT", "PATCH"):
                posted_type_id = request.POST.get("type") or None
                posted_catalog_id = request.POST.get("catalog_item") or None
            else:
                posted_type_id = request.GET.get("type") or None

            base_qs = CatalogItem.objects.all()
            if posted_type_id:
                qs = base_qs.filter(type_id=posted_type_id)
            else:
                obj = getattr(request, "_obj_", None)
                if obj and obj.type_id:
                    qs = base_qs.filter(type_id=obj.type_id)
                else:
                    qs = base_qs

            if posted_catalog_id:
                qs = (qs | base_qs.filter(pk=posted_catalog_id)).distinct()

            kwargs["queryset"] = qs

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        request._obj_ = obj
        return super().get_form(request, obj, **kwargs)

    def cover_thumb(self, obj):
        img = _cover_image(obj)
        if not img:
            return "-"
        url = None
        try:
            if img.image:
                url = img.image.url
        except Exception:
            url = None
        if not url and img.image_path:
            try:
                url = default_storage.url(img.image_path)
            except Exception:
                url = img.image_path
        if not url:
            return "-"
        return format_html(
            '<img src="{}" style="height:40px;object-fit:cover;border:1px solid #ddd;padding:1px;background:#fff;border-radius:2px;" />',
            url,
        )

    cover_thumb.short_description = "Zdjęcie"

    def export_selected_csv(self, request, queryset):
        resp = _csv_response(f"ogloszenia_{_now_stamp()}.csv")
        w = csv.writer(resp)
        w.writerow([
            "id_publiczne",
            "nazwa",
            "slug",
            "opis",
            "cena_kwota",
            "cena_waluta",
            "stan_magazynowy",
            "kondycja",
            "status",
            "typ_ogloszenia",
            "checkout_online",
            "dodane_przez",
            "sprzedawca_public_id",
            "sprzedawca_slug",
            "wlasciciel_public_id",
            "wlasciciel_email",
            "kategoria_public_id",
            "kategoria_sciezka",
            "kategoria_nazwa",
            "katalog_public_id",
            "katalog_slug",
            "dlugosc_cm",
            "szerokosc_cm",
            "wysokosc_cm",
            "waga_kg",
            "liczba_zdjec",
            "opcje_wysylki",
            "atrybuty_json",
            "utworzono",
            "zaktualizowano",
        ])

        ids = _ids(queryset)
        qs = _fresh_itemset_qs(ids, with_shipping=True, with_images=True)

        for it in qs.iterator(chunk_size=500):
            seller_pid = getattr(getattr(it, "seller_profile", None), "public_id", "") or ""
            seller_slug = getattr(getattr(it, "seller_profile", None), "slug", "") or ""
            owner_pid = getattr(getattr(it, "owner_user", None), "public_id", "") or ""
            owner_email = getattr(getattr(it, "owner_user", None), "email", "") or ""
            type_pid = getattr(getattr(it, "type", None), "public_id", "") or ""
            type_path = getattr(getattr(it, "type", None), "path", "") or ""
            type_name = getattr(getattr(it, "type", None), "name", "") or ""
            cat_pid = getattr(getattr(it, "catalog_item", None), "public_id", "") or ""
            cat_slug = getattr(getattr(it, "catalog_item", None), "slug", "") or ""

            cache = getattr(it, "_prefetched_objects_cache", None) or {}
            imgs = list(cache.get("images") or [])
            ships = list(cache.get("shipping_options") or [])

            ship_strs = []
            for s in ships:
                pkg = getattr(s, "package_type", None)
                pkg_pid = getattr(pkg, "public_id", "") if pkg else ""
                eff = s.price_override or (getattr(pkg, "price", None) if pkg else None)
                ship_strs.append(f"{pkg_pid}:{_money_amount(eff)}{_money_currency(eff)}")

            w.writerow([
                it.public_id,
                it.set_name,
                it.slug,
                (it.description or "").replace("\n", " ").strip(),
                _money_amount(it.price),
                _money_currency(it.price),
                it.stock_quantity,
                it.condition,
                it.status,
                it.listing_type,
                bool(it.allow_online_checkout),
                it.added_by,
                seller_pid,
                seller_slug,
                owner_pid,
                owner_email,
                type_pid,
                type_path,
                type_name,
                cat_pid,
                cat_slug,
                it.length_cm or "",
                it.width_cm or "",
                it.height_cm or "",
                str(it.weight_kg) if it.weight_kg is not None else "",
                len(imgs),
                ";".join(ship_strs),
                json.dumps(it.attributes or {}, ensure_ascii=False),
                _safe_iso(it.created_at),
                _safe_iso(it.updated_at),
            ])

        return resp

    export_selected_csv.short_description = "Eksport: zaznaczone ogłoszenia → CSV"

    def export_summary_csv(self, request, queryset):
        resp = _csv_response(f"ogloszenia_zestawienie_{_now_stamp()}.csv")
        w = csv.writer(resp)
        w.writerow([
            "status",
            "typ_ogloszenia",
            "dodane_przez",
            "waluta",
            "liczba",
            "suma_cena_kwota",
            "suma_stan_magazynowy",
        ])

        ids = _ids(queryset)
        qs = (
            ItemSet.objects.filter(pk__in=ids)
            .only("status", "listing_type", "added_by", "price", "price_currency", "stock_quantity")
            .iterator(chunk_size=5000)
        )

        buckets: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for it in qs:
            cur = getattr(it, "price_currency", "") or "PLN"
            key = (it.status, it.listing_type, it.added_by, cur)
            if key not in buckets:
                buckets[key] = {"count": 0, "sum_price": Decimal("0"), "sum_stock": 0}
            buckets[key]["count"] += 1
            try:
                buckets[key]["sum_stock"] += int(getattr(it, "stock_quantity", 0) or 0)
            except Exception:
                pass
            try:
                m = getattr(it, "price", None)
                if m is not None:
                    buckets[key]["sum_price"] += Decimal(str(getattr(m, "amount", 0) or 0))
            except Exception:
                pass

        for (status, lt, added_by, cur), agg in sorted(buckets.items()):
            w.writerow([
                status,
                lt,
                added_by,
                cur,
                agg["count"],
                str(Decimal(str(agg["sum_price"])).quantize(Decimal("0.01"))),
                agg["sum_stock"],
            ])
        return resp

    export_summary_csv.short_description = "Zestawienie: zaznaczone ogłoszenia → CSV"

    def generate_catalog_pdf(self, request, queryset):
        resp = HttpResponse(content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="katalog_ogloszen_{_now_stamp()}.pdf"'

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        page_w, page_h = A4

        ids = _ids(queryset)
        qs = _fresh_itemset_qs(ids, with_shipping=False, with_images=True)

        def draw_kv(y, k, v):
            c.setFont("Helvetica-Bold", 10)
            c.drawString(15 * mm, y, str(k))
            c.setFont("Helvetica", 10)
            c.drawString(55 * mm, y, str(v)[:120])

        for it in qs.iterator(chunk_size=200):
            c.setFont("Helvetica-Bold", 14)
            c.drawString(15 * mm, page_h - 20 * mm, it.set_name or "")
            c.setFont("Helvetica", 10)
            c.drawString(15 * mm, page_h - 27 * mm, f"ID: {it.public_id}   slug: {it.slug}")

            y = page_h - 40 * mm
            draw_kv(y, "Status", it.status)
            y -= 6 * mm
            draw_kv(y, "Typ ogłoszenia", it.listing_type)
            y -= 6 * mm
            draw_kv(y, "Dodane przez", it.added_by)
            y -= 6 * mm
            draw_kv(y, "Checkout online", bool(it.allow_online_checkout))
            y -= 6 * mm
            draw_kv(y, "Cena", f"{_money_amount(it.price)} {_money_currency(it.price)}")
            y -= 6 * mm
            draw_kv(y, "Stan magazynowy", it.stock_quantity)
            y -= 6 * mm
            draw_kv(y, "Kondycja", it.condition)
            y -= 6 * mm

            seller = getattr(it, "seller_profile", None)
            owner = getattr(it, "owner_user", None)
            draw_kv(y, "Sprzedawca", f"{getattr(seller, 'public_id', '')} {getattr(seller, 'slug', '')}".strip())
            y -= 6 * mm
            draw_kv(y, "Właściciel", f"{getattr(owner, 'public_id', '')} {getattr(owner, 'email', '')}".strip())
            y -= 6 * mm

            t = getattr(it, "type", None)
            draw_kv(y, "Kategoria", f"{getattr(t, 'path', '')}")
            y -= 6 * mm

            c.setFont("Helvetica-Bold", 10)
            c.drawString(15 * mm, y, "Opis")
            y -= 6 * mm
            c.setFont("Helvetica", 9)
            desc = (it.description or "").strip()
            if desc:
                for line in desc.splitlines():
                    if y < 20 * mm:
                        break
                    c.drawString(15 * mm, y, line[:140])
                    y -= 5 * mm

            img = _cover_image(it)
            if img:
                data = _open_image_bytes(img=img)
                if data:
                    try:
                        ir = ImageReader(BytesIO(data))
                        img_w = 80 * mm
                        img_h = 60 * mm
                        x = page_w - img_w - 15 * mm
                        y0 = page_h - img_h - 30 * mm
                        c.drawImage(ir, x, y0, width=img_w, height=img_h, preserveAspectRatio=True, anchor="c")
                    except Exception:
                        pass

            c.setFont("Helvetica", 8)
            c.drawString(15 * mm, 12 * mm, f"utworzono: {_safe_iso(it.created_at)}   zaktualizowano: {_safe_iso(it.updated_at)}")
            c.showPage()

        c.save()
        pdf = buf.getvalue()
        buf.close()
        resp.write(pdf)
        return resp

    generate_catalog_pdf.short_description = "Dokument: katalog PDF (zaznaczone ogłoszenia)"

    def _bulk_set_status(self, request, queryset, status: str):
        ok = 0
        bad = 0
        for it in queryset.iterator(chunk_size=500):
            try:
                listing_cmd.set_status(itemset=it, status=status)
                ok += 1
            except Exception as e:
                bad += 1
                self.message_user(request, f"{it.public_id}: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Ustawiono status={status}: {ok}", level=messages.SUCCESS)
        if bad:
            self.message_user(request, f"Błędy: {bad}", level=messages.ERROR)

    def set_status_available(self, request, queryset):
        self._bulk_set_status(request, queryset, "AVAILABLE")

    set_status_available.short_description = "Status: ustaw AVAILABLE"

    def set_status_closed(self, request, queryset):
        self._bulk_set_status(request, queryset, "CLOSED")

    set_status_closed.short_description = "Status: ustaw CLOSED"

    def set_status_reserved(self, request, queryset):
        self._bulk_set_status(request, queryset, "RESERVED")

    set_status_reserved.short_description = "Status: ustaw RESERVED"

    def set_status_sold(self, request, queryset):
        self._bulk_set_status(request, queryset, "SOLD")

    set_status_sold.short_description = "Status: ustaw SOLD"

    def set_status_suspended(self, request, queryset):
        self._bulk_set_status(request, queryset, "SUSPENDED")

    set_status_suspended.short_description = "Status: ustaw SUSPENDED"

    def set_status_deleted(self, request, queryset):
        ok = 0
        bad = 0
        for it in queryset.iterator(chunk_size=500):
            try:
                listing_cmd.soft_delete_itemset(itemset=it)
                ok += 1
            except Exception as e:
                bad += 1
                self.message_user(request, f"{it.public_id}: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"Usunięto (soft) ogłoszenia: {ok}", level=messages.SUCCESS)
        if bad:
            self.message_user(request, f"Błędy: {bad}", level=messages.ERROR)

    set_status_deleted.short_description = "Status: usuń (soft -> DELETED)"

    def service_expire_stale_user_available_30d(self, request, queryset):
        now = timezone.now()
        threshold = now - timedelta(days=30)

        qs = (
            ItemSet.objects
            .select_related("owner_user")
            .filter(added_by="USER", status="AVAILABLE", updated_at__lt=threshold)
            .order_by("updated_at")
        )

        ids = list(qs.values_list("id", flat=True)[:5000])
        if not ids:
            self.message_user(request, "Brak ogłoszeń USER do wygaszenia.", level=messages.INFO)
            return

        ItemSet.objects.filter(id__in=ids).update(status="EXPIRED", updated_at=now)

        items = ItemSet.objects.filter(id__in=ids).select_related("owner_user")
        for it in items.iterator(chunk_size=500):
            try:
                ensure_slot_matches_state(user=it.owner_user, itemset=it)
            except Exception:
                pass

        try:
            invalidate_public_itemsets_cache()
        except Exception:
            pass

        self.message_user(request, f"Wygaszono USER ogłoszenia (EXPIRED): {len(ids)}", level=messages.SUCCESS)

    service_expire_stale_user_available_30d.short_description = "Serwis: wygaś USER AVAILABLE starsze niż 30 dni (EXPIRED)"

    def service_invalidate_public_cache(self, request, queryset):
        try:
            invalidate_public_itemsets_cache()
            self.message_user(request, "Zainwalidowano cache publicznych ogłoszeń.", level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Błąd invalidacji cache: {e}", level=messages.ERROR)

    service_invalidate_public_cache.short_description = "Serwis: invalidate cache publicznych ogłoszeń"


@admin.register(ItemSetImage)
class ItemSetImageAdmin(admin.ModelAdmin):
    list_display = ("public_id", "item_set", "image_order", "image_path", "created_at")
    search_fields = ("public_id", "item_set__public_id", "item_set__set_name", "image_path")
    list_select_related = ("item_set",)
    ordering = ("item_set", "image_order", "id")
    readonly_fields = ("public_id", "created_at", "updated_at")
    show_full_result_count = False
    actions = ["export_selected_csv"]

    def export_selected_csv(self, request, queryset):
        resp = _csv_response(f"zdjecia_ogloszen_{_now_stamp()}.csv")
        w = csv.writer(resp)
        w.writerow(["id_publiczne", "ogloszenie_public_id", "ogloszenie_nazwa", "kolejnosc", "sciezka_pliku", "utworzono", "zaktualizowano"])
        qs = queryset.select_related("item_set")
        for img in qs.iterator(chunk_size=5000):
            it = img.item_set
            w.writerow([
                img.public_id,
                getattr(it, "public_id", ""),
                getattr(it, "set_name", ""),
                img.image_order,
                img.image_path,
                _safe_iso(img.created_at),
                _safe_iso(img.updated_at),
            ])
        return resp

    export_selected_csv.short_description = "Eksport: zaznaczone zdjęcia → CSV"


@admin.register(ItemSetShipping)
class ItemSetShippingAdmin(admin.ModelAdmin):
    list_display = ("public_id", "item_set", "package_type", "price_override", "created_at")
    search_fields = ("public_id", "item_set__public_id", "item_set__set_name", "package_type__public_id")
    list_select_related = ("item_set", "package_type")
    readonly_fields = ("public_id", "created_at", "updated_at")
    show_full_result_count = False
    actions = ["export_selected_csv"]

    def export_selected_csv(self, request, queryset):
        resp = _csv_response(f"opcje_wysylki_ogloszen_{_now_stamp()}.csv")
        w = csv.writer(resp)
        w.writerow([
            "id_publiczne",
            "ogloszenie_public_id",
            "ogloszenie_nazwa",
            "typ_paczki_public_id",
            "dostawca",
            "wymiary",
            "nadpisanie_ceny_kwota",
            "nadpisanie_ceny_waluta",
            "dlugosc_spakowana_cm",
            "szerokosc_spakowana_cm",
            "wysokosc_spakowana_cm",
            "waga_spakowana_kg",
            "utworzono",
            "zaktualizowano",
        ])
        qs = queryset.select_related("item_set", "package_type")
        for s in qs.iterator(chunk_size=5000):
            it = s.item_set
            pkg = s.package_type
            w.writerow([
                s.public_id,
                getattr(it, "public_id", ""),
                getattr(it, "set_name", ""),
                getattr(pkg, "public_id", ""),
                getattr(pkg, "provider", ""),
                getattr(pkg, "dimensions", ""),
                _money_amount(s.price_override),
                _money_currency(s.price_override),
                s.packed_length_cm or "",
                s.packed_width_cm or "",
                s.packed_height_cm or "",
                str(s.packed_weight_kg) if s.packed_weight_kg is not None else "",
                _safe_iso(s.created_at),
                _safe_iso(s.updated_at),
            ])
        return resp

    export_selected_csv.short_description = "Eksport: zaznaczone opcje wysyłki → CSV"
