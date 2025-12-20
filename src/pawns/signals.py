# src/pawns/signals.py
from __future__ import annotations
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from pawns.models import Pawn, PawnLine


def _recalc(pawn_id: int | None) -> None:
    if not pawn_id:
        return
    pawn = Pawn.objects.filter(pk=pawn_id).first()
    if pawn:
        pawn.recalc_appraisal(save=True)


@receiver(post_save, sender=PawnLine)
def recalc_appraisal_on_line_save(sender, instance: PawnLine, **kwargs):
    # liczymy po każdym create/update linii
    _recalc(getattr(instance, "pawn_id", None))


@receiver(post_delete, sender=PawnLine)
def recalc_appraisal_on_line_delete(sender, instance: PawnLine, **kwargs):
    # liczymy po usunięciu linii
    _recalc(getattr(instance, "pawn_id", None))
