"""Company operating-loop URL configuration."""

from django.urls import path

from adapters.api.company_ops.views import (
    AgencyHealthView,
    CompanyOperationObjectiveEvaluationView,
    CompanyOperationsLaunchView,
    CompanyOpportunitiesView,
    CompanyOpportunityStatusView,
    CompanyOpsOverviewView,
    CompanySignalQualifyView,
    CompanySignalsView,
    ProcurementDraftApprovalView,
    ProcurementDraftsView,
    PublicationDraftApprovalView,
    PublicationDraftsView,
)

urlpatterns = [
    path("overview", CompanyOpsOverviewView.as_view(), name="company-ops-overview"),
    path("agency-health", AgencyHealthView.as_view(), name="company-ops-agency-health"),
    path("signals", CompanySignalsView.as_view(), name="company-ops-signals"),
    path(
        "signals/<uuid:signal_id>/qualify",
        CompanySignalQualifyView.as_view(),
        name="company-ops-signal-qualify",
    ),
    path("opportunities", CompanyOpportunitiesView.as_view(), name="company-ops-opportunities"),
    path(
        "opportunities/<uuid:opportunity_id>/status",
        CompanyOpportunityStatusView.as_view(),
        name="company-ops-opportunity-status",
    ),
    path(
        "publication-drafts",
        PublicationDraftsView.as_view(),
        name="company-ops-publication-drafts",
    ),
    path(
        "publication-drafts/<uuid:draft_id>/request-approval",
        PublicationDraftApprovalView.as_view(),
        name="company-ops-publication-draft-approval",
    ),
    path(
        "procurement-drafts",
        ProcurementDraftsView.as_view(),
        name="company-ops-procurement-drafts",
    ),
    path(
        "procurement-drafts/<uuid:draft_id>/request-approval",
        ProcurementDraftApprovalView.as_view(),
        name="company-ops-procurement-draft-approval",
    ),
    path("operations", CompanyOperationsLaunchView.as_view(), name="company-ops-operations"),
    path(
        "operations/<uuid:operation_id>/objective-evaluation",
        CompanyOperationObjectiveEvaluationView.as_view(),
        name="company-ops-operation-objective-evaluation",
    ),
]
