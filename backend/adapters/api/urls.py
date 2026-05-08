"""
API URL configuration.

Clean Architecture: Interface Adapters layer.
"""

from django.urls import include, path

from adapters.api.auth.views import ws_ticket_view
from adapters.api.graphs.views import GraphVersionCreateView
from adapters.api.organizations.views import (
    OrganizationCurrentView,
    OrganizationListCreateView,
    OrganizationMeView,
)
from adapters.api.runs.views import RunListView

urlpatterns = [
    path("ws-ticket", ws_ticket_view, name="ws-ticket"),
    path("auth/", include("adapters.api.auth.urls")),
    path("system-state/", include("adapters.api.system_state.urls")),
    path("agents/", include("adapters.api.agents.urls")),
    path("tasks/", include("adapters.api.tasks.urls")),
    path("decisions/", include("adapters.api.decisions.urls")),
    path("accounting/", include("adapters.api.accounting.urls")),
    path("workflows/", include("adapters.api.workflows.urls")),
    path("executions/", include("adapters.api.executions.urls")),
    path("engine/", include("adapters.api.engine.urls")),
    path("credentials/", include("adapters.api.credentials.urls")),
    path("integrations/", include("adapters.api.integrations.urls")),
    path("interaction/", include("adapters.api.interaction.urls")),
    path("archive/", include("adapters.api.archive.urls")),
    path("company-ops/", include("adapters.api.company_ops.urls")),
    path("inventory/", include("adapters.api.inventory.urls")),
    path("commerce/", include("adapters.api.commerce.urls")),
    path("storefront/", include("adapters.api.storefront.urls")),
    path("learning/", include("adapters.api.learning.urls")),
    path("orgs", OrganizationListCreateView.as_view(), name="org-list-create-top-level"),
    path("orgs/current", OrganizationCurrentView.as_view(), name="org-current-top-level"),
    path("orgs/me", OrganizationMeView.as_view(), name="org-me-top-level"),
    path("orgs/", include("adapters.api.organizations.urls")),
    path("graphs/", include("adapters.api.graphs.urls")),
    path("graph-versions", GraphVersionCreateView.as_view(), name="graph-version-create-top-level"),
    path("health/", include("adapters.api.health.urls")),
    path("analytics/", include("adapters.api.analytics.urls")),
    path("billing/", include("adapters.api.billing.urls")),
    path("memory/", include("adapters.api.memory.urls")),
    path("reports/", include("adapters.api.reports.urls")),
    path("prompts/", include("adapters.api.prompts.urls")),
    path("templates/", include("adapters.api.templates.urls")),
    path("marketplace/", include("adapters.api.marketplace.urls")),
    path("runtime-tools/", include("adapters.api.runtime_tools.urls")),
    path("onboarding/", include("adapters.api.onboarding.urls")),
    path("metrics/", include("adapters.api.metrics.urls")),
    path("operator/", include("adapters.api.operator.urls")),
    path("ops/", include("adapters.api.ops.urls")),
    path("runs", RunListView.as_view(), name="run-list-create-top-level"),
    path("runs/", include("adapters.api.runs.urls")),
    path("approvals/", include("adapters.api.approvals.urls")),
    path("audit-logs/", include("adapters.api.audit_logs.urls")),
    path("policies/", include("adapters.api.policies.urls")),
    path("retention/", include("adapters.api.retention.urls")),
    path("scim/", include("adapters.api.scim.urls")),
]
