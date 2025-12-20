from __future__ import annotations
from django.contrib import admin

from coupons.models import Coupon, UserCoupon
from coupons.forms import CouponAdminForm


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    form = CouponAdminForm
    list_display = ("public_id", "code", "discount_type", "discount_value", "active", "expiration_date", "quantity", "points_cost")
    list_filter = ("discount_type", "active")
    search_fields = ("public_id", "code")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(UserCoupon)
class UserCouponAdmin(admin.ModelAdmin):
    list_display = ("public_id", "user", "coupon", "redeemed", "purchased_at", "redeemed_at", "points_paid")
    list_filter = ("redeemed",)
    search_fields = ("public_id", "user__email", "coupon__code")
    readonly_fields = ("public_id", "created_at", "updated_at")
