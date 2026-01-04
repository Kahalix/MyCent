from __future__ import annotations
from django.db import models
from common.models import PublicIdModel
from identity.models import User
from listings.models import ItemSet

class Cart(PublicIdModel):
    STATUS = [("ACTIVE","ACTIVE"),("CHECKED_OUT","CHECKED_OUT"),("ABANDONED","ABANDONED")]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="carts")
    status = models.CharField(max_length=12, choices=STATUS, default="ACTIVE")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user"], condition=models.Q(status="ACTIVE"), name="uq_active_cart_per_user")
        ]
        indexes = [models.Index(fields=["user","status"], name="ix_cart_user_status")]

    def __str__(self): return f"Cart {self.public_id} ({self.user.email})"

class CartItem(PublicIdModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    item_set = models.ForeignKey(ItemSet, on_delete=models.CASCADE, related_name="in_carts")
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = (("cart","item_set"),)
        indexes = [
            models.Index(fields=["cart"], name="ix_cartitem_cart"),
            models.Index(fields=["item_set"], name="ix_cartitem_item"),
            models.Index(fields=["cart", "item_set"], name="ix_cartitem_cart_item"),
        ]

    def __str__(self): return f"{self.item_set.set_name} x{self.quantity}"
