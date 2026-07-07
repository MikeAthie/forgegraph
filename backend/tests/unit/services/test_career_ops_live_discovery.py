from __future__ import annotations

import pytest

from application.services.career_ops_first_prompt import run_career_ops_first_prompt
from application.services.company_run_task_routing import TASK_SNAPSHOT_METADATA_KEY
from infrastructure.orm.models import (
    CompanyOpportunity,
    CompanySignal,
    TaskRoutingRecord,
    WorkWhiteboard,
)

pytestmark = pytest.mark.django_db

CV_TEXT = """
Miguel Athie
Backend-leaning Software Engineer building production APIs, data systems, AI-native workflows,
Python, FastAPI, Django, Go, PostgreSQL, Redis, Celery, RAG, LangGraph, agentic workflows,
observability, tests, Prometheus, React, Next.js and TypeScript. Built Lex Toolkit AI agents
for legal workflows and ForgeGraph, an AI-native backend platform for agentic workflows.
"""

CONSTRAINTS = {
    "citizenships": ["Mexico", "Spain"],
    "work_authorized_regions": ["Mexico", "European Union", "Spain"],
    "excluded_regions": ["United States"],
    "no_us_work_visa": True,
    "willing_to_relocate": True,
    "target_salary_usd": 60000,
    "salary_flexible": True,
}

LIVE_POSTINGS = [
    {
        "title": "Senior Backend Engineer, AI Platform",
        "company": "Madrid AI Systems",
        "location": "Madrid, Spain / EU Remote",
        "url": "https://jobs.example.test/madrid-ai-systems/backend-ai-platform?utm=ignored",
        "description": "Build Python FastAPI services, Django admin workflows, PostgreSQL, Redis, RAG and agentic workflow orchestration.",
        "salary_range_usd": [58000, 76000],
        "provider": "test_live_url_fixture",
    },
    {
        "title": "AI Workflow Engineer",
        "company": "Mexico Automation Labs",
        "location": "Mexico Remote",
        "url": "https://jobs.example.test/mexico-automation-labs/ai-workflow-engineer",
        "description": "Own Python APIs, async Celery jobs, LangGraph agents, observability, tests, and production service reliability.",
        "salary_range_usd": [50000, 66000],
        "provider": "test_live_url_fixture",
    },
    {
        "title": "Senior Backend Engineer",
        "company": "US Only Startup",
        "location": "United States Remote",
        "url": "https://jobs.example.test/us-only/startup-backend",
        "description": "US work authorization required. Python backend role.",
        "salary_range_usd": [120000, 160000],
        "provider": "test_live_url_fixture",
    },
    {
        "title": "Retail Store Manager",
        "company": "Spain Retail Co",
        "location": "Barcelona, Spain",
        "url": "https://jobs.example.test/spain-retail/store-manager",
        "description": "Manage in-store retail operations and inventory.",
        "salary_range_usd": [30000, 42000],
        "provider": "test_live_url_fixture",
    },
]


def test_live_discovery_filters_scores_persists_to_whiteboard_and_kanban(user) -> None:
    result = run_career_ops_first_prompt(
        actor=user,
        cv_text=CV_TEXT,
        constraints=CONSTRAINTS,
        prompt="Collect live job URLs, filter visa-ineligible roles, score against CV, and write the shortlist to the whiteboard.",
        idempotency_key="career-ops-live-discovery-test",
        live_postings=LIVE_POSTINGS,
    )

    assert [posting["url"] for posting in result.postings] == [
        "https://jobs.example.test/madrid-ai-systems/backend-ai-platform?utm=ignored",
        "https://jobs.example.test/mexico-automation-labs/ai-workflow-engineer",
    ]
    assert all(posting["provider"] == "test_live_url_fixture" for posting in result.postings)
    assert all(posting["visa_ok"] is True for posting in result.postings)
    assert all(posting["score"] >= 4.0 for posting in result.postings)
    assert all("United States" not in posting["location"] for posting in result.postings)

    whiteboard = WorkWhiteboard.objects.get(id=result.whiteboard_id)
    first_prompt = whiteboard.metadata_json["career_ops"]["first_prompt"]
    assert first_prompt["source_mode"] == "live_url_discovery"
    assert first_prompt["result_count"] == 2
    assert [posting["url"] for posting in first_prompt["postings"]] == [posting["url"] for posting in result.postings]

    snapshot = whiteboard.metadata_json[TASK_SNAPSHOT_METADATA_KEY]
    assert [task["title"] for task in snapshot["tasks"]] == [
        "Review posting",
        "Score fit",
        "Prepare tailored CV",
        "Approval before apply",
    ]
    assert snapshot["tasks"][1]["outputs"][0]["type"] == "live_job_shortlist"
    assert len(snapshot["tasks"][1]["outputs"][0]["postings"]) == 2

    cards = list(TaskRoutingRecord.objects.filter(id__in=result.task_ids).order_by("created_at"))
    assert [card.metadata_json["title"] for card in cards] == [
        "Review posting",
        "Score fit",
        "Prepare tailored CV",
        "Approval before apply",
    ]
    assert {card.status for card in cards} >= {"completed", "queued", "blocked"}

    assert CompanySignal.objects.filter(company_id=result.company_id, domain_context="career_ops").count() == 2
    opportunities = list(CompanyOpportunity.objects.filter(company_id=result.company_id).order_by("title"))
    assert len(opportunities) == 2
    assert all(opp.metadata_json["career_ops"]["source_mode"] == "live_url_discovery" for opp in opportunities)
    assert all(opp.metadata_json["career_ops"]["external_side_effects_allowed"] is False for opp in opportunities)
    assert all(opp.next_action == "Review live posting fit before generating a tailored CV." for opp in opportunities)


def test_live_discovery_is_idempotent_for_same_live_urls(user) -> None:
    kwargs = {
        "actor": user,
        "cv_text": CV_TEXT,
        "constraints": CONSTRAINTS,
        "prompt": "Collect live job URLs and write the shortlist to the whiteboard.",
        "idempotency_key": "career-ops-live-discovery-idempotent",
        "live_postings": LIVE_POSTINGS,
    }

    first = run_career_ops_first_prompt(**kwargs)
    second = run_career_ops_first_prompt(**kwargs)

    assert first.company_id == second.company_id
    assert first.whiteboard_id == second.whiteboard_id
    assert first.program_id == second.program_id
    assert len(second.postings) == 2
    assert CompanyOpportunity.objects.filter(company_id=second.company_id).count() == 2
    assert TaskRoutingRecord.objects.filter(id__in=second.task_ids).count() == 4
