from __future__ import annotations

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
    help = "Tworzy lub aktualizuje konto administratora admin@o2.pl oraz seeduje itemtypes, jeśli jeszcze nie zostały zseedowane."

    def handle(self, *args, **options):
        User = get_user_model()

        email = "admin@o2.pl"
        password = "Admin@1234"
        email_norm = email.lower().strip()

        user = User.objects.filter(email__iexact=email_norm).first()

        if user:
            changed_fields = []

            if not user.is_staff:
                user.is_staff = True
                changed_fields.append("is_staff")

            if not user.is_superuser:
                user.is_superuser = True
                changed_fields.append("is_superuser")

            if getattr(user, "role", None) != "OWNER":
                user.role = "OWNER"
                changed_fields.append("role")

            if getattr(user, "user_status", None) != "ACTIVE":
                user.user_status = "ACTIVE"
                changed_fields.append("user_status")

            if not user.is_active:
                user.is_active = True
                changed_fields.append("is_active")

            if changed_fields:
                user.save(update_fields=changed_fields)
                self.stdout.write(self.style.SUCCESS(f"Zaktualizowano istniejące konto admina: {email_norm}"))
            else:
                self.stdout.write(self.style.WARNING(f"Konto admina już istnieje i nie wymaga zmian: {email_norm}"))
        else:
            user = User.objects.create_superuser(
                email=email_norm,
                password=password,
                first_name="Admin",
                last_name="User",
                role="OWNER",
            )
            self.stdout.write(self.style.SUCCESS(f"Utworzono konto administratora: {user.email}"))

        if not _is_itemtypes_seeded():
            self.stdout.write("Seeduję itemtypes poprzez seed_itemtypes_pl…")
            call_command("seed_itemtypes_pl")
            self.stdout.write(self.style.SUCCESS("Seed itemtypes_pl zakończony."))
        else:
            self.stdout.write(self.style.WARNING("Itemtypes wyglądają na zseedowane, pomijam seed_itemtypes_pl."))
