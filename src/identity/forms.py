from __future__ import annotations
from typing import Optional

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError

from .models import SellerProfile, SellerBankAccount, SellerMembership
from .services.repositories import is_email_taken_ci
from .services.crud import authenticate_user

User = get_user_model()


# =========================
# Helpers
# =========================

def _lower(v: str | None) -> str | None:
    return v.lower().strip() if isinstance(v, str) else v

def _strip(v: str | None) -> str | None:
    return v.strip() if isinstance(v, str) else v


# =========================
# AUTH
# =========================

class RegisterForm(forms.Form):
    email = forms.EmailField()
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)

    def clean_email(self):
        email = _lower(self.cleaned_data["email"])
        if is_email_taken_ci(email):
            raise ValidationError("Ten e-mail jest już zajęty.")
        return email

    def clean_password(self):
        pwd = self.cleaned_data["password"]
        password_validation.validate_password(pwd)
        return pwd


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, do_authenticate: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.do_authenticate = do_authenticate
        self.user: Optional[User] = None

    def clean_email(self):
        return _lower(self.cleaned_data["email"])

    def clean(self):
        cleaned = super().clean()
        if self.do_authenticate and not self.errors:
            u = authenticate_user(email=cleaned.get("email"), password=cleaned.get("password"))
            if not u:
                raise ValidationError("Nieprawidłowy e-mail lub hasło.")
            if not u.is_active:
                raise ValidationError("Konto jest nieaktywne.")
            self.user = u
        return cleaned


class ForgotPasswordForm(forms.Form):
    email = forms.EmailField()
    def clean_email(self): return _lower(self.cleaned_data["email"])


class ResetPasswordForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput)
    new_password = forms.CharField(widget=forms.PasswordInput, label="Nowe hasło")
    new_password2 = forms.CharField(widget=forms.PasswordInput, label="Powtórz hasło")

    def clean_new_password(self):
        pwd = self.cleaned_data["new_password"]
        password_validation.validate_password(pwd)
        return pwd

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_password") != cleaned.get("new_password2"):
            raise ValidationError("Hasła muszą być identyczne.")
        return cleaned


class ChangeEmailForm(forms.Form):
    new_email = forms.EmailField()

    def __init__(self, *args, user: Optional[User] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_new_email(self):
        if not self.user:
            raise ValidationError("Brak kontekstu użytkownika.")
        new_email = _lower(self.cleaned_data["new_email"])
        if new_email == _lower(getattr(self.user, "email", "")):
            raise ValidationError("Nowy e-mail nie może być taki sam jak obecny.")
        if is_email_taken_ci(new_email, exclude_user_id=self.user.id):
            raise ValidationError("Ten e-mail jest już używany.")
        return new_email


class ConfirmRegistrationForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput)


class ConfirmEmailChangeForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput)


# =========================
# USER (self/admin)
# =========================

class UserSelfUpdateForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False)
    last_name  = forms.CharField(max_length=150, required=False)
    phone_number = forms.CharField(max_length=32, required=False)

    def clean_first_name(self): return _strip(self.cleaned_data.get("first_name"))
    def clean_last_name(self):  return _strip(self.cleaned_data.get("last_name"))
    def clean_phone_number(self): return _strip(self.cleaned_data.get("phone_number"))


class AvatarUploadForm(forms.Form):
    image = forms.ImageField()


def _user_role_choices():
    return [c[0] for c in User._meta.get_field("role").choices]

def _user_status_choices():
    return [c[0] for c in User._meta.get_field("user_status").choices]


class AdminUserCreateForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput, min_length=10)
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    role = forms.ChoiceField(choices=[(c, c) for c in _user_role_choices()], required=False)
    user_status = forms.ChoiceField(choices=[(c, c) for c in _user_status_choices()], required=False)
    is_staff = forms.BooleanField(required=False, initial=False)
    is_active = forms.BooleanField(required=False, initial=True)

    def clean_email(self):
        email = _lower(self.cleaned_data["email"])
        if is_email_taken_ci(email):
            raise ValidationError("Ten e-mail jest już zajęty.")
        return email

    def clean_password(self):
        pwd = self.cleaned_data["password"]
        password_validation.validate_password(pwd)
        return pwd


class AdminUserUpdateForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False)
    last_name  = forms.CharField(max_length=150, required=False)
    phone_number = forms.CharField(max_length=32, required=False)
    role = forms.ChoiceField(choices=[(c, c) for c in _user_role_choices()], required=False)
    user_status = forms.ChoiceField(choices=[(c, c) for c in _user_status_choices()], required=False)
    is_staff = forms.BooleanField(required=False)
    is_active = forms.BooleanField(required=False)


# =========================
# SELLER PROFILE (owner/admin)
# =========================

class SellerProfileCreateForm(forms.Form):
    company_name = forms.CharField(max_length=200)
    legal_name = forms.CharField(max_length=300, required=False)
    slug = forms.SlugField(max_length=64)
    description = forms.CharField(widget=forms.Textarea, required=False)
    contact_email = forms.EmailField(required=False)
    contact_phone = forms.CharField(max_length=32, required=False)
    website_url = forms.URLField(required=False)

    def clean_slug(self): return _lower(self.cleaned_data["slug"])
    def clean_contact_email(self): return _lower(self.cleaned_data.get("contact_email"))
    def clean_company_name(self): return _strip(self.cleaned_data["company_name"])
    def clean_legal_name(self): return _strip(self.cleaned_data.get("legal_name"))
    def clean_contact_phone(self): return _strip(self.cleaned_data.get("contact_phone"))


class SellerProfileUpdateForm(forms.Form):
    company_name = forms.CharField(max_length=200, required=False)
    legal_name = forms.CharField(max_length=300, required=False)
    description = forms.CharField(widget=forms.Textarea, required=False)
    contact_email = forms.EmailField(required=False)
    contact_phone = forms.CharField(max_length=32, required=False)
    website_url = forms.URLField(required=False)

    def clean_contact_email(self): return _lower(self.cleaned_data.get("contact_email"))
    def clean_company_name(self): return _strip(self.cleaned_data.get("company_name"))
    def clean_legal_name(self): return _strip(self.cleaned_data.get("legal_name"))
    def clean_contact_phone(self): return _strip(self.cleaned_data.get("contact_phone"))


class SellerLogoUploadForm(forms.Form):
    logo = forms.ImageField()


class SellerBannerUploadForm(forms.Form):
    banner = forms.ImageField()


class AdminSellerProfileCreateForm(SellerProfileCreateForm):
    owner_id = forms.IntegerField(required=False)
    owner_public_id = forms.CharField(required=False)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("owner_id") and not cleaned.get("owner_public_id"):
            raise ValidationError("Wymagane: owner_id lub owner_public_id.")
        return cleaned


class AdminSellerProfileUpdateForm(SellerProfileUpdateForm):
    pass


# =========================
# BANK ACCOUNTS (member/admin)
# =========================

class BaseBankAccountCreateForm(forms.Form):
    iban = forms.CharField(max_length=40)
    bank_name = forms.CharField(max_length=120, required=False)
    account_holder = forms.CharField(max_length=200, required=False)
    is_active = forms.BooleanField(required=False, initial=True)
    is_default = forms.BooleanField(required=False, initial=False)

    def clean_iban(self):
        return _strip(self.cleaned_data["iban"]).replace(" ", "").upper()

    def clean_bank_name(self): return _strip(self.cleaned_data.get("bank_name"))
    def clean_account_holder(self): return _strip(self.cleaned_data.get("account_holder"))


class MemberBankAccountCreateForm(BaseBankAccountCreateForm):
    seller_public_id = forms.CharField()


class BankAccountUpdateForm(forms.Form):
    bank_name = forms.CharField(max_length=120, required=False)
    account_holder = forms.CharField(max_length=200, required=False)
    is_active = forms.BooleanField(required=False)

    def clean_bank_name(self): return _strip(self.cleaned_data.get("bank_name"))
    def clean_account_holder(self): return _strip(self.cleaned_data.get("account_holder"))


class AdminBankAccountCreateForm(BaseBankAccountCreateForm):
    seller_public_id = forms.CharField()


class AdminBankAccountUpdateForm(BankAccountUpdateForm):
    pass


# =========================
# MEMBERSHIPS (owner/manager)
# =========================

def _membership_role_choices_without_owner():
    return [(c, c) for (c, _label) in SellerMembership.ROLE_CHOICES if c != "OWNER"]

class SellerMembershipCreateForm(forms.Form):
    user_public_id = forms.CharField(required=False)
    email = forms.EmailField(required=False)
    role = forms.ChoiceField(choices=_membership_role_choices_without_owner())

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("user_public_id") and not cleaned.get("email"):
            raise ValidationError("Podaj user_public_id lub email.")
        if cleaned.get("email"):
            cleaned["email"] = _lower(cleaned["email"])
        return cleaned


class SellerMembershipUpdateRoleForm(forms.Form):
    role = forms.ChoiceField(choices=_membership_role_choices_without_owner())
