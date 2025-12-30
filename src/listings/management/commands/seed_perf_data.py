from __future__ import annotations

import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from djmoney.money import Money

from catalog.models import ItemType
from identity.models import SellerProfile
from listings.models import ItemSet

User = get_user_model()


class Command(BaseCommand):
    help = "Seed database with users, sellers and item sets for performance tests."

    def add_arguments(self, parser):
        parser.add_argument("--num-users", type=int, default=500)
        parser.add_argument("--num-sellers", type=int, default=20)
        parser.add_argument("--items-per-seller", type=int, default=200)
        parser.add_argument("--password", type=str, default="PerfPass123!")
        parser.add_argument("--prefix", type=str, default="perf")

    @transaction.atomic
    def handle(self, *args, **options):
        num_users = options["num_users"]
        num_sellers = options["num_sellers"]
        items_per_seller = options["items_per_seller"]
        password = options["password"]
        prefix = options["prefix"]

        self.stdout.write("Seeding users")
        users = self._ensure_users(prefix=prefix, count=num_users, password=password)
        self.stdout.write(f"Users ready: {len(users)}")

        self.stdout.write("Seeding sellers and item types")
        sellers = self._ensure_sellers(prefix=prefix, count=num_sellers, owner_password=password)
        base_type = self._ensure_base_item_type(prefix=prefix)

        self.stdout.write("Seeding item sets")
        self._ensure_item_sets(sellers=sellers, base_type=base_type, items_per_seller=items_per_seller)

        self.stdout.write(self.style.SUCCESS("Perf data seed completed"))

    def _ensure_users(self, prefix: str, count: int, password: str) -> list[User]:
        users: list[User] = []
        for i in range(1, count + 1):
            email = f"{prefix}user{i:04d}@example.com"
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "role": "CLIENT",
                    "user_status": "ACTIVE",
                    "is_active": True,
                },
            )
            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
            users.append(user)
        return users

    def _ensure_sellers(self, prefix: str, count: int, owner_password: str) -> list[SellerProfile]:
        sellers: list[SellerProfile] = []
        for i in range(1, count + 1):
            owner_email = f"{prefix}owner{i:04d}@example.com"
            owner, created_owner = User.objects.get_or_create(
                email=owner_email,
                defaults={
                    "role": "OWNER",
                    "user_status": "ACTIVE",
                    "is_active": True,
                },
            )
            if created_owner:
                owner.set_password(owner_password)
                owner.save(update_fields=["password"])

            slug = f"{prefix}-perf-shop-{i:03d}"
            seller, created_seller = SellerProfile.objects.get_or_create(
                slug=slug,
                defaults={
                    "owner": owner,
                    "company_name": f"Perf Shop {i}",
                },
            )
            if not created_seller and seller.owner_id != owner.id:
                seller.owner = owner
                seller.save(update_fields=["owner"])

            sellers.append(seller)
        return sellers

    def _ensure_base_item_type(self, prefix: str) -> ItemType:
        name = f"{prefix}-perf-root"
        slug = slugify(name)
        existing = ItemType.objects.filter(name=name, parent__isnull=True).first()
        if existing:
            return existing
        existing_by_path = ItemType.objects.filter(path__in=[slug, f"{slug}-root"], parent__isnull=True).first()
        if existing_by_path:
            return existing_by_path
        obj = ItemType(name=name)
        obj.save()
        return obj

    def _ensure_item_sets(self, sellers: list[SellerProfile], base_type: ItemType, items_per_seller: int) -> None:
        for seller in sellers:
            existing_count = ItemSet.objects.filter(seller_profile=seller).count()
            to_create = max(0, items_per_seller - existing_count)

            for i in range(existing_count + 1, existing_count + to_create + 1):
                price_value = Decimal(random.randint(1000, 10000)) / Decimal("100")
                stock = random.randint(1, 20)

                allow_online = random.random() < 0.7
                listing_type = "BUY" if allow_online else "LISTING"

                set_name = f"Perf item {seller.slug} #{i}"

                ItemSet.objects.create(
                    set_name=set_name,
                    description="Perf test item",
                    price=Money(price_value, "PLN"),
                    stock_quantity=stock,
                    condition="USED",
                    status="AVAILABLE",
                    listing_type=listing_type,
                    allow_online_checkout=allow_online,
                    added_by="STAFF",
                    seller_profile=seller,
                    owner_user=None,
                    length_cm=random.randint(10, 100),
                    width_cm=random.randint(10, 100),
                    height_cm=random.randint(5, 50),
                    weight_kg=Decimal(random.randint(100, 3000)) / Decimal("1000"),
                    type=base_type,
                    catalog_item=None,
                    attributes={},
                )
