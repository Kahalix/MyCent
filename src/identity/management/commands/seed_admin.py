from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, call_command


def _is_itemtypes_seeded() -> bool:
    from catalog.models import ItemType

    return ItemType.objects.filter(
        name="Smartfony",
        parent__name="Telefony",
        parent__parent__name="Elektronika",
    ).exists()


class Command(BaseCommand):
    help = "Tworzy lub aktualizuje konto administratora na podstawie zmiennych środowiskowych oraz seeduje itemtypes."

    def handle(self, *args, **options):
        User = get_user_model()

        email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
        password = os.environ.get("ADMIN_PASSWORD") or ""
        first_name = os.environ.get("ADMIN_FIRST_NAME") or "Admin"
        last_name = os.environ.get("ADMIN_LAST_NAME") or "User"
        role = os.environ.get("ADMIN_ROLE") or "OWNER"

        if not email or not password:
            raise RuntimeError("Brak ADMIN_EMAIL lub ADMIN_PASSWORD w pliku .env.docker")

        user = User.objects.filter(email__iexact=email).first()

        if user:
            changed_fields = []

            if not user.is_staff:
                user.is_staff = True
                changed_fields.append("is_staff")

            if not user.is_superuser:
                user.is_superuser = True
                changed_fields.append("is_superuser")

            if getattr(user, "role", None) != role:
                user.role = role
                changed_fields.append("role")

            if getattr(user, "user_status", None) != "ACTIVE":
                user.user_status = "ACTIVE"
                changed_fields.append("user_status")

            if not user.is_active:
                user.is_active = True
                changed_fields.append("is_active")

            if first_name and getattr(user, "first_name", "") != first_name:
                user.first_name = first_name
                changed_fields.append("first_name")

            if last_name and getattr(user, "last_name", "") != last_name:
                user.last_name = last_name
                changed_fields.append("last_name")

            if changed_fields:
                user.save(update_fields=changed_fields)
                self.stdout.write(self.style.SUCCESS(f"Zaktualizowano konto admina: {email}"))
            else:
                self.stdout.write(self.style.WARNING(f"Konto admina już istnieje i nie wymaga zmian: {email}"))
        else:
            user = User.objects.create_superuser(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role=role,
            )
            self.stdout.write(self.style.SUCCESS(f"Utworzono konto administratora: {user.email}"))

        if not _is_itemtypes_seeded():
            self.stdout.write("Seeduję itemtypes poprzez seed_itemtypes_pl…")
            call_command("seed_itemtypes_pl")
            self.stdout.write(self.style.SUCCESS("Seed itemtypes_pl zakończony."))
        else:
            self.stdout.write(self.style.WARNING("Itemtypes wyglądają na zseedowane, pomijam seed_itemtypes_pl."))
