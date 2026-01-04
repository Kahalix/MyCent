from __future__ import annotations

from pawns.services import repositories as repo
from identity.models import User


def seller_pawns_qs(user: User, *, with_related: bool = False):
    return repo.seller_pawns_qs(user, with_related=with_related)


def admin_pawns_qs(*, with_related: bool = False):
    return repo.admin_pawns_qs(with_related=with_related)


def user_pawns_qs(user: User, *, with_related: bool = False):
    return repo.user_pawns_qs(user, with_related=with_related)
