from __future__ import annotations
from django.db import models
from common.models import PublicIdModel
from identity.models import User
from listings.models import ItemSet

class SavedListing(PublicIdModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_listings")
    item_set = models.ForeignKey(ItemSet, on_delete=models.CASCADE, related_name="saved_by")

    # snapshot ceny w momencie zapisu (uzupełniany sygnałem i/lub cronem)
    saved_price_amount   = models.DecimalField(max_digits=19, decimal_places=2, null=True, blank=True)
    saved_price_currency = models.CharField(max_length=3, default="PLN", blank=True)

    # flaga jednorazowego powiadomienia o spadku
    price_drop_notification_sent = models.BooleanField(default=False)

    # housekeeping
    last_price_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = (("user","item_set"),)
        indexes = [
            models.Index(fields=["user"], name="ix_saved_listing_user"),
            models.Index(fields=["item_set"], name="ix_saved_listing_item"),
            models.Index(fields=["user","item_set"], name="ix_saved_listing_user_item"),
        ]

    def __str__(self):
        return f"{self.user.email} -> {self.item_set.set_name}"


class SavedSearch(PublicIdModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_searches")
    # np. slugi połączone '/motoryzacja/car-audio'
    category_path = models.CharField(max_length=500, blank=True, default="")
    # oryginalny query string (np. ?q=radio&price_max=500)
    query_string = models.CharField(max_length=2000)
    # opcjonalna etykieta użytkownika
    search_phrase = models.CharField(max_length=255, blank=True)
    since_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"], name="ix_saved_search_user"),
            models.Index(fields=["user","search_phrase"], name="ix_saved_search_user_phrase"),
        ]

    def __str__(self):
        return f"{self.user.email} [{self.search_phrase or self.category_path}]"


class SavedSearchItem(PublicIdModel):
    saved_search = models.ForeignKey(SavedSearch, on_delete=models.CASCADE, related_name="items")
    item_set = models.ForeignKey(ItemSet, on_delete=models.CASCADE, related_name="in_saved_searches")

    class Meta:
        unique_together = (("saved_search","item_set"),)
        indexes = [
            models.Index(fields=["saved_search"], name="ix_saved_search_item_search"),
            models.Index(fields=["item_set"], name="ix_saved_search_item_item"),
        ]

    def __str__(self):
        return f"{self.saved_search_id} -> {self.item_set_id}"
