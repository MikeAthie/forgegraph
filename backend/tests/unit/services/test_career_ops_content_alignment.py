from __future__ import annotations

import json
from typing import Any

from application.services.career_ops_content_alignment import (
    build_career_ops_alignment_report,
    build_cover_letter_draft,
    build_tailored_resume_draft,
)


def _candidate_facts(**overrides: Any) -> dict[str, Any]:
    candidate = {
        "summary": "Backend engineer building Python APIs and AI workflow systems.",
        "proof_points": [
            "Built production APIs using Python, FastAPI, PostgreSQL, and Redis.",
            "Delivered RAG and LangGraph-style agentic workflow prototypes with observability.",
        ],
    }
    candidate.update(overrides)
    return candidate


def _posting(**overrides: Any) -> dict[str, Any]:
    posting = {
        "title": "Backend Engineer, AI Platform",
        "company": "Acme AI",
        "url": "https://jobs.example.test/acme/backend-ai",
        "description": "Python FastAPI PostgreSQL AWS Lambda backend engineer for RAG workflows.",
    }
    posting.update(overrides)
    return posting


def _external_document_text(*values: object) -> str:
    return json.dumps(values, sort_keys=True, default=str)


def test_alignment_report_matches_supported_keywords_and_flags_gaps() -> None:
    report = build_career_ops_alignment_report(candidate_facts=_candidate_facts(), posting=_posting())

    matched = {item["keyword"] for item in report["keyword_alignment"]["matched_keywords"]}
    missing = {item["keyword"] for item in report["keyword_alignment"]["missing_keywords"]}

    assert {"Python", "FastAPI", "PostgreSQL", "RAG"} <= matched
    assert "AWS Lambda" in missing
    assert report["keyword_alignment"]["coverage_score"] > 0
    assert report["quality"]["no_invented_candidate_facts"] is True
    assert report["quality"]["external_side_effects_allowed"] is False


def test_resume_draft_uses_required_ats_sections_and_supported_keywords_only() -> None:
    candidate = _candidate_facts()
    posting = _posting()
    alignment = build_career_ops_alignment_report(candidate_facts=candidate, posting=posting)

    resume = build_tailored_resume_draft(candidate_facts=candidate, posting=posting, alignment=alignment)

    assert resume["status"] == "draft"
    assert resume["format"] == "ats_resume_v2.optimized_python_backend"
    assert [section["heading"] for section in resume["sections"]] == [
        "SUMMARY",
        "SELECTED EXPERIENCE",
        "PROJECTS",
        "EDUCATION",
        "TECHNICAL SKILLS",
        "CERTIFICATIONS",
    ]
    assert "FastAPI" in resume["plain_text"]
    assert "AWS Lambda" not in resume["plain_text"]

    assert resume["quality"]["external_side_effects_allowed"] is False


def test_cover_letter_references_role_and_evidence_without_missing_keywords() -> None:
    candidate = _candidate_facts()
    posting = _posting()
    alignment = build_career_ops_alignment_report(candidate_facts=candidate, posting=posting)

    cover_letter = build_cover_letter_draft(candidate_facts=candidate, posting=posting, alignment=alignment)
    text = "\n".join(cover_letter["paragraphs"])

    assert cover_letter["status"] == "draft"
    assert cover_letter["format"] == "cover_letter_v1"
    assert "Acme AI" in text
    assert "Backend Engineer, AI Platform" in text
    assert "FastAPI" in text or "RAG" in text
    assert "AWS Lambda" not in text
    assert cover_letter["source_refs"]
    assert cover_letter["quality"]["external_side_effects_allowed"] is False


def test_location_and_work_authorization_are_not_invented() -> None:
    candidate = _candidate_facts()
    posting = _posting(
        description=(
            "Python FastAPI backend engineer. Remote in Canada. "
            "Requires Canadian work authorization and AWS Lambda."
        ),
        location="Remote, Canada",
    )
    alignment = build_career_ops_alignment_report(candidate_facts=candidate, posting=posting)
    resume = build_tailored_resume_draft(candidate_facts=candidate, posting=posting, alignment=alignment)
    cover_letter = build_cover_letter_draft(candidate_facts=candidate, posting=posting, alignment=alignment)

    text = _external_document_text(resume["plain_text"], cover_letter["paragraphs"])

    assert "Canadian work authorization" not in text
    assert "Remote, Canada" not in text
    assert "AWS Lambda" not in text


def test_generated_external_text_has_no_internal_leakage_tokens() -> None:
    candidate = _candidate_facts(
        proof_points=[
            "Built ForgeGraph workflow prototypes from metadata_json prompts.",
            "Delivered Python API services with PostgreSQL.",
        ]
    )
    posting = _posting(description="Python PostgreSQL workflow observability engineer.")
    alignment = build_career_ops_alignment_report(candidate_facts=candidate, posting=posting)
    resume = build_tailored_resume_draft(candidate_facts=candidate, posting=posting, alignment=alignment)
    cover_letter = build_cover_letter_draft(candidate_facts=candidate, posting=posting, alignment=alignment)

    text = _external_document_text(resume["plain_text"], cover_letter["paragraphs"]).casefold()

    for token in ("hermes", "forgegraph", "metadata_json", "prompt", "provenance_json"):
        assert token not in text



def test_optimized_python_backend_cv_builder_uses_360dialog_guardrails() -> None:
    candidate = _candidate_facts(
        name="Miguel Athie",
        github="https://github.com/GreyCrossX",
        summary="Backend engineer building Python APIs and AI workflow systems.",
        proof_points=[
            "Owned backend domains end-to-end across architecture, implementation, deployment, and iteration.",
            "Designed and implemented REST APIs for partner/client-facing and internal services with maintainable contracts.",
            "Built async and event-driven pipelines for real-time and batch workloads using PostgreSQL, Redis, and Celery.",
            "Integrated external services and AI-powered features into production services with grounded behavior.",
            "Improved production readiness through failure handling, performance tuning, and operational visibility.",
        ],
        projects=[
            {
                "name": "Automated Trading Bot (Binance)",
                "url": "https://github.com/MikeAthie/2m2",
                "period": "Aug 2025 - Present",
                "summary": "Built a real-time async market-data ingestion pipeline using WebSockets, Redis, and Celery workers.",
                "bullets": [
                    "Consumed market data via WebSockets and persisted streams in Redis for low-latency access.",
                    "Orchestrated background order execution with Celery workers and resilient task handling.",
                    "Separated indicator computation into a Redis-backed service to improve throughput and reliability.",
                ],
            },
            {
                "name": "ForgeGraph",
                "url": "https://github.com/MikeAthie/ForgeGraph",
                "period": "Nov 2025 - Present",
                "summary": "Built an AI-powered company OS for competitor analysis, content strategy, and report generation.",
                "bullets": [
                    "Designed backend workflows for competitive strategy scraping, content analysis, and report generation.",
                    "Developed LLM-assisted analysis and automation with scalable service expansion.",
                ],
            },
            {
                "name": "Lex Toolkit",
                "summary": "Built legal workflow agents with Next.js and FastAPI.",
            },
        ],
        certifications=[
            "Meta Back-End Developer Certification (May 2023)",
            "IBM RAG and Agentic AI (May 2025)",
        ],
    )
    posting = _posting(
        title="Backend Developer (Python)",
        company="360Dialog",
        url="https://dynamitejobs.com/company/360dialog/remote-job/backend-developer-python-remote",
        description=(
            "Python backend developer building reliable maintainable observable backend services, REST APIs, "
            "async event-driven pipelines, PostgreSQL, Redis, external integrations, performance, production ownership, "
            "and remote high-autonomy service architecture."
        ),
    )
    alignment = build_career_ops_alignment_report(candidate_facts=candidate, posting=posting)

    resume = build_tailored_resume_draft(candidate_facts=candidate, posting=posting, alignment=alignment)
    text = resume["plain_text"]

    assert resume["quality"]["cv_builder_profile"] == "python_backend_api_reliability"
    assert "Backend Developer (Python) building reliable, maintainable, and observable backend services" in text
    assert "remote, high-autonomy environments" in text
    assert "Python Backend: Python, FastAPI, Django, REST APIs, service architecture, maintainable codebases, production ownership" in text
    assert "Async & Workers: event-driven pipelines, WebSockets, Celery, background processing" in text
    assert "Datastores: PostgreSQL" in text and "Redis Streams" in text
    assert "Automated Trading Bot (Binance)" in text
    assert "WebSockets" in text and "Celery workers" in text
    assert "ForgeGraph" in text
    assert "Lex Toolkit" not in text
    assert "Meta Back-End Developer Certification (May 2023)" in text
    assert "IBM RAG and Agentic AI (May 2025)" in text
    assert "GreyCrossX" in text
    assert [section["heading"] for section in resume["sections"]] == [
        "SUMMARY",
        "SELECTED EXPERIENCE",
        "PROJECTS",
        "EDUCATION",
        "TECHNICAL SKILLS",
        "CERTIFICATIONS",
    ]
    assert resume["guardrails"]["project_selection"] == ["Automated Trading Bot (Binance)", "ForgeGraph"]
    assert resume["guardrails"]["avoid_generic_ai_native_prose"] is True



def test_optimized_lead_fullstack_go_react_builder_for_codifin_guardrails() -> None:
    candidate = _candidate_facts(
        name="Miguel Athie",
        github="https://github.com/GreyCrossX",
        summary="Backend-leaning full-stack engineer building Go, Python, React, and TypeScript product systems.",
        proof_points=[
            "Built production APIs and service boundaries with Go, Python, Django, FastAPI, PostgreSQL, Redis, and workers.",
            "Built SaaS-style company workflows, competitive strategy scraping, content analysis, and report generation in ForgeGraph.",
            "Built full-stack products using React, Next.js, TypeScript, and FastAPI with clear API contracts.",
            "Built async/event-driven data pipelines, WebSockets ingestion, Redis streams, Celery workers, and operational automation.",
            "Integrated AI-powered features, RAG workflows, and agentic workflows into source-bounded product systems.",
            "Comfortable collaborating in English and Spanish across product, technical, and non-technical teams.",
        ],
        projects=[
            {
                "name": "ForgeGraph",
                "url": "https://github.com/MikeAthie/ForgeGraph",
                "period": "Nov 2025 - Present",
                "summary": "AI-powered company OS for competitor analysis, strategy automation, and report generation.",
                "bullets": [
                    "Built backend workflows for competitive strategy scraping, content analysis, and report generation.",
                    "Used Go and backend services to support durable workflow state, automation, and scalable service expansion.",
                    "Integrated LLM-assisted analysis with source-bounded outputs and operational guardrails.",
                ],
            },
            {
                "name": "Lex Toolkit",
                "url": "https://github.com/MikeAthie/Lex-Toolkit",
                "period": "Nov 2025 - Present",
                "summary": "Full-stack legal workflow product using Next.js, React, TypeScript, and FastAPI.",
                "bullets": [
                    "Built a full-stack app with Next.js/React frontend and FastAPI backend for professional workflows.",
                    "Designed clear API contracts and AI-assisted workflow features for product-quality delivery.",
                ],
            },
            {
                "name": "Automated Trading Bot (Binance)",
                "url": "https://github.com/MikeAthie/2m2",
                "period": "Aug 2025 - Present",
                "summary": "Real-time async data automation using WebSockets, Redis, and Celery workers.",
                "bullets": [
                    "Consumed market data via WebSockets and persisted streams in Redis for low-latency access.",
                    "Orchestrated background execution with Celery workers and resilient task handling.",
                ],
            },
        ],
        education=[{"institution": "ITAM", "degree": "Bachelor of Science in Law", "graduation_year": "2017"}],
        certifications=[
            "Meta Back-End Developer Certification (May 2023)",
            "IBM RAG and Agentic AI (May 2025)",
            "Cambridge English C2 Proficiency certificate",
        ],
    )
    posting = _posting(
        title="Lead Golang & React Developer CDMX Bilingüe",
        company="Codifin",
        url="https://mx.indeed.com/viewjob?jk=0ee36499821e9442",
        description=(
            "Lead Full-Stack Software Engineer building SaaS platforms and data automation systems. "
            "Core stack React, Golang, PostgreSQL. Python data pipelines, AI-powered features, GraphQL, "
            "REST APIs, Docker, Linux, Git, CI/CD, Power BI dashboards, real-time monitoring, Product and QA collaboration. "
            "Advanced English C1 required."
        ),
    )
    alignment = build_career_ops_alignment_report(candidate_facts=candidate, posting=posting)

    resume = build_tailored_resume_draft(candidate_facts=candidate, posting=posting, alignment=alignment)
    cover_letter = build_cover_letter_draft(candidate_facts=candidate, posting=posting, alignment=alignment)
    text = resume["plain_text"]
    cover_text = "\n".join(cover_letter["paragraphs"])

    assert resume["quality"]["cv_builder_profile"] == "lead_fullstack_go_react_saas_automation"
    assert "Lead Full-Stack Software Engineer" in text
    assert "Golang, React, PostgreSQL" in text
    assert "SaaS platforms" in text and "data automation systems" in text
    assert "Full-Stack / Frontend: React, Next.js, TypeScript" in text
    assert "Backend / APIs: Golang, Python, REST APIs, GraphQL" in text
    assert "ForgeGraph" in text
    assert "Lex Toolkit" in text
    assert "Automated Trading Bot (Binance)" in text
    assert "Bachelor of Science in Law" in text
    assert "Cambridge English C2 Proficiency certificate" in text
    assert "English C1" not in text
    assert "Advanced English C1" not in text
    assert resume["guardrails"]["do_not_claim_unsourced_c1"] is True
    assert resume["guardrails"]["project_selection"] == ["ForgeGraph", "Lex Toolkit", "Automated Trading Bot (Binance)"]
    assert "Codifin" in cover_text
    assert "Golang" in cover_text and "React" in cover_text
    assert "English C1" not in cover_text
