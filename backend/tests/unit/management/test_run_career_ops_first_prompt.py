from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command

from infrastructure.orm.models import CompanyOpportunity, TaskRoutingRecord, WorkWhiteboard

pytestmark = pytest.mark.django_db


def test_run_career_ops_first_prompt_command_creates_whiteboard_and_results(user, tmp_path) -> None:
    cv_text_file = tmp_path / "cv.txt"
    cv_text_file.write_text(
        "Miguel Athie\nBackend Software Engineer with Python, FastAPI, Django, Go, PostgreSQL, Redis, RAG, LangGraph, agentic workflows.",
        encoding="utf-8",
    )
    out = StringIO()

    call_command(
        "run_career_ops_first_prompt",
        user_id=str(user.id),
        cv_text_file=str(cv_text_file),
        idempotency_key="command:first-prompt:test",
        prompt="Find possible jobs and write them to the whiteboard.",
        stdout=out,
    )

    payload = json.loads(out.getvalue())
    assert payload["status"] == "ok"
    assert payload["external_side_effects_allowed"] is False
    assert payload["company_id"]
    assert payload["whiteboard_id"]
    assert payload["program_id"]
    assert len(payload["postings"]) == 5
    whiteboard = WorkWhiteboard.objects.get(id=payload["whiteboard_id"])
    assert whiteboard.metadata_json["career_ops"]["first_prompt"]["result_count"] == 5
    assert TaskRoutingRecord.objects.filter(company_id=payload["company_id"]).count() == 4
    assert CompanyOpportunity.objects.filter(company_id=payload["company_id"]).count() == 5


def test_run_career_ops_first_prompt_command_accepts_live_posting_json_file(user, tmp_path) -> None:
    cv_text_file = tmp_path / "cv.txt"
    cv_text_file.write_text(
        "Miguel Athie\nPython FastAPI Django PostgreSQL Redis RAG LangGraph agentic workflows backend APIs.",
        encoding="utf-8",
    )
    live_postings = [
        {
            "title": "Backend AI Engineer",
            "company": "EU Live Jobs Co",
            "location": "Spain / EU Remote",
            "url": "https://jobs.example.test/eu-live/backend-ai-engineer",
            "description": "Python FastAPI backend APIs, PostgreSQL, Redis, RAG and agentic workflows.",
            "salary_range_usd": [55000, 72000],
            "provider": "command_fixture_live_urls",
        },
        {
            "title": "US Backend Engineer",
            "company": "US Live Jobs Co",
            "location": "United States Remote",
            "url": "https://jobs.example.test/us-live/backend-engineer",
            "description": "Python backend. US work authorization required.",
            "salary_range_usd": [120000, 160000],
            "provider": "command_fixture_live_urls",
        },
    ]
    live_file = tmp_path / "live_postings.json"
    live_file.write_text(json.dumps(live_postings), encoding="utf-8")
    out = StringIO()

    call_command(
        "run_career_ops_first_prompt",
        user_id=str(user.id),
        cv_text_file=str(cv_text_file),
        idempotency_key="command:first-prompt:live-test",
        prompt="Collect live job URLs and write the shortlist to the whiteboard.",
        live_postings_json_file=str(live_file),
        stdout=out,
    )

    payload = json.loads(out.getvalue())
    assert payload["status"] == "ok"
    assert payload["source_mode"] == "live_url_discovery"
    assert [posting["url"] for posting in payload["postings"]] == [
        "https://jobs.example.test/eu-live/backend-ai-engineer"
    ]
    whiteboard = WorkWhiteboard.objects.get(id=payload["whiteboard_id"])
    assert whiteboard.metadata_json["career_ops"]["first_prompt"]["source_mode"] == "live_url_discovery"
    assert CompanyOpportunity.objects.filter(company_id=payload["company_id"]).count() == 1


def test_run_career_ops_first_prompt_command_routes_live_search_skill_results(user, tmp_path) -> None:
    cv_text_file = tmp_path / "cv.txt"
    cv_text_file.write_text(
        "Miguel Athie\nPython FastAPI Django PostgreSQL Redis RAG LangGraph agentic workflows backend APIs.",
        encoding="utf-8",
    )
    search_hits = [
        {
            "title": "Backend AI Engineer",
            "company": "EU Search Skill Co",
            "location": "Spain / EU Remote",
            "url": "https://jobs.example.test/eu-search/backend-ai-engineer?utm=fixture",
            "description": "Python FastAPI backend APIs, PostgreSQL, Redis, RAG and agentic workflows.",
            "salary_range_usd": [55000, 72000],
        },
        {
            "title": "Duplicate Backend AI Engineer",
            "company": "EU Search Skill Co",
            "location": "Spain / EU Remote",
            "url": "https://jobs.example.test/eu-search/backend-ai-engineer?utm=duplicate",
            "description": "Duplicate tracking URL for the same role.",
            "salary_range_usd": [55000, 72000],
        },
        {
            "title": "US Backend Engineer",
            "company": "US Search Skill Co",
            "location": "United States Remote",
            "url": "https://jobs.example.test/us-search/backend-engineer",
            "description": "Python backend. US work authorization required.",
            "salary_range_usd": [120000, 160000],
        },
        {
            "title": "Retail Store Manager",
            "company": "Spain Retail Search Co",
            "location": "Barcelona, Spain",
            "url": "https://jobs.example.test/spain-retail/store-manager",
            "description": "Manage in-store retail operations and inventory.",
            "salary_range_usd": [30000, 42000],
        },
    ]
    search_hits_file = tmp_path / "search_hits.json"
    search_hits_file.write_text(json.dumps(search_hits), encoding="utf-8")
    out = StringIO()

    call_command(
        "run_career_ops_first_prompt",
        user_id=str(user.id),
        cv_text_file=str(cv_text_file),
        idempotency_key="command:first-prompt:live-search-skill-test",
        prompt="Use the live search skill to collect job URLs and write the shortlist to the whiteboard.",
        live_search_skill=True,
        live_search_query=["Python FastAPI backend AI jobs Spain"],
        live_search_results_json_file=str(search_hits_file),
        live_search_max_results=8,
        stdout=out,
    )

    payload = json.loads(out.getvalue())
    assert payload["status"] == "ok"
    assert payload["source_mode"] == "live_search_skill"
    assert [posting["url"] for posting in payload["postings"]] == [
        "https://jobs.example.test/eu-search/backend-ai-engineer"
    ]
    assert payload["postings"][0]["source_mode"] == "live_search_skill"
    assert payload["postings"][0]["provider"] == "career_ops_live_search_fixture"
    assert payload["postings"][0]["source_query"] == "Python FastAPI backend AI jobs Spain"
    assert payload["postings"][0]["external_side_effects_allowed"] is False

    whiteboard = WorkWhiteboard.objects.get(id=payload["whiteboard_id"])
    first_prompt = whiteboard.metadata_json["career_ops"]["first_prompt"]
    assert first_prompt["source_mode"] == "live_url_discovery"
    assert first_prompt["result_count"] == 1
    assert first_prompt["postings"][0]["source_mode"] == "live_search_skill"
    opportunities = list(CompanyOpportunity.objects.filter(company_id=payload["company_id"]))
    assert len(opportunities) == 1
    opportunity_career_ops = opportunities[0].metadata_json["career_ops"]
    assert opportunity_career_ops["posting_source_mode"] == "live_search_skill"
    assert opportunity_career_ops["source_query"] == "Python FastAPI backend AI jobs Spain"
    assert opportunity_career_ops["source_rank"] == 1
