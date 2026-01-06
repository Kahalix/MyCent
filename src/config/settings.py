import os
from pathlib import Path
import environ
from datetime import timedelta
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = os.environ.get("ENV_FILE", os.path.join(BASE_DIR.parent, ".env"))
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_SECRET_KEY=(str, "change-me"),
    DJANGO_ALLOWED_HOSTS=(str, "localhost,web,web-http,caddy,0.0.0.0"),
    DATABASE_URL=(str, ""),
    REDIS_URL=(str, "redis://localhost:6379/1"),
)
environ.Env.read_env(ENV_FILE)

DEBUG = env.bool("DJANGO_DEBUG")
SECRET_KEY = env.str("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = [h.strip() for h in env.str("DJANGO_ALLOWED_HOSTS").split(",") if h.strip()]

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",
    "drf_spectacular",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "djmoney",
    "corsheaders",
    "django_filters",
    "django_seed",
    "django_jsonform",
    "common",
    "identity",
    "catalog",
    "listings",
    "chat",
    "orders",
    "transactions",
    "coupons",
    "shipping",
    "saved",
    "services",
    "carts",
    "customers",
    "pawns",
    "payments",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.middleware.common.CommonMiddleware",
    "common.middleware.EnsureCSRFCookieMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db(
        default=(
            f"postgresql://{env.str('POSTGRES_USER', 'lown')}:"
            f"{env.str('POSTGRES_PASSWORD', 'lownpass')}@"
            f"{env.str('POSTGRES_HOST', '127.0.0.1')}:"
            f"{env.str('POSTGRES_PORT', '5432')}/"
            f"{env.str('POSTGRES_DB', 'lown')}"
        )
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=30)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Lown API",
    "DESCRIPTION": "Pawn & marketplace",
    "VERSION": "1.0.0",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ALGORITHM": "HS256",
}

JWT_REFRESH_IN_COOKIE = True
AUTH_COOKIE_NAME = "refresh_token"
AUTH_COOKIE_PATH = "/api/auth/"
AUTH_COOKIE_SECURE = env.bool("AUTH_COOKIE_SECURE", default=not DEBUG)
AUTH_COOKIE_DOMAIN = env.str("AUTH_COOKIE_DOMAIN", default="") or None
AUTH_COOKIE_HTTPONLY = True

if not DEBUG:
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=not DEBUG)

SESSION_COOKIE_SAMESITE = env.str("SESSION_COOKIE_SAMESITE", default="Lax")
CSRF_COOKIE_SAMESITE = env.str("CSRF_COOKIE_SAMESITE", default="Lax")

AUTH_COOKIE_HTTPONLY = True
AUTH_COOKIE_SAMESITE = env.str("AUTH_COOKIE_SAMESITE", default="Lax")

EMAIL_BACKEND = env.str("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env.str("EMAIL_HOST", "mailpit")
EMAIL_PORT = env.int("EMAIL_PORT", 1025)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", False)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", False)
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", "noreply@lown.local")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SERVICES_SIGNUP_FREE_PACKAGE_PUBLIC_IDS = [
    "awqsblage859z8sp99u21hpy",
    "awqsblagq859z8sqaap9yyyt",
]

REDIS_URL = env.str("REDIS_URL", "redis://redis:6379/1")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    },
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env.str("CACHE_URL", "redis://redis:6379/3"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 50,
                "retry_on_timeout": True,
            },
        },
        "KEY_PREFIX": "lown",
        "TIMEOUT": 60 * 60,
    }
}

PUBLIC_ITEMSETS_LIST_CACHE_TTL = env.int("PUBLIC_ITEMSETS_LIST_CACHE_TTL", default=20)
PUBLIC_ITEMSETS_DETAIL_CACHE_TTL = env.int("PUBLIC_ITEMSETS_DETAIL_CACHE_TTL", default=15)

CELERY_BROKER_URL = env.str("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = env.str("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
CELERY_TIMEZONE = "Europe/Warsaw"
CELERY_ENABLE_UTC = False

CELERY_BEAT_SCHEDULE = {
    "saved_check_price_drops": {
        "task": "saved.tasks.check_price_drops_periodic",
        "schedule": 15 * 60,
        "kwargs": {"notify": True, "limit": 0},
    },
    "saved_refresh_searches": {
        "task": "saved.tasks.refresh_saved_searches_periodic",
        "schedule": crontab(minute=0, hour=3),
        "kwargs": {"prune": True, "limit": 0},
    },
    "orders_purge_expired_reservations": {
        "task": "orders.purge_expired_reservations",
        "schedule": crontab(minute=0),
        "kwargs": {"days": 3},
    },
    "idempo_purge_old": {
        "task": "common.purge_old_idempotency_keys",
        "schedule": crontab(minute=10, hour=4),
        "kwargs": {"days": 30},
    },
    "transactions_cancel_stale_pending": {
        "task": "transactions.cancel_stale_pending",
        "schedule": crontab(minute="*/15"),
    },
    "listings_expire_stale_user_itemsets": {
        "task": "listings.tasks.expire_stale_user_itemsets_periodic",
        "schedule": crontab(minute=40, hour=4),
        "kwargs": {"days": 30, "limit": 0},
    },
}

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
CSRF_FAILURE_VIEW = "core.views.csrf_failure_view"

PAWN_RATE_BPS_PER_30D = int(env.int("PAWN_RATE_BPS_PER_30D", default=1000))
PAWN_MIN_FEE_AMOUNT = int(env.int("PAWN_MIN_FEE_AMOUNT", default=5))
PAWN_CURRENCY = "PLN"

LANGUAGE_CODE = "pl"
TIME_ZONE = "Europe/Warsaw"
USE_I18N = True
USE_TZ = True

SITE_NAME = env.str("SITE_NAME", "MyCent")
SITE_URL = env.str("SITE_URL", "http://localhost:8000")

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

USE_MANIFEST = env.bool("USE_MANIFEST", default=not DEBUG)

if DEBUG:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"
    WHITENOISE_USE_FINDERS = True
else:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
    WHITENOISE_USE_FINDERS = False

WHITENOISE_AUTOREFRESH = DEBUG

STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

TEMPLATES[0]["DIRS"] = [BASE_DIR / "templates"]

ORDERS_RESERVATION_TTL_MINUTES = int(
    env.int("ORDERS_RESERVATION_TTL_MINUTES", default=30)
)
TRANSACTIONS_PENDING_TTL_MINUTES = int(
    env.int("TRANSACTIONS_PENDING_TTL_MINUTES", default=60)
)

WS_ALLOWED_ORIGINS = env.list(
    "WS_ALLOWED_ORIGINS",
    default=(CSRF_TRUSTED_ORIGINS or CORS_ALLOWED_ORIGINS or []),
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "identity.User"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REDIRECT_EXEMPT = [r"^api/payments/webhooks/stripe/$"]

CHAT_NEW_MESSAGE_WEBHOOK_URL = "https://example.com/webhooks/chat/new-message"
CHAT_NEW_MESSAGE_WEBHOOK_SECRET = "supersecret"

STRIPE_PUBLISHABLE_KEY = env.str("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_SECRET_KEY = env.str("STRIPE_SECRET_KEY", default="")
STRIPE_WEBHOOK_SECRET = env.str("STRIPE_WEBHOOK_SECRET", default="")

TEMPLATES[0]["OPTIONS"]["context_processors"].append(
    "payments.payments_integrations.stripe_ctx.stripe_public_key"
)
