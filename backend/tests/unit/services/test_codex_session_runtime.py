from __future__ import annotations

from typing import Any

import pytest
from django.test import override_settings

from application.services.codex_session_runtime import (
    CodexSessionRunResult,
    CodexSessionRuntimeDisabled,
    build_codex_deliverable_for_stage,
    run_codex_session_prompt,
)
from application.services.department_pipeline import (
    complete_stage,
    create_pipeline_for_engagement,
    stage_state_for_engagement,
    start_stage,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    AssetVersion,
    DepartmentRegistry,
    Graph,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    TaskRoutingRecord,
    User,
)

pytestmark = pytest.mark.django_db

_STAGE_SLUGS = [
    "strategy_research",
    "brand_content",
    "channel_execution",
    "crm_lifecycle",
    "analytics_performance",
    "qa_compliance",
    "client_approval_ops",
]


def _organization(user: User):
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    return organization


def _engagement(user: User) -> ServiceEngagement:
    organization = _organization(user)
    company = Graph.objects.create(
        owner=user,
        organization=organization,
        name="Legacy",
        description="Marketing client.",
    )
    catalog = ServiceCatalogItem.objects.create(
        organization=organization,
        slug="codex-session-test",
        title="Codex Session Test",
        status="active",
        visibility="organization",
        created_by=user,
    )
    return ServiceEngagement.objects.create(
        organization=organization,
        company=company,
        catalog_item=catalog,
        status="in_progress",
        customer_status="working",
        public_summary="Create a strategy deliverable with a local Codex runtime.",
        requested_by=user,
    )


def _departments(user: User) -> None:
    organization = _organization(user)
    for slug in _STAGE_SLUGS:
        DepartmentRegistry.objects.create(
            organization=organization,
            slug=slug,
            name=slug.replace("_", " ").title(),
            department_type="atlas_agency",
            service_tags_json=["atlas", "digital_marketing_pro"],
        )


def test_codex_session_runtime_is_feature_flagged():
    def unused_runner(*_args: Any, **_kwargs: Any) -> CodexSessionRunResult:
        raise AssertionError("The disabled runtime must not invoke its runner.")

    with override_settings(ENABLE_CODEX_SESSION_RUNTIME=False):
        with pytest.raises(CodexSessionRuntimeDisabled):
            run_codex_session_prompt(prompt="Draft strategy", runner=unused_runner)


def test_codex_session_runtime_uses_fake_runner_without_leaking_auth():
    calls: list[list[str]] = []

    def fake_runner(command, **_kwargs):
        calls.append(command)
        return CodexSessionRunResult(
            status="succeeded",
            output_text="## Strategy\nUse Optical Noir as the weekend launch anchor.",
            error_text="",
            command_summary="codex exec <prompt>",
            duration_ms=12,
            exit_code=0,
        )

    with override_settings(
        ENABLE_CODEX_SESSION_RUNTIME=True, CODEX_SESSION_WORKDIR="/tmp/fg-codex"
    ):
        result = run_codex_session_prompt(prompt="Draft strategy", runner=fake_runner)

    assert result.status == "succeeded"
    assert "Optical Noir" in result.output_text
    assert calls[0][0:2] == ["codex", "exec"]
    assert "auth.json" not in result.command_summary
    assert "OPENAI_API_KEY" not in result.command_summary


def test_codex_output_becomes_stage_owned_deliverable(user):
    _departments(user)
    engagement = _engagement(user)
    create_pipeline_for_engagement(engagement, created_by=user)
    strategy = stage_state_for_engagement(engagement, "strategy_research")
    start_stage(strategy, actor=user)

    def fake_runtime(**_kwargs):
        return CodexSessionRunResult(
            status="succeeded",
            output_text="# Legacy Strategy\nLaunch Optical Noir with Spanish-first luxury positioning.",
            error_text="",
            command_summary="codex exec <prompt>",
            duration_ms=8,
            exit_code=0,
        )

    with override_settings(ENABLE_CODEX_SESSION_RUNTIME=True):
        deliverable = build_codex_deliverable_for_stage(
            engagement=engagement,
            stage_state=strategy,
            user=user,
            deliverable_type="codex_strategy_brief",
            title="Codex Strategy Brief",
            prompt="Create a concise Legacy launch strategy.",
            runtime=fake_runtime,
        )

    complete_stage(strategy, actor=user)
    deliverable.refresh_from_db()
    assert deliverable.status == "ready"
    department = deliverable.department
    assert department is not None
    assert department.slug == "strategy_research"
    assert deliverable.artifact is not None
    assert deliverable.metadata_json["source"] == "codex_session_runtime"
    assert deliverable.metadata_json["codex_session"]["status"] == "succeeded"
    lineage = deliverable.metadata_json["department_pipeline"]
    assert lineage["created_via_department_pipeline"] is True
    assert lineage["stage_id"] == "strategy_research"
    routing = deliverable.metadata_json["task_routing"]
    assert routing["runtime_provider"] == "codex_session_runtime"
    assert routing["stage_id"] == "strategy_research"
    assert TaskRoutingRecord.objects.filter(id=routing["routing_record_id"]).exists()
    version = AssetVersion.objects.get(id=deliverable.metadata_json["asset_version_id"])
    assert (
        version.provenance_json["task_routing"]["routing_record_id"] == routing["routing_record_id"]
    )
    assert (
        ServiceDeliverable.objects.filter(
            engagement=engagement, deliverable_type="codex_strategy_brief"
        ).count()
        == 1
    )
