from __future__ import annotations

import json
from typing import cast

import pytest

from application.services.atlas_retention_operator_workflow import (
    ATLAS_DEPARTMENT_SLUGS,
    ATLAS_RETENTION_STAGES,
    TEMPLATE_ID,
    WORKFLOW_METADATA_KEY,
    bootstrap_atlas_retention_operator_workflow,
)
from application.services.company_run_task_routing import (
    TASK_METADATA_KEY,
    TASK_SNAPSHOT_METADATA_KEY,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    CompanyProgram,
    DepartmentRegistry,
    Graph,
    Organization,
    ProgramStageState,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

pytestmark = pytest.mark.django_db


def _organization(user: User) -> Organization:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    return organization


def _company(user: User) -> Graph:
    organization = _organization(user)
    return cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name="Atlas Test Client",
            description="Retention workflow test company.",
        ),
    )


def _whiteboard(user: User, company: Graph) -> WorkWhiteboard:
    return WorkWhiteboard.objects.create(
        organization=company.organization,
        company=company,
        status=WorkWhiteboard.STATUS_IN_STRATEGY,
        work_status=WorkWhiteboard.WORK_STATUS_PLANNING,
        request_type="atlas_retention",
        project_name="June retention sprint",
        objective="Win back recent buyers with a proof-driven retention sprint.",
        created_by=user,
    )


def _workflow_snapshot() -> dict[str, object]:
    return {
        "stage_statuses": {"intake": "completed", "audit": "in_progress"},
        "campaign_package": {
            "deliverables": [
                {
                    "id": "campaign-package-1",
                    "title": "June Retention Campaign Package",
                    "summary": "Offer, audience, and lifecycle sequence are ready.",
                }
            ]
        },
        "assets": [
            {
                "asset_version_id": "asset-version-1",
                "title": "Winback carousel",
                "summary": "Approved creative for paid and CRM channels.",
            }
        ],
        "approval_packet": {
            "id": "approval-packet-1",
            "title": "Client approval packet",
            "status": "ready",
        },
        "lead_tracking": {
            "leads": [
                {
                    "lead_id": "lead-1",
                    "name": "Retail buyer",
                    "status": "follow_up_needed",
                }
            ]
        },
        "weekly_report": {
            "report_run_id": "report-run-1",
            "title": "Week 1 proof report",
            "summary": "Revenue proof and next-step recommendation.",
        },
    }


def test_bootstrap_creates_idempotent_atlas_operator_workflow(user):
    company = _company(user)
    whiteboard = _whiteboard(user, company)

    result = bootstrap_atlas_retention_operator_workflow(
        whiteboard,
        user=user,
        workflow_snapshot=_workflow_snapshot(),
        refresh_read_models=False,
    )
    again = bootstrap_atlas_retention_operator_workflow(
        whiteboard,
        user=user,
        workflow_snapshot=_workflow_snapshot(),
        refresh_read_models=False,
    )

    program = cast(CompanyProgram, result["program"])
    assert cast(CompanyProgram, again["program"]).id == program.id
    assert program.template_id == TEMPLATE_ID
    assert program.external_key.startswith(f"{TEMPLATE_ID}:company:{company.id}")
    assert CompanyProgram.objects.filter(company=company, template_id=TEMPLATE_ID).count() == 1
    assert ProgramStageState.objects.filter(program=program).count() == 10
    assert TaskRoutingRecord.objects.filter(company=company).count() == 10
    assert DepartmentRegistry.objects.filter(
        organization=company.organization,
        slug__in=ATLAS_DEPARTMENT_SLUGS,
    ).count() == len(ATLAS_DEPARTMENT_SLUGS)

    stage_ids = list(
        ProgramStageState.objects.filter(program=program)
        .order_by("sequence")
        .values_list("stage_id", flat=True)
    )
    assert stage_ids == [stage.stage_id for stage in ATLAS_RETENTION_STAGES]

    campaign_stage = ProgramStageState.objects.get(
        program=program,
        stage_id="campaign_design",
    )
    campaign_metadata = campaign_stage.state_json[WORKFLOW_METADATA_KEY]
    assert campaign_metadata["artifact_summaries"][0]["title"] == (
        "June Retention Campaign Package"
    )
    assert campaign_stage.state_json[TASK_METADATA_KEY]["outputs"][0]["type"] == (
        "atlas_retention_artifact"
    )

    records_by_stage = {
        record.metadata_json[TASK_METADATA_KEY]["stage_id"]: record
        for record in TaskRoutingRecord.objects.filter(company=company)
    }
    assert (
        records_by_stage["campaign_design"].metadata_json[WORKFLOW_METADATA_KEY][
            "artifact_summary_count"
        ]
        == 1
    )
    assert records_by_stage["asset_production"].to_department.slug == "brand_content"
    assert records_by_stage["follow_up_needed"].priority == "urgent"

    whiteboard.refresh_from_db()
    snapshot = whiteboard.metadata_json[TASK_SNAPSHOT_METADATA_KEY]
    assert snapshot["snapshot_source"] == "backend_db"
    assert snapshot["program_id"] == str(program.id)
    assert [task["stage_id"] for task in snapshot["tasks"]] == stage_ids
    report_task = next(task for task in snapshot["tasks"] if task["stage_id"] == "review_report")
    assert report_task["outputs"][0]["title"] == "Week 1 proof report"


def test_bootstrap_rebuilds_whiteboard_projection_from_durable_rows(user):
    company = _company(user)
    whiteboard = _whiteboard(user, company)
    result = bootstrap_atlas_retention_operator_workflow(
        whiteboard,
        user=user,
        workflow_snapshot=_workflow_snapshot(),
        refresh_read_models=False,
    )
    program = cast(CompanyProgram, result["program"])
    whiteboard.metadata_json = {"lost_cache_marker": True}
    whiteboard.save(update_fields=["metadata_json", "updated_at"])

    rebuilt = bootstrap_atlas_retention_operator_workflow(
        whiteboard,
        user=user,
        refresh_read_models=False,
    )

    assert cast(CompanyProgram, rebuilt["program"]).id == program.id
    assert CompanyProgram.objects.filter(company=company, template_id=TEMPLATE_ID).count() == 1
    assert ProgramStageState.objects.filter(program=program).count() == 10
    assert TaskRoutingRecord.objects.filter(company=company).count() == 10

    report_stage = ProgramStageState.objects.get(
        program=program,
        stage_id="review_report",
    )
    report_summary = report_stage.state_json[WORKFLOW_METADATA_KEY]["artifact_summaries"][0]
    assert report_summary["title"] == "Week 1 proof report"

    whiteboard.refresh_from_db()
    assert "lost_cache_marker" in whiteboard.metadata_json
    snapshot = whiteboard.metadata_json[TASK_SNAPSHOT_METADATA_KEY]
    report_task = next(task for task in snapshot["tasks"] if task["stage_id"] == "review_report")
    assert report_task["outputs"][0]["title"] == "Week 1 proof report"


def test_bootstrap_ignores_snapshot_statuses_that_would_regress_durable_state(user):
    company = _company(user)
    whiteboard = _whiteboard(user, company)
    result = bootstrap_atlas_retention_operator_workflow(
        whiteboard,
        user=user,
        workflow_snapshot=_workflow_snapshot(),
        refresh_read_models=False,
    )
    program = cast(CompanyProgram, result["program"])
    ProgramStageState.objects.filter(program=program).update(status="completed")
    program.status = "completed"
    program.current_stage_id = "closed_commission"
    program.save(update_fields=["status", "current_stage_id", "updated_at"])

    bootstrap_atlas_retention_operator_workflow(
        whiteboard,
        user=user,
        workflow_snapshot={
            "program_status": "cancelled",
            "stage_statuses": {stage.stage_id: "not_started" for stage in ATLAS_RETENTION_STAGES},
        },
        refresh_read_models=False,
    )

    program.refresh_from_db()
    assert program.status == "completed"
    assert program.current_stage_id == "closed_commission"
    assert set(
        ProgramStageState.objects.filter(program=program).values_list("status", flat=True)
    ) == {"completed"}


def test_bootstrap_sanitizes_sensitive_source_thread_artifacts(user):
    company = _company(user)
    whiteboard = _whiteboard(user, company)

    bootstrap_atlas_retention_operator_workflow(
        whiteboard,
        user=user,
        workflow_snapshot={
            "source_thread": {
                "id": "session-abc-raw",
                "subject": "WhatsApp from +1 (555) 123-4567",
                "content": "Raw buyer message: please call +1 555 123 4567 now.",
                "session_id": "session-secret-value",
                "phone_number": "+1 555 999 0000",
            }
        },
        refresh_read_models=False,
    )

    whiteboard.refresh_from_db()
    encoded = json.dumps(
        {
            "whiteboard": whiteboard.metadata_json,
            "stages": list(
                ProgramStageState.objects.filter(company=company).values_list(
                    "state_json", flat=True
                )
            ),
            "tasks": list(
                TaskRoutingRecord.objects.filter(company=company).values_list(
                    "metadata_json", flat=True
                )
            ),
        }
    )
    assert "session-abc-raw" not in encoded
    assert "session-secret-value" not in encoded
    assert "Raw buyer message" not in encoded
    assert "+1 (555) 123-4567" not in encoded
    assert "+1 555 123 4567" not in encoded
    assert "+1 555 999 0000" not in encoded
    assert "[REDACTED_PHONE]" not in encoded
    assert "Source context captured" in encoded


def test_explicit_artifact_routing_covers_scale_and_closed_commission(user):
    company = _company(user)
    whiteboard = _whiteboard(user, company)

    bootstrap_atlas_retention_operator_workflow(
        whiteboard,
        user=user,
        workflow_snapshot={
            "artifacts": [
                {
                    "id": "scale-rec-1",
                    "type": "recommendation",
                    "title": "Scale the winback campaign",
                },
                {
                    "id": "commission-1",
                    "type": "commission_summary",
                    "title": "Closed commission ledger",
                },
            ]
        },
        refresh_read_models=False,
    )

    scale_stage = ProgramStageState.objects.get(program__company=company, stage_id="scale_kill")
    commission_stage = ProgramStageState.objects.get(
        program__company=company,
        stage_id="closed_commission",
    )
    assert (
        scale_stage.state_json[WORKFLOW_METADATA_KEY]["artifact_summaries"][0]["title"]
        == "Scale the winback campaign"
    )
    assert (
        commission_stage.state_json[WORKFLOW_METADATA_KEY]["artifact_summaries"][0]["title"]
        == "Closed commission ledger"
    )
