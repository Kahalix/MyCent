from __future__ import annotations
from django.contrib import admin, messages
from django.utils import timezone
from django.contrib.admin.helpers import ActionForm
from django import forms
from django.contrib.auth import get_user_model

from .models import (
    ListingPackage, UserListingPackage, ListingUsageHistory, ServicePurchaseHistory
)
from .services.commands import purchase_package
from .services.exceptions import PurchaseError

User = get_user_model()


# ---------- Admin action form: grant package to user (FREE) ----------

class GrantPackageActionForm(ActionForm):
    user = forms.ModelChoiceField(
        queryset=User.objects.all(),
        required=True,
        label="Użytkownik (otrzyma wybrany pakiet)"
    )
    quantity = forms.IntegerField(min_value=1, initial=1, required=True, label="Ile razy dodać")


# ---------- ListingPackage ----------

@admin.register(ListingPackage)
class ListingPackageAdmin(admin.ModelAdmin):
    list_display = ("id", "public_id", "item_type", "listings_free", "price", "points", "created_at")
    list_filter  = ("item_type",)
    search_fields = ("public_id", "item_type__name")
    ordering = ("-created_at",)
    list_select_related = ("item_type",)
    readonly_fields = ("id", "public_id", "created_at", "updated_at")
    actions = ["grant_to_user_free"]
    action_form = GrantPackageActionForm

    def grant_to_user_free(self, request, queryset):
        """Akcja: przyznaj wybrany pakiet wskazanemu userowi (jako FREE, bez punktów i bez płatności)."""
        user = request.POST.get("user")
        qty_str = request.POST.get("quantity") or "1"
        try:
            target = User.objects.get(pk=user)
            qty = max(1, int(qty_str))
        except Exception:
            self.message_user(request, "Wybierz poprawnego użytkownika oraz ilość.", level=messages.ERROR)
            return

        granted = 0
        for pkg in queryset:
            for _ in range(qty):
                try:
                    purchase_package(user=target, package=pkg, pay_with="free")
                    granted += 1
                except PurchaseError as e:
                    self.message_user(request, f"Błąd dla pakietu {pkg.public_id}: {e}", level=messages.ERROR)
                    break
        self.message_user(request, f"Przyznano {granted} pakiet(ów) użytkownikowi {target}.", level=messages.SUCCESS)
    grant_to_user_free.short_description = "Przyznaj wybrany pakiet użytkownikowi (FREE)"


# ---------- UserListingPackage ----------

@admin.register(UserListingPackage)
class UserListingPackageAdmin(admin.ModelAdmin):
    list_display = ("id", "public_id", "user", "item_type", "listing_package", "free_total", "paid_total", "updated_at")
    list_filter  = ("listing_package__item_type",)
    search_fields = ("public_id", "user__email", "listing_package__public_id", "listing_package__item_type__name")
    ordering = ("-updated_at",)
    list_select_related = ("user", "listing_package", "listing_package__item_type")
    readonly_fields = ("id", "public_id", "created_at", "updated_at")

    def item_type(self, obj: UserListingPackage):
        return obj.listing_package.item_type
    item_type.short_description = "Item type"


# ---------- ListingUsageHistory ----------

@admin.register(ListingUsageHistory)
class ListingUsageHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "public_id", "user", "item_type", "item_set", "is_bought", "released_at", "created_at")
    list_filter  = ("item_type", "is_bought", ("released_at", admin.EmptyFieldListFilter))
    search_fields = ("public_id", "user__email", "item_set__public_id")
    ordering = ("-created_at",)
    list_select_related = ("user", "item_type", "item_set")
    readonly_fields = ("id", "public_id", "created_at", "updated_at")
    actions = ["release_selected"]

    def release_selected(self, request, queryset):
        now = timezone.now()
        updated = queryset.filter(released_at__isnull=True).update(released_at=now, updated_at=now)
        self.message_user(request, f"Zwolniono {updated} rezerwacji (slotów).", level=messages.SUCCESS)
    release_selected.short_description = "Zwolnij sloty dla zaznaczonych (ustaw released_at)"


# ---------- ServicePurchaseHistory ----------

@admin.register(ServicePurchaseHistory)
class ServicePurchaseHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "public_id", "user", "listing_package", "display_cost", "points_used", "created_at")
    list_filter  = ("listing_package__item_type",)
    search_fields = ("public_id", "user__email", "listing_package__public_id")
    ordering = ("-created_at",)
    list_select_related = ("user", "listing_package", "listing_package__item_type")
    readonly_fields = ("id", "public_id", "created_at", "updated_at")

    def display_cost(self, obj: ServicePurchaseHistory):
        if obj.purchase_cost_amount is not None:
            return f"{obj.purchase_cost_amount} {obj.purchase_cost_currency}"
        return "—"
    display_cost.short_description = "Koszt (PLN)"
