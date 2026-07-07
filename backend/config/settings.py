"""
Django settings for ForgeGraph backend.

Clean Architecture: This belongs to the Frameworks & Drivers layer.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

from corsheaders.defaults import default_headers
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")
_override_env_file = os.environ.get("FORGEGRAPH_ENV_FILE", "").strip()
if _override_env_file:
    _override_env_path = Path(_override_env_file)
    if not _override_env_path.is_absolute():
        _override_env_path = BASE_DIR.parent / _override_env_path
    load_dotenv(_override_env_path, override=True)

_LEGACY_ENV_VAR_RENAMES = {
    "SECRET_KEYS": "SECRET_KEY",
    "ENGINE_CALLBACK_SECRETS": "ENGINE_CALLBACK_SECRET",
}
_legacy_env_vars_present = [
    f"{legacy} is no longer supported; use {current}."
    for legacy, current in _LEGACY_ENV_VAR_RENAMES.items()
    if legacy in os.environ
]
if _legacy_env_vars_present:
    raise ImproperlyConfigured(" ".join(_legacy_env_vars_present))


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

OPERATING_MODEL_PACKS_DIR = os.environ.get("OPERATING_MODEL_PACKS_DIR", "").strip()
REQUIRED_OPERATING_MODEL_PACKS = _get_csv_env(
    "REQUIRED_OPERATING_MODEL_PACKS",
    "digital_marketing_pro",
)
VALIDATE_REQUIRED_OPERATING_MODEL_PACKS_ON_STARTUP = _get_bool_env(
    "VALIDATE_REQUIRED_OPERATING_MODEL_PACKS_ON_STARTUP",
    True,
)

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
    "adapters.api.security_middleware.ApiRequestSizeLimitMiddleware",
    "adapters.api.metrics_middleware.RequestMetricsMiddleware",
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

# Cache / channels
USE_IN_MEMORY_CHANNEL_LAYER = os.environ.get("USE_IN_MEMORY_CHANNEL_LAYER", "false").lower() in {
    "1",
    "true",
    "yes",
}
USE_IN_MEMORY_CACHE = os.environ.get(
    "USE_IN_MEMORY_CACHE",
    os.environ.get("USE_IN_MEMORY_CHANNEL_LAYER", "false"),
).lower() in {
    "1",
    "true",
    "yes",
}

if USE_SQLITE or USE_IN_MEMORY_CACHE:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "forgegraph-local-cache",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": f"redis://{os.environ.get('REDIS_HOST', 'localhost')}:{os.environ.get('REDIS_PORT', '6379')}/1",
        }
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
CORS_ALLOW_HEADERS = (*default_headers, "idempotency-key")
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
AUTH_REGISTER_THROTTLE_RATE = os.environ.get("AUTH_REGISTER_THROTTLE_RATE", "20/hour")
AUTH_LOGIN_THROTTLE_RATE = os.environ.get("AUTH_LOGIN_THROTTLE_RATE", "10/min")
AUTH_REFRESH_THROTTLE_RATE = os.environ.get("AUTH_REFRESH_THROTTLE_RATE", "60/min")
AUTH_WS_TICKET_THROTTLE_RATE = os.environ.get("AUTH_WS_TICKET_THROTTLE_RATE", "120/min")
API_ANON_THROTTLE_RATE = os.environ.get("API_ANON_THROTTLE_RATE", "120/min")
API_USER_THROTTLE_RATE = os.environ.get("API_USER_THROTTLE_RATE", "1200/min")
API_REQUEST_MAX_BYTES = int(os.environ.get("API_REQUEST_MAX_BYTES", str(1024 * 1024)))

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
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "anon": API_ANON_THROTTLE_RATE,
        "user": API_USER_THROTTLE_RATE,
        "auth_register": AUTH_REGISTER_THROTTLE_RATE,
        "auth_login": AUTH_LOGIN_THROTTLE_RATE,
        "auth_refresh": AUTH_REFRESH_THROTTLE_RATE,
        "auth_ws_ticket": AUTH_WS_TICKET_THROTTLE_RATE,
    },
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
READINESS_REQUIRE_ENGINE = _get_bool_env("READINESS_REQUIRE_ENGINE", False)
READINESS_REQUIRE_RUNTIME_TRANSPORT = _get_bool_env("READINESS_REQUIRE_RUNTIME_TRANSPORT", False)
READINESS_REQUIRE_COMMUNICATION_KAFKA = _get_bool_env(
    "READINESS_REQUIRE_COMMUNICATION_KAFKA",
    False,
)
READINESS_REQUIRE_WHITEBOARD_BOARD_KAFKA = _get_bool_env(
    "READINESS_REQUIRE_WHITEBOARD_BOARD_KAFKA",
    False,
)
FORGEGRAPH_STRICT_RUNTIME_ENV = _get_bool_env("FORGEGRAPH_STRICT_RUNTIME_ENV", False)
FORGEGRAPH_ALLOW_INSECURE_TRANSPORT = _get_bool_env("FORGEGRAPH_ALLOW_INSECURE_TRANSPORT", False)

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
MANAGED_LLM_MAX_TOKENS_PER_RUN = int(os.environ.get("MANAGED_LLM_MAX_TOKENS_PER_RUN", "25000"))
MANAGED_LLM_MAX_CALLS_PER_RUN = int(
    os.environ.get("MANAGED_LLM_MAX_CALLS_PER_RUN", str(RUN_RUNTIME_LIMIT_MAX_LLM_CALLS))
)
MANAGED_LLM_RATE_LIMIT_PER_USER_PER_MIN = int(
    os.environ.get("MANAGED_LLM_RATE_LIMIT_PER_USER_PER_MIN", "600")
)
MANAGED_LLM_DAILY_COST_CAP_USD = os.environ.get("MANAGED_LLM_DAILY_COST_CAP_USD", "10.00")
ENABLE_CODEX_SESSION_RUNTIME = _get_bool_env("ENABLE_CODEX_SESSION_RUNTIME", False)
CODEX_SESSION_COMMAND = os.environ.get("CODEX_SESSION_COMMAND", "codex").strip() or "codex"
CODEX_SESSION_WORKDIR = os.environ.get("CODEX_SESSION_WORKDIR", str(BASE_DIR.parent)).strip()
CODEX_SESSION_TIMEOUT_SECONDS = int(os.environ.get("CODEX_SESSION_TIMEOUT_SECONDS", "180"))

# Run queue configuration
RUN_QUEUE_ENABLED = os.environ.get("RUN_QUEUE_ENABLED", "false").lower() in {"1", "true", "yes"}
RUN_QUEUE_MAX_CONCURRENCY_PER_TENANT = int(
    os.environ.get("RUN_QUEUE_MAX_CONCURRENCY_PER_TENANT", "5")
)
RUN_QUEUE_WORKER_LOCK_SECONDS = int(os.environ.get("RUN_QUEUE_WORKER_LOCK_SECONDS", "300"))
RUN_QUEUE_RETRY_DELAY_SECONDS = int(os.environ.get("RUN_QUEUE_RETRY_DELAY_SECONDS", "30"))
RUN_QUEUE_WORKER_HEARTBEAT_TTL_SECONDS = int(
    os.environ.get(
        "RUN_QUEUE_WORKER_HEARTBEAT_TTL_SECONDS",
        str(max(RUN_QUEUE_WORKER_LOCK_SECONDS * 2, 120)),
    )
)

# Generic communication primitives are backend-owned durable state.
COMMUNICATION_ENABLED = _get_bool_env("COMMUNICATION_ENABLED", True)

# Generic email connector. Dry-run is safe by default; real send is opt-in.
EMAIL_CONNECTOR_PROVIDER = (
    os.environ.get("EMAIL_CONNECTOR_PROVIDER", "fake").strip().lower() or "fake"
)
EMAIL_CONNECTOR_DRY_RUN_DEFAULT = _get_bool_env("EMAIL_CONNECTOR_DRY_RUN_DEFAULT", True)
EMAIL_CONNECTOR_ALLOW_REAL_SEND = _get_bool_env("EMAIL_CONNECTOR_ALLOW_REAL_SEND", False)
EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST = _get_csv_env("EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST", "")
EMAIL_CONNECTOR_DEFAULT_FROM_EMAIL = os.environ.get(
    "EMAIL_CONNECTOR_DEFAULT_FROM_EMAIL", ""
).strip()
EMAIL_CONNECTOR_DEFAULT_FROM_NAME = os.environ.get("EMAIL_CONNECTOR_DEFAULT_FROM_NAME", "").strip()
EMAIL_CONNECTOR_TIMEOUT_SECONDS = float(os.environ.get("EMAIL_CONNECTOR_TIMEOUT_SECONDS", "10"))
EMAIL_CONNECTOR_MAX_RECIPIENTS = int(os.environ.get("EMAIL_CONNECTOR_MAX_RECIPIENTS", "50"))
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
RESEND_API_BASE_URL = os.environ.get("RESEND_API_BASE_URL", "https://api.resend.com").strip()
ATLAS_P2_REAL_CONNECTORS = _get_bool_env("ATLAS_P2_REAL_CONNECTORS", False)

# Generic outbound messaging connector. Web automation is experimental and opt-in.
WHATSAPP_CONNECTOR_PROVIDER = (
    os.environ.get("WHATSAPP_CONNECTOR_PROVIDER", "fake").strip().lower() or "fake"
)
WHATSAPP_WEB_AUTOMATION_ENABLED = _get_bool_env("WHATSAPP_WEB_AUTOMATION_ENABLED", False)
WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND = _get_bool_env(
    "WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND", False
)
WHATSAPP_CONNECTOR_ALLOW_REAL_SEND = _get_bool_env(
    "WHATSAPP_CONNECTOR_ALLOW_REAL_SEND", WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND
)
WHATSAPP_RECIPIENT_ALLOWLIST = _get_csv_env("WHATSAPP_RECIPIENT_ALLOWLIST", "")
WHATSAPP_WEB_AUTOMATION_MAX_RECIPIENTS = int(
    os.environ.get("WHATSAPP_WEB_AUTOMATION_MAX_RECIPIENTS", "5")
)
WHATSAPP_WEB_AUTOMATION_SESSION_REF = os.environ.get(
    "WHATSAPP_WEB_AUTOMATION_SESSION_REF", ""
).strip()
WHATSAPP_WEB_AUTOMATION_SIDECAR_URL = (
    os.environ.get("WHATSAPP_WEB_AUTOMATION_SIDECAR_URL")
    or os.environ.get("WHATSAPP_WEB_AUTOMATION_SIDEcar_URL")
    or os.environ.get("SELENIUM_URL", "")
).strip()
WHATSAPP_HERMES_BRIDGE_ENABLED = _get_bool_env("WHATSAPP_HERMES_BRIDGE_ENABLED", False)
WHATSAPP_HERMES_BRIDGE_URL = os.environ.get("WHATSAPP_HERMES_BRIDGE_URL", "").strip()
WHATSAPP_HERMES_BRIDGE_SESSION_REF = os.environ.get(
    "WHATSAPP_HERMES_BRIDGE_SESSION_REF", ""
).strip()
WHATSAPP_CONNECTOR_TIMEOUT_SECONDS = float(
    os.environ.get("WHATSAPP_CONNECTOR_TIMEOUT_SECONDS", "10")
)
WHATSAPP_CLOUD_API_TOKEN = os.environ.get("WHATSAPP_CLOUD_API_TOKEN", "").strip()
WHATSAPP_CLOUD_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_CLOUD_PHONE_NUMBER_ID", "").strip()
WHATSAPP_APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "").strip()

GATEWAY_CONNECTOR_ALLOW_REAL_SEND = _get_bool_env("GATEWAY_CONNECTOR_ALLOW_REAL_SEND", False)
GATEWAY_CONNECTOR_TIMEOUT_SECONDS = float(os.environ.get("GATEWAY_CONNECTOR_TIMEOUT_SECONDS", "10"))
GATEWAY_CONNECTOR_MAX_RECIPIENTS = int(os.environ.get("GATEWAY_CONNECTOR_MAX_RECIPIENTS", "10"))
GATEWAY_RECIPIENT_ALLOWLIST = _get_csv_env("GATEWAY_RECIPIENT_ALLOWLIST", "")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "").strip()
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "").strip()
MSGRAPH_CLIENT_STATE = os.environ.get("MSGRAPH_CLIENT_STATE", "").strip()

# Generic social publishing connector. Provider publish is opt-in; dry-run/manual evidence are policy gated.
SOCIAL_CONNECTOR_PROVIDER = (
    os.environ.get("SOCIAL_CONNECTOR_PROVIDER", "fake").strip().lower() or "fake"
)
SOCIAL_CONNECTOR_DRY_RUN_DEFAULT = _get_bool_env("SOCIAL_CONNECTOR_DRY_RUN_DEFAULT", True)
SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH = _get_bool_env(
    "SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH", False
)
SOCIAL_CONNECTOR_ALLOW_MANUAL_EVIDENCE = _get_bool_env(
    "SOCIAL_CONNECTOR_ALLOW_MANUAL_EVIDENCE", True
)
SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST = _get_csv_env("SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST", "")
SOCIAL_CONNECTOR_TIMEOUT_SECONDS = float(os.environ.get("SOCIAL_CONNECTOR_TIMEOUT_SECONDS", "10"))
SOCIAL_CONNECTOR_MAX_ASSETS_PER_POST = int(
    os.environ.get("SOCIAL_CONNECTOR_MAX_ASSETS_PER_POST", "1")
)
SOCIAL_CONNECTOR_MAX_CAPTION_CHARS = int(
    os.environ.get("SOCIAL_CONNECTOR_MAX_CAPTION_CHARS", "2200")
)
META_GRAPH_ACCESS_TOKEN = (
    os.environ.get("META_GRAPH_ACCESS_TOKEN")
    or os.environ.get("INSTAGRAM_GRAPH_API")
    or ""
).strip()
META_GRAPH_APP_ID = os.environ.get("META_GRAPH_APP_ID", "").strip()
META_GRAPH_APP_SECRET = os.environ.get("META_GRAPH_APP_SECRET", "").strip()
META_GRAPH_API_BASE_URL = os.environ.get(
    "META_GRAPH_API_BASE_URL", "https://graph.facebook.com"
).strip()
META_GRAPH_API_VERSION = os.environ.get("META_GRAPH_API_VERSION", "v24.0").strip()
META_GRAPH_PAGE_ID_ALLOWLIST = _get_csv_env("META_GRAPH_PAGE_ID_ALLOWLIST", "")
META_GRAPH_IG_USER_ID_ALLOWLIST = _get_csv_env("META_GRAPH_IG_USER_ID_ALLOWLIST", "")

# Optional communication event transport. The database outbox remains authoritative.
KAFKA_BROKERS = os.environ.get("KAFKA_BROKERS", "").strip()
KAFKA_CLIENT_ID = os.environ.get("KAFKA_CLIENT_ID", "").strip()
KAFKA_COMMUNICATION_TOPIC = os.environ.get("KAFKA_COMMUNICATION_TOPIC", "").strip()
KAFKA_COMMUNICATION_CONSUMER_GROUP = os.environ.get(
    "KAFKA_COMMUNICATION_CONSUMER_GROUP",
    "",
).strip()
KAFKA_TEST_TOPIC_PREFIX = os.environ.get("KAFKA_TEST_TOPIC_PREFIX", "").strip()
COMMUNICATION_KAFKA_ENABLED = _get_bool_env("COMMUNICATION_KAFKA_ENABLED", False)
COMMUNICATION_KAFKA_BOOTSTRAP_SERVERS = os.environ.get(
    "COMMUNICATION_KAFKA_BOOTSTRAP_SERVERS",
    KAFKA_BROKERS,
).strip()
COMMUNICATION_KAFKA_TOPIC = os.environ.get(
    "COMMUNICATION_KAFKA_TOPIC",
    KAFKA_COMMUNICATION_TOPIC or "forgegraph.communication.events.v1",
).strip()
COMMUNICATION_KAFKA_CLIENT_ID = os.environ.get(
    "COMMUNICATION_KAFKA_CLIENT_ID",
    KAFKA_CLIENT_ID or "forgegraph-communication-outbox",
).strip()
COMMUNICATION_KAFKA_CONSUMER_GROUP = os.environ.get(
    "COMMUNICATION_KAFKA_CONSUMER_GROUP",
    KAFKA_COMMUNICATION_CONSUMER_GROUP or "forgegraph-communication-events",
).strip()
COMMUNICATION_KAFKA_FLUSH_TIMEOUT_SECONDS = float(
    os.environ.get("COMMUNICATION_KAFKA_FLUSH_TIMEOUT_SECONDS", "5")
)
COMMUNICATION_KAFKA_PRODUCE_POLL_TIMEOUT_SECONDS = float(
    os.environ.get("COMMUNICATION_KAFKA_PRODUCE_POLL_TIMEOUT_SECONDS", "1")
)
COMMUNICATION_KAFKA_DELIVERY_TIMEOUT_MS = int(
    os.environ.get("COMMUNICATION_KAFKA_DELIVERY_TIMEOUT_MS", "30000")
)
COMMUNICATION_KAFKA_REQUEST_TIMEOUT_MS = int(
    os.environ.get("COMMUNICATION_KAFKA_REQUEST_TIMEOUT_MS", "10000")
)
COMMUNICATION_KAFKA_RETRIES = int(os.environ.get("COMMUNICATION_KAFKA_RETRIES", "5"))
COMMUNICATION_KAFKA_RETRY_BACKOFF_MS = int(
    os.environ.get("COMMUNICATION_KAFKA_RETRY_BACKOFF_MS", "250")
)
COMMUNICATION_KAFKA_LINGER_MS = int(os.environ.get("COMMUNICATION_KAFKA_LINGER_MS", "5"))
COMMUNICATION_KAFKA_COMPRESSION_TYPE = os.environ.get(
    "COMMUNICATION_KAFKA_COMPRESSION_TYPE",
    "lz4",
).strip()
COMMUNICATION_KAFKA_STATISTICS_INTERVAL_MS = int(
    os.environ.get("COMMUNICATION_KAFKA_STATISTICS_INTERVAL_MS", "0")
)
COMMUNICATION_KAFKA_MAX_PAYLOAD_BYTES = int(
    os.environ.get("COMMUNICATION_KAFKA_MAX_PAYLOAD_BYTES", str(64 * 1024))
)
COMMUNICATION_KAFKA_AUTO_OFFSET_RESET = os.environ.get(
    "COMMUNICATION_KAFKA_AUTO_OFFSET_RESET",
    "earliest",
).strip()
COMMUNICATION_KAFKA_ISOLATION_LEVEL = os.environ.get(
    "COMMUNICATION_KAFKA_ISOLATION_LEVEL",
    "read_committed",
).strip()
COMMUNICATION_KAFKA_SESSION_TIMEOUT_MS = int(
    os.environ.get("COMMUNICATION_KAFKA_SESSION_TIMEOUT_MS", "45000")
)
COMMUNICATION_KAFKA_MAX_POLL_INTERVAL_MS = int(
    os.environ.get("COMMUNICATION_KAFKA_MAX_POLL_INTERVAL_MS", "300000")
)
COMMUNICATION_KAFKA_METADATA_TIMEOUT_SECONDS = float(
    os.environ.get("COMMUNICATION_KAFKA_METADATA_TIMEOUT_SECONDS", "5")
)
COMMUNICATION_KAFKA_OUTBOX_BACKLOG_READY_THRESHOLD = int(
    os.environ.get("COMMUNICATION_KAFKA_OUTBOX_BACKLOG_READY_THRESHOLD", "1000")
)
COMMUNICATION_KAFKA_SECURITY_PROTOCOL = os.environ.get(
    "COMMUNICATION_KAFKA_SECURITY_PROTOCOL",
    "",
).strip()
COMMUNICATION_KAFKA_SASL_MECHANISM = os.environ.get(
    "COMMUNICATION_KAFKA_SASL_MECHANISM",
    "",
).strip()
COMMUNICATION_KAFKA_SASL_USERNAME = os.environ.get(
    "COMMUNICATION_KAFKA_SASL_USERNAME",
    "",
).strip()
COMMUNICATION_KAFKA_SASL_PASSWORD = os.environ.get(
    "COMMUNICATION_KAFKA_SASL_PASSWORD",
    "",
).strip()
COMMUNICATION_ROUTING_FROM_KAFKA_ENABLED = _get_bool_env(
    "COMMUNICATION_ROUTING_FROM_KAFKA_ENABLED",
    False,
)
REQUEST_ROUTER_FROM_KAFKA_ENABLED = _get_bool_env(
    "REQUEST_ROUTER_FROM_KAFKA_ENABLED",
    False,
)

# Optional whiteboard board event transport. The database remains authoritative;
# Kafka carries sanitized metadata and Redis snapshots are rebuildable from DB.
KAFKA_WHITEBOARD_BOARD_TOPIC = os.environ.get("KAFKA_WHITEBOARD_BOARD_TOPIC", "").strip()
KAFKA_WHITEBOARD_BOARD_CONSUMER_GROUP = os.environ.get(
    "KAFKA_WHITEBOARD_BOARD_CONSUMER_GROUP",
    "",
).strip()
WHITEBOARD_BOARD_KAFKA_ENABLED = _get_bool_env("WHITEBOARD_BOARD_KAFKA_ENABLED", False)
WHITEBOARD_BOARD_KAFKA_BOOTSTRAP_SERVERS = os.environ.get(
    "WHITEBOARD_BOARD_KAFKA_BOOTSTRAP_SERVERS",
    KAFKA_BROKERS,
).strip()
WHITEBOARD_BOARD_KAFKA_TOPIC = os.environ.get(
    "WHITEBOARD_BOARD_KAFKA_TOPIC",
    KAFKA_WHITEBOARD_BOARD_TOPIC or "forgegraph.whiteboard.board.events.v1",
).strip()
WHITEBOARD_BOARD_KAFKA_CLIENT_ID = os.environ.get(
    "WHITEBOARD_BOARD_KAFKA_CLIENT_ID",
    KAFKA_CLIENT_ID or "forgegraph-whiteboard-board-outbox",
).strip()
WHITEBOARD_BOARD_KAFKA_CONSUMER_GROUP = os.environ.get(
    "WHITEBOARD_BOARD_KAFKA_CONSUMER_GROUP",
    KAFKA_WHITEBOARD_BOARD_CONSUMER_GROUP or "forgegraph-whiteboard-board-events",
).strip()
WHITEBOARD_BOARD_KAFKA_FLUSH_TIMEOUT_SECONDS = float(
    os.environ.get("WHITEBOARD_BOARD_KAFKA_FLUSH_TIMEOUT_SECONDS", "5")
)
WHITEBOARD_BOARD_KAFKA_DELIVERY_TIMEOUT_MS = int(
    os.environ.get("WHITEBOARD_BOARD_KAFKA_DELIVERY_TIMEOUT_MS", "30000")
)
WHITEBOARD_BOARD_KAFKA_REQUEST_TIMEOUT_MS = int(
    os.environ.get("WHITEBOARD_BOARD_KAFKA_REQUEST_TIMEOUT_MS", "10000")
)
WHITEBOARD_BOARD_KAFKA_RETRIES = int(os.environ.get("WHITEBOARD_BOARD_KAFKA_RETRIES", "5"))
WHITEBOARD_BOARD_KAFKA_RETRY_BACKOFF_MS = int(
    os.environ.get("WHITEBOARD_BOARD_KAFKA_RETRY_BACKOFF_MS", "250")
)
WHITEBOARD_BOARD_KAFKA_LINGER_MS = int(os.environ.get("WHITEBOARD_BOARD_KAFKA_LINGER_MS", "5"))
WHITEBOARD_BOARD_KAFKA_COMPRESSION_TYPE = os.environ.get(
    "WHITEBOARD_BOARD_KAFKA_COMPRESSION_TYPE",
    "lz4",
).strip()
WHITEBOARD_BOARD_KAFKA_MAX_PAYLOAD_BYTES = int(
    os.environ.get("WHITEBOARD_BOARD_KAFKA_MAX_PAYLOAD_BYTES", str(64 * 1024))
)
WHITEBOARD_BOARD_KAFKA_AUTO_OFFSET_RESET = os.environ.get(
    "WHITEBOARD_BOARD_KAFKA_AUTO_OFFSET_RESET",
    "earliest",
).strip()
WHITEBOARD_BOARD_KAFKA_ISOLATION_LEVEL = os.environ.get(
    "WHITEBOARD_BOARD_KAFKA_ISOLATION_LEVEL",
    "read_committed",
).strip()
WHITEBOARD_BOARD_KAFKA_METADATA_TIMEOUT_SECONDS = float(
    os.environ.get("WHITEBOARD_BOARD_KAFKA_METADATA_TIMEOUT_SECONDS", "5")
)
WHITEBOARD_BOARD_KAFKA_OUTBOX_BACKLOG_READY_THRESHOLD = int(
    os.environ.get("WHITEBOARD_BOARD_KAFKA_OUTBOX_BACKLOG_READY_THRESHOLD", "1000")
)
WHITEBOARD_BOARD_KAFKA_SECURITY_PROTOCOL = os.environ.get(
    "WHITEBOARD_BOARD_KAFKA_SECURITY_PROTOCOL",
    "",
).strip()
WHITEBOARD_BOARD_KAFKA_SASL_MECHANISM = os.environ.get(
    "WHITEBOARD_BOARD_KAFKA_SASL_MECHANISM",
    "",
).strip()
WHITEBOARD_BOARD_KAFKA_SASL_USERNAME = os.environ.get(
    "WHITEBOARD_BOARD_KAFKA_SASL_USERNAME",
    "",
).strip()
WHITEBOARD_BOARD_KAFKA_SASL_PASSWORD = os.environ.get(
    "WHITEBOARD_BOARD_KAFKA_SASL_PASSWORD",
    "",
).strip()

# SLO thresholds (defaults)
FORGEGRAPH_RELEASE_TIER = os.environ.get("FORGEGRAPH_RELEASE_TIER", "beta")
SLO_EVALUATION_WINDOW_SECONDS = int(os.environ.get("SLO_EVALUATION_WINDOW_SECONDS", "3600"))
SLO_API_AVAILABILITY_BETA = float(os.environ.get("SLO_API_AVAILABILITY_BETA", "0.995"))
SLO_API_AVAILABILITY_PRODUCTION = float(os.environ.get("SLO_API_AVAILABILITY_PRODUCTION", "0.999"))
SLO_RUN_SUCCESS_RATE = float(os.environ.get("SLO_RUN_SUCCESS_RATE", "0.99"))
SLO_RUN_P95_LATENCY_MS = int(os.environ.get("SLO_RUN_P95_LATENCY_MS", "60000"))
SLO_QUEUE_MAX_DEPTH = int(os.environ.get("SLO_QUEUE_MAX_DEPTH", "500"))
SLO_API_P95_LATENCY_MS = int(os.environ.get("SLO_API_P95_LATENCY_MS", "5000"))
SLO_WEBSOCKET_SEND_P95_LATENCY_MS = int(os.environ.get("SLO_WEBSOCKET_SEND_P95_LATENCY_MS", "2000"))
SLO_RUNTIME_INTENT_PROCESSING_P95_MS = int(
    os.environ.get("SLO_RUNTIME_INTENT_PROCESSING_P95_MS", "1000")
)
SLO_WEBSOCKET_DELIVERY_P95_MS = int(os.environ.get("SLO_WEBSOCKET_DELIVERY_P95_MS", "2000"))
SLO_APPROVAL_TO_RESUME_P95_MS = int(os.environ.get("SLO_APPROVAL_TO_RESUME_P95_MS", "5000"))
SLO_TASK_PROJECTION_LAG_P95_MS = int(os.environ.get("SLO_TASK_PROJECTION_LAG_P95_MS", "2000"))
SLO_DEAD_LETTER_VISIBILITY_SECONDS = int(os.environ.get("SLO_DEAD_LETTER_VISIBILITY_SECONDS", "30"))
SLO_SILENT_TASK_LOSS_MAX = int(os.environ.get("SLO_SILENT_TASK_LOSS_MAX", "0"))
SLO_RUNTIME_INTENT_BACKLOG_WARNING = int(os.environ.get("SLO_RUNTIME_INTENT_BACKLOG_WARNING", "50"))
SLO_DEAD_LETTER_SPIKE_THRESHOLD = int(os.environ.get("SLO_DEAD_LETTER_SPIKE_THRESHOLD", "1"))
SLO_CALLBACK_AUTH_FAILURE_THRESHOLD = int(
    os.environ.get("SLO_CALLBACK_AUTH_FAILURE_THRESHOLD", "0")
)
SLO_WS_SLOW_DISCONNECT_THRESHOLD = int(os.environ.get("SLO_WS_SLOW_DISCONNECT_THRESHOLD", "0"))
SLO_RATE_LIMIT_BREACH_THRESHOLD = int(os.environ.get("SLO_RATE_LIMIT_BREACH_THRESHOLD", "0"))
SLO_LLM_QUEUE_DEPTH_THRESHOLD = int(os.environ.get("SLO_LLM_QUEUE_DEPTH_THRESHOLD", "25"))
SLO_LLM_TIMEOUT_THRESHOLD = int(os.environ.get("SLO_LLM_TIMEOUT_THRESHOLD", "0"))
SLO_COST_ANOMALY_USD_PER_WINDOW = float(os.environ.get("SLO_COST_ANOMALY_USD_PER_WINDOW", "100.0"))

# Run WebSocket scaling guardrails.
RUN_WS_MAX_CONNECTIONS_PER_ORG = int(os.environ.get("RUN_WS_MAX_CONNECTIONS_PER_ORG", "250"))
RUN_WS_MAX_CONNECTIONS_PER_USER = int(os.environ.get("RUN_WS_MAX_CONNECTIONS_PER_USER", "20"))
RUN_WS_HEARTBEAT_INTERVAL_SECONDS = int(os.environ.get("RUN_WS_HEARTBEAT_INTERVAL_SECONDS", "12"))
RUN_WS_SEND_TIMEOUT_SECONDS = float(os.environ.get("RUN_WS_SEND_TIMEOUT_SECONDS", "2.0"))
RUN_WS_REPLAY_LIMIT = int(os.environ.get("RUN_WS_REPLAY_LIMIT", "200"))
ORG_WS_HEARTBEAT_INTERVAL_SECONDS = int(os.environ.get("ORG_WS_HEARTBEAT_INTERVAL_SECONDS", "12"))
ORG_WS_SEND_TIMEOUT_SECONDS = float(os.environ.get("ORG_WS_SEND_TIMEOUT_SECONDS", "2.0"))
ORG_WS_REPLAY_LIMIT = int(os.environ.get("ORG_WS_REPLAY_LIMIT", "500"))

# Backend watchdog thresholds. The Docker healthcheck consumes /health and restarts
# the process when this watchdog reports an unhealthy state.
BACKEND_WATCHDOG_ENABLED = _get_bool_env("BACKEND_WATCHDOG_ENABLED", True)
BACKEND_WATCHDOG_HEALTH_TIMEOUT_SECONDS = int(
    os.environ.get("BACKEND_WATCHDOG_HEALTH_TIMEOUT_SECONDS", "5")
)
BACKEND_WATCHDOG_REQUEST_TIMEOUT_MS = int(
    os.environ.get("BACKEND_WATCHDOG_REQUEST_TIMEOUT_MS", "5000")
)
BACKEND_WATCHDOG_REQUEST_TIMEOUTS_PER_MINUTE = int(
    os.environ.get("BACKEND_WATCHDOG_REQUEST_TIMEOUTS_PER_MINUTE", "10")
)
BACKEND_WATCHDOG_QUEUE_BACKLOG_THRESHOLD = int(
    os.environ.get("BACKEND_WATCHDOG_QUEUE_BACKLOG_THRESHOLD", str(SLO_QUEUE_MAX_DEPTH))
)
BACKEND_WATCHDOG_LOG_THROTTLE_SECONDS = int(
    os.environ.get("BACKEND_WATCHDOG_LOG_THROTTLE_SECONDS", "60")
)

# Stripe billing configuration
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
COMMERCE_STRIPE_WEBHOOK_SECRET = os.environ.get(
    "COMMERCE_STRIPE_WEBHOOK_SECRET",
    os.environ.get("LEGACY_STRIPE_WEBHOOK_SECRET", ""),
)
LEGACY_STRIPE_WEBHOOK_SECRET = COMMERCE_STRIPE_WEBHOOK_SECRET

# Engine Configuration (Go gRPC service)
ENGINE_HOST = os.environ.get("ENGINE_HOST", "localhost")
ENGINE_PORT = int(os.environ.get("ENGINE_PORT", "50051"))
ENGINE_INSTANCE_ID = os.environ.get("ENGINE_INSTANCE_ID", "")
ENGINE_TARGETS = os.environ.get("ENGINE_TARGETS", "")
ENGINE_CALLBACK_URL = os.environ.get(
    "ENGINE_CALLBACK_URL",
    "http://localhost:8000/api/runs/engine-events",
)
ENGINE_CALLBACK_SECRET = os.environ.get("ENGINE_CALLBACK_SECRET", "")
ENGINE_CALLBACK_MAX_SKEW_SECONDS = int(os.environ.get("ENGINE_CALLBACK_MAX_SKEW_SECONDS", "600"))
RUNTIME_TOOL_SECRET = os.environ.get("RUNTIME_TOOL_SECRET", "")
ENGINE_DIRECT_RUNTIME_WRITES_ENABLED = _get_bool_env("ENGINE_DIRECT_RUNTIME_WRITES_ENABLED", False)
RUN_LIVENESS_TIMEOUT_SECONDS = int(os.environ.get("RUN_LIVENESS_TIMEOUT_SECONDS", "60"))
RUN_ENGINE_STALLED_TIMEOUT_SECONDS = int(os.environ.get("RUN_ENGINE_STALLED_TIMEOUT_SECONDS", "60"))
RUN_LIVENESS_RECONCILE_INTERVAL_SECONDS = int(
    os.environ.get("RUN_LIVENESS_RECONCILE_INTERVAL_SECONDS", "15")
)
ENGINE_EVENT_STATE_MUTATION_ENABLED = _get_bool_env(
    "ENGINE_EVENT_STATE_MUTATION_ENABLED",
    False,
)
ENGINE_LEGACY_EVENT_CALLBACKS_ENABLED = _get_bool_env(
    "ENGINE_LEGACY_EVENT_CALLBACKS_ENABLED",
    False,
)
RUN_EVENT_STREAM_DEFAULT_LEVEL = os.environ.get("RUN_EVENT_STREAM_DEFAULT_LEVEL", "default")
RUN_EVENT_STREAM_SUMMARY_MAX_PENDING_CHUNKS = int(
    os.environ.get("RUN_EVENT_STREAM_SUMMARY_MAX_PENDING_CHUNKS", "24")
)
RUN_EVENT_STREAM_SUMMARY_MAX_ACTIVE_STREAMS_PER_RUN = int(
    os.environ.get("RUN_EVENT_STREAM_SUMMARY_MAX_ACTIVE_STREAMS_PER_RUN", "16")
)
RUN_STREAM_ALLOW_QUERY_ACCESS_TOKEN = _get_bool_env("RUN_STREAM_ALLOW_QUERY_ACCESS_TOKEN", False)
ALLOWED_LLM_PROVIDERS = [
    provider.strip().lower()
    for provider in os.environ.get(
        "ALLOWED_LLM_PROVIDERS", "openai,anthropic,google,openrouter,codex"
    ).split(",")
    if provider.strip()
]
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_API_BASE_URL = os.environ.get(
    "OPENAI_API_BASE_URL",
    os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
).rstrip("/")
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1-mini")
GEMINI_API_BASE_URL = os.environ.get(
    "GEMINI_API_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta",
).rstrip("/")
GEMINI_IMAGEN_MODEL = os.environ.get("GEMINI_IMAGEN_MODEL", "imagen-4.0-generate-001")
GEMINI_VEO_MODEL = os.environ.get("GEMINI_VEO_MODEL", "veo-3.1-generate-preview")
OPENROUTER_API_BASE_URL = os.environ.get(
    "OPENROUTER_API_BASE_URL",
    "https://openrouter.ai/api/v1",
).rstrip("/")
OPENROUTER_IMAGE_MODEL = os.environ.get(
    "OPENROUTER_IMAGE_MODEL",
    "black-forest-labs/flux.2-klein-4b",
)
OPENROUTER_HTTP_REFERER = os.environ.get("OPENROUTER_HTTP_REFERER", FRONTEND_URL)
OPENROUTER_APP_TITLE = os.environ.get("OPENROUTER_APP_TITLE", "ForgeGraph")
_MEDIA_GENERATION_DEFAULT_BASE = (
    BASE_DIR if BASE_DIR.parent == BASE_DIR.parent.parent else BASE_DIR.parent
)
MEDIA_GENERATION_ARTIFACT_ROOT = Path(
    os.environ.get(
        "MEDIA_GENERATION_ARTIFACT_ROOT",
        os.environ.get(
            "LEGACY_MEDIA_ARTIFACT_ROOT",
            str(_MEDIA_GENERATION_DEFAULT_BASE / "logs" / "media-generations"),
        ),
    )
)
LEGACY_MEDIA_ARTIFACT_ROOT = MEDIA_GENERATION_ARTIFACT_ROOT
FF_CURATED_MEMORY_ENABLED = _get_bool_env("FF_CURATED_MEMORY_ENABLED", True)
FF_CURATED_MEMORY_VECTOR_INDEXING = _get_bool_env("FF_CURATED_MEMORY_VECTOR_INDEXING", True)
FF_OS_SHELL = _get_bool_env("FF_OS_SHELL", True)
FF_AGENT_REGISTRY = _get_bool_env("FF_AGENT_REGISTRY", True)
FF_TASK_PROJECTIONS = _get_bool_env("FF_TASK_PROJECTIONS", True)
FF_DECISION_CENTER = _get_bool_env("FF_DECISION_CENTER", True)
FF_ACCOUNTING_AGGREGATES = _get_bool_env("FF_ACCOUNTING_AGGREGATES", True)
FF_PUBLIC_API_ALIASES = _get_bool_env("FF_PUBLIC_API_ALIASES", True)
ENABLE_LEGACY_OS_PROJECTION_SWEEP = _get_bool_env("ENABLE_LEGACY_OS_PROJECTION_SWEEP", False)
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
