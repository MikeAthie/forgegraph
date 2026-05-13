from __future__ import annotations

from typing import cast

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from domain.services.graph_validator import GraphValidator
from infrastructure.orm.models import (
    AssertionRecord,
    Asset,
    AssetDependency,
    CompanyAccessPolicy,
    CompanyAssignment,
    CompanyOperatingModelInstallation,
    CompanySignal,
    EvaluationProfile,
    EvaluationRun,
    Graph,
    GraphVersion,
    MetricSnapshot,
    OperatingModelPackRelease,
    OrganizationMembership,
    PackInstallationConfigRevision,
    PackNamespaceClaim,
    PeriodicReviewDefinition,
    PolicyEvaluation,
    PolicyPack,
    ReportRun,
    ReworkPlan,
    Run,
    StateProjection,
    ToolExecution,
    User,
    ValidationDecision,
)

pytestmark = pytest.mark.django_db


def _company(user, name: str = "Acme Agency") -> Graph:
    return cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=user.default_organization,
            name=name,
            description="Run a pack-driven company operating model.",
        ),
    )


def test_no_marketing_api_namespace_is_registered():
    paths: set[str] = set()

    def walk(patterns: list[URLPattern | URLResolver], prefix: str = "") -> None:
        for pattern in patterns:
            route_part = str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns, prefix + route_part)
                continue
            paths.add(("/" + prefix + route_part).replace("//", "/"))

    walk(get_resolver().url_patterns)

    assert not [path for path in paths if path.startswith("/api/marketing")]


def test_no_marketing_core_models_exist():
    from infrastructure.orm import models as orm_models

    assert not [name for name in dir(orm_models) if name.startswith("Marketing")]


def test_pack_list_and_compile_are_generic_and_read_only(authenticated_client):
    before = {
        "packs": OperatingModelPackRelease.objects.count(),
        "companies": Graph.objects.count(),
        "versions": GraphVersion.objects.count(),
    }

    listed = authenticated_client.get("/api/operating-model-packs")
    compiled = authenticated_client.post(
        "/api/operating-model-packs/digital_marketing_pro.v1/compile",
        data={"company_name": "Acme", "objective": "Run DMP quality agency operations."},
        format="json",
    )
    legal = authenticated_client.post(
        "/api/operating-model-packs/legal_ops_demo.v1/compile",
        data={"company_name": "Legal Co", "objective": "Run legal operations."},
        format="json",
    )

    assert listed.status_code == 200
    assert "digital_marketing_pro.v1" in {
        item["pack_id"] for item in listed.json()["data"]["packs"]
    }
    assert compiled.status_code == 200
    graph_json = compiled.json()["data"]["graph_json"]
    assert graph_json["metadata"]["operating_model_pack"]["pack_id"] == "digital_marketing_pro.v1"
    assert any(
        item["id"] == "dmp.brand_intake" for item in compiled.json()["data"]["operation_templates"]
    )
    assert any(item["id"] == "growth_engineering" for item in compiled.json()["data"]["modules"])
    assert any(
        item["id"] == "dmp.cms_draft_publish" for item in compiled.json()["data"]["tool_packages"]
    )
    pack_files = compiled.json()["data"]["pack"]["files"]
    assert "service_model" in pack_files
    assert any(
        item["id"] == "atlas_brand_strategy_diagnosis"
        for item in pack_files["service_model"]["service_sections"]
    )
    assert GraphValidator().validate(graph_json, strict=True) == []
    assert legal.status_code == 200
    assert legal.json()["data"]["pack"]["pack_id"] == "legal_ops_demo.v1"
    assert OperatingModelPackRelease.objects.count() == before["packs"]
    assert Graph.objects.count() == before["companies"]
    assert GraphVersion.objects.count() == before["versions"]


def test_install_pack_requires_idempotency(authenticated_client, user):
    company = _company(user)

    response = authenticated_client.post(
        f"/api/companies/{company.id}/operating-model/packs/digital_marketing_pro.v1/install",
        data={},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert CompanyOperatingModelInstallation.objects.count() == 0


def test_install_pack_creates_company_scoped_generic_records_idempotently(
    authenticated_client,
    user,
):
    company = _company(user)
    path = f"/api/companies/{company.id}/operating-model/packs/digital_marketing_pro.v1/install"

    first = authenticated_client.post(
        path,
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="install-dmp-pack",
    )
    second = authenticated_client.post(
        path,
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="install-dmp-pack",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["installation"]["pack_id"] == "digital_marketing_pro.v1"
    assert second.json()["data"]["installation"]["id"] == first.json()["data"]["installation"]["id"]
    assert CompanyOperatingModelInstallation.objects.filter(company=company).count() == 1
    assert OperatingModelPackRelease.objects.filter(pack_id="digital_marketing_pro.v1").exists()
    assert GraphVersion.objects.filter(graph=company).count() == 1
    assert EvaluationProfile.objects.filter(company=company, profile_id="dmp.quick_check").exists()
    assert EvaluationProfile.objects.filter(
        company=company,
        profile_id="atlas_monthly_kpi_scorecard.v1",
    ).exists()
    assert PolicyPack.objects.filter(
        company=company, policy_pack_id="dmp.side_effect_governance"
    ).exists()


def test_generic_company_pack_api_installs_details_objects_updates_and_archives(
    authenticated_client,
    user,
):
    company = _company(user)

    installed = authenticated_client.post(
        f"/api/companies/{company.id}/packs/install",
        data={
            "pack_id": "digital_marketing_pro.v1",
            "role": "primary",
            "config": {"skip_graph_version": True, "selected_services": ["SEO"]},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="generic-install-dmp",
    )

    assert installed.status_code == 201
    installation = installed.json()["data"]["installation"]
    assert installation["pack_id"] == "digital_marketing_pro.v1"
    assert installation["role"] == "primary"
    assert installation["namespace"] == "digital_marketing_pro.v1"
    assert installation["config_revision_count"] == 1
    assert installation["namespace_claim_count"] > 0
    assert (
        PackInstallationConfigRevision.objects.filter(installation_id=installation["id"]).count()
        == 1
    )
    assert PackNamespaceClaim.objects.filter(
        company=company,
        status="active",
        namespaced_id__startswith="digital_marketing_pro.v1.",
    ).exists()

    listed = authenticated_client.get(f"/api/companies/{company.id}/packs")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["data"]["packs"]] == [installation["id"]]

    detail = authenticated_client.get(f"/api/companies/{company.id}/packs/{installation['id']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["installation"]["config_revisions"][0]["version"] == 1

    objects = authenticated_client.get(
        f"/api/companies/{company.id}/packs/{installation['id']}/objects"
    )
    assert objects.status_code == 200
    assert any(
        item["namespaced_id"] == "digital_marketing_pro.v1.dmp.engagement"
        for item in objects.json()["data"]["objects"]
    )

    patched = authenticated_client.patch(
        f"/api/companies/{company.id}/packs/{installation['id']}",
        data={"config": {"selected_services": ["SEO", "Reporting"]}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="generic-update-dmp",
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["installation"]["config_revision_count"] == 2

    archived = authenticated_client.post(
        f"/api/companies/{company.id}/packs/{installation['id']}/archive",
        data={"reason": "test archive"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="generic-archive-dmp",
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["installation"]["status"] == "archived"
    assert not PackNamespaceClaim.objects.filter(
        company=company,
        status="active",
        installation_id=installation["id"],
    ).exists()


def test_generic_company_pack_api_enforces_single_active_primary_pack(
    authenticated_client,
    user,
):
    company = _company(user)

    first = authenticated_client.post(
        f"/api/companies/{company.id}/packs/install",
        data={
            "pack_id": "digital_marketing_pro.v1",
            "role": "primary",
            "config": {"skip_graph_version": True},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="primary-dmp",
    )
    conflicting = authenticated_client.post(
        f"/api/companies/{company.id}/packs/install",
        data={
            "pack_id": "legal_ops_demo.v1",
            "role": "primary",
            "config": {"skip_graph_version": True},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="primary-legal-conflict",
    )
    addon = authenticated_client.post(
        f"/api/companies/{company.id}/packs/install",
        data={
            "pack_id": "legal_ops_demo.v1",
            "role": "addon",
            "config": {"skip_graph_version": True},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="addon-legal",
    )

    assert first.status_code == 201
    assert conflicting.status_code == 409
    assert conflicting.json()["error"]["code"] == "PRIMARY_PACK_CONFLICT"
    assert addon.status_code == 201
    assert addon.json()["data"]["installation"]["role"] == "addon"


def test_generic_company_pack_api_blocks_namespace_collision(authenticated_client, user):
    company = _company(user)
    release = OperatingModelPackRelease.objects.create(
        pack_id="conflict_pack.v1",
        base_pack_id="conflict_pack",
        version="0.1.0",
        display_name="Conflict Pack",
        checksum="conflict",
        manifest_json={},
        files_json={},
    )
    installation = CompanyOperatingModelInstallation.objects.create(
        organization=company.organization,
        company=company,
        pack_release=release,
        pack_id="conflict_pack.v1",
        base_pack_id="conflict_pack",
        role="addon",
        namespace="conflict_pack.v1",
        status="active",
        installed_by=user,
    )
    PackNamespaceClaim.objects.create(
        organization=company.organization,
        company=company,
        installation=installation,
        pack_id="conflict_pack.v1",
        object_type="program_template",
        object_id="dmp.engagement",
        namespaced_id="digital_marketing_pro.v1.dmp.engagement",
        status="active",
    )

    response = authenticated_client.post(
        f"/api/companies/{company.id}/packs/install",
        data={
            "pack_id": "digital_marketing_pro.v1",
            "role": "primary",
            "config": {"skip_graph_version": True},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="namespace-conflict",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PACK_NAMESPACE_CONFLICT"
    assert not CompanyOperatingModelInstallation.objects.filter(
        company=company,
        pack_id="digital_marketing_pro.v1",
    ).exists()


def test_company_pack_api_respects_restricted_company_assignments(api_client, user):
    allowed_company = _company(user, name="Assigned Company")
    restricted_company = _company(user, name="Restricted Company")
    member = User.objects.create_user(email="company-member@example.com", password="pw123456")
    member.default_organization = user.default_organization
    member.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(
        user=member,
        organization=user.default_organization,
        role="member",
    )
    CompanyAccessPolicy.objects.create(
        organization=user.default_organization,
        company=allowed_company,
        assignment_required=True,
        org_admin_access_enabled=False,
    )
    CompanyAccessPolicy.objects.create(
        organization=user.default_organization,
        company=restricted_company,
        assignment_required=True,
        org_admin_access_enabled=False,
    )
    CompanyAssignment.objects.create(
        organization=user.default_organization,
        company=allowed_company,
        user=member,
        role="admin",
        created_by=user,
    )
    api_client.force_authenticate(user=member)

    allowed = api_client.get(f"/api/companies/{allowed_company.id}/packs")
    restricted = api_client.get(f"/api/companies/{restricted_company.id}/packs")

    assert allowed.status_code == 200
    assert restricted.status_code == 404


def test_dmp_pack_flow_uses_generic_program_assertion_artifact_evaluation_policy_and_rework(
    authenticated_client,
    user,
):
    company = _company(user)
    authenticated_client.post(
        f"/api/companies/{company.id}/operating-model/packs/digital_marketing_pro.v1/install",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="install-dmp-flow",
    )

    program_response = authenticated_client.post(
        f"/api/companies/{company.id}/programs",
        data={"template_id": "dmp.engagement", "title": "Q2 Growth Engagement"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="create-program-flow",
    )
    assert program_response.status_code == 201
    program = program_response.json()["data"]["program"]
    assert program["display_label"] == "Engagement"
    assert len(program["stages"]) == 12
    assert program["stages"][0]["status"] == "in_progress"
    assert "dmp.brand_intake" in program["stages"][0]["operation_template_ids"]

    stage_response = authenticated_client.post(
        f"/api/programs/{program['id']}/stages/stage_01_client_inputs/advance",
        data={"status": "awaiting_validation"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="stage-awaiting-validation-flow",
    )
    assert stage_response.status_code == 200
    assert stage_response.json()["data"]["program"]["stages"][0]["status"] == "awaiting_validation"

    invalid_stage_response = authenticated_client.post(
        f"/api/programs/{program['id']}/stages/stage_01_client_inputs/advance",
        data={"status": "not_started"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="stage-invalid-flow",
    )
    assert invalid_stage_response.status_code == 409

    operation_response = authenticated_client.post(
        f"/api/programs/{program['id']}/stages/stage_01_client_inputs/operations/launch",
        data={"operation_template_id": "dmp.brand_intake"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="launch-stage-operation-flow",
    )
    assert operation_response.status_code == 201
    operation = operation_response.json()["data"]["operation"]
    assert operation["operation_label"] == "Brand Intake"
    assert Run.objects.filter(id=operation["id"], graph_version__graph=company).exists()

    assertion_response = authenticated_client.post(
        "/api/assertions",
        data={
            "company_id": str(company.id),
            "program_id": program["id"],
            "kind": "OPINION",
            "pack_label": "Opinion",
            "category": "positioning",
            "statement": "We are the premium option in the category.",
            "source": "client intake",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="create-assertion-flow",
    )
    assert assertion_response.status_code == 201
    assertion = assertion_response.json()["data"]["assertion"]
    assert AssertionRecord.objects.filter(company=company, kind="OPINION").count() == 1

    assertion_validation_response = authenticated_client.post(
        "/api/validation-decisions",
        data={
            "company_id": str(company.id),
            "program_id": program["id"],
            "assertion_id": assertion["id"],
            "decision": "ACCEPT",
            "category": "positioning",
            "rationale": "Stakeholder validated this positioning opinion.",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="assertion-validation-flow",
    )
    assert assertion_validation_response.status_code == 201
    assert AssertionRecord.objects.get(id=assertion["id"]).validation_status == "validated"

    artifact_response = authenticated_client.post(
        "/api/work-artifacts",
        data={
            "company_id": str(company.id),
            "program_id": program["id"],
            "title": "Brand Strategy",
            "artifact_type": "brand_strategy",
            "content": {"summary": "v1 unbiased market view"},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="create-artifact-flow",
    )
    assert artifact_response.status_code == 201
    artifact = artifact_response.json()["data"]["artifact"]
    revision = artifact_response.json()["data"]["revision"]

    v2_response = authenticated_client.post(
        f"/api/work-artifacts/{artifact['id']}/revisions",
        data={
            "content": {"summary": "v2 client validated view"},
            "parent_revision_id": revision["id"],
            "label": "v2",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="create-artifact-v2-flow",
    )
    assert v2_response.status_code == 201
    assert Asset.objects.filter(company=company).count() == 1
    assert AssetDependency.objects.filter(company=company).count() == 1

    validation_response = authenticated_client.post(
        "/api/validation-decisions",
        data={
            "company_id": str(company.id),
            "program_id": program["id"],
            "asset_id": artifact["id"],
            "decision": "EDIT",
            "category": "positioning",
            "rationale": "Client corrected positioning.",
            "proposed_change": {
                "content": {"summary": "v3 corrected positioning view"},
                "label": "v3",
                "stage_id": "stage_06_selective_v2_reruns",
            },
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="validation-flow",
    )
    assert validation_response.status_code == 201
    assert ValidationDecision.objects.filter(company=company).count() == 2

    rework_response = authenticated_client.post(
        "/api/rework-plans",
        data={
            "company_id": str(company.id),
            "program_id": program["id"],
            "validation_decision_ids": [
                validation_response.json()["data"]["validation_decision"]["id"]
            ],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="rework-flow",
    )
    assert rework_response.status_code == 201
    plan = rework_response.json()["data"]["rework_plan"]
    assert ReworkPlan.objects.filter(company=company).count() == 1
    assert "stage_06_selective_v2_reruns" in plan["impact"]["impacted_stages"]

    execute_rework_response = authenticated_client.post(
        f"/api/rework-plans/{plan['id']}/execute",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="execute-rework-flow",
    )
    assert execute_rework_response.status_code == 200
    assert Asset.objects.get(id=artifact["id"]).versions.count() == 3

    packet_response = authenticated_client.get(f"/api/programs/{program['id']}/validation-packet")
    assert packet_response.status_code == 200
    packet = packet_response.json()["data"]["validation_packet"]
    assert packet["assertions"]
    assert packet["artifacts"]

    eval_response = authenticated_client.post(
        "/api/evaluations/run",
        data={
            "company_id": str(company.id),
            "profile_id": "dmp.compliance_check",
            "content": "Guaranteed 100% results from this placeholder campaign.",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="eval-flow",
    )
    assert eval_response.status_code == 201
    assert eval_response.json()["data"]["evaluation"]["status"] == "BLOCK"
    assert EvaluationRun.objects.filter(company=company, status="BLOCK").count() == 1

    policy_response = authenticated_client.post(
        "/api/policy-evaluations",
        data={
            "company_id": str(company.id),
            "action_type": "launch_ads",
            "inputs": {"budget": 6000, "external_write_side_effect": True},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="policy-flow",
    )
    assert policy_response.status_code == 201
    policy = policy_response.json()["data"]["policy_evaluation"]
    assert policy["risk_level"] == "HIGH"
    assert policy["status"] == "approval_required"
    assert PolicyEvaluation.objects.filter(company=company).count() == 1

    tool_response = authenticated_client.post(
        "/api/tool-executions",
        data={
            "company_id": str(company.id),
            "operation_id": operation["id"],
            "tool_id": "cms_connector",
            "dry_run": True,
            "inputs": {"budget": 0},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="tool-dry-run-flow",
    )
    assert tool_response.status_code == 201
    assert tool_response.json()["data"]["tool_execution"]["dry_run"] is True
    assert ToolExecution.objects.filter(run_id=operation["id"], tool_name="cms_connector").exists()

    projections = authenticated_client.get(
        "/api/state-projections",
        data={
            "company_id": str(company.id),
            "program_id": program["id"],
            "projection_type": "currently_true_state",
        },
    )
    assert projections.status_code == 200
    assert StateProjection.objects.filter(company=company).exists()


def test_dmp_parts_7_to_12_generate_pack_driven_generic_outputs(
    authenticated_client,
    user,
):
    company = _company(user, "Parts 7-12 Co")
    authenticated_client.post(
        f"/api/companies/{company.id}/operating-model/packs/digital_marketing_pro.v1/install",
        data={"config": {"selected_services": ["Campaign planning", "Analytics reporting"]}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="install-dmp-parts-7-12",
    )
    program_response = authenticated_client.post(
        f"/api/companies/{company.id}/programs",
        data={"template_id": "dmp.engagement", "title": "Parts 7-12 Engagement"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="create-program-parts-7-12",
    )
    program = program_response.json()["data"]["program"]

    stage7 = authenticated_client.post(
        f"/api/programs/{program['id']}/stages/stage_07_preparation/outputs/generate",
        data={
            "workflow_id": "test.stage7",
            "artifact_schema_ids": [
                "campaign_architecture",
                "kpi_tree",
                "content_pillars",
                "approval_chain",
            ],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="stage7-outputs",
    )
    assert stage7.status_code == 201
    assert len(stage7.json()["data"]["stage_output"]["created_artifacts"]) == 4

    stage8 = authenticated_client.post(
        f"/api/programs/{program['id']}/stages/stage_08_growth_plan/outputs/generate",
        data={
            "workflow_id": "test.stage8",
            "artifact_schema_ids": ["growth_plan", "yearly_planner"],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="stage8-outputs",
    )
    assert stage8.status_code == 201
    assert not stage8.json()["data"]["stage_output"]["blockers"]
    assert Asset.objects.filter(
        company=company, metadata_json__artifact_type="growth_plan"
    ).exists()

    stage9 = authenticated_client.post(
        f"/api/programs/{program['id']}/stages/stage_09_channel_strategy/outputs/generate",
        data={
            "workflow_id": "test.stage9",
            "selected_family_ids": ["search_campaign", "measurement"],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="stage9-outputs",
    )
    assert stage9.status_code == 201
    created_types = {
        item["artifact_type"] for item in stage9.json()["data"]["stage_output"]["created_artifacts"]
    }
    assert created_types == {"search_strategy", "measurement_strategy"}
    assert "paid_platform_strategy" not in created_types

    stage10 = authenticated_client.post(
        f"/api/programs/{program['id']}/stages/stage_10_execution_artifacts/outputs/generate",
        data={
            "workflow_id": "test.stage10",
            "artifact_schema_ids": ["ad_copy", "headline_set"],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="stage10-outputs",
    )
    assert stage10.status_code == 201
    assert AssetDependency.objects.filter(company=company, dependency_type="informs").exists()

    stage11 = authenticated_client.post(
        f"/api/programs/{program['id']}/stages/stage_11_ai_creative_instructions/outputs/generate",
        data={"workflow_id": "test.stage11", "artifact_schema_ids": ["creative_instruction"]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="stage11-outputs",
    )
    assert stage11.status_code == 201
    assert Asset.objects.filter(
        company=company, metadata_json__artifact_type="creative_instruction"
    ).exists()

    stage12 = authenticated_client.post(
        f"/api/programs/{program['id']}/stages/stage_12_continuous_improvement/outputs/generate",
        data={"workflow_id": "test.stage12", "artifact_schema_ids": ["quarterly_brief"]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="stage12-outputs",
    )
    assert stage12.status_code == 201
    assert CompanySignal.objects.filter(company=company, source="program_stage_output").count() == 3
    assert StateProjection.objects.filter(company=company, program_id=program["id"]).exists()


def test_atlas_monthly_kpi_scorecard_uses_generic_evaluation_and_signals(
    authenticated_client,
    user,
):
    company = _company(user, "ATLAS Scorecard Co")
    authenticated_client.post(
        f"/api/companies/{company.id}/operating-model/packs/digital_marketing_pro.v1/install",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="install-atlas-scorecard",
    )
    program_response = authenticated_client.post(
        f"/api/companies/{company.id}/programs",
        data={"template_id": "dmp.engagement", "title": "Monthly Scorecard Engagement"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="create-program-atlas-scorecard",
    )
    program = program_response.json()["data"]["program"]

    response = authenticated_client.post(
        "/api/evaluations/run",
        data={
            "company_id": str(company.id),
            "program_id": program["id"],
            "profile_id": "atlas_monthly_kpi_scorecard.v1",
            "inputs": {
                "metrics": {
                    "social_engagement_rate": 0.7,
                    "email_open_rate": 20,
                    "roas": 3.5,
                    "cost_per_lead_services": {
                        "level": "acceptable",
                        "notes": "Sustainable for this ticket.",
                    },
                    "cac_vs_profit": {"level": "good", "notes": "CAC is profitable."},
                    "publishing_frequency": {
                        "level": "bad_or_risky",
                        "notes": "Cadence is below target.",
                    },
                }
            },
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="run-atlas-scorecard",
    )

    assert response.status_code == 201
    evaluation = response.json()["data"]["evaluation"]
    assert evaluation["status"] == "WARN"
    metrics = {item["metric_id"]: item for item in evaluation["scorecard"]["dimensions"]["metrics"]}
    assert metrics["social_engagement_rate"]["level"] == "bad_or_risky"
    assert metrics["email_open_rate"]["level"] == "acceptable"
    assert metrics["roas"]["level"] == "good"
    assert "atlas.hook_creation" in evaluation["result"]["recommended_operation_template_ids"]
    assert EvaluationRun.objects.filter(
        company=company,
        profile_key="atlas_monthly_kpi_scorecard.v1",
        status="WARN",
    ).exists()
    assert CompanySignal.objects.filter(company=company, source="evaluation_scorecard").count() == 2


def test_atlas_monthly_reporting_stage_outputs_service_history_projection(
    authenticated_client,
    user,
):
    company = _company(user, "ATLAS Monthly Reporting Co")
    authenticated_client.post(
        f"/api/companies/{company.id}/operating-model/packs/digital_marketing_pro.v1/install",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="install-atlas-monthly-reporting",
    )
    program_response = authenticated_client.post(
        f"/api/companies/{company.id}/programs",
        data={"template_id": "dmp.engagement", "title": "Monthly Reporting Engagement"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="create-program-atlas-monthly-reporting",
    )
    program = program_response.json()["data"]["program"]

    response = authenticated_client.post(
        f"/api/programs/{program['id']}/stages/stage_12_continuous_improvement/outputs/generate",
        data={
            "workflow_id": "atlas.monthly.reporting",
            "artifact_schema_ids": [
                "monthly_report",
                "monthly_kpi_scorecard",
                "client_service_history_entry",
            ],
            "evaluation_inputs": {
                "metrics": {
                    "landing_page_conversion": 3,
                    "email_open_rate": 20,
                    "roas": 3.5,
                    "cost_per_lead_services": {"level": "acceptable"},
                }
            },
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="stage12-atlas-monthly-reporting",
    )

    assert response.status_code == 201
    output = response.json()["data"]["stage_output"]
    assert {item["artifact_type"] for item in output["created_artifacts"]} == {
        "monthly_report",
        "monthly_kpi_scorecard",
        "client_service_history_entry",
    }
    assert any(
        item["profile_id"] == "atlas_monthly_kpi_scorecard.v1" for item in output["evaluations"]
    )
    assert StateProjection.objects.filter(
        company=company,
        program_id=program["id"],
        projection_type="client_service_history",
    ).exists()
    history = authenticated_client.get(
        "/api/state-projections",
        data={
            "company_id": str(company.id),
            "program_id": program["id"],
            "projection_type": "client_service_history",
        },
    )
    assert history.status_code == 200
    history_state = history.json()["data"]["state_projections"][0]["json_state"]
    assert history_state["service_artifacts"]
    assert history_state["evaluation_runs"]


def test_pack_install_creates_generic_periodic_review_definition(authenticated_client, user):
    company = _company(user, "Periodic Install Co")
    response = authenticated_client.post(
        f"/api/companies/{company.id}/operating-model/packs/digital_marketing_pro.v1/install",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="install-periodic-review",
    )

    assert response.status_code == 201
    review = PeriodicReviewDefinition.objects.get(
        company=company,
        template_id="atlas_monthly_review.v1",
    )
    assert review.evaluation_profile_key == "atlas_monthly_kpi_scorecard.v1"
    assert review.report_template_id == "atlas_monthly_report.v1"
    assert review.history_projection_type == "client_service_history"


def test_periodic_review_runs_from_metric_snapshots_and_tracks_trends(
    authenticated_client,
    user,
):
    company = _company(user, "Periodic Loop Co")
    authenticated_client.post(
        f"/api/companies/{company.id}/operating-model/packs/digital_marketing_pro.v1/install",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="install-periodic-loop",
    )
    program_response = authenticated_client.post(
        f"/api/companies/{company.id}/programs",
        data={"template_id": "dmp.engagement", "title": "Periodic Loop Engagement"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="create-periodic-loop-program",
    )
    program = program_response.json()["data"]["program"]
    review = PeriodicReviewDefinition.objects.get(
        company=company,
        template_id="atlas_monthly_review.v1",
    )

    first_snapshot = authenticated_client.post(
        "/api/metric-snapshots",
        data={
            "company_id": str(company.id),
            "program_id": program["id"],
            "review_definition_id": str(review.id),
            "period_start": "2026-03-01",
            "period_end": "2026-03-31",
            "source_type": "manual",
            "metric_values": {
                "social_engagement_rate": 0.7,
                "roas": 3.5,
                "website_bounce_rate": 72,
                "cost_per_lead_services": {
                    "value": 120,
                    "average_ticket": 2000,
                    "gross_margin": 0.45,
                    "lead_to_sale_conversion_rate": 0.08,
                    "target_profit_margin": 0.25,
                },
                "cac_vs_profit": {
                    "customer_acquisition_cost": 850,
                    "gross_profit_per_customer": 1200,
                },
                "publishing_frequency": {"level": "bad_or_risky"},
            },
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="periodic-snapshot-1",
    )
    assert first_snapshot.status_code == 201
    first_snapshot_id = first_snapshot.json()["data"]["metric_snapshot"]["id"]
    first_run = authenticated_client.post(
        f"/api/periodic-reviews/{review.id}/run",
        data={"metric_snapshot_id": first_snapshot_id},
        format="json",
        HTTP_IDEMPOTENCY_KEY="periodic-run-1",
    )
    assert first_run.status_code == 201

    second_snapshot = authenticated_client.post(
        "/api/metric-snapshots",
        data={
            "company_id": str(company.id),
            "program_id": program["id"],
            "review_definition_id": str(review.id),
            "period_start": "2026-04-01",
            "period_end": "2026-04-30",
            "source_type": "manual",
            "metric_values": {
                "social_engagement_rate": 2.1,
                "roas": 1.2,
                "website_bounce_rate": 75,
                "cost_per_lead_services": {
                    "value": 60,
                    "average_ticket": 2000,
                    "gross_margin": 0.45,
                    "lead_to_sale_conversion_rate": 0.08,
                    "target_profit_margin": 0.25,
                },
                "cac_vs_profit": {
                    "customer_acquisition_cost": 1450,
                    "gross_profit_per_customer": 1200,
                },
                "publishing_frequency": 18,
            },
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="periodic-snapshot-2",
    )
    assert second_snapshot.status_code == 201
    second_run = authenticated_client.post(
        f"/api/periodic-reviews/{review.id}/run",
        data={"metric_snapshot_id": second_snapshot.json()["data"]["metric_snapshot"]["id"]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="periodic-run-2",
    )

    assert second_run.status_code == 201
    payload = second_run.json()["data"]
    evaluation = payload["evaluation"]
    assert (
        evaluation["result"]["metric_snapshot_id"]
        == second_snapshot.json()["data"]["metric_snapshot"]["id"]
    )
    trends = evaluation["result"]["trend_summary"]
    assert "social_engagement_rate" in trends["recovered"]
    assert "website_bounce_rate" in trends["persistent_bad_or_risky"]
    assert "roas" in trends["newly_bad_or_risky"]
    assert ReportRun.objects.filter(company=company).count() == 2
    assert MetricSnapshot.objects.filter(company=company).count() == 2
    assert CompanySignal.objects.filter(company=company, source="evaluation_scorecard").exists()
    history = StateProjection.objects.get(
        company=company,
        program_id=program["id"],
        projection_type="client_service_history",
    )
    assert len(history.json_state["entries"]) == 2


def test_periodic_review_run_endpoint_can_create_snapshot_from_values(
    authenticated_client,
    user,
):
    company = _company(user, "Periodic Manual Run Co")
    authenticated_client.post(
        f"/api/companies/{company.id}/operating-model/packs/digital_marketing_pro.v1/install",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="install-periodic-manual-run",
    )
    review = PeriodicReviewDefinition.objects.get(
        company=company,
        template_id="atlas_monthly_review.v1",
    )

    response = authenticated_client.post(
        f"/api/periodic-reviews/{review.id}/run",
        data={
            "period_start": "2026-04-01",
            "period_end": "2026-04-30",
            "metric_values": {
                "social_engagement_rate": 0.7,
                "roas": 3.5,
                "cost_per_lead_services": {"level": "acceptable"},
                "cac_vs_profit": {"level": "good"},
                "publishing_frequency": 18,
            },
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="periodic-manual-run",
    )

    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["periodic_review_execution"]["metric_snapshot_id"]
    assert payload["evaluation"]["result"]["metric_snapshot_id"]
    assert payload["report_run"]["artifact"]
    assert MetricSnapshot.objects.filter(company=company).count() == 1
    assert ReportRun.objects.filter(company=company).count() == 1


def test_periodic_review_run_endpoint_supports_dry_run_and_duplicate_skip(
    authenticated_client,
    user,
):
    company = _company(user, "Periodic Dry Run Co")
    authenticated_client.post(
        f"/api/companies/{company.id}/operating-model/packs/digital_marketing_pro.v1/install",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="install-periodic-dry-run",
    )
    review = PeriodicReviewDefinition.objects.get(
        company=company,
        template_id="atlas_monthly_review.v1",
    )
    values = {
        "social_engagement_rate": 2.7,
        "roas": 3.1,
        "cost_per_lead_services": {"level": "acceptable"},
        "cac_vs_profit": {"level": "good"},
        "publishing_frequency": 18,
    }

    dry_run = authenticated_client.post(
        f"/api/periodic-reviews/{review.id}/run",
        data={
            "period_start": "2026-04-01",
            "period_end": "2026-04-30",
            "metric_values": values,
            "dry_run": True,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="periodic-dry-run",
    )
    created = authenticated_client.post(
        f"/api/periodic-reviews/{review.id}/run",
        data={
            "period_start": "2026-04-01",
            "period_end": "2026-04-30",
            "metric_values": values,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="periodic-created-run",
    )
    duplicate = authenticated_client.post(
        f"/api/periodic-reviews/{review.id}/run",
        data={
            "period_start": "2026-04-01",
            "period_end": "2026-04-30",
            "metric_values": values,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="periodic-duplicate-run",
    )

    assert dry_run.status_code == 200
    assert dry_run.json()["data"]["periodic_review_execution"]["status"] == "dry_run_ready"
    assert created.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json()["data"]["periodic_review_execution"]["status"] == ("skipped_duplicate")
    assert MetricSnapshot.objects.filter(company=company).count() == 1
    assert ReportRun.objects.filter(company=company).count() == 1


def test_periodic_review_run_endpoint_returns_missing_metric_blockers(
    authenticated_client,
    user,
):
    company = _company(user, "Periodic Missing Metrics Co")
    authenticated_client.post(
        f"/api/companies/{company.id}/operating-model/packs/digital_marketing_pro.v1/install",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="install-periodic-missing-metrics",
    )
    review = PeriodicReviewDefinition.objects.get(
        company=company,
        template_id="atlas_monthly_review.v1",
    )

    response = authenticated_client.post(
        f"/api/periodic-reviews/{review.id}/run",
        data={"period_start": "2026-04-01", "period_end": "2026-04-30"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="periodic-missing-metrics",
    )

    assert response.status_code == 200
    summary = response.json()["data"]["periodic_review_execution"]
    assert summary["status"] == "blocked"
    assert summary["blockers"][0]["type"] == "metric_input_required"
    assert CompanySignal.objects.filter(
        company=company,
        source="periodic_review_input_gap",
    ).exists()


def test_threshold_scorecard_contextual_metric_missing_context_is_explicit(
    authenticated_client,
    user,
):
    company = _company(user, "Contextual Metrics Co")
    authenticated_client.post(
        f"/api/companies/{company.id}/operating-model/packs/digital_marketing_pro.v1/install",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="install-contextual-metrics",
    )

    response = authenticated_client.post(
        "/api/evaluations/run",
        data={
            "company_id": str(company.id),
            "profile_id": "atlas_monthly_kpi_scorecard.v1",
            "inputs": {
                "metrics": {
                    "cost_per_lead_services": {"value": 120},
                    "cac_vs_profit": {
                        "customer_acquisition_cost": 600,
                        "gross_profit_per_customer": 1200,
                    },
                }
            },
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="run-contextual-metrics",
    )

    assert response.status_code == 201
    metrics = {
        item["metric_id"]: item
        for item in response.json()["data"]["evaluation"]["scorecard"]["dimensions"]["metrics"]
    }
    assert metrics["cost_per_lead_services"]["level"] == "needs_input"
    assert metrics["cac_vs_profit"]["level"] == "good"


def test_pack_installation_is_company_scoped(authenticated_client, user):
    allowed = _company(user, "Allowed")
    other = Graph.objects.create(
        owner=user,
        organization=user.default_organization,
        name="Other",
        description="Other company",
    )
    response = authenticated_client.post(
        f"/api/companies/{allowed.id}/operating-model/packs/digital_marketing_pro.v1/install",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="tenant-install",
    )
    assert response.status_code == 201

    other_model = authenticated_client.get(f"/api/companies/{other.id}/operating-model")

    assert other_model.status_code == 200
    assert other_model.json()["data"]["operating_model"]["installed_packs"] == []
