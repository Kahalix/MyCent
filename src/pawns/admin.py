from django.contrib import admin
from django.db import transaction  # ⬅️ nowy
from transactions.models import Transaction

from pawns.models import Pawn, PawnLine, PawnExtension
from pawns.forms import PawnAdminForm, PawnLineAdminForm, PawnExtensionAdminForm


class PawnLineInline(admin.TabularInline):
    model = PawnLine
    form = PawnLineAdminForm
    extra = 0
    fields = ("title", "description", "quantity", "appraisal_value", "item_snapshot")
    readonly_fields = ("item_snapshot",)


class PawnExtensionInline(admin.TabularInline):
    model = PawnExtension
    form = PawnExtensionAdminForm
    extra = 0
    fields = ("days", "fee", "previous_due", "new_due", "created_at")
    readonly_fields = ("fee", "previous_due", "new_due", "created_at")


@admin.register(Pawn)
class PawnAdmin(admin.ModelAdmin):
    form = PawnAdminForm
    list_display = ("public_id","seller_profile","status","principal","appraisal_total","start_date","due_date","customer")
    list_filter  = ("status","seller_profile")
    search_fields = ("public_id","customer__first_name","customer__last_name","customer_snapshot")
    inlines = [PawnLineInline, PawnExtensionInline]
    readonly_fields = ("public_id","created_at","updated_at","appraisal_total")

    @transaction.atomic
    def save_formset(self, request, form, formset, change):
        """
        Dla nowych PawnExtension:
          - utwórz Transaction(PAWN_EXTENSION, COMPLETED) z kwotą fee,
          - ustaw created_by,
          - przesuń pawn.due_date do new_due (spójnie z usługą extend_pawn).

        Dodatkowo:
          - obsłuż usuwanie inlinów (formset.deleted_objects),
          - po zmianie linii przelicz appraisal_total.
        """
        instances = formset.save(commit=False)

        for obj in formset.deleted_objects:
            obj.delete()

        for obj in instances:
            if isinstance(obj, PawnExtension) and obj.pk is None:
                tx = Transaction.objects.create(
                    user=request.user,
                    type="PAWN_EXTENSION",
                    status="COMPLETED",
                    expected_total_amount=(obj.fee.amount if obj.fee else 0),
                    expected_total_currency=(str(obj.fee.currency) if obj.fee else "PLN"),
                )
                obj.transaction = tx
                obj.created_by = request.user

                pawn = obj.pawn
                if pawn and obj.new_due and pawn.due_date != obj.new_due:
                    pawn.due_date = obj.new_due
                    pawn.save(update_fields=["due_date", "updated_at"])

            obj.save()

        formset.save_m2m()

        if formset.model is PawnLine:
            form.instance.recalc_appraisal(save=True)
