from __future__ import annotations

import json
from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command

from infrastructure.orm.management.commands.seed_atlas_marketing_company import (
    DEFAULT_COMPANY_NAME,
    DEFAULT_EMAIL,
    DEFAULT_ORG_NAME,
    DEFAULT_PACK_ID,
    EXTERNAL_REF,
    EXTERNAL_SOURCE,
)
from infrastructure.orm.models import (
    AssertionRecord,
    Asset,
    AssetVersion,
    CompanyOperatingModelInstallation,
    CompanyProgram,
    CompanySignal,
    EvaluationRun,
    Graph,
    MetricSnapshot,
    Organization,
    OrganizationMembership,
    PeriodicReviewDefinition,
    ProgramStageState,
    ReportRun,
    Run,
    StateProjection,
    User,
)


def _run_command(*args: str) -> dict[str, Any]:
    output = StringIO()
    call_command(
        "seed_atlas_marketing_company",
        *args,
        output_json=True,
        stdout=output,
    )
    payload = json.loads(output.getvalue())
    assert isinstance(payload, dict)
    return payload


@pytest.mark.django_db
def test_seed_atlas_marketing_company_creates_pack_backed_demo_state():
    payload = _run_command()

    user = User.objects.get(email=DEFAULT_EMAIL)
    organization = Organization.objects.get(id=payload["organization_id"])
    company = Graph.objects.get(id=payload["company_id"])
    installation = CompanyOperatingModelInstallation.objects.get(company=company)
    program = CompanyProgram.objects.get(id=payload["program_id"])

    assert organization.name == DEFAULT_ORG_NAME
    assert OrganizationMembership.objects.get(user=user, organization=organization).role == "owner"
    assert company.name == DEFAULT_COMPANY_NAME
    assert company.external_source == EXTERNAL_SOURCE
    assert company.external_ref == EXTERNAL_REF
    assert installation.pack_id == DEFAULT_PACK_ID
    assert installation.config_json["selected_services"]
    assert program.display_label == "Engagement"
    assert ProgramStageState.objects.filter(program=program).count() == 12
    assert (
        ProgramStageState.objects.get(program=program, stage_id="stage_01_client_inputs").status
        == "in_progress"
    )
    assert Run.objects.count() == 0

    assertions = AssertionRecord.objects.filter(company=company)
    assert assertions.count() == 5
    assert (
        assertions.filter(kind="FACT", validation_status="validated", pack_label="Stone").count()
        == 2
    )
    assert not assertions.exclude(kind="FACT").filter(validation_status="validated").exists()

    artifact = Asset.objects.get(id=payload["artifact_id"])
    assert artifact.metadata_json["artifact_type"] == "intake_summary"
    assert AssetVersion.objects.filter(asset=artifact).count() == 1

    projection = StateProjection.objects.get(id=payload["state_projection_id"])
    assert projection.display_label == "Living Instruction File"
    assert projection.projection_type == "currently_true_state"
    assert len(projection.json_state["validated_facts"]) == 2


@pytest.mark.django_db
def test_seed_atlas_marketing_company_is_idempotent():
    first = _run_command()
    second = _run_command()

    assert second["user_id"] == first["user_id"]
    assert second["organization_id"] == first["organization_id"]
    assert second["company_id"] == first["company_id"]
    assert second["program_id"] == first["program_id"]
    assert second["artifact_id"] == first["artifact_id"]
    assert User.objects.filter(email=DEFAULT_EMAIL).count() == 1
    assert (
        Graph.objects.filter(external_source=EXTERNAL_SOURCE, external_ref=EXTERNAL_REF).count()
        == 1
    )
    assert CompanyProgram.objects.count() == 1
    assert AssertionRecord.objects.count() == 5
    assert Asset.objects.count() == 1
    assert StateProjection.objects.count() == 1


@pytest.mark.django_db
def test_seed_atlas_marketing_company_full_demo_creates_parts_7_to_12_state():
    payload = _run_command("--full-demo")
    company = Graph.objects.get(id=payload["company_id"])
    program = CompanyProgram.objects.get(id=payload["program_id"])

    assert payload["generated_stage_outputs"]
    assert payload["validation_decision_ids"]
    assert payload["rework_plan_id"]
    assert ProgramStageState.objects.filter(program=program).count() == 12
    assert Asset.objects.filter(
        company=company, metadata_json__artifact_type="growth_plan"
    ).exists()
    assert Asset.objects.filter(
        company=company, metadata_json__artifact_type="yearly_planner"
    ).exists()
    assert Asset.objects.filter(
        company=company, metadata_json__artifact_type="search_strategy"
    ).exists()
    assert Asset.objects.filter(company=company, metadata_json__artifact_type="ad_copy").exists()
    assert Asset.objects.filter(
        company=company, metadata_json__artifact_type="creative_instruction"
    ).exists()
    assert Asset.objects.filter(
        company=company, metadata_json__artifact_type="quarterly_brief"
    ).exists()
    assert CompanySignal.objects.filter(company=company, source="program_stage_output").count() == 3
    assert StateProjection.objects.get(id=payload["state_projection_id"]).json_state["signals"]
    assert payload["atlas_service_model"]["evaluation_id"]
    assert payload["periodic_loop"]["review_definition"]["template_id"] == "atlas_monthly_review.v1"
    assert len(payload["periodic_loop"]["metric_snapshot_ids"]) == 2
    assert len(payload["periodic_loop"]["evaluation_run_ids"]) == 2
    assert len(payload["periodic_loop"]["report_run_ids"]) == 2
    assert payload["periodic_loop"]["trend_summary"]["recovered"]
    assert "brand_audit" in payload["atlas_service_model"]["artifact_types"]
    assert "monthly_report" in payload["atlas_service_model"]["artifact_types"]
    assert "client_service_history_entry" in payload["atlas_service_model"]["artifact_types"]
    assert EvaluationRun.objects.filter(
        company=company,
        profile_key="atlas_monthly_kpi_scorecard.v1",
    ).exists()
    assert StateProjection.objects.filter(
        company=company,
        program=program,
        projection_type="client_service_history",
    ).exists()
    assert PeriodicReviewDefinition.objects.filter(company=company).count() >= 1
    assert MetricSnapshot.objects.filter(company=company, program=program).count() == 2
    assert ReportRun.objects.filter(company=company, program=program).count() == 2
    assert payload["periodic_loop"]["scheduling"]["due_review_ids"]
    assert payload["periodic_loop"]["scheduling"]["overdue_review_ids"]
    assert payload["periodic_loop"]["scheduling"]["missing_metric_signal_ids"]

    second = _run_command("--full-demo")
    assert second["company_id"] == payload["company_id"]
    assert (
        Asset.objects.filter(company=company, metadata_json__artifact_type="growth_plan").count()
        == 1
    )
    assert CompanySignal.objects.filter(company=company, source="program_stage_output").count() == 3
    assert (
        EvaluationRun.objects.filter(
            company=company,
            profile_key="atlas_monthly_kpi_scorecard.v1",
        ).count()
        == 3
    )
    assert MetricSnapshot.objects.filter(company=company, program=program).count() == 2
    assert ReportRun.objects.filter(company=company, program=program).count() == 2


@pytest.mark.django_db
def test_seed_atlas_marketing_company_can_create_periodic_scheduling_states():
    payload = _run_command(
        "--with-periodic-scheduling",
        "--with-missing-metrics",
        "--with-overdue-review",
    )
    company = Graph.objects.get(id=payload["company_id"])
    scheduling = payload["periodic_loop"]["scheduling"]

    assert scheduling["due_review_ids"]
    assert scheduling["overdue_review_ids"]
    assert scheduling["missing_metric_signal_ids"]
    assert scheduling["missing_metric_blockers"]
    assert PeriodicReviewDefinition.objects.filter(company=company).count() >= 3
    assert CompanySignal.objects.filter(
        company=company,
        source="periodic_review_input_gap",
    ).exists()


@pytest.mark.django_db
def test_seed_atlas_marketing_company_can_create_scorecard_and_service_history_only():
    payload = _run_command(
        "--with-atlas-service-model",
        "--with-monthly-report",
        "--with-kpi-scorecard",
        "--with-client-history",
    )
    company = Graph.objects.get(id=payload["company_id"])
    program = CompanyProgram.objects.get(id=payload["program_id"])

    assert payload["atlas_service_model"]["scorecard_levels"]["social_engagement_rate"] == (
        "bad_or_risky"
    )
    assert payload["atlas_service_model"]["scorecard_levels"]["email_open_rate"] == "acceptable"
    assert payload["atlas_service_model"]["scorecard_levels"]["roas"] == "good"
    assert Asset.objects.filter(
        company=company, metadata_json__artifact_type="monthly_report"
    ).exists()
    assert CompanySignal.objects.filter(company=company, source="evaluation_scorecard").exists()
    assert StateProjection.objects.filter(
        company=company,
        program=program,
        projection_type="client_service_history",
    ).exists()
