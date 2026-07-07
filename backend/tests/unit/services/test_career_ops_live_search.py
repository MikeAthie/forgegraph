from __future__ import annotations

from typing import Any

import pytest

from application.services.career_ops_live_search import (
    StaticCareerOpsLiveSearchProvider,
    StdlibCareerOpsLiveSearchProvider,
    _parse_bing_html,
    build_career_ops_live_search_queries,
    normalize_career_ops_live_search_hit,
    run_career_ops_live_search,
)

CV_TEXT = """
Miguel Athie
Backend-leaning Software Engineer building production APIs, data systems, AI-native workflows,
Python, FastAPI, Django, Go, PostgreSQL, Redis, Celery, RAG, LangGraph, agentic workflows,
observability, tests, Prometheus, React, Next.js and TypeScript.
"""

CONSTRAINTS = {
    "work_authorized_regions": ["Mexico", "European Union", "Spain"],
    "excluded_regions": ["United States"],
    "target_salary_usd": 60000,
}


class RecordingProvider:
    provider_name = "recording_search_fixture"

    def __init__(self, hits_by_query: dict[str, list[dict[str, Any]]]) -> None:
        self.hits_by_query = hits_by_query
        self.queries: list[str] = []

    def search(self, *, query: str, max_results: int) -> list[dict[str, Any]]:
        self.queries.append(query)
        return list(self.hits_by_query.get(query, []))[:max_results]


class FakeSearchResponse:
    def __init__(self, body: str) -> None:
        self.headers = self
        self._body = body.encode()

    def __enter__(self) -> FakeSearchResponse:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def get_content_charset(self) -> str:
        return "utf-8"

    def read(self, _limit: int) -> bytes:
        return self._body


def test_parse_bing_html_extracts_result_url_title_and_snippet() -> None:
    hits = _parse_bing_html(
        """
        <li class="b_algo">
            <h2><a href="https://example.test/job?utm_source=bing">Backend AI Engineer</a></h2>
            <p>Python FastAPI backend role in Spain.</p>
        </li>
        """,
        limit=5,
    )

    assert hits == [
        {
            "url": "https://example.test/job?utm_source=bing",
            "title": "Backend AI Engineer",
            "snippet": "Python FastAPI backend role in Spain.",
        }
    ]


def test_stdlib_provider_falls_back_to_bing_when_duckduckgo_returns_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    requested_urls: list[str] = []

    def fake_urlopen(request: Any, *, timeout: float) -> FakeSearchResponse:
        del timeout
        requested_urls.append(request.full_url)
        if "duckduckgo.com" in request.full_url:
            return FakeSearchResponse("<html><body><p>interstitial</p></body></html>")
        return FakeSearchResponse(
            """
            <li class="b_algo">
                <h2><a href="https://example.test/job">Backend AI Engineer</a></h2>
                <p>Python FastAPI backend role in Spain.</p>
            </li>
            """
        )

    monkeypatch.setattr("application.services.career_ops_live_search.urlopen", fake_urlopen)

    provider = StdlibCareerOpsLiveSearchProvider(timeout_seconds=1)

    assert provider.search(query="backend ai engineer spain", max_results=3) == [
        {
            "url": "https://example.test/job",
            "title": "Backend AI Engineer",
            "snippet": "Python FastAPI backend role in Spain.",
        }
    ]
    assert "duckduckgo.com" in requested_urls[0]
    assert "bing.com" in requested_urls[1]


def test_build_career_ops_live_search_queries_uses_cv_facts_constraints_and_prompt() -> None:
    queries = build_career_ops_live_search_queries(
        cv_text=CV_TEXT,
        constraints=CONSTRAINTS,
        prompt="Find backend AI platform roles with RAG or agent workflows.",
    )

    assert queries[0] == '"Python" "FastAPI" backend AI jobs Spain'
    assert any("Mexico" in query for query in queries)
    assert any("European Union" in query for query in queries)
    assert any("agent workflows" in query or "agentic workflows" in query for query in queries)
    assert len(queries) == len(set(queries))


def test_run_career_ops_live_search_normalizes_dedupes_and_attaches_provenance() -> None:
    queries = build_career_ops_live_search_queries(
        cv_text=CV_TEXT,
        constraints=CONSTRAINTS,
        prompt="Find backend AI platform roles.",
    )
    provider = RecordingProvider(
        {
            queries[0]: [
                {
                    "title": "Senior Backend Engineer, AI Platform",
                    "company": "Madrid AI Systems",
                    "location": "Madrid, Spain / EU Remote",
                    "url": "https://jobs.example.test/madrid-ai/backend-ai?utm_source=fixture",
                    "snippet": "Build Python FastAPI services, Django workflows, PostgreSQL, Redis and RAG systems.",
                    "apply_url": "https://jobs.example.test/madrid-ai/backend-ai/apply",
                    "send_payload": {"candidate": "do not send"},
                },
                {
                    "title": "Duplicate Backend Engineer",
                    "company": "Madrid AI Systems",
                    "location": "Madrid, Spain / EU Remote",
                    "url": "https://jobs.example.test/madrid-ai/backend-ai?utm_source=other",
                    "description": "Duplicate URL with different tracking parameters.",
                    "salary_range_usd": [58000, 76000],
                },
            ],
            queries[1]: [
                {
                    "title": "AI Workflow Engineer",
                    "company": "Mexico Automation Labs",
                    "location": "Mexico Remote",
                    "url": "https://jobs.example.test/mexico-automation/ai-workflow",
                    "description": "Python APIs, Celery jobs, LangGraph agents and production observability.",
                    "salary_range_usd": [50000, 66000],
                    "provider": "fixture_override_provider",
                }
            ],
        }
    )

    postings = run_career_ops_live_search(
        cv_text=CV_TEXT,
        constraints=CONSTRAINTS,
        prompt="Find backend AI platform roles.",
        provider=provider,
        max_results=5,
    )

    assert [posting["url"] for posting in postings] == [
        "https://jobs.example.test/madrid-ai/backend-ai",
        "https://jobs.example.test/mexico-automation/ai-workflow",
    ]
    assert provider.queries[:2] == queries[:2]
    assert postings[0]["title"] == "Senior Backend Engineer, AI Platform"
    assert postings[0]["company"] == "Madrid AI Systems"
    assert postings[0]["description"].startswith("Build Python FastAPI services")
    assert postings[0]["salary_range_usd"] == [0, 0]
    assert postings[0]["provider"] == "recording_search_fixture"
    assert postings[0]["source_query"] == queries[0]
    assert postings[0]["source_rank"] == 1
    assert postings[0]["source_mode"] == "live_search_skill"
    assert postings[0]["external_side_effects_allowed"] is False
    assert "apply_url" not in postings[0]
    assert "send_payload" not in postings[0]
    assert postings[1]["provider"] == "fixture_override_provider"
    assert postings[1]["salary_range_usd"] == [50000, 66000]


@pytest.mark.parametrize(
    ("source_query", "expected_location"),
    [
        ('"Python" backend AI jobs Spain', "Spain Remote"),
        ('"Python" backend AI jobs Mexico', "Mexico Remote"),
        ('"Python" backend AI jobs Europe', "Europe Remote"),
        ('"Python" backend AI jobs European Union', "European Union Remote"),
        ('"Python" backend AI jobs EU', "European Union Remote"),
        ('"Python" backend AI jobs Remote', "Remote"),
    ],
)
def test_normalize_career_ops_live_search_hit_infers_safe_missing_locations_from_query(
    source_query: str,
    expected_location: str,
) -> None:
    posting = normalize_career_ops_live_search_hit(
        {
            "title": "Backend AI Engineer",
            "company": "Live Search Co",
            "url": "https://jobs.example.test/live-search/backend-ai-engineer",
            "description": "Python FastAPI backend systems.",
        },
        provider_name="recording_search_fixture",
        source_query=source_query,
        source_rank=1,
    )

    assert posting["location"] == expected_location
    assert posting["salary_range_usd"] == [0, 0]
    assert posting["source_mode"] == "live_search_skill"
    assert posting["external_side_effects_allowed"] is False


def test_normalize_career_ops_live_search_hit_preserves_explicit_location_and_does_not_infer_us() -> None:
    explicit_location = normalize_career_ops_live_search_hit(
        {
            "title": "Backend AI Engineer",
            "company": "Live Search Co",
            "location": "Madrid, Spain / EU Remote",
            "url": "https://jobs.example.test/live-search/backend-ai-engineer",
            "description": "Python FastAPI backend systems.",
        },
        provider_name="recording_search_fixture",
        source_query='"Python" backend AI jobs Spain',
        source_rank=1,
    )
    us_query_location = normalize_career_ops_live_search_hit(
        {
            "title": "Backend AI Engineer",
            "company": "Live Search Co",
            "url": "https://jobs.example.test/live-search/us-backend-ai-engineer",
            "description": "Python FastAPI backend systems.",
        },
        provider_name="recording_search_fixture",
        source_query='"Python" backend AI jobs United States Remote',
        source_rank=1,
    )

    assert explicit_location["location"] == "Madrid, Spain / EU Remote"
    assert us_query_location["location"] == ""


def test_static_provider_and_extra_queries_are_deterministic_without_network() -> None:
    provider = StaticCareerOpsLiveSearchProvider(
        [
            {
                "title": "Backend AI Engineer",
                "company": "EU Fixture Co",
                "location": "Spain / EU Remote",
                "url": "https://jobs.example.test/eu-fixture/backend-ai-engineer",
                "description": "Python FastAPI RAG backend APIs.",
            }
        ],
        provider_name="json_fixture_provider",
    )

    postings = run_career_ops_live_search(
        cv_text=CV_TEXT,
        constraints=CONSTRAINTS,
        prompt="Find backend AI jobs.",
        provider=provider,
        extra_queries=["custom backend AI Spain"],
        max_results=3,
    )

    assert postings == [
        {
            "title": "Backend AI Engineer",
            "company": "EU Fixture Co",
            "location": "Spain / EU Remote",
            "url": "https://jobs.example.test/eu-fixture/backend-ai-engineer",
            "description": "Python FastAPI RAG backend APIs.",
            "salary_range_usd": [0, 0],
            "provider": "json_fixture_provider",
            "source_query": "custom backend AI Spain",
            "source_rank": 1,
            "source_mode": "live_search_skill",
            "external_side_effects_allowed": False,
        }
    ]
