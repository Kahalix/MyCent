from __future__ import annotations
from typing import Mapping
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

def send_templated_email(*, to: str, subject: str, template: str, context: Mapping):
    """
    template: ścieżka bazowa bez rozszerzenia, np. 'email/confirm_registration'
    spodziewa się plików: <template>.html i <template>.txt
    """
    html_body = render_to_string(f"{template}.html", context)
    try:
        text_body = render_to_string(f"{template}.txt", context)
    except Exception:
        text_body = strip_tags(html_body)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)
