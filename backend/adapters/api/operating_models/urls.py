"""URL configuration for generic operating model pack APIs."""

from django.urls import path

from adapters.api.operating_models.views import (
    ArtifactCanonicalRevisionView,
    ArtifactLineageView,
    ArtifactRevisionCreateView,
    AssertionsView,
    CompanyOperatingModelView,
    CompanyPackInstallView,
    CompanyPackRemoveView,
    CompanyPackUpgradeView,
    CompanyProgramListCreateView,
    EvaluationDetailView,
    EvaluationRunView,
    MetricSnapshotListCreateView,
    OperatingModelPackCompileView,
    OperatingModelPackDetailView,
    OperatingModelPackListView,
    PackToolExecutionView,
    PeriodicReviewListCreateView,
    PeriodicReviewRunView,
    PolicyEvaluationView,
    ProgramDetailView,
    ProgramStageAdvanceView,
    ProgramStageOperationLaunchView,
    ProgramStageOutputGenerationView,
    ProgramValidationPacketView,
    ReportRunListView,
    ReworkPlanCreateView,
    ReworkPlanExecuteView,
    StateProjectionListView,
    ValidationDecisionsView,
    WorkArtifactDetailView,
    WorkArtifactsView,
)

urlpatterns = [
    path(
        "operating-model-packs",
        OperatingModelPackListView.as_view(),
        name="operating-model-pack-list",
    ),
    path(
        "operating-model-packs/<str:pack_id>",
        OperatingModelPackDetailView.as_view(),
        name="operating-model-pack-detail",
    ),
    path(
        "operating-model-packs/<str:pack_id>/compile",
        OperatingModelPackCompileView.as_view(),
        name="operating-model-pack-compile",
    ),
    path(
        "companies/<uuid:company_id>/operating-model",
        CompanyOperatingModelView.as_view(),
        name="company-operating-model",
    ),
    path(
        "companies/<uuid:company_id>/operating-model/packs/<str:pack_id>/install",
        CompanyPackInstallView.as_view(),
        name="company-operating-model-pack-install",
    ),
    path(
        "companies/<uuid:company_id>/operating-model/packs/<str:pack_id>/upgrade",
        CompanyPackUpgradeView.as_view(),
        name="company-operating-model-pack-upgrade",
    ),
    path(
        "companies/<uuid:company_id>/operating-model/packs/<str:pack_id>",
        CompanyPackRemoveView.as_view(),
        name="company-operating-model-pack-remove",
    ),
    path(
        "companies/<uuid:company_id>/programs",
        CompanyProgramListCreateView.as_view(),
        name="company-program-list-create",
    ),
    path("programs/<uuid:program_id>", ProgramDetailView.as_view(), name="program-detail"),
    path(
        "programs/<uuid:program_id>/stages/<str:stage_id>/advance",
        ProgramStageAdvanceView.as_view(),
        name="program-stage-advance",
    ),
    path(
        "programs/<uuid:program_id>/stages/<str:stage_id>/operations/launch",
        ProgramStageOperationLaunchView.as_view(),
        name="program-stage-operation-launch",
    ),
    path(
        "programs/<uuid:program_id>/stages/<str:stage_id>/outputs/generate",
        ProgramStageOutputGenerationView.as_view(),
        name="program-stage-output-generate",
    ),
    path(
        "programs/<uuid:program_id>/validation-packet",
        ProgramValidationPacketView.as_view(),
        name="program-validation-packet",
    ),
    path("assertions", AssertionsView.as_view(), name="assertion-list-create"),
    path(
        "validation-decisions",
        ValidationDecisionsView.as_view(),
        name="validation-decision-create",
    ),
    path("work-artifacts", WorkArtifactsView.as_view(), name="work-artifact-list-create"),
    path(
        "work-artifacts/<uuid:artifact_id>",
        WorkArtifactDetailView.as_view(),
        name="work-artifact-detail",
    ),
    path(
        "work-artifacts/<uuid:artifact_id>/revisions",
        ArtifactRevisionCreateView.as_view(),
        name="work-artifact-revision-create",
    ),
    path(
        "work-artifacts/<uuid:artifact_id>/lineage",
        ArtifactLineageView.as_view(),
        name="work-artifact-lineage",
    ),
    path(
        "work-artifacts/<uuid:artifact_id>/canonical-revision",
        ArtifactCanonicalRevisionView.as_view(),
        name="work-artifact-canonical-revision",
    ),
    path("evaluations/run", EvaluationRunView.as_view(), name="evaluation-run"),
    path(
        "evaluations/<uuid:evaluation_id>",
        EvaluationDetailView.as_view(),
        name="evaluation-detail",
    ),
    path(
        "periodic-reviews",
        PeriodicReviewListCreateView.as_view(),
        name="periodic-review-list-create",
    ),
    path(
        "periodic-reviews/<uuid:review_id>/run",
        PeriodicReviewRunView.as_view(),
        name="periodic-review-run",
    ),
    path(
        "metric-snapshots",
        MetricSnapshotListCreateView.as_view(),
        name="metric-snapshot-list-create",
    ),
    path("report-runs", ReportRunListView.as_view(), name="report-run-list"),
    path("policy-evaluations", PolicyEvaluationView.as_view(), name="policy-evaluation-create"),
    path("tool-executions", PackToolExecutionView.as_view(), name="pack-tool-execution-create"),
    path("rework-plans", ReworkPlanCreateView.as_view(), name="rework-plan-create"),
    path(
        "rework-plans/<uuid:plan_id>/execute",
        ReworkPlanExecuteView.as_view(),
        name="rework-plan-execute",
    ),
    path("state-projections", StateProjectionListView.as_view(), name="state-projection-list"),
]
