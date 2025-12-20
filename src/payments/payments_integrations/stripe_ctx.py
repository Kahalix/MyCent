from django.conf import settings
def stripe_public_key(_):
    return {"STRIPE_PUBLISHABLE_KEY": settings.STRIPE_PUBLISHABLE_KEY}