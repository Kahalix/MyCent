from __future__ import annotations
from django.db.models import Prefetch
from listings.models import ItemSet, ItemSetImage, ItemSetShipping
from shipping.models import PackageType
import re

SLUG_TAIL_RE = re.compile(r"-([a-z0-9][a-z0-9_-]{5,})$")

def public_itemsets_qs():
    return (
        ItemSet.objects
        .select_related("seller_profile", "owner_user", "type", "catalog_item")
        .prefetch_related(
            Prefetch("images", queryset=ItemSetImage.objects.order_by("image_order", "id")),
        )
        .filter(status="AVAILABLE")
        .order_by("-created_at")
    )

def suggest_package_types(itemset):
    links = {link.package_type_id: link for link in itemset.shipping_options.select_related("package_type").all()}
    out = []
    pkgs = PackageType.objects.all()

    def leq(a, b):
        return b is None or a is None or a <= b

    for pkg in pkgs:
        link = links.get(pkg.id)
        if link:
            length = link.packed_length_cm or itemset.length_cm
            width = link.packed_width_cm or itemset.width_cm
            height = link.packed_height_cm or itemset.height_cm
            weight = link.packed_weight_kg or itemset.weight_kg
            fits = leq(length, pkg.max_length_cm) and leq(width, pkg.max_width_cm) and leq(height, pkg.max_height_cm) and leq(
                float(weight) if weight is not None else None,
                float(pkg.max_weight_kg) if pkg.max_weight_kg is not None else None
            )
            if not fits:
                continue
            effective_price = link.price_override if link.price_override is not None else pkg.price
            price_source = "override" if link.price_override else ("catalog" if pkg.price is not None else "unknown")
            already_linked = True
        else:
            fits = itemset.fits_package(pkg)
            if not fits:
                continue
            effective_price = pkg.price
            price_source = "catalog" if pkg.price is not None else "unknown"
            already_linked = False

        out.append({
            "package_type": pkg,
            "effective_price": effective_price,
            "price_source": price_source,
            "already_linked": already_linked,
        })

    def sort_key(row):
        price = row["effective_price"]
        amount = price.amount if price is not None else None
        provider = row["package_type"].provider or ""
        dimensions = row["package_type"].dimensions or ""
        return (1, "", "") if amount is None else (0, amount, f"{provider} {dimensions}")

    out.sort(key=sort_key)
    return out

def itemset_by_slug(slug: str):
    m = SLUG_TAIL_RE.search(slug)
    if m:
        pid = m.group(1)
        obj = (
            ItemSet.objects
            .filter(public_id=pid, status="AVAILABLE")
            .select_related("seller_profile", "owner_user", "type", "catalog_item")
            .prefetch_related(
                Prefetch("images", queryset=ItemSetImage.objects.order_by("image_order", "id")),
                Prefetch("shipping_options", queryset=ItemSetShipping.objects.select_related("package_type")),
            )
            .first()
        )
        if obj:
            return obj
    return (
        ItemSet.objects
        .select_related("seller_profile", "owner_user", "type", "catalog_item")
        .prefetch_related(
            Prefetch("images", queryset=ItemSetImage.objects.order_by("image_order", "id")),
            Prefetch("shipping_options", queryset=ItemSetShipping.objects.select_related("package_type")),
        )
        .filter(slug=slug, status="AVAILABLE")
        .first()
    )