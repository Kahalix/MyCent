from django.contrib import admin
from orders.models import Order, OrderLine, OrderShipping, ItemReservation
from orders.forms import OrderAdminForm, OrderLineAdminForm
from djmoney.forms.fields import MoneyField as AdminMoneyField

class OrderLineInline(admin.TabularInline):
    model = OrderLine
    form = OrderLineAdminForm
    extra = 0
    fields = ("item_set","quantity","unit_price","line_total","item_snapshot")
    readonly_fields = ("line_total","item_snapshot")

class OrderShippingInline(admin.TabularInline):
    model = OrderShipping
    extra = 0
    fields = ("order_line","package_type","price","tracking_number","shipping_status","package_label")

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    list_display = ("public_id","order_name","seller_profile","buyer","order_status","items_total","shipping_total","purchase_cost","created_at")
    list_filter = ("order_status","seller_profile")
    search_fields = ("public_id","order_name","description","buyer__email","seller_profile__slug")
    inlines = [OrderLineInline, OrderShippingInline]
    readonly_fields = ("public_id","created_at","updated_at","items_total","shipping_total","purchase_cost")
    list_select_related = ("seller_profile", "buyer")
    date_hierarchy = "created_at"
    show_full_result_count = False

    actions = ["recalc_totals_action"]


    def recalc_totals_action(self, request, queryset):
        for o in queryset:
            o.recalc_totals(save=True)
    recalc_totals_action.short_description = "Przelicz sumy zamówienia"

@admin.register(ItemReservation)
class ItemReservationAdmin(admin.ModelAdmin):
    list_display = ("item_set","transaction","order_line","user","quantity","expires_at","released_at","created_at")
    list_filter = ("released_at",)
    search_fields = ("item_set__set_name","transaction__public_id","order_line__public_id","user__email")
    list_select_related = ("item_set", "transaction", "order_line", "user")
    show_full_result_count = False
