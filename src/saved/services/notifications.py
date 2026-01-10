from __future__ import annotations
from decimal import Decimal

from django.conf import settings
from django.urls import reverse

from identity.services import emails


def _abs_base() -> str:
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    return base or "http://localhost:8000"


def _abs_url(path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{_abs_base()}{path}"


def _listing_url(item_set) -> str:
    """
    Link do szczegółu oferty:
      path("i/<slug:slug>", views.item_detail, name="item_detail")
    """
    slug = getattr(item_set, "slug", None)
    if slug:
        path = reverse("core:item_detail", kwargs={"slug": slug})
        return _abs_url(path)
    # fallback
    path = reverse("core:offers_public")
    return _abs_url(f"{path}?item={item_set.public_id}")


def _fmt_money(amount: Decimal, currency: str) -> str:
    q = Decimal("0.01")
    return f"{Decimal(str(amount)).quantize(q)} {currency}"


def notify_price_drop(*, user, item_set, old_amount, new_amount, currency: str) -> None:
    """
    Wysyła mail o spadku ceny w stylu maili z identity.
    Używa szablonów: templates/email/saved_price_drop.(html|txt)
    """
    action_url = _listing_url(item_set)
    subject = f"Spadek ceny: {getattr(item_set, 'set_name', 'oferta')}"

    ctx = {
        # nagłówek itp.
        "first_name": (getattr(user, "first_name", "") or user.email),
        "site_name": getattr(settings, "SITE_NAME", "MyCent"),
        "action_url": action_url,

        # dane specyficzne do treści
        "item_name": getattr(item_set, "set_name", ""),
        "item_url": action_url,
        "old_price": _fmt_money(old_amount, currency),
        "new_price": _fmt_money(new_amount, currency),

        "user": user,
        "item": item_set,
    }

    emails.send_templated_email(
        to=user.email,
        subject=subject,
        template="email/saved_price_drop",
        context=ctx,
    )
