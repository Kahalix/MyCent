from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from djmoney.models.fields import MoneyField
from moneyed import Money

from common.models import PublicIdModel
from identity.models import SellerProfile, User
from catalog.models import ItemType, CatalogItem, _validate_against_schema, _normalize_and_validate_attrs
from shipping.models import PackageType


class ItemSet(PublicIdModel):
    set_name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=220, blank=True)
    description = models.TextField(blank=True)

    price = MoneyField(max_digits=19, decimal_places=2, default_currency="PLN")
    stock_quantity = models.PositiveIntegerField(default=1)

    CONDITION = [("NEW", "New"), ("USED", "Used"), ("DAMAGED", "Damaged")]
    condition = models.CharField(max_length=7, choices=CONDITION, default="USED")

    STATUS = [("AVAILABLE", "Available"), ("SOLD", "Sold"), ("RESERVED", "Reserved"), ("EXPIRED", "Expired"), ("CLOSED", "Closed"), ("SUSPENDED", "Suspended"), ("DELETED", "Deleted")]
    status = models.CharField(max_length=9, choices=STATUS, default="AVAILABLE")

    TYPE = [("BUY", "Buy"), ("LISTING", "Listing"), ("EXCHANGE", "Exchange")]
    listing_type = models.CharField(max_length=8, choices=TYPE, default="LISTING")

    allow_online_checkout = models.BooleanField(default=False)

    ADDED_BY = [("STAFF", "STAFF"), ("USER", "USER")]
    added_by = models.CharField(max_length=5, choices=ADDED_BY, default="STAFF")

    seller_profile = models.ForeignKey(SellerProfile, null=True, blank=True, on_delete=models.PROTECT, related_name="item_sets")
    owner_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="item_sets_created")

    length_cm = models.PositiveIntegerField(null=True, blank=True)
    width_cm = models.PositiveIntegerField(null=True, blank=True)
    height_cm = models.PositiveIntegerField(null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)

    type = models.ForeignKey(ItemType, on_delete=models.PROTECT, related_name="item_sets")
    catalog_item = models.ForeignKey(CatalogItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="item_sets")

    attributes = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["seller_profile", "slug"], name="uq_itemset_seller_slug"),
            models.UniqueConstraint(fields=["owner_user", "slug"], condition=Q(owner_user__isnull=False), name="uq_itemset_user_slug"),
            models.CheckConstraint(
                name="ck_user_no_online_checkout",
                check=Q(added_by="STAFF") | Q(added_by="USER", allow_online_checkout=False),
            ),
            models.CheckConstraint(
                name="ck_nonbuy_no_online",
                check=Q(listing_type="BUY") | Q(allow_online_checkout=False),
            ),
        ]
        indexes = [
            models.Index(fields=["status", "listing_type", "price"], name="ix_item_sets_status_type_price"),
            models.Index(fields=["type"], name="ix_item_sets_item_type"),
            models.Index(fields=["seller_profile", "slug"], name="ix_item_sets_seller_slug_idx"),
            models.Index(fields=["owner_user", "slug"], name="ix_item_sets_user_slug_idx"),
            models.Index(fields=["added_by"], name="ix_item_sets_added_by"),
            models.Index(fields=["allow_online_checkout"], name="ix_item_sets_online_idx"),
            models.Index(fields=["status", "-created_at"], name="ix_item_sets_status_created"),
        ]

    def _make_slug(self) -> str:
        base = slugify(self.set_name or "").strip("-") or "ogloszenie"
        return f"{base}-{self.public_id}"

    def save(self, *args, **kwargs):
        creating = self.pk is None
        if creating and not self.public_id and not self.slug:
            super().save(*args, **kwargs)
            self.slug = self._make_slug()
            super(ItemSet, self).save(update_fields=["slug"])
            return
        if not self.slug:
            self.slug = self._make_slug()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()

        if self.catalog_item_id and not self.type_id and self.catalog_item:
            self.type = self.catalog_item.type

        if self.type_id and ItemType.objects.filter(parent_id=self.type_id).exists():
            raise ValidationError({"type": "Wybierz kategorię końcową (bez podkategorii)."})

        if self.catalog_item_id and self.type_id and self.catalog_item and self.catalog_item.type_id != self.type_id:
            raise ValidationError({"catalog_item": "CatalogItem musi należeć do tej samej kategorii (ItemType)."})

        if not (self.attributes or {}):
            if self.catalog_item_id and self.catalog_item:
                self.attributes = dict(self.catalog_item.attributes or {})

        if self.type_id:
            t = ItemType.objects.only("id", "schema_json").filter(id=self.type_id).first()
            if t and t.schema_json:
                self.attributes = _normalize_and_validate_attrs(
                    self.attributes or {}, t.schema_json, where="attributes", require_same_fields=False
                )

        if self.added_by == "USER":
            if self.allow_online_checkout:
                raise ValidationError({"allow_online_checkout": "Użytkownik nie może włączać zakupu online."})
            if self.seller_profile is not None:
                raise ValidationError({"seller_profile": "Propozycja USER nie może mieć seller_profile."})
            if self.listing_type not in ("LISTING", "EXCHANGE"):
                raise ValidationError({"listing_type": "Użytkownik może dodać tylko LISTING/EXCHANGE."})
            if self.owner_user is None:
                raise ValidationError({"owner_user": "Propozycja USER wymaga owner_user."})

        if self.allow_online_checkout:
            if self.listing_type != "BUY":
                raise ValidationError({"allow_online_checkout": "Checkout online dozwolony wyłącznie dla listing_type=BUY."})
            if not self.seller_profile_id:
                raise ValidationError({"seller_profile": "Oferta z checkoutem online wymaga powiązanego SellerProfile."})

        sq = self.stock_quantity
        try:
            sq_i = int(sq) if sq is not None else 0
        except Exception:
            sq_i = 0

        if self.status == "AVAILABLE" and sq_i <= 0:
            raise ValidationError({
                "stock_quantity": "Aby aktywować ogłoszenie, stock_quantity musi być > 0."
            })

    def fits_package(self, pkg: PackageType) -> bool:
        def leq(a, b):
            return b is None or a is None or a <= b
        return (
            leq(self.length_cm, pkg.max_length_cm)
            and leq(self.width_cm, pkg.max_width_cm)
            and leq(self.height_cm, pkg.max_height_cm)
            and leq(float(self.weight_kg) if self.weight_kg is not None else None,
                    float(pkg.max_weight_kg) if pkg.max_weight_kg is not None else None)
        )

    def __str__(self):
        return self.set_name

class ItemSetImage(PublicIdModel):
    item_set = models.ForeignKey(ItemSet, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="itemsets/", blank=True, null=True)
    image_path = models.CharField(max_length=1024, blank=True)
    image_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("image_order",)
        # constraints = [
        #     models.UniqueConstraint(
        #         fields=["item_set", "image_order"],
        #         name="uq_itemset_image_unique_order",
        #     ),
        # ]
        indexes = [models.Index(fields=["item_set", "image_order"], name="ix_itemset_images")]

    def __str__(self):
        return f"{self.item_set.set_name} [{self.image_order}]"


class ItemSetShipping(PublicIdModel):
    item_set = models.ForeignKey(ItemSet, on_delete=models.CASCADE, related_name="shipping_options")
    package_type = models.ForeignKey("shipping.PackageType", on_delete=models.PROTECT, related_name="itemset_links")
    price_override = MoneyField(max_digits=19, decimal_places=2, default_currency="PLN", null=True, blank=True)

    packed_length_cm = models.PositiveIntegerField(null=True, blank=True)
    packed_width_cm  = models.PositiveIntegerField(null=True, blank=True)
    packed_height_cm = models.PositiveIntegerField(null=True, blank=True)
    packed_weight_kg = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item_set", "package_type"], name="uq_itemset_shipping_pkg")
        ]
        indexes = [
            models.Index(fields=["item_set"], name="ix_itemset_shipping_item"),
            models.Index(fields=["package_type"], name="ix_itemset_shipping_pkg"),
        ]

    def clean(self):
        # tylko SELLER + BUY + checkout online
        if not (self.item_set.allow_online_checkout and self.item_set.listing_type == "BUY" and self.item_set.added_by == "STAFF"):
            raise ValidationError("Opcje wysyłki są dostępne wyłącznie dla ofert SELLER (STAFF) z listing_type=BUY i checkoutem online.")

        def pick(field):
            return getattr(self, f"packed_{field}") or getattr(self.item_set, field)

        length = pick("length_cm")
        width  = pick("width_cm")
        height = pick("height_cm")
        weight = pick("weight_kg")

        for name, val in [("packed_length_cm", self.packed_length_cm),
                          ("packed_width_cm",  self.packed_width_cm),
                          ("packed_height_cm", self.packed_height_cm)]:
            if val is not None and val <= 0:
                raise ValidationError({name: "Musi być > 0 (albo puste)."})

        if self.packed_weight_kg is not None and self.packed_weight_kg <= 0:
            raise ValidationError({"packed_weight_kg": "Musi być > 0 (albo puste)."})

        pkg = self.package_type
        def leq(a, b): return b is None or a is None or a <= b
        ok = (
            leq(length, pkg.max_length_cm)
            and leq(width,  pkg.max_width_cm)
            and leq(height, pkg.max_height_cm)
            and leq(float(weight) if weight is not None else None,
                    float(pkg.max_weight_kg) if pkg.max_weight_kg is not None else None)
        )
        if not ok:
            raise ValidationError("Wymiary/masa nie mieszczą się w wybranym typie paczki.")

    def __str__(self):
        return f"{self.item_set.set_name} -> {self.package_type}"
