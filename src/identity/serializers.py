from __future__ import annotations
from django.contrib.auth import get_user_model, password_validation
from rest_framework import serializers
from .models import SellerProfile, SellerBankAccount, SellerMembership

User = get_user_model()

# ======= USER - Responses =======

class PublicUserSafeResponse(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("public_id", "first_name", "last_name", "user_image")


class PublicUserResponse(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "public_id", "email", "first_name", "last_name", "phone_number", "role",
            "is_staff", "is_superuser", "user_status", "points", "user_image"
        )

class UserResponse(PublicUserSafeResponse):
    pass

class UserAdminResponse(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "public_id","email","first_name","last_name","phone_number","points","user_image",
            "role","user_status","is_active","is_staff","last_login","date_joined"
        )

class UserAdminListResponse(UserAdminResponse):
    """lista może mieć te same pola; oddzielone pod ew. zmianę w przyszłości"""
    pass

# ======= USER - Requests =======

class RegisterRequest(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=10)
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    def validate_email(self, value): return value.lower()
    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

class LoginRequest(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    def validate_email(self, value): return value.lower()

class RefreshRequest(serializers.Serializer):
    refresh = serializers.CharField(required=False, write_only=True)

    def validate(self, attrs):
        if attrs.get("refresh"):
            raise serializers.ValidationError(
                {"refresh": "Refresh token jest akceptowany wyłącznie przez HttpOnly cookie."}
            )
        return {}

class ForgotPasswordRequest(serializers.Serializer):
    email = serializers.EmailField()
    def validate_email(self, v): return v.lower()

class ResetPasswordRequest(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=10)
    def validate_new_password(self, v):
        password_validation.validate_password(v)
        return v

class ChangeEmailRequest(serializers.Serializer):
    new_email = serializers.EmailField()
    def validate_new_email(self, v): return v.lower()

class ConfirmEmailChangeRequest(serializers.Serializer):
    token = serializers.CharField()

class ConfirmRegistrationRequest(serializers.Serializer):
    token = serializers.CharField()

class UserSelfUpdateRequest(serializers.Serializer):
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name  = serializers.CharField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)

class ChangePasswordRequest(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=10)
    def validate_new_password(self, v):
        password_validation.validate_password(v)
        return v

class UserAdminCreateRequest(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=10)
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    role = serializers.ChoiceField(choices=[c[0] for c in User._meta.get_field("role").choices], required=False)
    user_status = serializers.ChoiceField(choices=[c[0] for c in User._meta.get_field("user_status").choices], required=False)
    is_staff = serializers.BooleanField(required=False, default=False)
    is_active = serializers.BooleanField(required=False, default=True)
    def validate_email(self, v): return v.lower()
    def validate_password(self, v):
        password_validation.validate_password(v)
        return v

class UserAdminUpdateRequest(serializers.Serializer):
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name  = serializers.CharField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=[c[0] for c in User._meta.get_field("role").choices], required=False)
    user_status = serializers.ChoiceField(choices=[c[0] for c in User._meta.get_field("user_status").choices], required=False)
    is_staff = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)

class AdminUserStatusUpdateRequest(serializers.Serializer):
    user_status = serializers.ChoiceField(
        choices=[c[0] for c in User._meta.get_field("user_status").choices]
    )
    # domyślne mapowanie is_active
    is_active = serializers.BooleanField(required=False)

class AvatarUploadRequest(serializers.Serializer):
    image = serializers.ImageField()

# ======= SELLER PROFILE =======

class SellerProfilePublicResponse(serializers.ModelSerializer):
    # owner = PublicUserSafeResponse()

    class Meta:
        model = SellerProfile
        fields = (
            "public_id", "company_name", "slug", "description", "contact_email", "contact_phone",
            "website_url", "logo_image", "banner_image", "followers_count", "rating", "rating_count", "owner"
        )

class SellerProfilePrivateResponse(serializers.ModelSerializer):
    class Meta:
        model = SellerProfile
        fields = (
            "public_id","company_name","legal_name","slug","description","contact_email","contact_phone",
            "website_url","logo_image","banner_image","followers_count","rating","rating_count"
        )

class SellerProfileAdminResponse(serializers.ModelSerializer):
    owner = UserAdminResponse()
    class Meta:
        model = SellerProfile
        fields = (
            "public_id","company_name","legal_name","slug","description","contact_email","contact_phone",
            "website_url","logo_image","banner_image","followers_count","rating","rating_count","owner"
        )

class SellerProfileCreateRequest(serializers.ModelSerializer):
    class Meta:
        model = SellerProfile
        fields = ("company_name","legal_name","slug","description","contact_email","contact_phone","website_url")

class SellerProfileUpdateRequest(serializers.ModelSerializer):
    class Meta:
        model = SellerProfile
        fields = ("company_name","legal_name","description","contact_email","contact_phone","website_url")

class SellerLogoUploadRequest(serializers.Serializer):
    logo = serializers.ImageField()

class SellerBannerUploadRequest(serializers.Serializer):
    banner = serializers.ImageField()

# ===== SELLER BANK ACCOUNTS =====

class SellerBankAccountOwnerResponse(serializers.ModelSerializer):
    class Meta:
        model = SellerBankAccount
        fields = (
            "public_id", "iban", "bank_name", "account_holder",
            "is_active", "is_default", "created_at", "updated_at"
        )

class SellerBankAccountAdminResponse(serializers.ModelSerializer):
    seller_public_id = serializers.CharField(source="seller_profile.public_id", read_only=True)
    seller_slug = serializers.CharField(source="seller_profile.slug", read_only=True)
    owner_email = serializers.EmailField(source="seller_profile.owner.email", read_only=True)

    class Meta:
        model = SellerBankAccount
        fields = (
            "public_id", "iban", "bank_name", "account_holder",
            "is_active", "is_default", "created_at", "updated_at",
            "seller_public_id", "seller_slug", "owner_email"
        )

class SellerBankAccountCreateRequest(serializers.ModelSerializer):
    class Meta:
        model = SellerBankAccount
        fields = ("iban", "bank_name", "account_holder", "is_active", "is_default")

    def validate_iban(self, v):
        return v.replace(" ", "").upper()

class SellerBankAccountUpdateRequest(serializers.ModelSerializer):
    class Meta:
        model = SellerBankAccount
        fields = ("bank_name", "account_holder", "is_active")

# ===== MEMBERSHIPS =====
from .models import SellerMembership

class SellerMembershipResponse(serializers.ModelSerializer):
    user = PublicUserResponse()
    seller_public_id = serializers.CharField(source="seller_profile.public_id", read_only=True)
    seller_slug = serializers.CharField(source="seller_profile.slug", read_only=True)

    class Meta:
        model = SellerMembership
        fields = (
            "public_id", "seller_public_id", "seller_slug",
            "user", "role", "is_active", "created_at", "updated_at"
        )

class SellerMembershipCreateRequest(serializers.Serializer):
    # Możesz wskazać użytkownika po public_id lub email (wymagane jedno z nich)
    user_public_id = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False)
    role = serializers.ChoiceField(choices=[c[0] for c in SellerMembership.ROLE_CHOICES if c[0] != "OWNER"])

    def validate(self, data):
        if not data.get("user_public_id") and not data.get("email"):
            raise serializers.ValidationError("Podaj user_public_id lub email.")
        return data

class SellerMembershipUpdateRoleRequest(serializers.Serializer):
    role = serializers.ChoiceField(choices=[c[0] for c in SellerMembership.ROLE_CHOICES if c[0] != "OWNER"])

# ===== SELLER CONTEXT =====
from .models import SellerMembership

class SellerContextResponse(serializers.Serializer):
    in_shop = serializers.BooleanField()
    role = serializers.ChoiceField(
        choices=[c[0] for c in SellerMembership.ROLE_CHOICES] + ["CLIENT"],
        allow_null=True
    )
    seller_public_id = serializers.CharField(allow_null=True)
    seller_slug = serializers.CharField(allow_null=True)

    # Jakie zakładki wolno - do prostego sterowania UI
    allowed_tabs = serializers.SerializerMethodField()

    def get_allowed_tabs(self, obj):
        role = obj.get("role")
        matrix = {
            "OWNER":     ["overview", "data", "graphics", "accounts", "members",  "offers"],
            "MANAGER":   ["overview",                                 "members",  "offers"],
            "MODERATOR": ["overview",                                             "offers"],
            "EMPLOYEE":  ["overview",                                             "offers"],
            "CLIENT":    [],
            None:        [],
        }
        return matrix.get(role, [])



