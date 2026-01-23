from __future__ import annotations
import uuid
from django.contrib import admin
from django import forms
from django.http import JsonResponse, Http404
from django.urls import path
from django.utils.text import slugify
from django.core.files.storage import default_storage
from django.utils.html import format_html
from os.path import splitext

from .models import ItemType, CatalogItem
from common.widgets import SimpleJSONSchemaWidget, DEFAULT_EMPTY_SCHEMA

# ========= ItemType admin =========

@admin.register(ItemType)
class ItemTypeAdmin(admin.ModelAdmin):
    list_display  = ("name", "slug", "path", "parent", "is_leaf", "created_at")
    list_filter   = ("parent",)
    search_fields = ("name", "slug", "path")
    readonly_fields = ("path",)
    # AUTOCOMPLETE OFF
    autocomplete_fields = ("parent",)
    raw_id_fields = ("parent",)
    actions = ["rebuild_paths"]
    show_full_result_count = False

    def is_leaf(self, obj):
        return not obj.children.exists()
    is_leaf.boolean = True
    is_leaf.short_description = "Leaf"

    def get_search_results(self, request, queryset, search_term):
        qs, use_distinct = super().get_search_results(request, queryset, search_term)
        if request.GET.get("field_name") == "type":
            qs = qs.filter(children__isnull=True)
        return qs, use_distinct

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # w popupie raw-id pokaż tylko liście
        if request.GET.get("_popup"):
            qs = qs.filter(children__isnull=True)
        return qs

    def get_fieldsets(self, request, obj=None):
        base = (None, {"fields": ("name", "parent", "slug", "path")})
        if obj and not obj.children.exists():
            return base, ("Schemat (tylko liście)", {"fields": ("schema_json", "ui_schema_json")})
        return (base,)

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj and obj.children.exists():
            ro += ["schema_json", "ui_schema_json"]
        return ro

    def rebuild_paths(self, request, queryset):
        for it in queryset: it.save()
    rebuild_paths.short_description = "Rebuild paths for selected nodes"

    def get_urls(self):
        urls = super().get_urls()
        extra = [
            path(
                "schema/<uuid:pk>/",
                self.admin_site.admin_view(self.schema_json_view),
                name="itemtype-schema-json",
            ),
        ]
        return extra + urls

    def schema_json_view(self, request, pk: uuid.UUID):
        try:
            it = ItemType.objects.get(pk=pk)
        except ItemType.DoesNotExist:
            raise Http404
        return JsonResponse({
            "id": str(it.pk),
            "path": it.path,
            "is_leaf": not it.children.exists(),
            "schema": it.schema_json if not it.children.exists() else {},
            "ui_schema": it.ui_schema_json if not it.children.exists() else {},
        })


# ========= CatalogItem admin =========

class CatalogItemAdminForm(forms.ModelForm):
    image_upload = forms.ImageField(required=False, help_text="Wgraj plik - zapisze się do 'image_path'.")
    image_clear  = forms.BooleanField(required=False, label="Usuń obecny obrazek")

    class Meta:
        model = CatalogItem
        fields = "__all__"
        widgets = {
            "attributes": SimpleJSONSchemaWidget(schema=DEFAULT_EMPTY_SCHEMA),
        }

    class Media:
        js = ("catalog/admin_fill_attrs.js",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["type"].queryset = ItemType.objects.filter(children__isnull=True)

        it = self.initial.get("type") or getattr(self.instance, "type", None)
        if isinstance(it, (uuid.UUID, str, int)):
            it = ItemType.objects.filter(pk=it).only("schema_json").first()
        schema = it.schema_json if it and it.schema_json else DEFAULT_EMPTY_SCHEMA
        self.fields["attributes"].widget = SimpleJSONSchemaWidget(schema=schema)

@admin.register(CatalogItem)
class CatalogItemAdmin(admin.ModelAdmin):
    form = CatalogItemAdminForm
    list_display  = ("thumb", "item_name", "type", "created_at")
    list_filter   = ("type",)
    search_fields = ("item_name", "type__name", "type__path")
    autocomplete_fields = ("type",)
    raw_id_fields = ("type",)
    readonly_fields = ("public_id", "created_at", "updated_at", "image_path", "image_preview")
    show_full_result_count = False

    fieldsets = (
        (None, {"fields": ("item_name", "type", "slug")}),
        ("Atrybuty", {"fields": ("attributes",)}),
        ("Obrazek", {"fields": ("image_preview", "image_upload", "image_clear", "image_path")}),
        ("Meta", {"classes": ("collapse",), "fields": ("public_id", "created_at", "updated_at")}),
    )

    # --------- helpers: URL obrazka ---------
    def _image_url(self, obj):
        if not obj or not getattr(obj, "image_path", ""):
            return None
        try:
            return default_storage.url(obj.image_path)
        except Exception:
            return obj.image_path  # fallback: surowa ścieżka

    # --------- lista: miniaturka ---------
    def thumb(self, obj):
        url = self._image_url(obj)
        if not url:
            return "-"
        return format_html(
            '<img src="{}" style="height:40px;object-fit:cover;'
            'border:1px solid #ddd;padding:1px;background:#fff;border-radius:2px;" />',
            url
        )

    thumb.short_description = "Podgląd"

    # --------- formularz: podgląd ---------
    def image_preview(self, obj):
        url = self._image_url(obj)
        if not url:
            return "-"
        return format_html(
            '<img src="{}" style="max-height:120px;max-width:180px;object-fit:contain;'
            'border:1px solid #ddd;padding:2px;background:#fff;" />',
            url
        )

    image_preview.short_description = "Podgląd"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "type":
            # tylko liście
            from django.db.models import Count
            kwargs["queryset"] = ItemType.objects.annotate(c=Count("children")).filter(c=0)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        image = form.cleaned_data.get("image_upload")
        clear = form.cleaned_data.get("image_clear")

        # if image:
        #     # upload nowego -> usuń poprzedni jeśli był, zapisz nowy
        #     if obj.image_path:
        #         try:
        #             default_storage.delete(obj.image_path)
        #         except Exception:
        #             pass
        #     dest = f"catalog/{obj.public_id}/{slugify(getattr(image, 'name', 'image'))}"
        #     saved = default_storage.save(dest, image)
        #     CatalogItem.objects.filter(pk=obj.pk).update(image_path=saved)
        #     obj.image_path = saved
        # elif clear:
        if image:
            if obj.image_path:
                try:
                    default_storage.delete(obj.image_path)
                except Exception:
                    pass

            orig = getattr(image, "name", "image")
            stem, ext = splitext(orig)
            dest = f"catalog/{obj.public_id}/{slugify(stem)}{(ext or '').lower()}"
            saved = default_storage.save(dest, image)
            CatalogItem.objects.filter(pk=obj.pk).update(image_path=saved)
            obj.image_path = saved
        elif clear:
            # brak uploadu, ale zaznaczono kasowanie -> usuń plik i wyczyść pole
            if obj.image_path:
                try:
                    default_storage.delete(obj.image_path)
                except Exception:
                    pass
            CatalogItem.objects.filter(pk=obj.pk).update(image_path="")
            obj.image_path = ""

    def get_urls(self):
        urls = super().get_urls()
        extra = [
            path(
                "attrs/<uuid:pk>/",
                self.admin_site.admin_view(self.attrs_json_view),
                name="catalogitem-attrs-json",
            ),
        ]
        return extra + urls

    def attrs_json_view(self, request, pk: uuid.UUID):
        try:
            obj = CatalogItem.objects.select_related("type").get(pk=pk)
        except CatalogItem.DoesNotExist:
            raise Http404
        return JsonResponse({
            "id": str(obj.pk),
            "type_id": str(obj.type_id),
            "type_path": obj.type.path if obj.type_id else "",
            "attributes": obj.attributes or {},
        })