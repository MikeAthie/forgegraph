"""
URL configuration for ForgeGraph backend.

Clean Architecture: This belongs to the Frameworks & Drivers layer.
"""

from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest, JsonResponse  # Added HttpRequest
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from adapters.api.health.readiness import build_readiness_payload


def health_check(request: HttpRequest) -> JsonResponse:
    """Health check endpoint."""
    return JsonResponse({"status": "ok"})


def readiness_check(request: HttpRequest) -> JsonResponse:
    """Readiness check endpoint."""
    payload, status_code = build_readiness_payload()
    return JsonResponse(payload, status=status_code)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health_check, name="health"),
    path("ready", readiness_check, name="ready"),
    path("api/", include("adapters.api.urls")),
    # Optional versioned API namespace for future compatibility.
    path("api/v1/", include("adapters.api.urls")),
]

# API Documentation (only in DEBUG mode or explicitly enabled)
if settings.DEBUG or getattr(settings, "ENABLE_API_DOCS", False):
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
        path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    ]
