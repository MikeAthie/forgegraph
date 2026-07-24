from __future__ import annotations

import pytest

from application.services.career_ops_first_prompt import run_career_ops_first_prompt
from application.services.company_run_task_routing import TASK_SNAPSHOT_METADATA_KEY
from infrastructure.orm.models import (
    CompanyOpportunity,
    CompanyProgram,
    CompanySignal,
    DepartmentRegistry,
    Graph,
    ProgramStageState,
    TaskRoutingRecord,
    WorkWhiteboard,
)

pytestmark = pytest.mark.django_db

CV_TEXT = """
Miguel Athie
Mexico City, MX
Backend-leaning Software Engineer building production APIs, data systems, AI-native workflows,
async service architectures, Python, FastAPI, Django, Go, PostgreSQL, Redis, Celery, RAG,
LangGraph, agentic workflows, observability, tests, Prometheus, React, Next.js and TypeScript.
Built Lex Toolkit AI agents for legal workflows and ForgeGraph, an AI-native backend platform
for agentic workflows, memory, summaries, retry logic, dry-run execution, batching and admin endpoints.
"""


def test_first_prompt_bootstraps_company_whiteboard_kanban_and_job_results(user) -> None:
    result = run_career_ops_first_prompt(
        actor=user,
        cv_text=CV_TEXT,
        constraints={
            "citizenships": ["Mexico", "Spain"],
            "work_authorized_regions": ["Mexico", "European Union", "Spain"],
            "excluded_regions": ["United States"],
            "no_us_work_visa": True,
            "willing_to_relocate": True,
            "target_salary_usd": 60000,
            "salary_flexible": True,
        },
        prompt="Find possible jobs for me. Start with a limited result list and write it to the whiteboard.",
        idempotency_key="career-ops-first-prompt-test",
    )

    company = Graph.objects.get(id=result.company_id)
    assert company.external_source == "career_ops"
    assert "Miguel Athie" in company.name

    department_slugs = set(
        DepartmentRegistry.objects.filter(
            organization=company.organization,
            metadata_json__career_ops__company_id=str(company.id),
        ).values_list("slug", flat=True)
    )
    assert department_slugs >= {
        "candidate-profile-strategy",
        "market-role-discovery",
        "opportunity-evaluation",
        "pipeline-integrity-analytics",
    }

    whiteboard = WorkWhiteboard.objects.get(id=result.whiteboard_id)
    assert whiteboard.company_id == company.id
    assert whiteboard.request_type == "career_ops_discovery"
    assert whiteboard.work_status == WorkWhiteboard.WORK_STATUS_IN_PROGRESS
    assert whiteboard.known_facts_json["candidate"]["name"] == "Miguel Athie"
    assert whiteboard.constraints_json["work_authorized_regions"] == [
        "Mexico",
        "European Union",
        "Spain",
    ]
    assert whiteboard.metadata_json["career_ops"]["first_prompt"]["result_count"] == 5
    assert len(whiteboard.metadata_json["career_ops"]["first_prompt"]["postings"]) == 5

    program = CompanyProgram.objects.get(id=result.program_id)
    assert program.company_id == company.id
    assert program.pack_id == "career_ops.v1"
    assert program.template_id == "career_ops_first_prompt_discovery"

    stages = list(ProgramStageState.objects.filter(program=program).order_by("sequence"))
    assert [stage.stage_id for stage in stages] == [
        "candidate_profile_intake",
        "market_role_discovery",
        "opportunity_shortlist",
        "candidate_review",
    ]

    cards = list(TaskRoutingRecord.objects.filter(company=company).order_by("created_at"))
    assert len(cards) == 4
    assert {card.status for card in cards} >= {"completed", "queued"}
    assert all(
        card.metadata_json["company_run_task"]["program_id"] == str(program.id) for card in cards
    )

    snapshot = whiteboard.metadata_json[TASK_SNAPSHOT_METADATA_KEY]
    assert snapshot["schema_version"] == "company_run_task_snapshot_v1"
    assert [task["stage_id"] for task in snapshot["tasks"]] == [stage.stage_id for stage in stages]
    assert snapshot["tasks"][1]["outputs"][0]["type"] == "possible_job_list"
    assert len(snapshot["tasks"][1]["outputs"][0]["postings"]) == 5

    assert len(result.postings) == 5
    assert CompanySignal.objects.filter(company=company, domain_context="career_ops").count() == 5
    opportunities = list(CompanyOpportunity.objects.filter(company=company).order_by("title"))
    assert len(opportunities) == 5
    assert all(opp.metadata_json["career_ops"]["visa_ok"] is True for opp in opportunities)
    assert all(
        "United States" not in opp.metadata_json["career_ops"]["locations"] for opp in opportunities
    )
    assert any(
        "Agent" in posting["title"] or "AI" in posting["title"] for posting in result.postings
    )


def test_first_prompt_is_idempotent_for_same_actor_and_key(user) -> None:
    kwargs = {
        "actor": user,
        "cv_text": CV_TEXT,
        "constraints": {
            "citizenships": ["Mexico", "Spain"],
            "work_authorized_regions": ["Mexico", "European Union"],
            "excluded_regions": ["United States"],
            "target_salary_usd": 60000,
        },
        "prompt": "Find possible jobs and write them to the whiteboard.",
        "idempotency_key": "career-ops-first-prompt-idem",
    }

    first = run_career_ops_first_prompt(**kwargs)
    second = run_career_ops_first_prompt(**kwargs)

    assert first.company_id == second.company_id
    assert first.whiteboard_id == second.whiteboard_id
    assert first.program_id == second.program_id
    assert len(second.postings) == 5
    assert (
        Graph.objects.filter(
            external_source="career_ops", external_ref="career-ops-first-prompt-idem"
        ).count()
        == 1
    )
    assert (
        WorkWhiteboard.objects.filter(
            idempotency_key="career-ops:first_prompt:career-ops-first-prompt-idem"
        ).count()
        == 1
    )
    assert (
        CompanyProgram.objects.filter(
            external_key="career-ops:first-prompt:career-ops-first-prompt-idem"
        ).count()
        == 1
    )
