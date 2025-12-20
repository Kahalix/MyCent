from django.db import models
from django.db.models import Q

from common.models import PublicIdModel
from catalog.models import ItemType
from identity.models import SellerProfile, User
from django.conf import settings
from djmoney.models.fields import MoneyField

class ListingPackage(PublicIdModel):
    listings_free = models.PositiveIntegerField(default=0)
    price  = MoneyField(max_digits=19, decimal_places=2, default_currency="PLN", null=True, blank=True)
    points = models.PositiveIntegerField(default=0)
    item_type = models.ForeignKey(ItemType, on_delete=models.PROTECT, related_name="listing_packages")

    class Meta:
        indexes = [
            models.Index(fields=["item_type"], name="ix_pkg_itemtype"),
            models.Index(fields=["item_type", "points"], name="ix_pkg_itemtype_points"),
            models.Index(fields=["item_type", "price"], name="ix_pkg_itemtype_price"),
        ]

    def __str__(self) -> str:
        return f"{self.item_type.name} / free:{self.listings_free} price:{self.price or '-'} pts:{self.points}"

class UserListingPackage(PublicIdModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="listing_packages")
    listing_package = models.ForeignKey(ListingPackage, on_delete=models.PROTECT, related_name="user_packages")
    free_total = models.PositiveIntegerField(default=0)
    paid_total = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "listing_package"], name="uq_user_listing_package")
        ]
        indexes = [
            models.Index(fields=["user","listing_package"], name="ix_user_pkg"),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} / {self.listing_package.public_id} (free:{self.free_total}, paid:{self.paid_total})"

class ListingUsageHistory(PublicIdModel):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="listing_usages")
    item_type = models.ForeignKey(ItemType, on_delete=models.PROTECT, related_name="listing_usages")
    item_set = models.ForeignKey("listings.ItemSet", null=True, blank=True, on_delete=models.CASCADE, related_name="usage_links")
    is_bought = models.BooleanField(default=False)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item_set"],
                condition=Q(released_at__isnull=True),
                name="uq_active_usage_per_itemset",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "item_type", "released_at"], name="ix_usage_user_type_released"),
            models.Index(fields=["item_set", "released_at"], name="ix_usage_itemset_released"),
        ]

    def __str__(self) -> str:
        state = "ACTIVE" if self.released_at is None else "RELEASED"
        kind = "PAID" if self.is_bought else "FREE"
        return f"{self.user.email} / {self.item_type.name} [{kind}] {state}"

class ServicePurchaseHistory(PublicIdModel):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="service_purchases")
    listing_package = models.ForeignKey(ListingPackage, null=True, blank=True, on_delete=models.SET_NULL)
    purchase_cost_amount = models.DecimalField(max_digits=19, decimal_places=2, null=True, blank=True)
    purchase_cost_currency = models.CharField(max_length=3, default="PLN", blank=True)
    points_used = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"], name="ix_purchase_user_created"),
            models.Index(fields=["listing_package", "created_at"], name="ix_purchase_pkg_created"),
        ]

    def __str__(self) -> str:
        if self.purchase_cost_amount is not None:
            return f"{self.user.email} {self.purchase_cost_amount} {self.purchase_cost_currency}"
        if self.points_used:
            return f"{self.user.email} {self.points_used} pts"
        return f"{self.user.email} FREE"
