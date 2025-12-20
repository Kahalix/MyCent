from django.contrib import admin
from .models import Cart, CartItem

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("public_id","user","status","created_at")
    list_filter = ("status",)
    search_fields = ("public_id","user__email")
    readonly_fields = ("public_id","created_at","updated_at")
    list_select_related = ("user",)
    show_full_result_count = False
    list_per_page = 50

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("cart","item_set","quantity")
    search_fields = ("item_set__set_name","cart__public_id")
    readonly_fields = ("public_id","created_at","updated_at")
