from __future__ import annotations

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import PermissionDenied
from django.utils.html import format_html

from .models import User, SellerProfile, SellerBankAccount, UserToken, SellerMembership

# ========= helpers / stałe =========

STATUS_THAT_DISABLE_LOGIN = {"SUSPENDED", "DELETED"}
SPECIAL_PERM = "identity.can_set_user_status"  # niestandardowe uprawnienie „zmiana statusu”

ALLOWED_ROLES_FOR_NON_SUPERUSER_EDIT = {"CLIENT", "EMPLOYEE"}
ROLES_EDIT_DELETE_OWNER_ONLY = {"MANAGER", "MODERATOR"}  # tylko OWNER (lub superuser) może ich ruszać

def _safe_file_url(field) -> str:
    """
    Zwraca URL pliku jeśli istnieje, w przeciwnym razie pusty string.
    Unika ValueError: The 'X' attribute has no file associated with it.
    """
    try:
        if not field or not getattr(field, "name", None):
            return ""
        return field.url
    except Exception:
        return ""


def _is_protected_target(target: User, acting_user: User) -> bool:
    """
    Czy konto jest „chronione” przed edycją/usunięciem przez działającego użytkownika?
    - superuser: może wszystko
    - staff / superuser / OWNER – zawsze chronione dla nie-superusera
    - MANAGER/MODERATOR – chronione, chyba że acting_user ma globalną rolę OWNER
    - własne konto – chronione
    """
    if not target:
        return False
    if acting_user.is_superuser:
        return False  # superuser może wszystko

    if target.is_superuser or target.is_staff or getattr(target, "role", None) == "OWNER":
        return True

    if target.role in ROLES_EDIT_DELETE_OWNER_ONLY and getattr(acting_user, "role", None) != "OWNER":
        return True

    if target.pk == acting_user.pk:
        return True

    return False


# ========= UserAdmin =========

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    model = User

    list_display = (
        "avatar_thumb",
        "email", "first_name", "last_name",
        "role", "user_status", "is_active", "is_staff",
    )
    list_display_links = ("email",)
    # domyślnie pozwalamy na edycję inline; ukryjemy dla osób bez SPECIAL_PERM
    list_editable = ("user_status", "is_active")
    list_filter = ("role", "user_status", "is_active", "is_staff")
    ordering = ("email",)
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("image_preview",)

    actions = ("mark_active", "mark_suspended", "mark_deleted")

    # Formularz dodawania: celowo BEZ pól uprawnień i roli
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "first_name", "last_name"),
        }),
    )

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {
            "fields": (
                "first_name", "last_name", "phone_number", "points",
                "image_preview", "user_image",
            )
        }),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Status/Role", {"fields": ("role", "user_status")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    # --- ograniczenie wyboru ról w UI dla nie-superusera ---
    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "role" and not request.user.is_superuser:
            full = dict(User._meta.get_field("role").choices)
            kwargs["choices"] = [(k, full[k]) for k in ALLOWED_ROLES_FOR_NON_SUPERUSER_EDIT]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    # ---------- wejście w edycję ----------
    def has_change_permission(self, request, obj=None):
        base = super().has_change_permission(request, obj)
        if request.user.is_superuser:
            return True if obj is None else base
        if obj is not None and _is_protected_target(obj, request.user):
            return False
        # osoby z samym SPECIAL_PERM mogą wejść (status-only) – resztę zablokujemy polami read-only
        if request.user.has_perm(SPECIAL_PERM):
            return True
        return base

    # ---------- usuwanie ----------
    def has_delete_permission(self, request, obj=None):
        base = super().has_delete_permission(request, obj)
        if request.user.is_superuser:
            return base
        if obj is not None and _is_protected_target(obj, request.user):
            return False
        return base

    def delete_model(self, request, obj):
        if not request.user.is_superuser and _is_protected_target(obj, request.user):
            raise PermissionDenied("Nie możesz usuwać tego konta.")
        return super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        if request.user.is_superuser:
            return super().delete_queryset(request, queryset)
        qs = (
            queryset
            .exclude(is_superuser=True)
            .exclude(is_staff=True)
            .exclude(role="OWNER")
            .exclude(pk=request.user.pk)
        )
        # MANAGER/MODERATOR tylko dla OWNERa
        if getattr(request.user, "role", None) != "OWNER":
            qs = qs.exclude(role__in=list(ROLES_EDIT_DELETE_OWNER_ONLY))
        skipped = queryset.count() - qs.count()
        super().delete_queryset(request, qs)
        if skipped:
            self.message_user(
                request,
                "Pominięto usuwanie kont chronionych (OWNER/staff/superuser oraz MANAGER/MODERATOR) lub własnego.",
                level=messages.WARNING,
            )

    # ---------- widok listy ----------
    def changelist_view(self, request, extra_context=None):
        # schowaj inline-edycję statusu/aktywności jeśli brak SPECIAL_PERM
        if not (request.user.is_superuser or request.user.has_perm(SPECIAL_PERM)):
            original = self.list_editable
            self.list_editable = ()
            try:
                return super().changelist_view(request, extra_context)
            finally:
                self.list_editable = original
        return super().changelist_view(request, extra_context)

    def get_actions(self, request):
        actions = super().get_actions(request)
        # usuń delete_selected dla nie-superuserów
        if not request.user.is_superuser:
            actions.pop("delete_selected", None)
        # usuń akcje statusowe, jeśli brak SPECIAL_PERM
        if not (request.user.is_superuser or request.user.has_perm(SPECIAL_PERM)):
            for k in ("mark_active", "mark_suspended", "mark_deleted"):
                actions.pop(k, None)
        return actions

    # ---------- pola read-only dynamicznie ----------
    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))

        # Zawsze zablokowane dla nie-superusera
        ALWAYS_RO = {"is_staff", "is_superuser", "groups", "user_permissions"}

        if not request.user.is_superuser:
            ro = sorted(set(ro) | ALWAYS_RO)

            if obj is not None:
                # Chronione cele: całkowicie blokujemy (również user_status/is_active)
                if _is_protected_target(obj, request.user):
                    ro = sorted(set(ro) | {"role", "user_status", "is_active"})
                else:
                    # Osoba z samym SPECIAL_PERM (bez standardowego change) – pozwól tylko na status/aktywność
                    has_std_change = super().has_change_permission(request, obj)
                    has_special = request.user.has_perm(SPECIAL_PERM)
                    if has_special and not has_std_change:
                        editable = {"user_status", "is_active"}
                        all_fields = set()
                        for _title, fs in self.fieldsets:
                            f = fs.get("fields", ())
                            if isinstance(f, (list, tuple)):
                                all_fields.update(f)
                            elif isinstance(f, str):
                                all_fields.add(f)
                        ro = sorted((all_fields - editable) | set(ro))

        return ro

    # ---------- helpery ----------
    def _revoke_tokens(self, user: User):
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
        from .services.repositories import delete_all_refreshes
        delete_all_refreshes(user)
        for t in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=t)

    # ---------- zapis z egzekwowaniem zasad ----------
    def save_model(self, request, obj, form, change):
        # twarda blokada edycji kont chronionych dla nie-superusera
        if not request.user.is_superuser and obj and _is_protected_target(obj, request.user):
            raise PermissionDenied("Nie możesz modyfikować tego konta.")

        # nie-superuser nie dotyka pól uprawnień
        perm_fields = {"is_staff", "is_superuser", "groups", "user_permissions"}
        if not request.user.is_superuser and (set(form.changed_data) & perm_fields):
            raise PermissionDenied("Brak uprawnień do zmiany uprawnień użytkownika.")

        # ograniczenie zmiany roli dla nie-superusera -> dozwolone tylko CLIENT/EMPLOYEE
        if not request.user.is_superuser and "role" in form.changed_data:
            new_role = form.cleaned_data.get("role")
            if new_role not in ALLOWED_ROLES_FOR_NON_SUPERUSER_EDIT:
                raise PermissionDenied("Nie możesz ustawiać tej roli (dozwolone: CLIENT lub EMPLOYEE).")

        # zmiana statusu/aktywności wymaga SPECIAL_PERM (dla nie-superuserów)
        changed_status_fields = any(f in form.changed_data for f in ("user_status", "is_active"))
        if changed_status_fields and not request.user.is_superuser and not request.user.has_perm(SPECIAL_PERM):
            raise PermissionDenied("Brak uprawnienia do zmiany statusu użytkownika.")

        creating = not change
        super().save_model(request, obj, form, change)  # zapisz, żeby istniał PK

        if not request.user.is_superuser:
            if creating:
                # podczas tworzenia wymuś bezpieczne wartości
                must_update = False
                if obj.role not in ALLOWED_ROLES_FOR_NON_SUPERUSER_EDIT:
                    obj.role = "CLIENT"; must_update = True
                if obj.is_staff or obj.is_superuser:
                    obj.is_staff = False; obj.is_superuser = False; must_update = True
                if must_update:
                    obj.save(update_fields=["role", "is_staff", "is_superuser"])

            # wyloguj, jeśli status blokuje logowanie
            if changed_status_fields and (obj.user_status in STATUS_THAT_DISABLE_LOGIN or obj.is_active is False):
                self._revoke_tokens(obj)

    # nie pozwól nadawać grup/perms przy save_related (osoby nie-superuser)
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if not request.user.is_superuser:
            obj.groups.clear()
            obj.user_permissions.clear()
            # przy tworzeniu – dopnij jeszcze raz bezpieczeństwo roli
            if not change and obj.role not in ALLOWED_ROLES_FOR_NON_SUPERUSER_EDIT:
                obj.role = "CLIENT"
                obj.save(update_fields=["role"])

    # ---------- akcje masowe (status) ----------
    def _bulk_set(self, request, queryset, status_value: str, is_active: bool):
        if not (request.user.is_superuser or request.user.has_perm(SPECIAL_PERM)):
            raise PermissionDenied("Brak uprawnień.")
        updated, skipped = 0, 0
        for u in queryset:
            if _is_protected_target(u, request.user):
                skipped += 1
                continue
            u.user_status = status_value
            u.is_active = is_active
            u.save(update_fields=["user_status", "is_active"])
            if (status_value in STATUS_THAT_DISABLE_LOGIN) or (is_active is False):
                self._revoke_tokens(u)
            updated += 1

        if updated:
            self.message_user(request, f"Zmieniono status {updated} użytkownikom.", level=messages.SUCCESS)
        if skipped:
            self.message_user(
                request,
                "Pominięto konta chronione (OWNER/staff/superuser oraz MANAGER/MODERATOR) lub własne.",
                level=messages.WARNING,
            )

    @admin.action(description="Ustaw status: ACTIVE")
    def mark_active(self, request, queryset):
        self._bulk_set(request, queryset, "ACTIVE", True)

    @admin.action(description="Ustaw status: SUSPENDED (wyloguj)")
    def mark_suspended(self, request, queryset):
        self._bulk_set(request, queryset, "SUSPENDED", False)

    @admin.action(description="Ustaw status: DELETED (wyloguj)")
    def mark_deleted(self, request, queryset):
        self._bulk_set(request, queryset, "DELETED", False)

    # ---------- UI: miniatury ----------
    @admin.display(description="", ordering=None)
    def avatar_thumb(self, obj):
        url = _safe_file_url(getattr(obj, "user_image", None))
        if not url:
            return format_html(
                '<span style="display:inline-block;width:32px;height:32px;'
                'border-radius:50%;background:#eee;border:1px solid #ddd;"></span>'
            )
        return format_html(
            '<img src="{}" style="width:32px;height:32px;object-fit:cover;'
            'border-radius:50%;border:1px solid #ddd;" />',
            url,
        )

    def image_preview(self, obj):
        url = _safe_file_url(getattr(obj, "user_image", None))
        if not url:
            return "— brak —"
        return format_html(
            '<a href="{0}" target="_blank">'
            '<img src="{0}" style="max-width:240px;max-height:240px;'
            'border:1px solid #ddd;border-radius:4px;padding:2px;" /></a>',
            url
        )
    image_preview.short_description = "Podgląd avatara"


# ========= SellerProfileAdmin =========

@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = ("logo_thumb", "company_name", "slug", "owner", "followers_count", "rating", "rating_count")
    list_display_links = ("company_name",)
    search_fields = ("company_name", "slug", "owner__email")
    autocomplete_fields = ("owner",)
    list_select_related = ("owner",)
    show_full_result_count = False

    readonly_fields = ("logo_preview", "banner_preview")

    fieldsets = (
        (None, {"fields": ("owner", "company_name", "legal_name", "slug", "description")}),
        ("Kontakt", {"fields": ("contact_email", "contact_phone", "website_url")}),
        ("Grafika", {"fields": ("logo_preview", "logo_image", "banner_preview", "banner_image")}),
        ("Statystyki", {"fields": ("followers_count", "rating", "rating_count")}),
    )

    def _img_field(self, field, max_w, max_h):
        url = _safe_file_url(field)
        if not url:
            return "— brak —"
        return format_html(
            '<a href="{0}" target="_blank">'
            '<img src="{0}" style="max-width:{}px;max-height:{}px;'
            'border:1px solid #ddd;border-radius:4px;padding:2px;" /></a>',
            url, max_w, max_h
        )

    def logo_preview(self, obj):
        return self._img_field(getattr(obj, "logo_image", None), 240, 160)
    logo_preview.short_description = "Logo – podgląd"

    def banner_preview(self, obj):
        return self._img_field(getattr(obj, "banner_image", None), 480, 180)
    banner_preview.short_description = "Banner – podgląd"

    @admin.display(description="Logo")
    def logo_thumb(self, obj):
        url = _safe_file_url(getattr(obj, "logo_image", None))
        if not url:
            return format_html(
                '<span style="display:inline-block;width:48px;height:32px;'
                'background:#f5f5f5;border:1px solid #ddd;border-radius:3px;"></span>'
            )
        return format_html(
            '<img src="{}" style="height:32px;max-width:64px;object-fit:contain;'
            'background:#fff;border:1px solid #ddd;border-radius:3px;padding:1px;" />',
            url,
        )


# ========= SellerBankAccountAdmin =========

@admin.register(SellerBankAccount)
class SellerBankAccountAdmin(admin.ModelAdmin):
    list_display = ("seller_profile", "iban", "is_active", "is_default")
    search_fields = ("iban", "seller_profile__company_name")
    list_filter = ("is_active", "is_default")
    autocomplete_fields = ("seller_profile",)


# ========= UserTokenAdmin =========

@admin.register(UserToken)
class UserTokenAdmin(admin.ModelAdmin):
    list_display = ("public_id", "user", "type", "expiry", "created_at")
    list_filter = ("type",)
    search_fields = ("public_id", "user__email")


# ========= SellerMembershipAdmin (sklep – członkowie) =========
# Ograniczenia:
# - Nikt poza superuserem nie może edytować/usuwać członkostwa OWNERA.
# - Nie można dodać/ustawić roli OWNER (z wyjątkiem superusera – ale i tak zwykle nie robimy tego w adminie).
# - (Pozostałe reguły biznesowe wymuszasz też w API, tutaj to twarde zabezpieczenie na panelu)

@admin.register(SellerMembership)
class SellerMembershipAdmin(admin.ModelAdmin):
    list_display = ("seller_profile", "user", "role", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("seller_profile__slug", "user__email")
    autocomplete_fields = ("seller_profile", "user")

    # wytnij OWNER z wyboru ról dla nie-superuserów
    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "role" and not request.user.is_superuser:
            full = dict(SellerMembership.ROLE_CHOICES)
            choices = [(k, full[k]) for k in full.keys() if k != "OWNER"]
            kwargs["choices"] = choices
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def _is_owner_membership(self, obj: SellerMembership | None) -> bool:
        if not obj:
            return False
        try:
            return obj.user_id == obj.seller_profile.owner_id
        except Exception:
            return False

    # blokuj edycję członkostwa OWNERA
    def has_change_permission(self, request, obj=None):
        base = super().has_change_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return base
        if self._is_owner_membership(obj):
            return False
        return base

    # blokuj usuwanie członkostwa OWNERA
    def has_delete_permission(self, request, obj=None):
        base = super().has_delete_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return base
        if self._is_owner_membership(obj):
            return False
        return base

    def delete_model(self, request, obj):
        if not request.user.is_superuser and self._is_owner_membership(obj):
            raise PermissionDenied("Nie możesz usuwać członkostwa właściciela.")
        return super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        if request.user.is_superuser:
            return super().delete_queryset(request, queryset)
        qs = queryset.exclude(user_id=models.F("seller_profile__owner_id"))
        skipped = queryset.count() - qs.count()
        super().delete_queryset(request, qs)
        if skipped:
            self.message_user(request, "Pominięto członkostwo OWNERA.", level=messages.WARNING)

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser and obj is not None and self._is_owner_membership(obj):
            # zablokuj wszystko sensowne
            ro = sorted(set(ro) | {"seller_profile", "user", "role", "is_active"})
        return ro

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            # twardy zakaz ustawienia OWNER
            new_role = form.cleaned_data.get("role", obj.role)
            if new_role == "OWNER" or obj.role == "OWNER":
                raise PermissionDenied("Nie możesz ustawić lub modyfikować członkostwa OWNERA.")
        super().save_model(request, obj, form, change)
