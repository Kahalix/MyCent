from __future__ import annotations
from django.db import models
from common.models import PublicIdModel
from identity.models import User
from djmoney.models.fields import MoneyField
from django.db.models import Q

class PackageType(PublicIdModel):
    """
    Definicja typu paczki u przewoźnika oraz jego limitów.
    None w limitach oznacza brak limitu.
    """
    PROVIDER = [
        ("INPOST","InPost"),("DPD","DPD"),("POCZTAPOLSKA","Poczta Polska"),
        ("ORLEN","Orlen"),("OTHER","Other")
    ]
    provider = models.CharField(max_length=20, choices=PROVIDER, default="OTHER")

    # Marketingowa etykieta (np. Gabaryt A, Paczkomat M)
    dimensions = models.CharField(max_length=120, blank=True)

    # Limity techniczne (cm / kg)
    max_length_cm = models.PositiveIntegerField(null=True, blank=True)
    max_width_cm  = models.PositiveIntegerField(null=True, blank=True)
    max_height_cm = models.PositiveIntegerField(null=True, blank=True)
    max_weight_kg = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)

    # Cena katalogowa + punkty
    price  = MoneyField(max_digits=19, decimal_places=2, default_currency="PLN", null=True, blank=True)
    points = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["provider"], name="ix_pkg_provider"),
            models.Index(fields=["max_length_cm","max_width_cm","max_height_cm","max_weight_kg"], name="ix_pkg_limits"),
            models.Index(fields=["points"], name="ix_pkg_points"),
            models.Index(fields=["price_currency","price"], name="ix_pkg_price_cur_amount"),
        ]
        constraints = [
            models.CheckConstraint(name="ck_pkg_points_nonneg", check=Q(points__gte=0)),
            models.CheckConstraint(name="ck_pkg_price_nonneg", check=Q(price__isnull=True) | Q(price__gte=0)),
        ]

    def __str__(self):
        label = self.dimensions or ""
        return f"{self.get_provider_display()} {label}".strip()

class ShippingAddress(PublicIdModel):
    """
    Jeden adres wysyłkowy przypięty do użytkownika (OneToOne).
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="shipping_address")
    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)
    phone_number = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    street = models.CharField(max_length=120, blank=True)
    house_number = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=60, blank=True)

    def __str__(self):
        parts = [self.first_name, self.last_name, self.city, self.country]
        return " ".join([p for p in parts if p]) or f"Addr {self.public_id}"
