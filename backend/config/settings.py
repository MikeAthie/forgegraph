"""
Django settings for ForgeGraph backend.

Clean Architecture: This belongs to the Frameworks & Drivers layer.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")


def _get_bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_csv_env(name: str, default: str) -> list[str]:
    raw = os.environ.get(name, default)
    return [part.strip() for part in raw.split(",") if part.strip()]


DEBUG = _get_bool_env("DEBUG", False)
TESTING = _get_bool_env("TESTING", False) or any("pytest" in arg.lower() for arg in sys.argv)
IS_DEV_LIKE = DEBUG or TESTING


SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()
if not SECRET_KEY:
    if IS_DEV_LIKE:
        SECRET_KEY = "django-insecure-dev-key-change-in-production"
    else:
        raise ImproperlyConfigured("SECRET_KEY must be configured when DEBUG is False.")

_default_allowed_hosts = "localhost,127.0.0.1,testserver" if IS_DEV_LIKE else ""
ALLOWED_HOSTS = _get_csv_env("ALLOWED_HOSTS", _default_allowed_hosts)
if not ALLOWED_HOSTS and not IS_DEV_LIKE:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be configured when DEBUG is False.")

FORGEGRAPH_RUNTIME_MODE = os.environ.get("FORGEGRAPH_RUNTIME_MODE", "cloud").strip().lower()
if FORGEGRAPH_RUNTIME_MODE not in {"cloud", "self_hosted"}:
    FORGEGRAPH_RUNTIME_MODE = "cloud"

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # Third-party
    "channels",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    # Local apps
    "infrastructure.orm",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "adapters.api.deprecation_middleware.ApiDeprecationMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
USE_SQLITE = os.environ.get("USE_SQLITE", "false").lower() in {"1", "true", "yes"}
if USE_SQLITE:
    _sqlite_db_path_env = os.environ.get("SQLITE_DB_PATH")
    if _sqlite_db_path_env:
        _sqlite_path = Path(_sqlite_db_path_env)
        if not _sqlite_path.is_absolute():
            _sqlite_path = BASE_DIR / _sqlite_path
    else:
        _sqlite_path = BASE_DIR / "db.sqlite3"

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": _sqlite_path,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "forgegraph"),
            "USER": os.environ.get("DB_USER", "forgegraph"),
            "PASSWORD": os.environ.get("DB_PASSWORD", "forgegraph_secret"),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5433"),
        }
    }

# Cache
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"redis://{os.environ.get('REDIS_HOST', 'localhost')}:{os.environ.get('REDIS_PORT', '6379')}/1",
    }
}

# Channels
USE_IN_MEMORY_CHANNEL_LAYER = os.environ.get("USE_IN_MEMORY_CHANNEL_LAYER", "false").lower() in {
    "1",
    "true",
    "yes",
}
CHANNEL_LAYERS: dict[str, dict[str, Any]]
if USE_SQLITE or USE_IN_MEMORY_CHANNEL_LAYER:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [
                    [
                        os.environ.get("REDIS_HOST", "localhost"),
                        int(os.environ.get("REDIS_PORT", "6379")),
                    ]
                ]
            },
        }
    }

# Custom User Model
AUTH_USER_MODEL = "orm.User"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS Configuration
CORS_ALLOW_ALL_ORIGINS = IS_DEV_LIKE and _get_bool_env("CORS_ALLOW_ALL_ORIGINS", False)
CORS_ALLOWED_ORIGINS = _get_csv_env(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
    if IS_DEV_LIKE
    else "",
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = _get_csv_env(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
    if IS_DEV_LIKE
    else "",
)

# Web security defaults
SESSION_COOKIE_SECURE = _get_bool_env("SESSION_COOKIE_SECURE", not IS_DEV_LIKE)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SECURE = _get_bool_env("CSRF_COOKIE_SECURE", not IS_DEV_LIKE)
CSRF_COOKIE_HTTPONLY = _get_bool_env("CSRF_COOKIE_HTTPONLY", False)
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
SECURE_CONTENT_TYPE_NOSNIFF = _get_bool_env("SECURE_CONTENT_TYPE_NOSNIFF", not IS_DEV_LIKE)
SECURE_REFERRER_POLICY = os.environ.get("SECURE_REFERRER_POLICY", "strict-origin-when-cross-origin")
X_FRAME_OPTIONS = os.environ.get("X_FRAME_OPTIONS", "DENY")
SECURE_SSL_REDIRECT = _get_bool_env("SECURE_SSL_REDIRECT", not IS_DEV_LIKE)
SECURE_HSTS_SECONDS = int(
    os.environ.get("SECURE_HSTS_SECONDS", "31536000" if not IS_DEV_LIKE else "0")
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _get_bool_env("SECURE_HSTS_INCLUDE_SUBDOMAINS", not IS_DEV_LIKE)
SECURE_HSTS_PRELOAD = _get_bool_env("SECURE_HSTS_PRELOAD", False)
USE_X_FORWARDED_HOST = _get_bool_env("USE_X_FORWARDED_HOST", not IS_DEV_LIKE)
if _get_bool_env("USE_SECURE_PROXY_SSL_HEADER", not IS_DEV_LIKE):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# REST Framework Configuration
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "adapters.api.authentication.RevocableJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# API Documentation (drf-spectacular)
SPECTACULAR_SETTINGS = {
    "TITLE": "ForgeGraph API",
    "DESCRIPTION": "API for the ForgeGraph visual workflow engine for AI agents.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/",
    "TAGS": [
        {"name": "auth", "description": "Authentication endpoints"},
        {"name": "graphs", "description": "Graph and workflow management"},
        {"name": "prompts", "description": "Prompt template library"},
        {"name": "runs", "description": "Workflow execution runs"},
    ],
}

# Add browsable API in debug/test mode
if IS_DEV_LIKE:
    _renderer_classes: list[str] = REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"]  # type: ignore[assignment]
    _renderer_classes.append("rest_framework.renderers.BrowsableAPIRenderer")
    _parser_classes: list[str] = REST_FRAMEWORK["DEFAULT_PARSER_CLASSES"]  # type: ignore[assignment]
    _parser_classes.extend(
        [
            "rest_framework.parsers.FormParser",
            "rest_framework.parsers.MultiPartParser",
        ]
    )

# JWT Settings
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}
AUTH_WS_TICKET_TTL_SECONDS = int(os.environ.get("AUTH_WS_TICKET_TTL_SECONDS", "45"))
ENGINE_GRPC_TLS_ENABLED = _get_bool_env("ENGINE_GRPC_TLS_ENABLED", False)
ENGINE_GRPC_TLS_CA_FILE = os.environ.get("ENGINE_GRPC_TLS_CA_FILE", "")
ENGINE_GRPC_TLS_SERVER_NAME = os.environ.get("ENGINE_GRPC_TLS_SERVER_NAME", "")

# Refresh token cookie (recommended for SPAs)
AUTH_REFRESH_COOKIE = os.environ.get("AUTH_REFRESH_COOKIE", "refresh_token")
AUTH_REFRESH_COOKIE_PATH = os.environ.get("AUTH_REFRESH_COOKIE_PATH", "/api/auth/")
AUTH_REFRESH_COOKIE_DOMAIN = os.environ.get("AUTH_REFRESH_COOKIE_DOMAIN") or None
AUTH_REFRESH_COOKIE_SAMESITE = os.environ.get("AUTH_REFRESH_COOKIE_SAMESITE", "Lax").title()
AUTH_REFRESH_COOKIE_SECURE = os.environ.get(
    "AUTH_REFRESH_COOKIE_SECURE", "true" if not IS_DEV_LIKE else "false"
).lower() in {"1", "true", "yes"}

# Frontend base URL for redirects (SSO, billing)
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

# Adaptive rate limits
RUN_START_RATE_LIMIT_PER_MIN = int(os.environ.get("RUN_START_RATE_LIMIT_PER_MIN", "60"))
RUN_INVOKE_RATE_LIMIT_PER_MIN = int(os.environ.get("RUN_INVOKE_RATE_LIMIT_PER_MIN", "120"))
RUN_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RUN_RATE_LIMIT_WINDOW_SECONDS", "60"))
RUN_MAX_ACTIVE_PER_TENANT = int(os.environ.get("RUN_MAX_ACTIVE_PER_TENANT", "25"))
RUN_INPUT_MAX_BYTES = int(os.environ.get("RUN_INPUT_MAX_BYTES", str(256 * 1024)))
RUN_RUNTIME_LIMIT_MAX_DURATION_MS = int(
    os.environ.get("RUN_RUNTIME_LIMIT_MAX_DURATION_MS", "300000")
)
RUN_RUNTIME_LIMIT_MAX_TOOL_CALLS = int(os.environ.get("RUN_RUNTIME_LIMIT_MAX_TOOL_CALLS", "32"))
RUN_RUNTIME_LIMIT_MAX_LLM_CALLS = int(os.environ.get("RUN_RUNTIME_LIMIT_MAX_LLM_CALLS", "24"))

# Run queue configuration
RUN_QUEUE_ENABLED = os.environ.get("RUN_QUEUE_ENABLED", "false").lower() in {"1", "true", "yes"}
RUN_QUEUE_MAX_CONCURRENCY_PER_TENANT = int(
    os.environ.get("RUN_QUEUE_MAX_CONCURRENCY_PER_TENANT", "5")
)
RUN_QUEUE_WORKER_LOCK_SECONDS = int(os.environ.get("RUN_QUEUE_WORKER_LOCK_SECONDS", "300"))
RUN_QUEUE_RETRY_DELAY_SECONDS = int(os.environ.get("RUN_QUEUE_RETRY_DELAY_SECONDS", "30"))

# SLO thresholds (defaults)
SLO_RUN_SUCCESS_RATE = float(os.environ.get("SLO_RUN_SUCCESS_RATE", "0.99"))
SLO_RUN_P95_LATENCY_MS = int(os.environ.get("SLO_RUN_P95_LATENCY_MS", "60000"))
SLO_QUEUE_MAX_DEPTH = int(os.environ.get("SLO_QUEUE_MAX_DEPTH", "500"))

# Stripe billing configuration
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# Engine Configuration (Go gRPC service)
ENGINE_HOST = os.environ.get("ENGINE_HOST", "localhost")
ENGINE_PORT = int(os.environ.get("ENGINE_PORT", "50051"))
ENGINE_CALLBACK_URL = os.environ.get(
    "ENGINE_CALLBACK_URL",
    "http://localhost:8000/api/runs/engine-events",
)
ENGINE_CALLBACK_SECRET = os.environ.get("ENGINE_CALLBACK_SECRET", "")
ENGINE_CALLBACK_MAX_SKEW_SECONDS = int(os.environ.get("ENGINE_CALLBACK_MAX_SKEW_SECONDS", "600"))
RUN_LIVENESS_TIMEOUT_SECONDS = int(os.environ.get("RUN_LIVENESS_TIMEOUT_SECONDS", "300"))
ALLOWED_LLM_PROVIDERS = [
    provider.strip().lower()
    for provider in os.environ.get("ALLOWED_LLM_PROVIDERS", "openai,anthropic").split(",")
    if provider.strip()
]
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
FF_CURATED_MEMORY_ENABLED = _get_bool_env("FF_CURATED_MEMORY_ENABLED", True)
FF_CURATED_MEMORY_VECTOR_INDEXING = _get_bool_env("FF_CURATED_MEMORY_VECTOR_INDEXING", True)
FF_OS_SHELL = _get_bool_env("FF_OS_SHELL", True)
FF_AGENT_REGISTRY = _get_bool_env("FF_AGENT_REGISTRY", True)
FF_TASK_PROJECTIONS = _get_bool_env("FF_TASK_PROJECTIONS", True)
FF_DECISION_CENTER = _get_bool_env("FF_DECISION_CENTER", True)
FF_ACCOUNTING_AGGREGATES = _get_bool_env("FF_ACCOUNTING_AGGREGATES", True)
FF_PUBLIC_API_ALIASES = _get_bool_env("FF_PUBLIC_API_ALIASES", True)
CURATED_MEMORY_EMBEDDING_MODEL = os.environ.get(
    "CURATED_MEMORY_EMBEDDING_MODEL",
    "text-embedding-ada-002",
)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG" if IS_DEV_LIKE else "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "forgegraph_json": {
            "()": "application.services.structured_logging.JsonLogFormatter",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "forgegraph_json",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "forgegraph": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}

# Telegram Integration
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_WEBHOOK_REQUEST_TIMEOUT_SECONDS = int(
    os.environ.get("TELEGRAM_WEBHOOK_REQUEST_TIMEOUT_SECONDS", "15")
)
TELEGRAM_VOICE_TRANSCRIPTION_MODEL = os.environ.get(
    "TELEGRAM_VOICE_TRANSCRIPTION_MODEL",
    "whisper-1",
)

# WhatsApp (Twilio) Integration
WHATSAPP_WEBHOOK_REQUEST_TIMEOUT_SECONDS = int(
    os.environ.get("WHATSAPP_WEBHOOK_REQUEST_TIMEOUT_SECONDS", "15")
)
WHATSAPP_VOICE_TRANSCRIPTION_MODEL = os.environ.get(
    "WHATSAPP_VOICE_TRANSCRIPTION_MODEL",
    "whisper-1",
)

# Generic Webhook Integration
GENERIC_WEBHOOK_SECRET = os.environ.get("GENERIC_WEBHOOK_SECRET", "")

# Encryption Configuration
# Generate key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")
ENCRYPTION_KEY_PREVIOUS = _get_csv_env("ENCRYPTION_KEY_PREVIOUS", "")
if not ENCRYPTION_KEY and TESTING:
    ENCRYPTION_KEY = "31w_1yyrCRlD_5Uyp9iofvy68W9T1ty9W81BbBlkbWI="
if not ENCRYPTION_KEY and not IS_DEV_LIKE:
    raise ImproperlyConfigured("ENCRYPTION_KEY must be configured when DEBUG is False.")
