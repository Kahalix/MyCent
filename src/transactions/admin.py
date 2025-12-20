from __future__ import annotations
from django.contrib import admin
from transactions.models import Transaction, TransactionStatusHistory

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("public_id", "type", "status", "user", "expected_total_amount", "expected_total_currency", "created_at")
    list_filter = ("status", "type")
    search_fields = ("public_id", "user__email", "notes")
    readonly_fields = ("public_id", "created_at", "updated_at")
    list_select_related = ("user",)
    date_hierarchy = "created_at"
    show_full_result_count = False

@admin.register(TransactionStatusHistory)
class TransactionStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("transaction", "from_status", "to_status", "created_at")
    list_filter = ("from_status", "to_status")
    search_fields = ("transaction__public_id",)
    readonly_fields = ("public_id", "created_at", "updated_at")
