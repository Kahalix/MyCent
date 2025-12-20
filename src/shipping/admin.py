from __future__ import annotations
from django.contrib import admin
from .models import PackageType, ShippingAddress


@admin.register(PackageType)
class PackageTypeAdmin(admin.ModelAdmin):
    list_display = ("provider","dimensions","max_length_cm","max_width_cm","max_height_cm","max_weight_kg","price","points")
    list_filter = ("provider",)
    search_fields = ("dimensions",)
    ordering = ("provider","points")


@admin.register(ShippingAddress)
class ShippingAddressAdmin(admin.ModelAdmin):
    list_display = ("user","first_name","last_name","city","country","postal_code")
    search_fields = ("user__email","city","country","postal_code","first_name","last_name")
    autocomplete_fields = ("user",)
