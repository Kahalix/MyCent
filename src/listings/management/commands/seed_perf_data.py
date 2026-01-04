from __future__ import annotations

import random
from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from djmoney.money import Money

from catalog.models import ItemType
from identity.models import SellerProfile, SellerMembership
from listings.models import ItemSet
from customers.models import Customer
from pawns.models import Pawn, PawnLine, PawnExtension
from transactions.models import Transaction

try:
    from pawns.services.fees import calc_extension_fee
except Exception:
    calc_extension_fee = None

User = get_user_model()


class Command(BaseCommand):
    help = "Seed database with users, sellers, item sets and pawns for performance tests."

    def add_arguments(self, parser):
        parser.add_argument("--num-users", type=int, default=500)
        parser.add_argument("--num-sellers", type=int, default=20)
        parser.add_argument("--items-per-seller", type=int, default=200)
        parser.add_argument("--password", type=str, default="PerfPass123!")
        parser.add_argument("--prefix", type=str, default="perf")

        parser.add_argument("--pawns-per-user", type=int, default=2)
        parser.add_argument("--lines-per-pawn", type=int, default=2)
        parser.add_argument("--extensions-rate", type=float, default=0.25)

    @transaction.atomic
    def handle(self, *args, **options):
        num_users = int(options["num_users"])
        num_sellers = int(options["num_sellers"])
        items_per_seller = int(options["items_per_seller"])
        password = str(options["password"])
        prefix = str(options["prefix"])

        pawns_per_user = int(options["pawns_per_user"])
        lines_per_pawn = int(options["lines_per_pawn"])
        extensions_rate = float(options["extensions_rate"])

        self.stdout.write("Seeding users")
        users = self._ensure_users(prefix=prefix, count=num_users, password=password)
        self.stdout.write(f"Users ready: {len(users)}")

        self.stdout.write("Seeding sellers and item types")
        sellers = self._ensure_sellers(prefix=prefix, count=num_sellers, owner_password=password)
        base_type = self._ensure_base_item_type(prefix=prefix)

        self.stdout.write("Seeding item sets")
        self._ensure_item_sets(sellers=sellers, base_type=base_type, items_per_seller=items_per_seller)

        self.stdout.write("Seeding customers")
        customers = self._ensure_customers_for_users(users=users)
        self.stdout.write(f"Customers ready: {len(customers)}")

        self.stdout.write("Preparing item sets cache")
        itemsets_by_seller = self._itemsets_by_seller(sellers=sellers)

        self.stdout.write("Seeding pawns")
        created = self._ensure_pawns(
            users=users,
            customers=customers,
            sellers=sellers,
            itemsets_by_seller=itemsets_by_seller,
            pawns_per_user=pawns_per_user,
            lines_per_pawn=lines_per_pawn,
            extensions_rate=extensions_rate,
        )
        self.stdout.write(f"Pawns created: {created}")

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

            SellerMembership.objects.get_or_create(
                seller_profile=seller,
                user=owner,
                defaults={"role": "OWNER", "is_active": True},
            )

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

    def _ensure_customers_for_users(self, users: list[User]) -> list[Customer]:
        out: list[Customer] = []
        for u in users:
            c = Customer.objects.filter(user=u).first()
            if not c:
                try:
                    c = Customer.objects.create(user=u, email=u.email or "")
                except Exception:
                    c = Customer.objects.filter(email__iexact=(u.email or "")).first()
                    if not c:
                        c = Customer.objects.create(user=u, email=u.email or "")
                    elif not c.user_id:
                        c.user = u
                        c.save(update_fields=["user"])
            out.append(c)
        return out

    def _itemsets_by_seller(self, sellers: list[SellerProfile]) -> dict[int, list[ItemSet]]:
        out: dict[int, list[ItemSet]] = {}
        for s in sellers:
            out[s.id] = list(ItemSet.objects.filter(seller_profile=s))
        return out

    def _ensure_pawns(
        self,
        *,
        users: list[User],
        customers: list[Customer],
        sellers: list[SellerProfile],
        itemsets_by_seller: dict[int, list[ItemSet]],
        pawns_per_user: int,
        lines_per_pawn: int,
        extensions_rate: float,
    ) -> int:
        created = 0
        today = timezone.now().date()

        cust_by_user_id = {c.user_id: c for c in customers if c.user_id}

        for u in users:
            c = cust_by_user_id.get(u.id)
            if not c:
                continue

            existing = Pawn.objects.filter(customer=c).count()
            to_create = max(0, pawns_per_user - existing)
            if to_create <= 0:
                continue

            for _ in range(to_create):
                seller = random.choice(sellers)
                operator = seller.owner

                principal_amount = Decimal(random.randint(5000, 150000)) / Decimal("100")
                principal = Money(principal_amount, "PLN")

                age_days = random.randint(0, 180)
                start_date = today - timedelta(days=age_days)
                due_date = start_date + timedelta(days=random.choice([14, 30, 60]))

                tx = Transaction.objects.create(
                    user=operator,
                    type="PLEDGE",
                    status="COMPLETED",
                    expected_total_amount=0,
                    expected_total_currency="PLN",
                )

                pawn = Pawn.objects.create(
                    transaction=tx,
                    seller_profile=seller,
                    operator=operator,
                    customer=c,
                    customer_snapshot={"email": c.email, "customer_public_id": c.public_id},
                    principal=principal,
                    appraisal_total=Money(0, "PLN"),
                    start_date=start_date,
                    due_date=due_date,
                    status="ACTIVE",
                )

                items = itemsets_by_seller.get(seller.id) or []
                if not items:
                    items = list(ItemSet.objects.filter(seller_profile=seller))
                    itemsets_by_seller[seller.id] = items

                total = Money(0, "PLN")
                lines: list[PawnLine] = []
                for _i in range(max(1, lines_per_pawn)):
                    iset = random.choice(items) if items else None
                    qty = random.randint(1, 3)
                    if iset and getattr(iset, "price", None):
                        val = iset.price
                    else:
                        val = Money(Decimal(random.randint(1000, 50000)) / Decimal("100"), "PLN")
                    total += val * qty

                    lines.append(
                        PawnLine(
                            pawn=pawn,
                            item_set=iset,
                            title=(iset.set_name if iset else "Pozycja"),
                            description="",
                            quantity=qty,
                            appraisal_value=val,
                            item_snapshot={},
                        )
                    )

                PawnLine.objects.bulk_create(lines)

                pawn.appraisal_total = total
                pawn.save(update_fields=["appraisal_total", "updated_at"])

                if extensions_rate > 0 and random.random() < extensions_rate:
                    days = random.choice([7, 14, 30])
                    if calc_extension_fee:
                        fee = calc_extension_fee(principal=pawn.principal, days=int(days))
                    else:
                        fee_amount = (pawn.principal.amount * Decimal("0.01")) * Decimal(days) / Decimal("7")
                        fee = Money(fee_amount.quantize(Decimal("0.01")), "PLN")

                    ext_tx = Transaction.objects.create(
                        user=operator,
                        type="PAWN_EXTENSION",
                        status="COMPLETED",
                        expected_total_amount=fee.amount,
                        expected_total_currency=str(fee.currency),
                    )

                    prev = pawn.due_date
                    new_due = pawn.due_date + timedelta(days=int(days))
                    pawn.due_date = new_due
                    pawn.save(update_fields=["due_date", "updated_at"])

                    PawnExtension.objects.create(
                        pawn=pawn,
                        days=int(days),
                        fee=fee,
                        previous_due=prev,
                        new_due=new_due,
                        transaction=ext_tx,
                        created_by=operator,
                    )

                created += 1

        return created
