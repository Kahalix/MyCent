# src/saved/admin.py
from django.contrib import admin
from .models import SavedListing, SavedSearch, SavedSearchItem

@admin.register(SavedListing)
class SavedListingAdmin(admin.ModelAdmin):
    list_display = ("user","item_set","saved_price_amount","saved_price_currency",
                    "price_drop_notification_sent","last_price_checked_at","created_at")
    list_filter  = ("price_drop_notification_sent",)
    search_fields = ("user__email","item_set__set_name","item_set__public_id")
    list_select_related = ("user", "item_set")
    show_full_result_count = False

@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = ("user","category_path","search_phrase","created_at")
    search_fields = ("user__email","category_path","search_phrase","query_string")

@admin.register(SavedSearchItem)
class SavedSearchItemAdmin(admin.ModelAdmin):
    list_display = ("saved_search","item_set","created_at")
    search_fields = ("saved_search__user__email","item_set__set_name","item_set__public_id")
    list_select_related = ("saved_search", "item_set")
    show_full_result_count = False
