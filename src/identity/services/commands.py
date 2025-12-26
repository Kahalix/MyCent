from __future__ import annotations
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import password_validation
from django.core.files.storage import default_storage

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from . import queries, emails
from .exceptions import (
    EmailAlreadyUsed, InvalidCredentials, AccountNotActive,
    TokenInvalid, RefreshMissing, RefreshInvalid, RefreshNotRecognized
)

# Kto ma pełne prawa do kont bankowych – tylko właściciel sklepu
BANK_ADMIN_ROLES = {"OWNER"}
# Kto ma prawo do sekcji „Członkowie”: OWNER i MANAGER
MEMBER_ADMIN_ROLES = {"OWNER", "MANAGER"}

from .repositories import (
    create_user, find_user_by_email_ci, is_email_taken_ci,
    issue_ephemeral, consume_ephemeral,
    save_refresh, exists_refresh, delete_refresh, delete_all_refreshes,
    get_user_by_id, get_user_by_public_id,
    get_seller_by_public_id, get_seller_by_slug,
    get_seller_for_owner, get_bank_account_by_public_id, set_default_for_seller, is_member
)
from ..serializers import PublicUserResponse
from ..models import SellerProfile, SellerBankAccount, SellerMembership, User


# ---------- AUTH ----------

def _auth_payload(user, refresh: RefreshToken | None = None) -> dict:
    if refresh is None:
        refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    return {"access": str(access), "refresh": str(refresh), "user": PublicUserResponse(user).data}

def register_user(request, *, email: str, password: str, first_name: str, last_name: str) -> dict:
    email = email.lower()
    if is_email_taken_ci(email):
        raise EmailAlreadyUsed("Konto o podanym adresie e-mail już istnieje")
    user = create_user(email, password, first_name, last_name, active=False)
    _send_registration_confirmation_email(request, user=user, hours_valid=24)
    return {"message": "Sprawdź e-mail w celu aktywacji."}

def _send_registration_confirmation_email(request, *, user, hours_valid: int = 24) -> None:
    token = issue_ephemeral(user, "EMAIL_CONFIRMATION", minutes=60 * hours_valid)
    url = request.build_absolute_uri(reverse("core:login")) + f"?confirm={token}"
    emails.send_templated_email(
        to=user.email,
        subject="Potwierdź rejestrację",
        template="email/confirm_registration",
        context={
            "first_name": user.first_name or user.email,
            "action_url": url,
            "valid_for_hours": hours_valid,
            "site_name": "MyCent",
        },
    )

def confirm_registration(*, token: str) -> dict:
    tok = consume_ephemeral(token, "EMAIL_CONFIRMATION")
    if not tok:
        raise TokenInvalid("Token invalid/expired")
    user = tok.user
    user.is_active = True
    user.save(update_fields=["is_active"])
    return {"message": "Konto aktywowane."}

# def login_user(request, *, email: str, password: str) -> dict:
#     from .crud import authenticate_user
#     user = authenticate_user(email=email.lower(), password=password)
#     if not user:
#         raise InvalidCredentials("Invalid credentials")
#     if not user.is_active:
#         raise AccountNotActive("Account not active")
#
#     refresh = RefreshToken.for_user(user)
#     payload = _auth_payload(user, refresh)
#     save_refresh(
#         user, payload["refresh"],
#         data={"ua": request.META.get("HTTP_USER_AGENT", ""), "ip": request.META.get("REMOTE_ADDR", ""),
#               "rotated_at": timezone.now().isoformat()}
#     )
#     return payload

def login_user(request, *, email: str, password: str) -> dict:
    from .repositories import find_user_by_email_ci

    email = email.lower()
    user = find_user_by_email_ci(email)

    if not user or not user.check_password(password):
        raise InvalidCredentials("Invalid credentials")

    if not user.is_active:
        status = getattr(user, "user_status", "")
        if status == "ACTIVE":
            _send_registration_confirmation_email(request, user=user, hours_valid=24)
            raise AccountNotActive("Konto nie zostało jeszcze aktywowane. Wysłaliśmy ponownie link aktywacyjny na e-mail.")
        raise AccountNotActive("Konto jest nieaktywne lub zablokowane. Skontaktuj się z administratorem.")

    refresh = RefreshToken.for_user(user)
    payload = _auth_payload(user, refresh)
    save_refresh(
        user, payload["refresh"],
        data={
            "ua": request.META.get("HTTP_USER_AGENT", ""),
            "ip": request.META.get("REMOTE_ADDR", ""),
            "rotated_at": timezone.now().isoformat(),
        },
    )
    return payload


def refresh_tokens(request, *, refresh_jwt: str | None) -> dict:
    if not refresh_jwt and settings.JWT_REFRESH_IN_COOKIE:
        refresh_jwt = request.COOKIES.get(settings.AUTH_COOKIE_NAME)
    if not refresh_jwt:
        raise RefreshMissing("Missing refresh token")

    try:
        old = RefreshToken(refresh_jwt)
        user_id = old["user_id"]
    except Exception:
        raise RefreshInvalid("Invalid refresh token")

    user = get_user_by_id(user_id)
    if not user or not user.is_active:
        raise RefreshInvalid("User not found/inactive")

    if not exists_refresh(user, refresh_jwt):
        raise RefreshNotRecognized("Refresh not recognized (revoked/rotated)")

    new_refresh = RefreshToken.for_user(user)
    delete_refresh(user, refresh_jwt)
    save_refresh(
        user, str(new_refresh),
        data={"ua": request.META.get("HTTP_USER_AGENT",""), "ip": request.META.get("REMOTE_ADDR",""),
              "rotated_at": timezone.now().isoformat()}
    )
    return _auth_payload(user, new_refresh)

def logout_user(request, *, user) -> None:
    delete_all_refreshes(user)
    for t in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=t)

def forgot_password(request, *, email: str) -> dict:
    user = find_user_by_email_ci(email.lower())
    if user and user.is_active:
        token = issue_ephemeral(user, "PASSWORD_RESET", minutes=30)
        url = request.build_absolute_uri(reverse("core:reset")) + f"?token={token}"
        emails.send_templated_email(
            to=user.email,
            subject="Reset hasła",
            template="email/password_reset",
            context={
                "first_name": user.first_name or user.email,
                "action_url": url,
                "valid_for_minutes": 30,
                "site_name": "MyCent",
            },
        )
    return {"message": "Jeśli konto istnieje, wysłaliśmy instrukcje."}

def reset_password(*, token: str, new_password: str) -> dict:
    tok = consume_ephemeral(token, "PASSWORD_RESET")
    if not tok:
        raise TokenInvalid("Token invalid/expired")
    user = tok.user
    user.set_password(new_password)
    user.save(update_fields=["password"])
    return {"message": "Hasło ustawione."}

def request_email_change(request, *, user, new_email: str) -> dict:
    new_email = new_email.lower()
    if is_email_taken_ci(new_email, exclude_user_id=user.id):
        raise EmailAlreadyUsed("Email already in use")
    token = issue_ephemeral(user, "EMAIL_CHANGE", minutes=60, data={"new_email": new_email})
    url = request.build_absolute_uri(reverse("core:confirm_email")) + f"?token={token}"
    emails.send_templated_email(
        to=new_email,
        subject="Potwierdź zmianę e-maila",
        template="email/change_email",
        context={
            "first_name": user.first_name or user.email,
            "action_url": url,
            "valid_for_minutes": 60,
            "site_name": "MyCent",
            "new_email": new_email,
        },
    )
    return {"message": "Wysłano link potwierdzający na nowy e-mail."}

def confirm_email_change(*, token: str) -> dict:
    tok = consume_ephemeral(token, "EMAIL_CHANGE")
    if not tok:
        raise TokenInvalid("Token invalid/expired")
    user = tok.user
    new_email = tok.data.get("new_email")
    if not new_email:
        raise TokenInvalid("Token payload invalid")
    if is_email_taken_ci(new_email, exclude_user_id=user.id):
        raise EmailAlreadyUsed("New email invalid/taken")
    user.email = new_email
    user.save(update_fields=["email"])
    return {"message": "Email zmieniony."}

# ---------- USER COMMANDS (self/admin) ----------

def update_user_self(*, user, first_name: str|None=None, last_name: str|None=None, phone_number: str|None=None) -> dict:
    changed = []
    if first_name is not None: user.first_name = first_name; changed.append("first_name")
    if last_name is not None:  user.last_name  = last_name;  changed.append("last_name")
    if phone_number is not None: user.phone_number = phone_number; changed.append("phone_number")
    if changed:
        user.save(update_fields=changed)
    return {"message": "Zaktualizowano profil."}

def change_password(*, user, old_password: str, new_password: str) -> dict:
    if not user.check_password(old_password):
        raise InvalidCredentials("Nieprawidłowe obecne hasło")
    password_validation.validate_password(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    delete_all_refreshes(user)
    return {"message": "Hasło zmienione. Zaloguj się ponownie."}

def admin_create_user(*, email: str, password: str, first_name: str, last_name: str,
                      role: str|None=None, user_status: str|None=None, is_staff: bool=False, is_active: bool=True):
    email = email.lower()
    if is_email_taken_ci(email):
        raise EmailAlreadyUsed("Konto o podanym adresie e-mail już istnieje")
    u = create_user(email, password, first_name, last_name, active=is_active)
    if role: u.role = role
    if user_status: u.user_status = user_status
    u.is_staff = is_staff
    u.save()
    return u

def admin_update_user(*, public_id: str, **changes):
    u = get_user_by_public_id(public_id)
    if not u:
        raise TokenInvalid("User not found")
    allowed = {"first_name","last_name","phone_number","role","user_status","is_staff","is_active"}
    updated = {}
    for k,v in changes.items():
        if k in allowed and v is not None:
            setattr(u, k, v); updated[k]=v
    if updated:
        u.save()
    return u

def admin_delete_user(*, public_id: str) -> None:
    u = get_user_by_public_id(public_id)
    if u:
        u.delete()


def _map_is_active_for_status(user_status: str) -> bool:
    # domyślna polityka:
    # ACTIVE -> True, INACTIVE/SUSPENDED/DELETED -> False
    return user_status == "ACTIVE"

def _revoke_all_tokens(user):
    # kasujemy refreshy w DB + blacklistujemy accessy
    delete_all_refreshes(user)
    for t in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=t)

def admin_set_user_status(*, public_id: str, user_status: str, is_active: bool | None = None):
    u = get_user_by_public_id(public_id)
    if not u:
        raise TokenInvalid("User not found")

    # ustaw pola
    u.user_status = user_status
    u.is_active = _map_is_active_for_status(user_status) if is_active is None else bool(is_active)
    u.save(update_fields=["user_status", "is_active"])

    # jeśli konto zostało zdezaktywowane lub zawieszone – wyloguj wszędzie
    if not u.is_active or user_status in ("SUSPENDED", "DELETED"):
        _revoke_all_tokens(u)

    return u

# ---------- IMAGE HELPERS ----------

def _replace_file_and_set(model_instance, field_name: str, file) -> str:
    """
    Nadpisuje poprzedni plik (usuwa z storage), ustawia nowy, zwraca URL.
    """
    field = getattr(model_instance, field_name, None)
    # usuń stary
    if field and getattr(field, "name", None):
        try:
            default_storage.delete(field.name)
        except Exception:
            pass
    setattr(model_instance, field_name, file)
    model_instance.save(update_fields=[field_name])
    # zwróć pełny URL
    try:
        return model_instance.__class__.objects.get(pk=model_instance.pk).__getattribute__(field_name).url
    except Exception:
        return ""

def upload_user_avatar(*, user, image) -> str:
    return _replace_file_and_set(user, "user_image", image)

def delete_user_avatar(*, user) -> None:
    if user.user_image and user.user_image.name:
        try:
            default_storage.delete(user.user_image.name)
        except Exception:
            pass
    user.user_image = None
    user.save(update_fields=["user_image"])

def upload_seller_logo(*, seller: SellerProfile, logo) -> str:
    return _replace_file_and_set(seller, "logo_image", logo)

def delete_seller_logo(*, seller: SellerProfile) -> None:
    if seller.logo_image and seller.logo_image.name:
        try: default_storage.delete(seller.logo_image.name)
        except Exception: pass
    seller.logo_image = None
    seller.save(update_fields=["logo_image"])

def upload_seller_banner(*, seller: SellerProfile, banner) -> str:
    return _replace_file_and_set(seller, "banner_image", banner)

def delete_seller_banner(*, seller: SellerProfile) -> None:
    if seller.banner_image and seller.banner_image.name:
        try: default_storage.delete(seller.banner_image.name)
        except Exception: pass
    seller.banner_image = None
    seller.save(update_fields=["banner_image"])

# ---------- SELLER COMMANDS ----------

def create_seller_for_owner(*, owner, data: dict) -> SellerProfile:
    if get_seller_for_owner(owner):
        raise TokenInvalid("Seller profile already exists for this user")
    sp = SellerProfile(owner=owner, **data)
    sp.save()
    ensure_owner_membership(sp)
    return sp

def update_seller_owned(*, seller: SellerProfile, data: dict) -> SellerProfile:
    allowed = {"company_name","legal_name","description","contact_email","contact_phone","website_url"}
    for k,v in data.items():
        if k in allowed and v is not None:
            setattr(seller, k, v)
    seller.save()
    return seller


# ===== OWNER (właściciel profilu) =====

def owner_create_bank_account(*, owner, data: dict) -> SellerBankAccount:
    sp = get_seller_for_owner(owner)
    if not sp:
        raise TokenInvalid("Seller profile not found for user")
    acc = SellerBankAccount(seller_profile=sp, **data)
    acc.save()
    if data.get("is_default"):
        set_default_for_seller(sp, acc)
    return acc

def owner_update_bank_account(*, owner, public_id: str, data: dict) -> SellerBankAccount:
    acc = get_bank_account_by_public_id(public_id)
    if not acc or acc.seller_profile.owner_id != owner.id:
        raise TokenInvalid("Not found")
    for k, v in data.items():
        setattr(acc, k, v)
    acc.save()
    return acc

def owner_delete_bank_account(*, owner, public_id: str) -> None:
    acc = get_bank_account_by_public_id(public_id)
    if not acc or acc.seller_profile.owner_id != owner.id:
        raise TokenInvalid("Not found")
    acc.delete()

def owner_set_default_bank_account(*, owner, public_id: str) -> SellerBankAccount:
    acc = get_bank_account_by_public_id(public_id)
    if not acc or acc.seller_profile.owner_id != owner.id:
        raise TokenInvalid("Not found")
    set_default_for_seller(acc.seller_profile, acc)
    return acc

# ===== ADMIN =====

def admin_create_bank_account(*, seller_profile: SellerProfile, data: dict) -> SellerBankAccount:
    acc = SellerBankAccount(seller_profile=seller_profile, **data)
    acc.save()
    if data.get("is_default"):
        set_default_for_seller(seller_profile, acc)
    return acc

def admin_update_bank_account(*, public_id: str, data: dict) -> SellerBankAccount:
    acc = get_bank_account_by_public_id(public_id)
    if not acc:
        raise TokenInvalid("Not found")
    for k, v in data.items():
        setattr(acc, k, v)
    acc.save()
    return acc

def admin_delete_bank_account(*, public_id: str) -> None:
    acc = get_bank_account_by_public_id(public_id)
    if acc:
        acc.delete()

def admin_set_default_bank_account(*, public_id: str) -> SellerBankAccount:
    acc = get_bank_account_by_public_id(public_id)
    if not acc:
        raise TokenInvalid("Nie znaleziono")
    set_default_for_seller(acc.seller_profile, acc)
    return acc


def member_create_bank_account(*, user, seller_public_id: str, data: dict) -> SellerBankAccount:
    if not is_member(user, seller_public_id, BANK_ADMIN_ROLES):
        raise TokenInvalid("Brak uprawnień do tego sklepu")
    sp = get_seller_by_public_id(seller_public_id)
    if not sp:
        raise TokenInvalid("Nie znaleziono sprzedawcy")
    acc = SellerBankAccount(seller_profile=sp, **data)
    acc.save()
    if data.get("is_default"):
        set_default_for_seller(sp, acc)
    return acc

def member_update_bank_account(*, user, public_id: str, data: dict) -> SellerBankAccount:
    acc = get_bank_account_by_public_id(public_id)
    if not acc or not is_member(user, acc.seller_profile.public_id, BANK_ADMIN_ROLES):
        raise TokenInvalid("Nie znaleziono lub brak uprawnień")
    for k, v in data.items():
        setattr(acc, k, v)
    acc.save()
    return acc

def member_delete_bank_account(*, user, public_id: str) -> None:
    acc = get_bank_account_by_public_id(public_id)
    if not acc or not is_member(user, acc.seller_profile.public_id, BANK_ADMIN_ROLES):
        raise TokenInvalid("Nie znaleziono lub brak uprawnień")
    acc.delete()

def member_set_default_bank_account(*, user, public_id: str) -> SellerBankAccount:
    acc = get_bank_account_by_public_id(public_id)
    if not acc or not is_member(user, acc.seller_profile.public_id, BANK_ADMIN_ROLES):
        raise TokenInvalid("Not found or no permission")
    set_default_for_seller(acc.seller_profile, acc)
    return acc

# --- helper: zapewnij OWNER-membership dla właściciela sklepu ---
def ensure_owner_membership(seller: SellerProfile):
    if not SellerMembership.objects.filter(seller_profile=seller, user_id=seller.owner_id).exists():
        SellerMembership.objects.create(seller_profile=seller, user_id=seller.owner_id, role="OWNER", is_active=True)

# wywołaj ensure_owner_membership w miejscach tworzenia sklepu:
# - po commands.create_seller_for_owner(...)
# - po AdminSellerProfileViewSet.create(...)

# ==== MEMBERSHIP COMMANDS ====

@transaction.atomic
def add_member(*, actor: User, seller: SellerProfile, target_user: User, role: str) -> SellerMembership:
    if not queries.can_manage_members(actor, seller):
        raise PermissionError("Not allowed")

    # Nie dodajemy użytkowników-klientów
    if target_user.role == "CLIENT":
        raise TokenInvalid("Użytkownik z rolą CLIENT nie może zostać członkiem sklepu")

    if role == "OWNER":
        raise TokenInvalid("Nie można nadać uprawnień właściciela (OWNER)")

    actor_role = queries.user_role_in_seller(actor, seller)

    # Manager może dodać TYLKO pracownika
    if actor_role == "MANAGER" and role != "EMPLOYEE":
        raise PermissionError("Manager może dodawać wyłącznie pracowników (EMPLOYEE)")

    # nie dubluj
    m, created = SellerMembership.objects.get_or_create(
        seller_profile=seller, user=target_user,
        defaults={"role": role, "is_active": True}
    )
    if not created:
        # jeśli istnieje nieaktywny – reaktywuj i ustaw rolę
        if not m.is_active:
            m.is_active = True
        m.role = role
        m.save(update_fields=["is_active", "role"])
    return m

@transaction.atomic
def update_member_role(*, actor: User, seller: SellerProfile, member: SellerMembership, new_role: str) -> SellerMembership:
    if not queries.can_manage_members(actor, seller):
        raise PermissionError("Not allowed")
    if member.user_id == seller.owner_id:
        raise TokenInvalid("Nie można zmieniać roli właściciela")
    if new_role == "OWNER":
        raise TokenInvalid("Nie można przydzielać roli OWNER innym użytkownikom")

    actor_role = queries.user_role_in_seller(actor, seller)

    # Tylko OWNER może ruszać MANAGERÓW
    if member.role == "MANAGER" or new_role == "MANAGER":
        if actor_role != "OWNER" and not actor.is_staff:
            raise PermissionError("Tylko właściciel może modyfikować rolę MANAGER")

    # Manager nie rusza MODERATORÓW (ten sam poziom)
    if actor_role == "MANAGER" and (member.role == "MODERATOR" or new_role == "MODERATOR"):
        raise PermissionError("Manager nie może modyfikować roli MODERATOR")

    # Manager może zmieniać tylko w obrębie EMPLOYEE (przy rozwoju api może dojdą nowe role)
    if actor_role == "MANAGER" and new_role != "EMPLOYEE":
        raise PermissionError("Manager może ustawiać wyłącznie rolę EMPLOYEE")

    member.role = new_role
    member.save(update_fields=["role"])
    return member

@transaction.atomic
def remove_member(*, actor: User, seller: SellerProfile, member: SellerMembership) -> None:
    if not queries.can_manage_members(actor, seller):
        raise PermissionError("Not allowed")
    if member.user_id == seller.owner_id:
        raise TokenInvalid("Nie można usunąć właściciela sklepu")

    actor_role = queries.user_role_in_seller(actor, seller)

    # Manager nie usuwa MANAGERÓW ani MODERATORÓW
    if actor_role == "MANAGER" and member.role in {"MANAGER", "MODERATOR"}:
        raise PermissionError("Manager może usuwać wyłącznie pracowników (EMPLOYEE)")

    member.is_active = False
    member.save(update_fields=["is_active"])

