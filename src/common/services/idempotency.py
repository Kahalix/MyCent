from __future__ import annotations
from typing import Optional, Sequence
from django.db import transaction
from django.contrib.auth import get_user_model
from common.models import IdempotencyKey

User = get_user_model()

def _scope(scope: str, fingerprint: str) -> str:
    return f"{scope}:{fingerprint}"

@transaction.atomic
def get_existing(*, user: User, scope: str, fingerprint: str, key: str) -> Optional[IdempotencyKey]:
    return IdempotencyKey.objects.filter(user=user, scope=_scope(scope, fingerprint), key=key).first()

@transaction.atomic
def save_result(*, user: User, scope: str, fingerprint: str, key: str,
                target_type: str, target_ids: Sequence[str]) -> IdempotencyKey:
    rec, _ = IdempotencyKey.objects.get_or_create(
        user=user, scope=_scope(scope, fingerprint), key=key,
        defaults={"target_type": target_type, "target_ids": list(target_ids)}
    )
    return rec
