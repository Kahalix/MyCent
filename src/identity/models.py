from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from common.models import PublicIdModel


# ========= Custom User =========

class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: Optional[str], **extra_fields):
        if not email:
            raise ValueError("The Email musi być ustalony")
        email = self.normalize_email(email).lower()
        extra_fields.setdefault("is_active", True)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: Optional[str] = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser musi mieć is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser musi mieć is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser, PublicIdModel):
    """
    Użytkownik: logowanie e-mailem (case-insensitive unikalność).
    """
    username = None
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=32, blank=True)
    points = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    user_image = models.ImageField(upload_to="users/", blank=True, null=True)

    ROLE_CHOICES = [
        ("CLIENT", "Client"),
        ("EMPLOYEE", "Employee"),
        ("MODERATOR", "Moderator"),
        ("MANAGER", "Manager"),
        ("OWNER", "Owner"),
    ]
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default="CLIENT")

    STATUS_CHOICES = [("ACTIVE","Active"),("INACTIVE","Inactive"),("SUSPENDED","Suspended"),("DELETED","Deleted")]
    user_status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="ACTIVE")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=["date_joined"], name="ix_user_date_joined"),
            models.Index(fields=["email"], name="ix_user_email_ci"),
        ]
        constraints = [
            models.UniqueConstraint(Lower("email"), name="uq_users_email_ci"),
        ]
        permissions = [
            ("can_set_user_status", "Can change user status"),
        ]

    def __str__(self) -> str:
        return self.email


# ========= Seller Profile & Bank Account =========

slug_validator = RegexValidator(regex=r"^[a-z0-9-]{3,64}$", message="Dozwolone małe litery, cyfry i myślnik.")

class SellerProfile(PublicIdModel):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller_profile")
    company_name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=300, blank=True)
    slug = models.SlugField(max_length=64, unique=True, validators=[slug_validator])
    description = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=32, blank=True)
    website_url = models.URLField(blank=True)
    logo_image = models.ImageField(upload_to="seller/logo/", blank=True, null=True)
    banner_image = models.ImageField(upload_to="seller/banner/", blank=True, null=True)
    followers_count = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    rating_count = models.PositiveIntegerField(default=0)

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="SellerMembership",
        related_name="seller_profiles",
        blank=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["slug"], name="ix_seller_slug"),
            models.Index(fields=["company_name"], name="ix_seller_company"),
        ]

    def __str__(self) -> str:
        return self.company_name


# --- SellerMembership (wiele osób przy jednym sklepie) ---
class SellerMembership(PublicIdModel):
    ROLE_CHOICES = [
        ("OWNER", "Owner"),
        ("MANAGER", "Manager"),
        ("EMPLOYEE", "Employee"),
        ("MODERATOR", "Moderator"),
    ]
    seller_profile = models.ForeignKey(
        SellerProfile, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller_memberships"
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default="EMPLOYEE")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (("seller_profile", "user"),)
        indexes = [
            models.Index(fields=["seller_profile", "role"], name="ix_members_role"),
            models.Index(fields=["user", "is_active"], name="ix_members_user_active"),
        ]

    def __str__(self) -> str:
        return f"{self.seller_profile.slug} :: {self.user.email} ({self.role})"


class SellerBankAccount(PublicIdModel):
    seller_profile = models.ForeignKey(SellerProfile, on_delete=models.CASCADE, related_name="bank_accounts")
    iban = models.CharField(
        max_length=40,
        unique=True,
        validators=[RegexValidator(regex=r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$", message="IBAN bez spacji, wielkie litery.")],
    )
    bank_name = models.CharField(max_length=120, blank=True)
    account_holder = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["seller_profile"], name="ix_bank_accounts_profile"),
            models.Index(fields=["seller_profile","is_default"], name="ix_bank_accounts_default"),
        ]
        constraints = [
            # tylko jedno domyślne konto per seller_profile
            models.UniqueConstraint(
                fields=["seller_profile"],
                condition=Q(is_default=True),
                name="uq_default_bank_account_per_seller",
            )
        ]

    def save(self, *args, **kwargs):
        if self.iban:
            self.iban = self.iban.replace(" ", "").upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.seller_profile.company_name} / {self.iban}"


# ========= UserToken (ephemeral + REFRESH_TOKEN w DB) =========

class UserToken(PublicIdModel):
    """
    Hashowane tokeny jednorazowe i refresh JWT przechowywane w DB.
    """
    TYPE_CHOICES = [
        ("EMAIL_CONFIRMATION", "EMAIL_CONFIRMATION"),
        ("PASSWORD_RESET", "PASSWORD_RESET"),
        ("EMAIL_CHANGE", "EMAIL_CHANGE"),
        ("REFRESH_TOKEN", "REFRESH_TOKEN"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tokens")
    type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    hash = models.CharField(max_length=64)  # sha-256 hex
    expiry = models.DateTimeField()
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["type", "expiry"], name="ix_usertoken_type_expiry"),
            models.Index(fields=["user", "type"], name="ix_usertoken_user_type"),
        ]

    # --- helpers ---

    @staticmethod
    def _sha256(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_random() -> str:
        return secrets.token_urlsafe(32)

    @classmethod
    def issue_ephemeral(cls, user: User, typ: str, minutes_valid: int, data: Optional[dict] = None) -> str:
        raw = cls.generate_random()
        cls.objects.create(
            user=user,
            type=typ,
            hash=cls._sha256(raw),
            expiry=timezone.now() + timedelta(minutes=minutes_valid),
            data=data or {},
        )
        return raw

    @classmethod
    def consume_ephemeral(cls, raw: str, typ: str) -> Optional["UserToken"]:
        obj = cls.objects.filter(
            type=typ,
            hash=cls._sha256(raw),
            expiry__gt=timezone.now()
        ).first()
        if not obj:
            return None
        obj.delete()
        return obj

    # ---- REFRESH JWT w DB ----

    @classmethod
    def save_refresh(cls, user: User, raw_refresh_jwt: str, data: Optional[dict] = None) -> "UserToken":
        lifetime = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
        return cls.objects.create(
            user=user,
            type="REFRESH_TOKEN",
            hash=cls._sha256(raw_refresh_jwt),
            expiry=timezone.now() + lifetime,
            data=data or {},
        )

    @classmethod
    def exists_refresh(cls, user: User, raw_refresh_jwt: str) -> bool:
        return cls.objects.filter(
            user=user,
            type="REFRESH_TOKEN",
            hash=cls._sha256(raw_refresh_jwt),
            expiry__gt=timezone.now(),
        ).exists()

    @classmethod
    def delete_refresh(cls, user: User, raw_refresh_jwt: str) -> int:
        return cls.objects.filter(
            user=user,
            type="REFRESH_TOKEN",
            hash=cls._sha256(raw_refresh_jwt),
        ).delete()[0]

    @classmethod
    def delete_all_refreshes(cls, user: User) -> int:
        return cls.objects.filter(user=user, type="REFRESH_TOKEN").delete()[0]
