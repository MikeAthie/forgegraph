"""Backend invariants for Organization -> Company -> PackInstallation -> generic primitives."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APIClient

from application.services import operating_model_packs
from application.services.operating_model_packs import (
    OperatingModelPackError,
    install_pack_for_company,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Asset,
    CompanyAccessPolicy,
    CompanyAssignment,
    CompanyOperatingModelInstallation,
    CompanySignal,
    EvaluationRun,
    EvaluationScorecard,
    Graph,
    MetricSnapshot,
    Organization,
    OrganizationMembership,
    PackNamespaceClaim,
    PeriodicReviewDefinition,
    ReportRun,
    StateProjection,
    ToolExecution,
    User,
    WorkWhiteboard,
)

pytestmark = pytest.mark.django_db

FUNCTION_COMPANY_NAMES = {
    "Legacy Marketing",
    "Legacy Accounting",
    "Legacy Legal",
    "Legacy Consulting",
}


def _operator_org(user: User) -> Organization:
    organization = user.default_organization
    assert organization is not None
    organization.name = "ATLAS Test Operator Org"
    organization.save(update_fields=["name"])
    return organization


def _company(user: User, name: str = "Legacy Eyewear") -> Graph:
    organization = _operator_org(user)
    return cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description="Legacy Eyewear customer company.",
        ),
    )


def _member_in_org(owner: User, *, role: str = "viewer") -> User:
    organization = _operator_org(owner)
    member = User.objects.create_user(
        email=f"product-mode-member-{uuid4().hex}@example.com",
        password="testpassword123",
    )
    ensure_default_organization(member)
    member.default_organization = organization
    member.save(update_fields=["default_organization"])
    OrganizationMembership.objects.update_or_create(
        organization=organization,
        user=member,
        defaults={"role": role, "is_default": True},
    )
    return member


def _restrict_company(company: Graph) -> None:
    CompanyAccessPolicy.objects.update_or_create(
        company=company,
        defaults={
            "organization": company.organization,
            "assignment_required": True,
            "org_admin_access_enabled": False,
        },
    )


def _assign_company(owner: User, company: Graph, member: User, *, role: str) -> None:
    CompanyAssignment.objects.update_or_create(
        organization=company.organization,
        company=company,
        user=member,
        defaults={"role": role, "status": "active", "created_by": owner},
    )


def _install_pack(
    client: APIClient,
    company: Graph,
    *,
    pack_id: str,
    role: str,
    key: str,
) -> dict[str, Any]:
    response = client.post(
        f"/api/companies/{company.id}/packs/install",
        data={
            "pack_id": pack_id,
            "role": role,
            "config": {"skip_graph_version": True, "selected_services": ["Operations"]},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json()["data"]["installation"])


def _seed_company_history(owner: User, company: Graph) -> dict[str, Any]:
    organization = company.organization
    assert organization is not None
    artifact = Asset.objects.create(
        organization=organization,
        company=company,
        title="Legacy operating summary",
        asset_type="deliverable",
        created_by_type="system",
        metadata_json={"artifact_type": "operating_summary"},
    )
    review = PeriodicReviewDefinition.objects.create(
        organization=organization,
        company=company,
        pack_id="digital_marketing_pro.v1",
        template_id=f"monthly-review-{uuid4().hex}",
        display_name="Monthly operating review",
        cadence="monthly",
        report_template_id="legacy_monthly_report.v1",
        history_projection_type="client_service_history",
        created_by=owner,
    )
    snapshot = MetricSnapshot.objects.create(
        organization=organization,
        company=company,
        review_definition=review,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        source_type="seed",
        metric_values_json={"stock_units_available": 62, "low_stock_products": 3},
        created_by=owner,
    )
    report = ReportRun.objects.create(
        organization=organization,
        company=company,
        review_definition=review,
        metric_snapshot=snapshot,
        artifact=artifact,
        report_template_id="legacy_monthly_report.v1",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        generated_sections_json={"summary": "Legacy Eyewear monthly operating history."},
        created_by=owner,
    )
    projection = StateProjection.objects.create(
        organization=organization,
        company=company,
        projection_type="client_service_history",
        display_label="Service history",
        json_state={
            "company_name": "Legacy Eyewear",
            "entries": [{"report_run_id": str(report.id), "artifact_id": str(artifact.id)}],
        },
        markdown_summary="Legacy Eyewear service history.",
    )
    return {
        "artifact": artifact,
        "review": review,
        "snapshot": snapshot,
        "report": report,
        "projection": projection,
    }


def _assert_no_marketing_specific_shape(payload: Any) -> None:
    serialized = str(payload).lower()
    assert "/api/marketing/" not in serialized
    assert "marketing_company" not in serialized
    assert "marketingmodel" not in serialized


def _review_board_section(
    area_names: list[str],
    *,
    score: float,
    required_improvements: list[str] | None = None,
    exceptional: bool = False,
) -> dict[str, Any]:
    rationale = (
        "Exceptional, top-tier rationale grounded in the submitted evidence."
        if exceptional
        else "Strong rationale grounded in Legacy context and the submitted evidence."
    )
    scores: list[dict[str, Any]] = [
        {
            "area": area,
            "score": score,
            "rationale": rationale,
            "improvement": f"Improve {area.lower()} with a concrete next operating step.",
        }
        for area in area_names
    ]
    average = round(sum(float(item["score"]) for item in scores) / len(scores), 2)
    return {
        "average": average,
        "scores": scores,
        "top_strengths": [
            "Uses company-scoped Legacy Eyewear context.",
            "Keeps ATLAS and Legacy boundaries separate.",
        ],
        "required_improvements": required_improvements
        or [
            "Add sharper operating owner and timing detail.",
            "Tie the next review to a measurable company signal.",
        ],
    }


def _submitted_review_board_scorecard(
    *,
    score: float = 4.3,
    decision: str = "client_ready",
    hard_fail: bool = False,
    approval_status: str = "approved_for_review",
    primitive: str = "CompanySignal",
    exceptional: bool = False,
) -> dict[str, Any]:
    atlas_areas = [
        "Diagnostic depth",
        "Strategic reasoning",
        "Use of Legacy context",
        "Execution design",
        "Tool/capability honesty",
        "Client communication quality",
        "Operating-system maturity",
    ]
    legacy_areas = [
        "Context completeness",
        "Commercial readiness",
        "Brand readiness",
        "Channel readiness",
        "Approval readiness",
        "Measurement readiness",
        "Operational maturity",
    ]
    engagement_areas = [
        "Goal clarity",
        "Evidence quality",
        "Deliverable completeness",
        "Cross-company boundary correctness",
        "Client safety",
        "Execution continuity",
        "Reusability/history",
    ]
    atlas = _review_board_section(atlas_areas, score=score, exceptional=exceptional)
    legacy = _review_board_section(legacy_areas, score=score, exceptional=exceptional)
    engagement = _review_board_section(engagement_areas, score=score, exceptional=exceptional)
    overall_average = round(
        (atlas["average"] + legacy["average"] + engagement["average"]) / 3,
        2,
    )
    return {
        "schema_version": "consulting_review_board_v1",
        "decision": decision,
        "hard_fail": hard_fail,
        "overall_average": overall_average,
        "client_readiness_level": "client_ready",
        "atlas": atlas,
        "legacy": legacy,
        "engagement": engagement,
        "company_improvement_plan": [
            {
                "target": "ATLAS",
                "primitive": primitive,
                "title": "Create a sharper consulting follow-up signal",
                "priority": "medium",
                "rationale": "ATLAS should convert judge feedback into a generic next-step primitive.",
            },
            {
                "target": "Legacy Eyewear",
                "primitive": "OperationRecommendation",
                "title": "Prepare approval-ready execution checklist",
                "priority": "high",
                "rationale": "Legacy needs a generic recommendation before public execution.",
            },
        ],
        "approval_gate": {
            "client_deliverable_status": approval_status,
            "execution_status": "ready"
            if approval_status == "approved_for_review"
            else "blocked_until_missing_capabilities_resolved",
            "reason": "The review board gate is based on company-scoped evidence.",
        },
        "judge_prompt": "internal prompt must not persist",
        "internal_reasoning": "private chain-of-thought must not persist",
        "evidence_bundle": {"private": "must not persist"},
        "raw_judge_prompt": "raw prompt must not persist",
        "private_reasoning": "private reasoning must not persist",
        "raw_evidence_bundle": {"private": "raw evidence must not persist"},
        "pack_manifest": {"private": "pack manifest must not persist"},
        "private_config": {"secret": "private config must not persist"},
    }


def _submitted_atlas_rubric_scorecard(
    *,
    score: float = 4.3,
    decision: str = "sellable",
    judge_kind: str = "department",
    subject_id: str = "strategy_research",
    subject_label: str = "Strategy & Research",
    hard_fail: bool = False,
    primitive: str = "CompanySignal",
) -> dict[str, Any]:
    criteria = [
        {
            "key": "problem_framing",
            "label": "Problem framing",
            "score": score,
            "critical": True,
            "rationale": "The judge cites durable whiteboard, approval, and operation evidence.",
            "improvement": "Make the framing more specific to the approved operating constraints.",
            "evidence_refs": [
                {"type": "work_whiteboard", "id": "whiteboard-1"},
                {"type": "product_operation", "id": "operation-1"},
            ],
        },
        {
            "key": "evidence_discipline",
            "label": "Evidence discipline",
            "score": score,
            "rationale": "Evidence references are tied to backend-owned generic primitives.",
            "improvement": "Attach more precise artifact revisions to each claim.",
            "evidence_refs": [{"type": "work_artifact", "id": "artifact-1"}],
        },
        {
            "key": "targeting_positioning",
            "label": "Targeting and positioning",
            "score": score,
            "rationale": "The target audience and positioning stay inside the company boundary.",
            "improvement": "Separate approved audience hypotheses from unvalidated assumptions.",
            "evidence_refs": [{"type": "state_projection", "id": "projection-1"}],
        },
        {
            "key": "constraint_use",
            "label": "Constraint use",
            "score": score,
            "rationale": "The judge considers inventory, connector, and approval constraints.",
            "improvement": "Turn every hard blocker into a visible generic next step.",
            "evidence_refs": [{"type": "company_signal", "id": "signal-1"}],
        },
        {
            "key": "downstream_usefulness",
            "label": "Downstream usefulness",
            "score": score,
            "rationale": "The output can guide later workstreams without adding vertical state.",
            "improvement": "Add a concise handoff summary for downstream workstreams.",
            "evidence_refs": [{"type": "metric_snapshot", "id": "metric-1"}],
        },
    ]
    overall_average = round(sum(float(item["score"]) for item in criteria) / len(criteria), 2)
    return {
        "schema_version": "atlas_rubric_scorecard_v1",
        "judge_kind": judge_kind,
        "subject_id": subject_id,
        "subject_label": subject_label,
        "decision": decision,
        "hard_fail": hard_fail,
        "overall_average": overall_average,
        "criteria": criteria,
        "top_strengths": [
            "Uses backend-owned Atlas agency evidence.",
            "Keeps quality judging separate from deterministic system assertions.",
        ],
        "required_improvements": [
            "Tighten the client-facing evidence bundle before paid delivery.",
            "Convert low-confidence items into generic backend-owned follow-up primitives.",
        ],
        "improvement_plan": [
            {
                "target": subject_label,
                "primitive": primitive,
                "title": "Create a paid-readiness improvement signal",
                "priority": "high",
                "rationale": "Atlas should persist judge feedback as an actionable generic primitive.",
                "evidence_refs": [{"type": "evaluation_subject", "id": subject_id}],
            },
            {
                "target": subject_label,
                "primitive": "OperationRecommendation",
                "title": "Prepare the next operation recommendation",
                "priority": "medium",
                "rationale": "The next operation should close the largest judged quality gap.",
                "evidence_refs": [{"type": "evaluation_subject", "id": subject_id}],
            },
        ],
        "judge_prompt": "internal prompt must not persist",
        "internal_reasoning": "private chain-of-thought must not persist",
        "evidence_bundle": {"private": "must not persist"},
        "raw_judge_output": {"private": "raw judge output must not persist"},
    }


def _run_submitted_scorecard(
    client: APIClient,
    company: Graph,
    scorecard: dict[str, Any],
    *,
    key: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/evaluations/run",
        data={
            "company_id": str(company.id),
            "profile_id": "consulting_ops_demo.v1.quality_judge",
            "input_refs": [{"type": "artifact", "id": "strategy-output"}],
            "inputs": {"submitted_scorecard": scorecard},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json()["data"]["evaluation"])


def _run_invalid_submitted_scorecard(
    client: APIClient,
    company: Graph,
    scorecard: dict[str, Any],
    *,
    key: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/evaluations/run",
        data={
            "company_id": str(company.id),
            "profile_id": "consulting_ops_demo.v1.quality_judge",
            "input_refs": [{"type": "artifact", "id": "strategy-output"}],
            "inputs": {"submitted_scorecard": scorecard},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert response.status_code == 400
    return cast(dict[str, Any], response.json())


def test_legacy_can_be_one_company_with_multiple_pack_installations(authenticated_client, user):
    company = _company(user)

    primary = _install_pack(
        authenticated_client,
        company,
        pack_id="digital_marketing_pro.v1",
        role="primary",
        key="product-mode-primary-pack",
    )
    addon = _install_pack(
        authenticated_client,
        company,
        pack_id="legal_ops_demo.v1",
        role="addon",
        key="product-mode-legal-addon",
    )

    assert Graph.objects.filter(name="Legacy Eyewear").count() == 1
    assert not Graph.objects.filter(name__in=FUNCTION_COMPANY_NAMES).exists()
    assert primary["role"] == "primary"
    assert addon["role"] == "addon"

    installations = CompanyOperatingModelInstallation.objects.filter(company=company)
    assert {item.company_id for item in installations} == {company.id}
    assert installations.filter(role="primary", status="active").count() == 1
    assert installations.filter(role="addon", status="active").count() >= 1

    model_response = authenticated_client.get(f"/api/companies/{company.id}/operating-model")
    assert model_response.status_code == 200
    model = model_response.json()["data"]["operating_model"]
    assert model["company_id"] == str(company.id)
    assert {pack["company_id"] for pack in model["installed_packs"]} == {str(company.id)}


def test_pack_defined_objects_are_exposed_with_pack_namespaced_ids(authenticated_client, user):
    company = _company(user)
    installation = _install_pack(
        authenticated_client,
        company,
        pack_id="digital_marketing_pro.v1",
        role="primary",
        key="product-mode-namespaced-pack",
    )

    objects_response = authenticated_client.get(
        f"/api/companies/{company.id}/packs/{installation['id']}/objects"
    )

    assert objects_response.status_code == 200
    objects = objects_response.json()["data"]["objects"]
    assert objects
    for item in objects:
        assert item["company_id"] == str(company.id)
        assert item["pack_id"] == "digital_marketing_pro.v1"
        assert item["namespaced_id"].startswith("digital_marketing_pro.v1.")


def test_pack_namespace_claim_validation_rejects_invalid_namespaced_ids(
    authenticated_client,
    user,
):
    company = _company(user)
    installation = _install_pack(
        authenticated_client,
        company,
        pack_id="digital_marketing_pro.v1",
        role="primary",
        key="product-mode-invalid-namespace-pack",
    )
    valid_claim = PackNamespaceClaim(
        organization=company.organization,
        company=company,
        installation_id=installation["id"],
        pack_id="digital_marketing_pro.v1",
        object_type="program_template",
        object_id="campaign_brief",
        namespaced_id="digital_marketing_pro.v1.campaign_brief",
        status="active",
    )
    valid_claim.full_clean()

    un_namespaced_claim = PackNamespaceClaim(
        organization=company.organization,
        company=company,
        installation_id=installation["id"],
        pack_id="digital_marketing_pro.v1",
        object_type="program_template",
        object_id="dmp.engagement",
        namespaced_id="dmp.engagement",
        status="active",
    )
    wrong_pack_claim = PackNamespaceClaim(
        organization=company.organization,
        company=company,
        installation_id=installation["id"],
        pack_id="digital_marketing_pro.v1",
        object_type="program_template",
        object_id="campaign_brief",
        namespaced_id="accounting_ops.v1.campaign_brief",
        status="active",
    )

    with pytest.raises(ValidationError, match="owning pack id plus a dot"):
        un_namespaced_claim.full_clean()

    with pytest.raises(ValidationError, match="owning pack id plus a dot"):
        wrong_pack_claim.full_clean()

    existing_claim = PackNamespaceClaim.objects.filter(
        company=company,
        status="active",
    ).first()
    assert existing_claim is not None
    organization = company.organization
    assert organization is not None
    with pytest.raises(IntegrityError):
        PackNamespaceClaim.objects.create(
            organization=organization,
            company=company,
            installation_id=installation["id"],
            pack_id=existing_claim.pack_id,
            object_type=existing_claim.object_type,
            object_id=existing_claim.object_id,
            namespaced_id=existing_claim.namespaced_id,
            status="active",
        )


def test_pack_install_service_rejects_invalid_namespace_claims(monkeypatch, user):
    company = _company(user)

    def invalid_claims(_definition):
        return [
            {
                "object_type": "program_template",
                "object_id": "campaign_brief",
                "namespaced_id": "campaign_brief",
            }
        ]

    monkeypatch.setattr(operating_model_packs, "_pack_namespace_claims", invalid_claims)

    with pytest.raises(OperatingModelPackError, match="owning pack id plus a dot"):
        install_pack_for_company(
            company=company,
            user=user,
            pack_id="digital_marketing_pro.v1",
            config={"skip_graph_version": True},
            role="primary",
        )

    assert not PackNamespaceClaim.objects.filter(
        company=company,
        namespaced_id="campaign_brief",
    ).exists()


def test_generic_artifacts_reports_and_history_are_company_scoped(api_client, user):
    legacy_company = _company(user)
    other_company = _company(user, "Other Client")
    _seed_company_history(user, legacy_company)
    _seed_company_history(user, other_company)
    legacy_member = _member_in_org(user, role="viewer")
    other_member = _member_in_org(user, role="viewer")
    for company in [legacy_company, other_company]:
        _restrict_company(company)
    _assign_company(user, legacy_company, legacy_member, role="viewer")
    _assign_company(user, other_company, other_member, role="viewer")

    api_client.force_authenticate(user=legacy_member)
    artifacts = api_client.get("/api/work-artifacts", {"company_id": str(legacy_company.id)})
    reports = api_client.get("/api/report-runs", {"company_id": str(legacy_company.id)})
    history = api_client.get(
        "/api/state-projections",
        {"company_id": str(legacy_company.id), "projection_type": "client_service_history"},
    )
    other_artifacts = api_client.get("/api/work-artifacts", {"company_id": str(other_company.id)})

    assert artifacts.status_code == 200
    assert reports.status_code == 200
    assert history.status_code == 200
    assert other_artifacts.status_code == 404
    assert {item["company_id"] for item in artifacts.json()["data"]["artifacts"]} == {
        str(legacy_company.id)
    }
    assert {item["company_id"] for item in reports.json()["data"]["report_runs"]} == {
        str(legacy_company.id)
    }
    assert {item["company_id"] for item in history.json()["data"]["state_projections"]} == {
        str(legacy_company.id)
    }

    api_client.force_authenticate(user=other_member)
    blocked_history = api_client.get(
        "/api/state-projections",
        {"company_id": str(legacy_company.id), "projection_type": "client_service_history"},
    )
    assert blocked_history.status_code == 404
    _assert_no_marketing_specific_shape(artifacts.json())
    _assert_no_marketing_specific_shape(reports.json())
    _assert_no_marketing_specific_shape(history.json())


def test_customer_cannot_read_internal_pack_config_references(api_client, user):
    company = _company(user)
    api_client.force_authenticate(user=user)
    installation_payload = _install_pack(
        api_client,
        company,
        pack_id="digital_marketing_pro.v1",
        role="primary",
        key="product-mode-private-config-pack",
    )
    installation = CompanyOperatingModelInstallation.objects.get(id=installation_payload["id"])
    installation.private_config_ref = "vault://product-mode/private-config"
    installation.save(update_fields=["private_config_ref", "updated_at"])
    _restrict_company(company)
    _assign_company(user, company, user, role="admin")
    customer = _member_in_org(user, role="viewer")
    _assign_company(user, company, customer, role="viewer")

    api_client.force_authenticate(user=user)
    operator_response = api_client.get(f"/api/companies/{company.id}/packs/{installation.id}")
    assert operator_response.status_code == 200
    assert operator_response.json()["data"]["installation"]["public_config"]

    api_client.force_authenticate(user=customer)
    customer_response = api_client.get(f"/api/companies/{company.id}/packs/{installation.id}")
    assert customer_response.status_code == 200
    serialized = str(customer_response.json())
    assert "vault://product-mode/private-config" not in serialized
    assert "private_config_ref" not in serialized


def test_non_admin_capability_actor_cannot_mutate_another_pack_config(api_client, user):
    company = _company(user)
    api_client.force_authenticate(user=user)
    first = _install_pack(
        api_client,
        company,
        pack_id="digital_marketing_pro.v1",
        role="primary",
        key="product-mode-pack-a",
    )
    second = _install_pack(
        api_client,
        company,
        pack_id="legal_ops_demo.v1",
        role="addon",
        key="product-mode-pack-b",
    )
    _restrict_company(company)
    member = _member_in_org(user, role="member")
    _assign_company(user, company, member, role="member")
    target = CompanyOperatingModelInstallation.objects.get(id=second["id"])

    api_client.force_authenticate(user=member)
    response = api_client.patch(
        f"/api/companies/{company.id}/packs/{target.id}",
        data={
            "config": {
                "source_pack_id": first["pack_id"],
                "attempted_private_write": "blocked",
            }
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="product-mode-cross-pack-config-write",
    )

    assert response.status_code == 403
    target.refresh_from_db()
    assert "attempted_private_write" not in target.config_json


def test_archived_pack_is_not_active_but_company_history_remains_readable(
    authenticated_client,
    user,
):
    company = _company(user)
    _install_pack(
        authenticated_client,
        company,
        pack_id="digital_marketing_pro.v1",
        role="primary",
        key="product-mode-archive-primary",
    )
    addon = _install_pack(
        authenticated_client,
        company,
        pack_id="legal_ops_demo.v1",
        role="addon",
        key="product-mode-archive-addon",
    )
    _seed_company_history(user, company)

    archive_response = authenticated_client.post(
        f"/api/companies/{company.id}/packs/{addon['id']}/archive",
        data={"reason": "product-mode invariant"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="product-mode-archive-addon-command",
    )

    assert archive_response.status_code == 200
    assert archive_response.json()["data"]["installation"]["status"] == "archived"
    assert not CompanyOperatingModelInstallation.objects.filter(
        id=addon["id"],
        status="active",
    ).exists()
    assert not PackNamespaceClaim.objects.filter(
        installation_id=addon["id"],
        status="active",
    ).exists()

    artifacts = authenticated_client.get("/api/work-artifacts", {"company_id": str(company.id)})
    reports = authenticated_client.get("/api/report-runs", {"company_id": str(company.id)})
    history = authenticated_client.get(
        "/api/state-projections",
        {"company_id": str(company.id), "projection_type": "client_service_history"},
    )
    assert artifacts.status_code == 200
    assert artifacts.json()["data"]["artifacts"]
    assert reports.status_code == 200
    assert reports.json()["data"]["report_runs"]
    assert history.status_code == 200
    assert history.json()["data"]["state_projections"]


def test_review_board_scorecard_client_ready_persists_sanitized_generic_pass(
    authenticated_client,
    user,
):
    company = _company(user)

    evaluation = _run_submitted_scorecard(
        authenticated_client,
        company,
        _submitted_review_board_scorecard(score=4.3, decision="client_ready"),
        key="quality-judge-pass",
    )

    assert evaluation["status"] == "PASS"
    assert evaluation["score"] == 4.3
    assert evaluation["result"]["schema_version"] == "consulting_review_board_v1"
    assert evaluation["result"]["decision"] == "client_ready"
    assert evaluation["result"]["hard_fail"] is False
    assert evaluation["result"]["overall_average"] == 4.3
    assert evaluation["result"]["atlas"]["average"] == 4.3
    assert evaluation["result"]["legacy"]["average"] == 4.3
    assert evaluation["result"]["engagement"]["average"] == 4.3
    assert evaluation["result"]["company_improvement_plan"][0]["primitive"] == "CompanySignal"
    assert "judge_prompt" not in str(evaluation)
    persisted = EvaluationRun.objects.get(id=evaluation["id"])
    assert persisted.company == company
    signal_ids = persisted.result_json["signal_ids"]
    assert signal_ids
    signals = CompanySignal.objects.filter(company=company, source="consulting_review_board")
    assert signals.count() == 2
    assert {str(signal.id) for signal in signals} == set(signal_ids)
    assert {signal.metadata_json["primitive"] for signal in signals} == {
        "CompanySignal",
        "OperationRecommendation",
    }
    scorecard = EvaluationScorecard.objects.get(evaluation=persisted)
    assert scorecard.composite_score == 4.3
    assert scorecard.dimensions_json["schema_version"] == "consulting_review_board_v1"
    assert scorecard.dimensions_json["sections"]["atlas"]["scores"]
    assert "judge_prompt" not in str(scorecard.dimensions_json)
    serialized = str({"run": persisted.result_json, "scorecard": scorecard.dimensions_json}).lower()
    assert "raw prompt" not in serialized
    assert "private reasoning" not in serialized
    assert "raw evidence" not in serialized
    assert "pack manifest" not in serialized
    assert "private config" not in serialized


def test_review_board_scorecard_revision_required_persists_generic_warn_with_improvements(
    authenticated_client,
    user,
):
    company = _company(user)

    evaluation = _run_submitted_scorecard(
        authenticated_client,
        company,
        _submitted_review_board_scorecard(
            score=3.5,
            decision="revision_required",
            approval_status="needs_revision",
        ),
        key="quality-judge-warn",
    )

    assert evaluation["status"] == "WARN"
    assert evaluation["score"] == 3.5
    assert evaluation["result"]["decision"] == "revision_required"
    assert evaluation["result"]["approval_gate"]["client_deliverable_status"] == "needs_revision"
    assert (
        evaluation["result"]["approval_gate"]["execution_status"]
        == "blocked_until_missing_capabilities_resolved"
    )
    assert evaluation["findings"][0]["severity"] == "WARNING"
    assert evaluation["findings"][0]["blocking"] is False
    assert {item["primitive"] for item in evaluation["result"]["company_improvement_plan"]} >= {
        "CompanySignal",
        "OperationRecommendation",
    }
    persisted = EvaluationRun.objects.get(id=evaluation["id"])
    assert persisted.status == "WARN"
    assert persisted.result_json["signal_ids"]
    signals = CompanySignal.objects.filter(company=company, source="consulting_review_board")
    assert signals.count() == 2
    assert all(signal.metadata_json["decision"] == "revision_required" for signal in signals)
    assert all(
        signal.metadata_json["execution_status"] == "blocked_until_missing_capabilities_resolved"
        for signal in signals
    )


def test_review_board_scorecard_hard_fail_persists_generic_block(
    authenticated_client,
    user,
):
    company = _company(user)

    evaluation = _run_submitted_scorecard(
        authenticated_client,
        company,
        _submitted_review_board_scorecard(
            score=4.4,
            decision="fail",
            hard_fail=True,
            approval_status="blocked",
        ),
        key="quality-judge-block",
    )

    assert evaluation["status"] == "BLOCK"
    assert evaluation["score"] == 4.4
    assert evaluation["result"]["hard_fail"] is True
    assert evaluation["result"]["approval_gate"]["client_deliverable_status"] == "blocked"
    assert evaluation["findings"][0]["severity"] == "CRITICAL"
    assert evaluation["findings"][0]["blocking"] is True
    assert not CompanySignal.objects.filter(
        company=company, source="consulting_review_board"
    ).exists()


def test_review_board_downgrades_unapproved_client_ready_gate_to_warn(
    authenticated_client,
    user,
):
    company = _company(user)

    evaluation = _run_submitted_scorecard(
        authenticated_client,
        company,
        _submitted_review_board_scorecard(
            score=4.4,
            decision="client_ready",
            approval_status="needs_revision",
        ),
        key="quality-judge-client-ready-needs-revision",
    )

    assert evaluation["status"] == "WARN"
    assert evaluation["result"]["decision"] == "revision_required"
    assert evaluation["result"]["client_readiness_level"] == "strong_with_minor_revisions"
    assert evaluation["result"]["approval_gate"]["client_deliverable_status"] == "needs_revision"


def test_missing_connector_recommendations_create_generic_signals_without_fake_execution(
    authenticated_client,
    user,
):
    company = _company(user)
    scorecard = _submitted_review_board_scorecard(
        score=3.8,
        decision="revision_required",
        approval_status="needs_revision",
    )
    scorecard["company_improvement_plan"] = [
        {
            "target": "ATLAS",
            "primitive": "CompanySignal",
            "title": "Prioritize social connector readiness",
            "priority": "high",
            "rationale": "Social publishing is recommended but not connected, so create readiness work.",
        },
        {
            "target": "Legacy Eyewear",
            "primitive": "CompanySignal",
            "title": "Prepare WhatsApp approval checklist",
            "priority": "high",
            "rationale": "WhatsApp execution is recommended but unavailable until a connector exists.",
        },
        {
            "target": "engagement",
            "primitive": "OperationRecommendation",
            "title": "Block landing-page deployment until connector exists",
            "priority": "medium",
            "rationale": "Landing-page deployment must remain a recommendation, not fake execution.",
        },
    ]

    evaluation = _run_submitted_scorecard(
        authenticated_client,
        company,
        scorecard,
        key="quality-judge-missing-connectors",
    )

    assert evaluation["status"] == "WARN"
    assert evaluation["result"]["decision"] == "revision_required"
    signals = list(CompanySignal.objects.filter(company=company, source="consulting_review_board"))
    assert len(signals) == 3
    serialized_signals = str([signal.title + signal.summary for signal in signals]).lower()
    assert "social" in serialized_signals
    assert "whatsapp" in serialized_signals
    assert "landing-page" in serialized_signals
    assert not ToolExecution.objects.filter(
        run__graph_version__graph=company,
        tool_name__in=[
            "social_publisher",
            "whatsapp_connector",
            "landing_page_deployer",
            "production_email_sender",
        ],
        status="succeeded",
    ).exists()


def test_legacy_100_point_scorecard_is_rejected(authenticated_client, user):
    company = _company(user)

    payload = _run_invalid_submitted_scorecard(
        authenticated_client,
        company,
        {
            "overall_score": 100,
            "decision": "client_ready",
            "scores": {"grounding_in_legacy_context": 20},
        },
        key="quality-judge-legacy-scorecard",
    )

    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "consulting_review_board_v1" in str(payload["error"]["details"])


def test_review_board_scorecard_rejects_scores_outside_one_to_five(
    authenticated_client,
    user,
):
    company = _company(user)
    scorecard = _submitted_review_board_scorecard(score=4.2, decision="client_ready")
    scorecard["atlas"]["scores"][0]["score"] = 6

    payload = _run_invalid_submitted_scorecard(
        authenticated_client,
        company,
        scorecard,
        key="quality-judge-out-of-range",
    )

    assert "between 1 and 5" in str(payload["error"]["details"])


def test_review_board_scorecard_rejects_missing_sections(authenticated_client, user):
    company = _company(user)
    scorecard = _submitted_review_board_scorecard(score=4.2, decision="client_ready")
    del scorecard["legacy"]

    payload = _run_invalid_submitted_scorecard(
        authenticated_client,
        company,
        scorecard,
        key="quality-judge-missing-section",
    )

    assert "legacy section is required" in str(payload["error"]["details"])


def test_review_board_scorecard_rejects_unearned_perfect_scores(authenticated_client, user):
    company = _company(user)

    payload = _run_invalid_submitted_scorecard(
        authenticated_client,
        company,
        _submitted_review_board_scorecard(
            score=5,
            decision="client_ready",
            exceptional=False,
        ),
        key="quality-judge-unearned-perfect",
    )

    assert "perfect section average requires exceptional rationale" in str(
        payload["error"]["details"]
    )


def test_atlas_rubric_scorecard_persists_sanitized_generic_evidence(
    authenticated_client,
    user,
):
    company = _company(user)

    evaluation = _run_submitted_scorecard(
        authenticated_client,
        company,
        _submitted_atlas_rubric_scorecard(),
        key="atlas-rubric-quality-judge-pass",
    )

    assert evaluation["status"] == "PASS"
    assert evaluation["score"] == 4.3
    assert evaluation["result"]["schema_version"] == "atlas_rubric_scorecard_v1"
    assert evaluation["result"]["engine"] == "submitted_atlas_rubric_scorecard"
    assert evaluation["result"]["judge_kind"] == "department"
    assert evaluation["result"]["subject_id"] == "strategy_research"
    assert evaluation["result"]["decision"] == "sellable"
    assert evaluation["result"]["sellability_gate"]["passed"] is True
    assert len(evaluation["result"]["criteria"]) == 5
    assert evaluation["result"]["criteria"][0]["evidence_refs"]
    assert evaluation["result"]["improvement_plan"][0]["primitive"] == "CompanySignal"
    assert "judge_prompt" not in str(evaluation)

    persisted = EvaluationRun.objects.get(id=evaluation["id"])
    scorecard = EvaluationScorecard.objects.get(evaluation=persisted)
    assert scorecard.composite_score == 4.3
    assert scorecard.dimensions_json["schema_version"] == "atlas_rubric_scorecard_v1"
    assert scorecard.dimensions_json["subject_label"] == "Strategy & Research"
    assert len(scorecard.dimensions_json["criteria"]) == 5
    assert "raw judge output" not in str(scorecard.dimensions_json).lower()

    signal_ids = persisted.result_json["signal_ids"]
    signals = CompanySignal.objects.filter(company=company, source="atlas_rubric_scorecard")
    assert signals.count() == 2
    assert {str(signal.id) for signal in signals} == set(signal_ids)
    assert {signal.metadata_json["primitive"] for signal in signals} == {
        "CompanySignal",
        "OperationRecommendation",
    }
    assert all(
        signal.metadata_json["schema_version"] == "atlas_rubric_scorecard_v1" for signal in signals
    )


def test_atlas_rubric_scorecard_reports_low_quality_without_faking_sellability(
    authenticated_client,
    user,
):
    company = _company(user)

    evaluation = _run_submitted_scorecard(
        authenticated_client,
        company,
        _submitted_atlas_rubric_scorecard(score=3.4, decision="sellable"),
        key="atlas-rubric-quality-judge-warn",
    )

    assert evaluation["status"] == "WARN"
    assert evaluation["score"] == 3.4
    assert evaluation["result"]["decision"] == "needs_revision"
    assert evaluation["result"]["sellability_gate"]["passed"] is False
    assert evaluation["findings"]
    assert all(item["blocking"] is False for item in evaluation["findings"])
    persisted = EvaluationRun.objects.get(id=evaluation["id"])
    assert persisted.result_json["signal_ids"]


def test_atlas_rubric_scorecard_hard_fail_blocks_without_improvement_signals(
    authenticated_client,
    user,
):
    company = _company(user)

    evaluation = _run_submitted_scorecard(
        authenticated_client,
        company,
        _submitted_atlas_rubric_scorecard(
            score=4.4,
            decision="blocked",
            hard_fail=True,
        ),
        key="atlas-rubric-quality-judge-block",
    )

    assert evaluation["status"] == "BLOCK"
    assert evaluation["result"]["decision"] == "blocked"
    assert evaluation["findings"][0]["severity"] == "CRITICAL"
    assert evaluation["findings"][0]["blocking"] is True
    assert not CompanySignal.objects.filter(
        company=company, source="atlas_rubric_scorecard"
    ).exists()


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda scorecard: scorecard["criteria"].pop(), "exactly five scored criteria"),
        (lambda scorecard: scorecard["criteria"][0].__setitem__("score", 6), "between 1 and 5"),
        (
            lambda scorecard: scorecard.__setitem__("overall_average", 1),
            "server-computed criterion average",
        ),
        (
            lambda scorecard: scorecard.__setitem__("required_improvements", []),
            "At least one required improvement",
        ),
        (
            lambda scorecard: scorecard["improvement_plan"][0].__setitem__(
                "primitive", "MarketingCampaign"
            ),
            "generic ForgeGraph primitive",
        ),
        (
            lambda scorecard: scorecard["criteria"][0].__setitem__("evidence_refs", []),
            "at least one reference",
        ),
    ],
)
def test_atlas_rubric_scorecard_rejects_invalid_judge_payloads(
    authenticated_client,
    user,
    mutator,
    expected,
):
    company = _company(user)
    scorecard = _submitted_atlas_rubric_scorecard()
    mutator(scorecard)

    payload = _run_invalid_submitted_scorecard(
        authenticated_client,
        company,
        scorecard,
        key=f"atlas-rubric-invalid-{uuid4().hex}",
    )

    assert expected in str(payload["error"]["details"])


def test_customer_can_read_quality_summary_without_judge_internals(api_client, user):
    company = _company(user)
    api_client.force_authenticate(user=user)
    evaluation = _run_submitted_scorecard(
        api_client,
        company,
        _submitted_review_board_scorecard(score=4.4, decision="client_ready"),
        key="quality-judge-viewer-safe",
    )
    _restrict_company(company)
    viewer = _member_in_org(user, role="viewer")
    _assign_company(user, company, viewer, role="viewer")

    api_client.force_authenticate(user=viewer)
    response = api_client.get(f"/api/evaluations/{evaluation['id']}")

    assert response.status_code == 200
    payload = response.json()["data"]["evaluation"]
    assert payload["company_id"] == str(company.id)
    assert payload["result"]["schema_version"] == "consulting_review_board_v1"
    assert payload["result"]["approval_gate"]
    serialized = str(payload).lower()
    assert "judge_prompt" not in serialized
    assert "internal_reasoning" not in serialized
    assert "evidence_bundle" not in serialized
    assert "pack manifest" not in serialized


def test_product_mode_routes_and_models_remain_generic():
    paths: set[str] = set()

    def walk(patterns: list[URLPattern | URLResolver], prefix: str = "") -> None:
        for pattern in patterns:
            route_part = str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns, prefix + route_part)
                continue
            paths.add(("/" + prefix + route_part).replace("//", "/"))

    walk(get_resolver().url_patterns)
    marketing_routes = [
        path for path in paths if path.startswith("/api/marketing/") or path == "/api/marketing"
    ]
    marketing_models = [
        model.__name__ for model in apps.get_models() if model.__name__.startswith("Marketing")
    ]

    assert marketing_routes == []
    assert marketing_models == []


def test_company_ops_default_objective_language_remains_generic():
    from application.services.company_ops import (
        COMPANY_PROGRESS_OBJECTIVE,
        build_operation_objective_contract,
    )

    contract = build_operation_objective_contract(operation_type="daily_operating_brief")
    serialized = str(
        {
            "primary_objective": COMPANY_PROGRESS_OBJECTIVE,
            "run_goal": contract["run_goal"],
            "hypothesis": contract["hypothesis"],
            "target_signal": contract["target_signal"],
            "action_plan": contract["action_plan_json"],
            "integrity_gates": contract["integrity_gates_json"],
        }
    ).lower()

    assert contract["operation_family"] == "brief"
    assert contract["domain_context"] == "general"
    assert "sell-through" not in serialized
    assert "paid order" not in serialized
    assert "stockout" not in serialized
    assert "fulfillment" not in serialized
    assert "procurement" not in serialized


def test_work_whiteboard_generic_boundary_fields_and_primary_frontend_methods():
    field_names = {field.name for field in WorkWhiteboard._meta.fields}
    assert {
        "work_status",
        "project_name",
        "stakeholder_context_json",
        "resource_context_json",
        "delivery_context_json",
        "work_missing_fields_json",
    }.issubset(field_names)

    work_status_values = {choice[0] for choice in WorkWhiteboard.WORK_STATUS_CHOICES}
    assert work_status_values == {
        "draft",
        "intake",
        "ready_for_planning",
        "planning",
        "in_progress",
        "review",
        "delivery",
        "measurement",
        "closed",
    }

    root = Path(__file__).resolve().parents[4]
    repository = (
        root / "frontend" / "domain" / "repositories" / "whiteboardRepository.ts"
    ).read_text(encoding="utf-8")
    api = (root / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")

    assert "readyForPlanning" in repository
    assert "startPlanning" in repository
    assert "getPlanning" in repository
    assert "synthesizePlanning" in repository
    assert "Compatibility helper" in repository
    assert "/ready-for-planning" in api
    assert "/start-planning" in api
    assert "/planning" in api
    assert "/planning/synthesize" in api


def _markdown_section(document: str, heading: str) -> str:
    start = document.index(heading)
    next_heading = document.find("\n## ", start + len(heading))
    if next_heading == -1:
        return document[start:]
    return document[start:next_heading]


def test_company_ops_docs_keep_vertical_terms_out_of_generic_sections():
    root = Path(__file__).resolve().parents[4]
    document = (root / "docs" / "ops" / "company-operating-loop.md").read_text(encoding="utf-8")
    generic_objects = _markdown_section(document, "## Generic Objects").lower()
    operating_templates = _markdown_section(document, "## Operating Templates").lower()
    vertical_terms = [
        "sell-through",
        "paid order",
        "paid_order",
        "stockout",
        "fulfillment",
        "content",
        "procurement",
    ]

    for term in vertical_terms:
        assert term not in generic_objects

    for line in operating_templates.splitlines():
        if not any(term in line for term in vertical_terms):
            continue
        assert (
            "compatibility" in line or "domain-specific" in line or "operation type values" in line
        )
