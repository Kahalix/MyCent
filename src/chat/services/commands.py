from __future__ import annotations
from django.db import transaction as dbtx
from identity.models import User
from listings.models import ItemSet
from chat.models import ChatThread
from chat.services import repositories as repo
from chat.services.exceptions import DomainError, Forbidden


def _default_counterpart_for_item(item: ItemSet) -> User | None:
    # STAFF: właściciel profilu sklepu
    if item.added_by == "STAFF" and item.seller_profile and item.seller_profile.owner:
        return item.seller_profile.owner
    # USER: właściciel ogłoszenia
    if item.added_by == "USER" and item.owner_user:
        return item.owner_user
    return None


@dbtx.atomic
def start_dm(*, initiator: User, other_user: User | None, item: ItemSet | None = None) -> ChatThread:
    if item:
        if other_user is None:
            other_user = _default_counterpart_for_item(item)
            if other_user is None:
                raise DomainError("Nie można wyznaczyć drugiej strony rozmowy dla ogłoszenia. Podaj other_user.")
        if initiator.id == other_user.id:
            raise DomainError("Nie możesz rozpocząć rozmowy z samym sobą.")
        return repo.get_or_create_dm_thread(initiator, other_user, item=item)

    if other_user is None:
        raise DomainError("Dla rozmowy ogólnej musisz wskazać other_user.")
    if initiator.id == other_user.id:
        raise DomainError("Nie możesz rozpocząć rozmowy z samym sobą.")
    return repo.get_or_create_dm_thread(initiator, other_user, item=None)


@dbtx.atomic
def send_message(*, thread: ChatThread, sender: User, content: str):
    if not content or not content.strip():
        raise DomainError("Wiadomość nie może być pusta.")
    if not repo.user_has_access_to_thread(sender, thread):
        raise Forbidden("Brak dostępu do tego wątku.")
    repo.ensure_participant(thread, sender)
    return repo.create_message(thread=thread, sender=sender, content=content)


@dbtx.atomic
def mark_read(*, thread: ChatThread, user: User):
    if not repo.user_has_access_to_thread(user, thread):
        raise Forbidden("Brak dostępu do wątku.")
    repo.ensure_participant(thread, user)
    return repo.mark_read_up_to_now(thread=thread, user=user)
