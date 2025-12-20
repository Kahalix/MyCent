from __future__ import annotations
from django.contrib import admin

from payments.forms import PaymentAdminForm
from payments.models import Payment
from payments.services.commands import confirm_payment_simulator, cancel_active_payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = ("public_id","provider","status","amount","transaction","created_at")
    list_filter   = ("provider","status")
    search_fields = ("public_id","transaction__public_id","provider_payment_id")
    readonly_fields = ("public_id","created_at","updated_at")
    form = PaymentAdminForm
    list_select_related = ("transaction",)
    date_hierarchy = "created_at"
    show_full_result_count = False
    list_per_page = 50

    actions = ["mark_succeeded","mark_failed","mark_cancelled"]

    def mark_succeeded(self, request, queryset):
        for p in queryset:
            confirm_payment_simulator(payment=p, succeed=True)
    mark_succeeded.short_description = "Oznacz jako SUCCEEDED"

    def mark_failed(self, request, queryset):
        for p in queryset:
            confirm_payment_simulator(payment=p, succeed=False)
    mark_failed.short_description = "Oznacz jako FAILED"

    def mark_cancelled(self, request, queryset):
        for p in queryset:
            cancel_active_payment(payment=p, reason="Admin action")
    mark_cancelled.short_description = "Oznacz jako CANCELLED"
