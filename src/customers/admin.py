from django.contrib import admin
from customers.models import Customer
from customers.forms import CustomerAdminForm

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    form = CustomerAdminForm
    list_display = ("public_id","first_name","last_name","email","phone","city","created_at")
    # list_filter = ("city",)
    search_fields = ("first_name","last_name","email","phone","document_number","city","postal_code")
    readonly_fields = ("public_id","created_at","updated_at")
