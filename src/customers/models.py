from __future__ import annotations
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from common.models import PublicIdModel
from identity.models import User


class Customer(PublicIdModel):
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="customers")

    # podstawowe dane kontaktowe
    first_name = models.CharField(max_length=120, blank=True)
    last_name  = models.CharField(max_length=120, blank=True)
    email      = models.EmailField(blank=True)
    phone      = models.CharField(max_length=32, blank=True)

    # adres korespondencyjny
    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    postal_code   = models.CharField(max_length=20, blank=True)
    city          = models.CharField(max_length=120, blank=True)
    country       = models.CharField(max_length=2, blank=True)  # ISO 3166-1 alpha-2

    # dokument (opcjonalnie)
    document_type   = models.CharField(max_length=32, blank=True)  # np. "ID", "PASSPORT"
    document_number = models.CharField(max_length=64, blank=True)
    birth_date      = models.DateField(null=True, blank=True)

    notes = models.TextField(blank=True)  # wewnętrzne notatki

    class Meta:
        indexes = [
            models.Index(Lower("email"), name="ix_customer_email_ci"),
            models.Index(fields=["phone"], name="ix_customer_phone"),
            models.Index(fields=["last_name", "first_name"], name="ix_customer_name"),
            models.Index(fields=["city"], name="ix_customer_city"),
        ]
        constraints = [
            # brak „twardych” wymaganych pól, ale jeśli jest email – to niepusty
            models.CheckConstraint(
                name="ck_customer_email_not_blank",
                check=Q(email__isnull=True) | ~Q(email=""),
            ),
        ]

    def __str__(self):
        fn = f"{self.first_name} {self.last_name}".strip()
        return fn or self.email or self.phone or self.public_id
