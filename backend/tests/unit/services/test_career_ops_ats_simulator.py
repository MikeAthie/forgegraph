from __future__ import annotations

from copy import deepcopy
from typing import Any

from application.services.career_ops_ats_simulator import simulate_career_ops_ats


def _candidate_facts(**overrides: Any) -> dict[str, Any]:
    facts = {
        "summary": "Backend engineer building Python APIs and AI workflow systems.",
        "proof_points": [
            "Built production APIs using Python, FastAPI, PostgreSQL, and Redis.",
            "Delivered RAG and agentic workflow prototypes with observability.",
        ],
        "skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "RAG", "observability"],
        "projects": [
            "Career automation backend using Python, FastAPI, PostgreSQL, and RAG workflows."
        ],
        "education": ["B.S. Computer Science"],
    }
    facts.update(overrides)
    return facts


def _posting(**overrides: Any) -> dict[str, Any]:
    posting = {
        "id": "opp-123",
        "title": "Backend Engineer, AI Platform",
        "company": "Acme AI",
        "url": "https://jobs.ashbyhq.com/acme/123",
        "provider": "ashby",
        "description": "Build Python FastAPI PostgreSQL backend APIs for RAG workflows with observability.",
    }
    posting.update(overrides)
    return posting


def _resume(**overrides: Any) -> dict[str, Any]:
    resume = {
        "status": "draft",
        "format": "ats_resume_v1",
        "sections": [
            {
                "heading": "SUMMARY",
                "items": [
                    "Backend engineer building Python APIs, FastAPI services, and RAG workflow systems."
                ],
            },
            {
                "heading": "TECHNICAL SKILLS",
                "items": ["Python", "FastAPI", "PostgreSQL", "Redis", "RAG", "observability"],
            },
            {
                "heading": "SELECTED EXPERIENCE",
                "items": [
                    {
                        "text": "Built production APIs using Python, FastAPI, PostgreSQL, and Redis.",
                        "source_ref": {"type": "cv_proof_point", "index": 0},
                    },
                    {
                        "text": "Delivered RAG and agentic workflow prototypes with observability.",
                        "source_ref": {"type": "cv_proof_point", "index": 1},
                    },
                ],
            },
            {
                "heading": "PROJECTS",
                "items": [
                    {
                        "text": "Career automation backend using Python, FastAPI, PostgreSQL, and RAG workflows.",
                        "source_ref": {"type": "cv_project", "index": 0},
                    }
                ],
            },
            {
                "heading": "EDUCATION",
                "items": [
                    {
                        "text": "B.S. Computer Science",
                        "source_ref": {"type": "cv_education", "index": 0},
                    }
                ],
            },
        ],
        "plain_text": (
            "SUMMARY - Backend engineer building Python APIs, FastAPI services, and RAG workflow systems.\n"
            "TECHNICAL SKILLS - Python - FastAPI - PostgreSQL - Redis - RAG - observability\n"
            "SELECTED EXPERIENCE - Built production APIs using Python, FastAPI, PostgreSQL, and Redis.\n"
            "SELECTED EXPERIENCE - Delivered RAG and agentic workflow prototypes with observability.\n"
            "PROJECTS - Career automation backend using Python, FastAPI, PostgreSQL, and RAG workflows.\n"
            "EDUCATION - B.S. Computer Science"
        ),
        "claim_source_map": [
            {"claim": "Python", "source_ref": {"type": "cv_skill", "index": 0}},
            {"claim": "FastAPI", "source_ref": {"type": "cv_skill", "index": 1}},
        ],
        "source_refs": [{"type": "cv_proof_point", "index": 0}],
        "quality": {"source_backed_claims": True, "external_side_effects_allowed": False},
    }
    resume.update(overrides)
    return resume


def _packet(resume: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "draft",
        "opportunity": {
            "id": "opp-123",
            "employer_name": "Acme AI",
            "role_title": "Backend Engineer",
        },
        "alignment": {
            "keyword_alignment": {
                "matched_keywords": [
                    {"keyword": "Python", "cv_source_ref": {"type": "cv_skill", "index": 0}},
                    {"keyword": "FastAPI", "cv_source_ref": {"type": "cv_skill", "index": 1}},
                    {"keyword": "PostgreSQL", "cv_source_ref": {"type": "cv_skill", "index": 2}},
                    {"keyword": "RAG", "cv_source_ref": {"type": "cv_skill", "index": 4}},
                    {"keyword": "observability", "cv_source_ref": {"type": "cv_skill", "index": 5}},
                ],
                "missing_keywords": [],
                "coverage_score": 1.0,
            }
        },
        "artifacts": {"tailored_resume": resume or _resume(), "cover_letter": {"status": "draft"}},
        "source_refs": [{"type": "opportunity", "id": "opp-123"}],
        "quality": {"external_side_effects_allowed": False, "source_backed_claims": True},
    }


def _score_for(resume: dict[str, Any], posting: dict[str, Any] | None = None) -> dict[str, Any]:
    return simulate_career_ops_ats(
        packet=_packet(resume), posting=posting or _posting(), candidate_facts=_candidate_facts()
    )


def test_ats_simulator_scores_well_structured_source_backed_resume() -> None:
    report = _score_for(_resume())

    assert report["format"] == "career_ops_ats_simulation_v1"
    assert report["status"] == "simulated"
    assert report["atsScore"] >= 85
    assert report["scoreBand"] in {"human_review", "send_ready"}
    assert set(report["scoreBreakdown"]) == {
        "formatting",
        "keywords",
        "structure",
        "readability",
        "risk",
    }
    matched = {item["keyword"] for item in report["keywordAnalysis"]["matched"]}
    assert {"Python", "FastAPI", "PostgreSQL", "RAG"} <= matched
    assert report["quality"]["external_side_effects_allowed"] is False
    assert report["thresholds"] == {"human_review": 85, "send_ready": 90, "improvement_review": 70}


def test_ats_simulator_flags_missing_job_keywords_without_inventing_claims() -> None:
    original_resume = _resume()
    before = deepcopy(original_resume)
    report = _score_for(
        original_resume,
        _posting(description="Build Python FastAPI services with AWS Lambda and PostgreSQL."),
    )

    missing = {item["keyword"]: item for item in report["keywordAnalysis"]["missing"]}

    assert "AWS Lambda" in missing
    assert missing["AWS Lambda"]["requires_source_fact"] is True
    assert "unless CV source supports it" in missing["AWS Lambda"]["recommendation"]
    assert original_resume == before


def test_ats_simulator_blocks_internal_leakage() -> None:
    resume = _resume(plain_text="This resume leaks ForgeGraph metadata_json internals.")

    report = _score_for(resume)

    assert report["status"] == "blocked"
    assert report["scoreBand"] == "blocked"
    assert report["atsScore"] < 70
    assert any(flag["code"] == "internal_leakage" for flag in report["parseability"]["flags"])
    assert report["quality"]["external_side_effects_allowed"] is False


def test_ats_simulator_penalizes_missing_required_sections() -> None:
    resume = _resume()
    resume["sections"] = [
        section for section in resume["sections"] if section["heading"] != "EDUCATION"
    ]

    report = _score_for(resume)

    assert report["atsScore"] < _score_for(_resume())["atsScore"]
    assert "EDUCATION" not in report["parseability"]["present_sections"]
    assert any(suggestion["priority"] == "high" for suggestion in report["suggestions"])


def test_ats_simulator_detects_keyword_stuffing() -> None:
    clean = _score_for(_resume())
    stuffed_resume = _resume(
        plain_text=_resume()["plain_text"] + "\n" + " ".join(["Python"] * 12),
    )

    stuffed = _score_for(stuffed_resume)

    assert any(item["keyword"] == "Python" for item in stuffed["keywordAnalysis"]["overused"])
    assert stuffed["atsScore"] < clean["atsScore"]


def test_ats_simulator_caps_sparse_generic_keyword_sets_below_send_ready() -> None:
    report = _score_for(
        _resume(),
        _posting(description="Remote backend Python engineer role."),
    )

    assert report["keywordAnalysis"]["evidenceConfidence"]["level"] == "sparse"
    assert report["keywordAnalysis"]["evidenceConfidence"]["specificity"] == "generic"
    assert report["atsScore"] < 90
    assert report["quality"]["send_minimum_passed"] is False


def test_ats_simulator_gives_more_credit_for_specific_than_generic_sparse_keywords() -> None:
    generic = _score_for(_resume(), _posting(description="Remote backend Python engineer role."))
    specific = _score_for(_resume(), _posting(description="Build Python FastAPI backend APIs."))

    assert generic["atsScore"] < specific["atsScore"] < 90
    assert generic["keywordAnalysis"]["evidenceConfidence"]["specificity"] == "generic"
    assert specific["keywordAnalysis"]["evidenceConfidence"]["specificity"] == "mixed"
