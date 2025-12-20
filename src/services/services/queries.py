from __future__ import annotations
from django.contrib.auth import get_user_model

from catalog.models import ItemType
from . import repositories as repo

User = get_user_model()

def get_slot_summary(user: User):
    from .commands import slot_summary_for_user
    return slot_summary_for_user(user)

def get_available_packages_for_type(item_type: ItemType):
    from services.models import ListingPackage
    return ListingPackage.objects.filter(item_type=item_type).order_by("price", "points")
