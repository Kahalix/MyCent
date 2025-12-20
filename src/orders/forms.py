from __future__ import annotations
from django import forms
from django.core.exceptions import ValidationError

from orders.models import Order, OrderLine, OrderShipping

class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        # Wszystkie linie muszą należeć do tego samego sprzedawcy
        inst: Order = self.instance
        if inst and inst.pk:
            seller = cleaned.get("seller_profile") or inst.seller_profile
            for line in inst.order_lines.select_related("item_set__seller_profile"):
                if line.item_set.seller_profile_id != seller.id:
                    raise ValidationError("Wszystkie pozycje w zamówieniu muszą pochodzić od tego samego sprzedawcy.")
        return cleaned

class OrderLineAdminForm(forms.ModelForm):
    class Meta:
        model = OrderLine
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        order = cleaned.get("order") or self.instance.order
        item = cleaned.get("item_set", self.instance.item_set)
        if item is not None and order is not None:
            if item.seller_profile_id != order.seller_profile_id:
                raise ValidationError("Pozycja musi należeć do tego samego sprzedawcy co zamówienie.")
        if cleaned.get("quantity", 1) <= 0:
            raise ValidationError("Quantity > 0.")
        return cleaned


class OrderShippingAdminForm(forms.ModelForm):
    class Meta:
        model = OrderShipping
        fields = "__all__"
