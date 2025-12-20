from django.core.management.base import BaseCommand
from saved.services.refresh import refresh_saved_searches, check_price_drops

class Command(BaseCommand):
    help = "Odświeża SavedSearch i sprawdza spadki cen."

    def add_arguments(self, p):
        p.add_argument("--search-only", action="store_true")
        p.add_argument("--prices-only", action="store_true")
        p.add_argument("--prune", action="store_true")
        p.add_argument("--limit-searches", type=int, default=0)
        p.add_argument("--limit-listings", type=int, default=0)
        p.add_argument("--notify", action="store_true")

    def handle(self, *args, **o):
        if not o["prices_only"]:
            s = refresh_saved_searches(limit=o["limit_searches"] or None, prune=o["prune"])
            self.stdout.write(self.style.SUCCESS(f"SavedSearch: {s}"))
        if not o["search_only"]:
            s = check_price_drops(limit=o["limit_listings"] or None, notify=o["notify"])
            self.stdout.write(self.style.SUCCESS(f"PriceDrops: {s}"))
