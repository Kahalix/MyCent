from django.contrib import admin
from datetime import timedelta
from django.utils import timezone
from django.utils.html import format_html
from django.core.files.storage import default_storage
from catalog.models import ItemType, CatalogItem
from .models import ItemSet, ItemSetImage, ItemSetShipping
from .forms import ItemSetAdminForm, ItemSetShippingAdminForm, ItemSetImageAdminForm

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
            '<img src="{}" style="max-height:80px;max-width:120px;object-fit:contain;'
            'border:1px solid #ddd;padding:2px;background:#fff;" />', url
        )
    preview.short_description = "Podgląd"

class ItemSetShippingInline(admin.TabularInline):
    model = ItemSetShipping
    extra = 0
    form = ItemSetShippingAdminForm
    fields = ("package_type","price_override","packed_length_cm","packed_width_cm","packed_height_cm","packed_weight_kg")

@admin.register(ItemSet)
class ItemSetAdmin(admin.ModelAdmin):
    form = ItemSetAdminForm

    class Media:
        js = ("catalog/admin_fill_attrs.js",)

    list_display = ("cover_thumb","set_name","slug","price","status","listing_type",
                    "added_by","seller_profile","owner_user","type","created_at")
    list_filter = ("status","listing_type","type","added_by","seller_profile")
    search_fields = ("set_name","slug","description","public_id","owner_user__email")
    inlines = [ItemSetImageInline, ItemSetShippingInline]
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = ("public_id","created_at","updated_at")
    show_full_result_count = False

    fieldsets = (
        ("Podstawowe", {"fields": ("set_name","slug","description","price","stock_quantity","condition","status")}),
        ("Atrybuty i typ", {"fields": ("type","catalog_item","attributes")}),
        ("Wymiary i waga", {"fields": ("length_cm","width_cm","height_cm","weight_kg")}),
        ("Własność i checkout", {"fields": ("added_by","listing_type","allow_online_checkout","seller_profile","owner_user")}),
        ("Identyfikatory", {"classes": ("collapse",), "fields": ("public_id","created_at","updated_at")}),
    )

    autocomplete_fields = ("type","catalog_item")
    raw_id_fields = ("type","catalog_item")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "type":
            # tylko liście
            kwargs["queryset"] = ItemType.objects.filter(children__isnull=True)

        if db_field.name == "catalog_item":
            # 1) preferuj typ z POST (zmieniony w tym żądaniu),
            # 2) jeśli go nie ma – użyj typu z bieżącego obiektu (widok edycji),
            # 3) zawsze dołącz wybrany w POST catalog_item, żeby uniknąć "invalid choice"
            posted_type_id = None
            posted_catalog_id = None

            if request.method in ("POST", "PUT", "PATCH"):
                posted_type_id = request.POST.get("type") or None
                posted_catalog_id = request.POST.get("catalog_item") or None
            else:
                # czasem typ może przyjść w querystring (rzadkie, ale bezpieczne)
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

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        # if obj and obj.created_at and timezone.now() - obj.created_at >= timedelta(hours=24):
        #     ro.append("type")
        # if obj and obj.catalog_item_id and "type" not in ro:
        #     ro.append("type")
        return ro

    def cover_thumb(self, obj):
        img = obj.images.order_by("image_order").first()
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
        return format_html('<img src="{}" style="height:40px;object-fit:cover;border:1px solid #ddd;'
                           'padding:1px;background:#fff;border-radius:2px;" />', url)

    cover_thumb.short_description = "photo"
