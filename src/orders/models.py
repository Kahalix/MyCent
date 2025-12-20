from __future__ import annotations
from django.db import models
from django.db.models import Q
from djmoney.models.fields import MoneyField
from django.utils import timezone
from django.core.validators import MinValueValidator
from moneyed import Money

from common.models import PublicIdModel
from customers.models import Customer
from identity.models import User, SellerProfile
from listings.models import ItemSet
from transactions.models import Transaction


class Order(PublicIdModel):
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, related_name="orders")
    seller_profile = models.ForeignKey(SellerProfile, on_delete=models.PROTECT, related_name="orders")
    buyer = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")

    order_name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    purchase_date = models.DateField(null=True, blank=True)

    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    customer_snapshot = models.JSONField(default=dict, blank=True)  # imię, nazwisko, kontakt, adres, dokument
    shipping_address = models.JSONField(default=dict, blank=True)  # jeśli wysyłka pocztą; inaczej puste

    items_total = MoneyField(max_digits=19, decimal_places=2, default_currency="PLN", null=True, blank=True)
    shipping_total = MoneyField(max_digits=19, decimal_places=2, default=Money(0, "PLN"), default_currency="PLN", null=True, blank=True)

    purchase_cost = MoneyField(
        max_digits=19, decimal_places=2,
        default=Money(0, "PLN"), default_currency="PLN",
        null=True, blank=True
    )

    PAYMENT_METHOD = [
        ("CREDIT_CARD","Credit Card"),("DEBIT_CARD","Debit Card"),
        ("PAYPAL","PayPal"),("ONLINE_PAYMENT","Online Payment"),
        ("BANK_TRANSFER","Bank Transfer"),("CASH_ON_DELIVERY","Cash on Delivery"),("CASH","Cash")
    ]
    payment_method = models.CharField(max_length=16, choices=PAYMENT_METHOD, default="CASH")

    STATUS = [("PENDING","Pending"),("COMPLETED","Completed"),("CANCELLED","Cancelled"),("REFUNDED","Refunded")]
    order_status = models.CharField(max_length=10, choices=STATUS, default="PENDING")

    class Meta:
        indexes = [
            models.Index(fields=["seller_profile", "order_status"], name="ix_orders_seller_status"),
            models.Index(fields=["buyer", "order_status"], name="ix_orders_buyer_status"),
            models.Index(fields=["purchase_date"], name="ix_orders_date"),
            models.Index(fields=["transaction"], name="ix_orders_tx"),
        ]

    # --- domena ---
    def recalc_totals(self, save: bool = True):
        try:
            self._prefetched_objects_cache.pop('order_lines', None)
            self._prefetched_objects_cache.pop('shippings', None)
        except AttributeError:
            pass

        items = None
        for l in OrderLine.objects.filter(order_id=self.id).only('line_total', 'line_total_currency').iterator():
            items = l.line_total if items is None else (items + l.line_total)
        self.items_total = items

        ship_total = None
        for s in OrderShipping.objects.filter(order_id=self.id).only('price', 'price_currency').iterator():
            if s.price is not None:
                ship_total = s.price if ship_total is None else (ship_total + s.price)
        from moneyed import Money
        self.shipping_total = ship_total or Money(0, "PLN")

        if self.items_total is None and (ship_total is None or ship_total.amount == 0):
            self.purchase_cost = None
        else:
            base = self.items_total or Money(0, "PLN")
            self.purchase_cost = base + (self.shipping_total or Money(0, "PLN"))

        if save:
            self.save(update_fields=["items_total", "shipping_total", "purchase_cost", "updated_at"])

    @property
    def grand_total(self):
        """
        Suma do zapłaty dla tego zamówienia (items_total + shipping_total).
        Zwraca Money(0, 'PLN') gdy nie ma jeszcze pozycji.
        """
        if self.purchase_cost is not None:
            return self.purchase_cost
        # jeśli brak pozycji – zwróć neutralne 0 PLN:
        return Money(0, "PLN")


class OrderLine(PublicIdModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="order_lines")
    item_set = models.ForeignKey(ItemSet, null=True, blank=True, on_delete=models.PROTECT, related_name="order_lines")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = MoneyField(max_digits=19, decimal_places=2, default=Money(0, "PLN"), default_currency="PLN")
    line_total = MoneyField(max_digits=19, decimal_places=2, default=Money(0, "PLN"), default_currency="PLN")

    item_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["order"], name="ix_order_lines_order"),
            models.Index(fields=["item_set"], name="ix_order_lines_item"),
        ]

    def save(self, *args, **kwargs):
        self.line_total = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def display_name(self) -> str:
        if self.item_set_id:
            return self.item_set.set_name
        return (self.item_snapshot.get("title")
                or self.item_snapshot.get("set_name")
                or self.item_snapshot.get("description")
                or "Pozycja")

    def __str__(self) -> str:
        return f"{self.display_name()} x{self.quantity}"


class OrderShipping(PublicIdModel):
    """
    Wysyłka *dla pozycji* (split per metoda). Jedna wysyłka per linia (domyślnie).
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="shippings")
    order_line = models.OneToOneField(OrderLine, on_delete=models.CASCADE, related_name="shipping")  # 1:1 per linia
    tracking_number = models.CharField(max_length=120, blank=True)

    # opcjonalnie: jaka metoda (np. PackageType) i jej cena
    package_type = models.ForeignKey("shipping.PackageType", null=True, blank=True, on_delete=models.SET_NULL, related_name="order_shippings")
    price = MoneyField(max_digits=19, decimal_places=2, default_currency="PLN", null=True, blank=True)

    SHIPPING_STATUS = [("PENDING","Pending"),("SHIPPED","Shipped"),("DELIVERED","Delivered"),("CANCELLED","Cancelled"),("RETURNED","Returned")]
    shipping_status = models.CharField(max_length=9, choices=SHIPPING_STATUS, default="PENDING")
    package_label = models.CharField(max_length=120, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["order","shipping_status"], name="ix_ordershipping_status"),
        ]

    def clean(self):
        # spójność: linia należy do tego samego ordera
        if self.order_line and self.order_id and self.order_line.order_id != self.order_id:
            from django.core.exceptions import ValidationError
            raise ValidationError("order_line nie należy do tego ordera.")

    def __str__(self) -> str:
        return f"Shipping {self.public_id} [{self.shipping_status}]"


class ItemReservation(PublicIdModel):
    """
    Rezerwacja sztuk na czas trwania płatności (lub do TTL).
    Aktywna = released_at IS NULL i expires_at > now().
    """
    item_set = models.ForeignKey(ItemSet, on_delete=models.CASCADE, related_name="reservations")
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="reservations")
    order_line = models.ForeignKey("orders.OrderLine", null=True, blank=True, on_delete=models.SET_NULL, related_name="reservations")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reservations")

    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    expires_at = models.DateTimeField(db_index=True)
    released_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["item_set", "expires_at"], name="ix_resv_item_exp"),
            models.Index(fields=["transaction"], name="ix_resv_tx"),
        ]

    @property
    def is_active(self) -> bool:
        return self.released_at is None and self.expires_at > timezone.now()

    def __str__(self) -> str:
        return f"RESV {self.item_set_id} x{self.quantity}"
