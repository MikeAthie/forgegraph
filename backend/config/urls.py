"""
URL configuration for ForgeGraph backend.

Clean Architecture: This belongs to the Frameworks & Drivers layer.
"""

from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)


def health_check(request):
    """Health check endpoint."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health_check, name="health"),
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
