"""API-only deprecation headers for legacy builder-first surfaces.

These headers are for integrators and observability. Primary UX must translate
these routes through the product terminology boundary instead of showing them to
users.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse


class ApiDeprecationMiddleware:
    """Annotate legacy API routes while compatibility aliases are active."""

    LEGACY_PREFIXES = ("/api/graphs", "/api/runs", "/api/approvals")
    SUNSET_AT = "2026-12-31T00:00:00Z"
    DOC_LINK = '</docs/product/canonical-ontology.md>; rel="deprecation"'

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if request.path.startswith(self.LEGACY_PREFIXES):
            response["Deprecation"] = "true"
            response["Sunset"] = self.SUNSET_AT
            response["Link"] = self.DOC_LINK
        return response
