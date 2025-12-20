from __future__ import annotations
from pawns.services import repositories as repo
from identity.models import User

def seller_pawns_qs(user: User):
    return repo.seller_pawns_qs(user)

def admin_pawns_qs():
    return repo.admin_pawns_qs()

def user_pawns_qs(user: User):
    return repo.user_pawns_qs(user)
