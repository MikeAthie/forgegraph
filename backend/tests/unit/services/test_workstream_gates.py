from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from application.services.deployment_orchestration import list_available_deployment_policies
from application.services.operating_model_packs import install_pack_for_company
from application.services.performance_orchestration import list_available_performance_policies
from application.services.routing import list_department_inbox
from application.services.workstream_gates import (
    WorkstreamGateError,
    complete_workstream,
    evaluate_gate,
    get_phase_contract,
    list_available_phase_definitions,
    list_phase_workstreams,
    start_phase_for_whiteboard,
    synthesize_phase_outputs,
)
from infrastructure.orm.models import (
    ApprovalTask,
    Asset,
    CompanyAccessPolicy,
    CompanyAssignment,
    CompanySignal,
    DepartmentMembership,
    Graph,
    Organization,
    OrganizationMembership,
    Run,
    StateProjection,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)
from tests.fixtures.workstream_phase_policies import (
    atlas_content_production_policy,
    failing_atlas_content_scorecard,
    legal_contract_review_policy,
    passing_atlas_content_scorecard,
)

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str, role: str = "member") -> User:
    user = User.objects.create_user(email=email, password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(organization=org, user=user, role=role, is_default=True)
    return user


def _company(org: Organization, owner: User, *, name: str = "Legacy Eyewear") -> Graph:
    company = cast(
        Graph,
        Graph.objects.create(owner=owner, organization=org, name=name, description="Test company"),
    )
    CompanyAccessPolicy.objects.create(
        organization=org,
        company=company,
        assignment_required=True,
        org_admin_access_enabled=True,
    )
    return company


def _assign(org: Organization, company: Graph, user: User, role: str = "member") -> None:
    CompanyAssignment.objects.create(
        organization=org,
        company=company,
        user=user,
        role=role,
        status="active",
    )


def _whiteboard(
    company: Graph, owner: User, *, status: str = WorkWhiteboard.STATUS_READY_FOR_STRATEGY
) -> WorkWhiteboard:
    organization = company.organization
    assert organization is not None
    return WorkWhiteboard.objects.create(
        organization=organization,
        company=company,
        status=status,
        request_type="service_request",
        client_name=company.name,
        request_summary="Company-scoped work request.",
        objective="Complete the configured phase.",
        completion_score=100,
        created_by=owner,
    )


def _complete_all(user: User, whiteboard: WorkWhiteboard, definition: dict[str, object]) -> None:
    phase_id = str(definition["phase_id"])
    workstreams = cast(list[object], definition["workstreams"])
    for item in workstreams:
        workstream = cast(dict[str, object], item)
        complete_workstream(
            user=user,
            whiteboard=whiteboard,
            phase_id=phase_id,
            workstream_id=str(workstream["id"]),
            result={"summary": f"{workstream['id']} complete"},
            definition=definition,
        )


def _dependency_phase_policy() -> dict[str, object]:
    return {
        "phase_id": "dependency_ops.v1.launch",
        "source_policy_id": "dependency_ops.v1.launch",
        "pack_id": "dependency_ops.v1",
        "phase_name": "Dependency Launch",
        "workstreams": [
            {
                "id": "foundation",
                "name": "Foundation",
                "department": "strategy",
                "required": True,
            },
            {
                "id": "legal",
                "name": "Legal",
                "department": "legal",
                "required": True,
            },
            {
                "id": "copy",
                "name": "Copy",
                "department": "content",
                "required": True,
                "dependencies": [
                    {
                        "workstream_id": "foundation",
                        "type": "soft",
                        "required_status": "completed",
                    }
                ],
            },
            {
                "id": "content",
                "name": "Content",
                "department": "content",
                "required": True,
                "dependencies": [
                    {"workstream_id": "copy", "type": "hard", "required_status": "completed"},
                    {
                        "workstream_id": "legal",
                        "type": "hard",
                        "required_status": "completed",
                    },
                ],
            },
            {
                "id": "launch",
                "name": "Launch",
                "department": "deployment",
                "required": True,
                "dependencies": ["content"],
            },
        ],
    }


def test_phase_definition_creates_whiteboard_scoped_workstreams_idempotently() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "phase-start@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    whiteboard = _whiteboard(company, owner)
    definition = atlas_content_production_policy()

    first = start_phase_for_whiteboard(
        user=owner,
        whiteboard=whiteboard,
        phase_id=str(definition["phase_id"]),
        definition=definition,
    )
    second = start_phase_for_whiteboard(
        user=owner,
        whiteboard=whiteboard,
        phase_id=str(definition["phase_id"]),
        definition=definition,
    )

    assert len(first["workstreams"]) == 8
    assert len(second["workstreams"]) == 8
    assert (
        TaskRoutingRecord.objects.filter(
            company=company,
            metadata_json__whiteboard_id=str(whiteboard.id),
            metadata_json__phase_id=definition["phase_id"],
        ).count()
        == 8
    )
    assert (
        Run.objects.filter(
            input_json__whiteboard_id=str(whiteboard.id),
            input_json__phase_id=definition["phase_id"],
        ).count()
        == 8
    )
    workstream_assets = Asset.objects.filter(
        company=company,
        source_key__startswith=f"whiteboard:{whiteboard.id}:phase:{definition['phase_id']}:workstream:",
    )
    assert workstream_assets.count() == 8
    assert all(asset.versions.exists() for asset in workstream_assets)
    assert StateProjection.objects.filter(
        company=company, projection_type__startswith="workstream_phase:"
    ).exists()


def test_phase_dependencies_block_provision_and_auto_unblock_from_backend_state() -> None:
    org = Organization.objects.create(name="Dependency Ops")
    owner = _user(org, "phase-dependencies@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    whiteboard = _whiteboard(company, owner)
    definition = _dependency_phase_policy()
    phase_id = str(definition["phase_id"])

    contract = start_phase_for_whiteboard(
        user=owner,
        whiteboard=whiteboard,
        phase_id=phase_id,
        definition=definition,
    )
    workstreams = {item["id"]: item for item in contract["workstreams"]}

    assert workstreams["foundation"]["status"] == "queued"
    assert workstreams["copy"]["status"] == "queued"
    assert workstreams["copy"]["dependencies"][0]["type"] == "soft"
    assert workstreams["copy"]["dependency_state"]["status"] == "provisional"
    assert workstreams["content"]["status"] == "blocked"
    assert workstreams["content"]["dependency_state"]["blockers"]
    assert workstreams["launch"]["dependencies"][0]["type"] == "hard"

    with pytest.raises(WorkstreamGateError) as blocked:
        complete_workstream(
            user=owner,
            whiteboard=whiteboard,
            phase_id=phase_id,
            workstream_id="content",
            result={"summary": "too early"},
            definition=definition,
        )
    assert blocked.value.code == "workstream_dependencies_blocked"

    complete_workstream(
        user=owner,
        whiteboard=whiteboard,
        phase_id=phase_id,
        workstream_id="foundation",
        result={"summary": "foundation complete"},
        definition=definition,
    )
    refreshed = {
        item["id"]: item
        for item in list_phase_workstreams(
            whiteboard=whiteboard, phase_id=phase_id, definition=definition
        )
    }
    assert refreshed["copy"]["status"] == "queued"
    assert refreshed["copy"]["dependency_state"]["status"] == "ready"
    assert refreshed["content"]["status"] == "blocked"

    for workstream_id in ("legal", "copy"):
        complete_workstream(
            user=owner,
            whiteboard=whiteboard,
            phase_id=phase_id,
            workstream_id=workstream_id,
            result={"summary": f"{workstream_id} complete"},
            definition=definition,
        )
    refreshed = {
        item["id"]: item
        for item in list_phase_workstreams(
            whiteboard=whiteboard, phase_id=phase_id, definition=definition
        )
    }
    assert refreshed["content"]["status"] == "queued"

    with pytest.raises(WorkstreamGateError) as incomplete:
        synthesize_phase_outputs(
            user=owner,
            whiteboard=whiteboard,
            phase_id=phase_id,
            definition=definition,
        )
    assert incomplete.value.code == "workstreams_incomplete"

    complete_workstream(
        user=owner,
        whiteboard=whiteboard,
        phase_id=phase_id,
        workstream_id="content",
        result={"summary": "content complete"},
        definition=definition,
    )
    refreshed = {
        item["id"]: item
        for item in list_phase_workstreams(
            whiteboard=whiteboard, phase_id=phase_id, definition=definition
        )
    }
    assert refreshed["launch"]["status"] == "queued"
    complete_workstream(
        user=owner,
        whiteboard=whiteboard,
        phase_id=phase_id,
        workstream_id="launch",
        result={"summary": "launch complete"},
        definition=definition,
    )

    asset, version = synthesize_phase_outputs(
        user=owner,
        whiteboard=whiteboard,
        phase_id=phase_id,
        definition=definition,
    )
    assert asset.id
    assert version.id


def test_digital_marketing_pack_loads_agency_phase_deployment_and_performance_policies() -> None:
    org = Organization.objects.create(name="Pack Policies")
    owner = _user(org, "phase-pack-policies@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    whiteboard = _whiteboard(company, owner)
    install_pack_for_company(
        company=company,
        user=owner,
        pack_id="digital_marketing_pro.v1",
        config={"skip_graph_version": True},
        role="primary",
    )

    phase_ids = {
        item["phase_id"] for item in list_available_phase_definitions(whiteboard=whiteboard)
    }
    deployment_ids = {
        item["policy_id"] for item in list_available_deployment_policies(whiteboard=whiteboard)
    }
    performance_ids = {
        item["policy_id"] for item in list_available_performance_policies(whiteboard=whiteboard)
    }

    assert "digital_marketing_pro.v1.atlas_agency_work_graph" in phase_ids
    assert "digital_marketing_pro.v1.atlas_launch_deployment" in deployment_ids
    assert "digital_marketing_pro.v1.atlas_performance_review" in performance_ids


def test_atlas_content_policy_passes_into_approval_with_generic_primitives() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "phase-atlas-pass@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    definition = atlas_content_production_policy()
    phase_id = str(definition["phase_id"])
    passing_whiteboard = _whiteboard(company, owner)
    start_phase_for_whiteboard(
        user=owner, whiteboard=passing_whiteboard, phase_id=phase_id, definition=definition
    )
    _complete_all(owner, passing_whiteboard, definition)
    synthesize_phase_outputs(
        user=owner, whiteboard=passing_whiteboard, phase_id=phase_id, definition=definition
    )
    evaluation = evaluate_gate(
        user=owner,
        whiteboard=passing_whiteboard,
        phase_id=phase_id,
        scorecard=passing_atlas_content_scorecard(),
        definition=definition,
    )
    passing_whiteboard.refresh_from_db()

    assert evaluation.status == "PASS"
    assert passing_whiteboard.status == WorkWhiteboard.STATUS_IN_APPROVAL
    approval = ApprovalTask.objects.get(run=evaluation.operation)
    assert approval.payload["whiteboard_id"] == str(passing_whiteboard.id)
    routing_record = TaskRoutingRecord.objects.get(
        company=company,
        metadata_json__whiteboard_id=str(passing_whiteboard.id),
        metadata_json__gate_result="pass",
    )
    assert routing_record.to_department.slug == "client-services"


def test_atlas_content_policy_failure_routes_revision_signal_without_approval() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "phase-atlas-fail@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    definition = atlas_content_production_policy()
    phase_id = str(definition["phase_id"])
    failing_whiteboard = _whiteboard(company, owner)
    start_phase_for_whiteboard(
        user=owner, whiteboard=failing_whiteboard, phase_id=phase_id, definition=definition
    )
    _complete_all(owner, failing_whiteboard, definition)
    synthesize_phase_outputs(
        user=owner, whiteboard=failing_whiteboard, phase_id=phase_id, definition=definition
    )
    failing_eval = evaluate_gate(
        user=owner,
        whiteboard=failing_whiteboard,
        phase_id=phase_id,
        scorecard=failing_atlas_content_scorecard(),
        definition=definition,
    )
    failing_whiteboard.refresh_from_db()

    assert failing_eval.status == "BLOCK"
    assert failing_whiteboard.status == WorkWhiteboard.STATUS_IN_CONTENT
    assert not ApprovalTask.objects.filter(run=failing_eval.operation).exists()
    signal = CompanySignal.objects.get(
        company=company, metadata_json__whiteboard_id=str(failing_whiteboard.id)
    )
    assert set(signal.metadata_json["weak_areas"]) == {"strategy_alignment", "legal_compliance"}
    routing_record = TaskRoutingRecord.objects.get(
        company=company,
        metadata_json__whiteboard_id=str(failing_whiteboard.id),
        metadata_json__gate_result="fail",
    )
    assert routing_record.to_department.slug == "content-revision"
    assert routing_record.status == "blocked"


def test_core_services_do_not_hardcode_atlas_content_criteria() -> None:
    service_root = Path(__file__).resolve().parents[3] / "application" / "services"
    service_text = "\n".join(
        (service_root / filename).read_text(encoding="utf-8")
        for filename in ("workstream_gates.py", "strategy_orchestration.py")
    )

    for forbidden in (
        "brand_alignment",
        "strategy_alignment",
        "channel_fit",
        "claim_support",
        "legal_compliance",
        "format_compliance",
        "execution_readiness",
        "copywriting",
        "whatsapp_script",
        "content_quality_gate",
    ):
        assert forbidden not in service_text


def test_non_marketing_fixture_works_with_different_criteria() -> None:
    org = Organization.objects.create(name="Legal Ops")
    owner = _user(org, "phase-legal@example.com", "owner")
    company = _company(org, owner, name="Contract Client")
    _assign(org, company, owner, "member")
    whiteboard = _whiteboard(company, owner, status=WorkWhiteboard.STATUS_ONBOARDING)
    definition = legal_contract_review_policy()
    phase_id = str(definition["phase_id"])

    start_phase_for_whiteboard(
        user=owner, whiteboard=whiteboard, phase_id=phase_id, definition=definition
    )
    _complete_all(owner, whiteboard, definition)
    synthesize_phase_outputs(
        user=owner, whiteboard=whiteboard, phase_id=phase_id, definition=definition
    )
    evaluation = evaluate_gate(
        user=owner,
        whiteboard=whiteboard,
        phase_id=phase_id,
        scorecard={"missing_required_clause_count": 0, "high_risk_clause_count": 1},
        definition=definition,
    )

    assert evaluation.status == "PASS"
    assert {
        item["id"]
        for item in list_phase_workstreams(
            whiteboard=whiteboard, phase_id=phase_id, definition=definition
        )
    } == {
        "clause_extraction",
        "risk_review",
    }


def test_department_membership_without_company_access_cannot_see_phase_routing() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "phase-rbac-owner@example.com", "owner")
    department_user = _user(org, "phase-rbac-dept@example.com", "member")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    whiteboard = _whiteboard(company, owner)
    definition = atlas_content_production_policy()

    start_phase_for_whiteboard(
        user=owner,
        whiteboard=whiteboard,
        phase_id=str(definition["phase_id"]),
        definition=definition,
    )
    record = TaskRoutingRecord.objects.filter(
        metadata_json__whiteboard_id=str(whiteboard.id)
    ).first()
    assert record is not None
    DepartmentMembership.objects.create(
        organization=org,
        department=record.to_department,
        user=department_user,
        role="member",
        status="active",
    )

    assert (
        list(list_department_inbox(user=department_user, department_id=record.to_department_id))
        == []
    )


def test_viewer_contract_omits_internal_gate_and_routing_details() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "phase-view-owner@example.com", "owner")
    viewer = _user(org, "phase-viewer@example.com", "viewer")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, viewer, "viewer")
    whiteboard = _whiteboard(company, owner)
    definition = atlas_content_production_policy()
    phase_id = str(definition["phase_id"])
    start_phase_for_whiteboard(
        user=owner, whiteboard=whiteboard, phase_id=phase_id, definition=definition
    )

    viewer_contract = get_phase_contract(
        user=viewer, whiteboard=whiteboard, phase_id=phase_id, definition=definition
    )
    operator_contract = get_phase_contract(
        user=owner, whiteboard=whiteboard, phase_id=phase_id, definition=definition
    )

    assert "criteria" not in viewer_contract["gate"]
    assert "department_id" not in viewer_contract["workstreams"][0]
    assert viewer_contract["allowed_actions"] == []
    assert "criteria" in operator_contract["gate"]
    assert "department_id" in operator_contract["workstreams"][0]


def test_phase_state_is_scoped_to_one_whiteboard() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "phase-scope@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    definition = atlas_content_production_policy()
    phase_id = str(definition["phase_id"])
    first_whiteboard = _whiteboard(company, owner)
    second_whiteboard = _whiteboard(company, owner)

    start_phase_for_whiteboard(
        user=owner, whiteboard=first_whiteboard, phase_id=phase_id, definition=definition
    )
    start_phase_for_whiteboard(
        user=owner, whiteboard=second_whiteboard, phase_id=phase_id, definition=definition
    )
    first_contract = get_phase_contract(
        user=owner, whiteboard=first_whiteboard, phase_id=phase_id, definition=definition
    )
    second_contract = get_phase_contract(
        user=owner, whiteboard=second_whiteboard, phase_id=phase_id, definition=definition
    )

    first_asset_ids = {item["asset_id"] for item in first_contract["workstreams"]}
    second_asset_ids = {item["asset_id"] for item in second_contract["workstreams"]}
    assert first_asset_ids
    assert second_asset_ids
    assert first_asset_ids.isdisjoint(second_asset_ids)
    assert all(
        str(first_whiteboard.id) in key
        for key in Asset.objects.filter(id__in=first_asset_ids).values_list("source_key", flat=True)
    )
