from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import SellerProfile, SellerMembership

User = get_user_model()

@receiver(post_save, sender=SellerProfile)
def ensure_owner_membership(sender, instance: SellerProfile, created, **kwargs):
    if not instance.owner_id:
        return
    SellerMembership.objects.get_or_create(
        seller_profile=instance,
        user=instance.owner,
        defaults={"role": "OWNER", "is_active": True},
    )

@receiver(post_save, sender=User)
def _grant_defaults_on_signup(sender, instance: User, created: bool, **kwargs):
    """
    Jeśli skonfigurujemy SERVICES_SIGNUP_FREE_PACKAGE_PUBLIC_IDS w settings,
    spróbujemy nadać pakiety startowe.
    """
    if not created:
        return
    try:
        from services.services.commands import grant_signup_freebies
    except Exception:
        return
    try:
        grant_signup_freebies(instance)
    except Exception:
        # nie blokuj rejestracji
        pass
