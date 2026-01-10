from __future__ import annotations
from django.contrib.auth import authenticate, get_user_model

User = get_user_model()

def authenticate_user(email: str, password: str):
    """
    Używa domyślnego ModelBackend.
    """
    return authenticate(email=email, password=password)
