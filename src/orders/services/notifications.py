from __future__ import annotations
from typing import Iterable

from django.conf import settings
from django.urls import reverse

from identity.services import emails


# ===== helpers: URL =====
def _abs_base() -> str:
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    return base or "https://localhost"

def _abs_url(path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{_abs_base()}{path}"

def _order_url(public_id: str) -> str:
    """
    core: path("orders/<str:order_public_id>", ..., name="buyer_order_detail")
    """
    path = reverse("core:buyer_order_detail", kwargs={"order_public_id": public_id})
    return _abs_url(path)


# ===== notifications =====
def notify_order_confirmed(*, user, orders: Iterable) -> None:
    """
    Jeden mail do kupującego z listą zamówień w ramach transakcji.
    Szablony:
      - templates/email/order_confirmed.html  (extends email/_base.html)
      - templates/email/order_confirmed.txt
    """
    site = getattr(settings, "SITE_NAME", "MyCent")
    subject = f"[{site}] Potwierdzenie zamówienia"

    items = [{"order": o, "order_url": _order_url(o.public_id)} for o in orders]
    ctx = {
        "first_name": (getattr(user, "first_name", "") or user.email),
        "site_name": site,
        "subject": subject,          # <- dla nagłówka w _base.html
        "orders": items,
    }

    emails.send_templated_email(
        to=user.email,
        subject=subject,
        template="email/order_confirmed",
        context=ctx,
    )


def notify_order_shipped(*, user, order) -> None:
    """
    Mail o wysyłce konkretnego zamówienia.
    Szablony:
      - templates/email/order_shipped.html   (extends email/_base.html)
      - templates/email/order_shipped.txt
    """
    site = getattr(settings, "SITE_NAME", "MyCent")
    subject = f"[{site}] Twoje zamówienie zostało wysłane"

    ctx = {
        "first_name": (getattr(user, "first_name", "") or user.email),
        "site_name": site,
        "subject": subject,          # <- dla nagłówka w _base.html
        "order": order,
        "order_url": _order_url(order.public_id),
    }

    emails.send_templated_email(
        to=user.email,
        subject=subject,
        template="email/order_shipped",
        context=ctx,
    )
