from __future__ import annotations
import django_filters
from django.db.models import Q
from chat.models import ChatThread


class ChatThreadFilter(django_filters.FilterSet):
    """
    Filtry do skrzynki czatów (inbox).
    - listing_bucket / thread_kind:
        * my_user       - rozmowy do moich ogłoszeń USER (added_by=USER & owner_user==me)
        * users_other   - rozmowy do ogłoszeń innych użytkowników (added_by=USER & owner!=me)
        * users         - wszystkie rozmowy do ogłoszeń USER (niezależnie czy moje)
        * sellers       - rozmowy do ogłoszeń sprzedawców (added_by=STAFF)
        * all_listings  - wszystkie rozmowy powiązane z ogłoszeniem (USER+STAFF)
        * dm            - rozmowy bez ogłoszenia (DM)
    - q: pełnotekstowe (preview, tytuł ogłoszenia, dane uczestników)
    - unread_only: tylko wątki z nieprzeczytanymi
    - item_public_id: ograniczenie do konkretnego ogłoszenia
    - ordering: przez django_filters.OrderingFilter ("last_message_at" | "updated_at", z minusami)
    """
    item_public_id = django_filters.CharFilter(field_name="item_set__public_id", lookup_expr="exact")
    q = django_filters.CharFilter(method="filter_q")
    unread_only = django_filters.BooleanFilter(method="filter_unread_only")

    # kubełki
    listing_bucket = django_filters.CharFilter(method="filter_listing_bucket")
    # alias  żeby można było wołać ?thread_kind=...
    thread_kind = django_filters.CharFilter(method="filter_listing_bucket")

    ordering = django_filters.OrderingFilter(
        fields=(
            ("last_message_at", "last_message_at"),
            ("updated_at", "updated_at"),
        ),
        field_labels={
            "last_message_at": "Ostatnia wiadomość",
            "updated_at": "Aktualizacja",
        },
        label="Sortuj",
    )

    class Meta:
        model = ChatThread
        fields = ["item_public_id", "unread_only", "listing_bucket", "thread_kind"]

    # --- helpers ---

    def _authed_user(self):
        u = getattr(self.request, "user", None)
        return u if (u and u.is_authenticated) else None

    # --- implementacje ---

    def filter_q(self, qs, name, value):
        v = (value or "").strip()
        if not v:
            return qs
        return qs.filter(
            Q(last_message_preview__icontains=v)
            | Q(item_set__set_name__icontains=v)
            | Q(participants__user__first_name__icontains=v)
            | Q(participants__user__last_name__icontains=v)
            | Q(participants__user__email__icontains=v)
        ).distinct()

    def filter_unread_only(self, qs, name, value):
        if not value:
            return qs
        user = self._authed_user()
        if not user:
            return qs.none()
        return qs.filter(
            participants__user=user,
            participants__is_deleted=False,
            participants__unread_count__gt=0,
        )

    def filter_listing_bucket(self, qs, name, value):
        v = (value or "").strip().lower()
        if not v:
            return qs

        user = self._authed_user()

        if v in ("my_user", "mine", "my"):
            if not user:
                return qs.none()
            return qs.filter(
                item_set__isnull=False,
                item_set__added_by="USER",
                item_set__owner_user=user,
            )

        if v in ("users_other", "users-not-mine", "users_except_mine"):
            base = qs.filter(item_set__isnull=False, item_set__added_by="USER")
            return base.exclude(item_set__owner_user=user) if user else base

        if v in ("users", "user", "user_listings"):
            return qs.filter(item_set__isnull=False, item_set__added_by="USER")

        if v in ("sellers", "seller", "staff"):
            return qs.filter(item_set__isnull=False, item_set__added_by="STAFF")

        if v in ("all_listings", "listings", "items"):
            return qs.filter(item_set__isnull=False)

        if v in ("dm", "direct", "noitem", "none"):
            return qs.filter(item_set__isnull=True)

        # nieznany kubełek -> brak dodatkowego filtra
        return qs
