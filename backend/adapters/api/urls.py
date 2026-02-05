"""
API URL configuration.

Clean Architecture: Interface Adapters layer.
"""

from django.urls import include, path

urlpatterns = [
    path("auth/", include("adapters.api.auth.urls")),
    path("engine/", include("adapters.api.engine.urls")),
    path("credentials/", include("adapters.api.credentials.urls")),
    path("orgs/", include("adapters.api.organizations.urls")),
    path("graphs/", include("adapters.api.graphs.urls")),
    path("health/", include("adapters.api.health.urls")),
    path("analytics/", include("adapters.api.analytics.urls")),
    path("billing/", include("adapters.api.billing.urls")),
    path("memory/", include("adapters.api.memory.urls")),
    path("prompts/", include("adapters.api.prompts.urls")),
    path("templates/", include("adapters.api.templates.urls")),
    path("marketplace/", include("adapters.api.marketplace.urls")),
    path("onboarding/", include("adapters.api.onboarding.urls")),
    path("metrics/", include("adapters.api.metrics.urls")),
    path("runs/", include("adapters.api.runs.urls")),
    path("approvals/", include("adapters.api.approvals.urls")),
    path("audit-logs/", include("adapters.api.audit_logs.urls")),
    path("policies/", include("adapters.api.policies.urls")),
    path("retention/", include("adapters.api.retention.urls")),
    path("scim/", include("adapters.api.scim.urls")),
]
