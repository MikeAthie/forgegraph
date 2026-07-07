from __future__ import annotations

from application.services.career_ops_resume_formatter import render_career_ops_ats_resume

SOURCE_SUMMARY = (
    "Backend-leaning Software Engineer with strong end-to-end ownership building production APIs, "
    "data systems, AI-native workflows, and async service architectures. Experienced with Python, "
    "FastAPI, PostgreSQL, Redis, workers, and Go-based backend services; comfortable taking systems "
    "from discovery and architecture through implementation, testing, observability, and launch. "
    "Strong interest in B2B/enterprise products, integrations, agentic AI, RAG, and production-grade "
    "systems that require reliability, maintainability, and operational rigor."
)


def _minimal_tailored_resume() -> dict[str, object]:
    return {
        "status": "draft",
        "format": "ats_resume_v1",
        "sections": [
            {"heading": "SUMMARY", "items": ["Thin generated summary."]},
            {"heading": "TECHNICAL SKILLS", "items": ["Python", "FastAPI"]},
            {"heading": "SELECTED EXPERIENCE", "items": ["Thin experience bullet."]},
            {"heading": "PROJECTS", "items": ["Thin project bullet."]},
            {"heading": "EDUCATION", "items": ["ITAM — BSc in Law — 2017"]},
        ],
        "quality": {"external_side_effects_allowed": False},
    }


def _candidate_profile() -> dict[str, object]:
    return {
        "name": "Miguel Athie",
        "location": "Mexico City, MX",
        "email": "miguel.athien@gmail.com",
        "phone": "+52 55 3900 3599",
        "github": "GitHub: https://github.com/GreyCrossX",
        "professional_summary": SOURCE_SUMMARY,
        "experience": [
            {
                "organization": "Grey Cross Developments",
                "role": "Product Engineer",
                "period": "Jul 2022 – Present",
                "bullets": [
                    "Owned backend products end-to-end (discovery → architecture → implementation → deployment), delivering data-driven systems for SMBs and consulting clients.",
                    "Designed and implemented APIs and service boundaries with a focus on clean, maintainable interfaces and long-term iteration.",
                ],
            },
            {
                "organization": "Vittahouse",
                "role": "Automation & Data Consultant",
                "period": "Oct 2019 – Nov 2025",
                "bullets": [
                    "Automated accounting and audit workflows, reducing manual effort and improving consistency of recurring operational processes.",
                    "Built discrepancy-detection tools to surface data issues earlier and support data-driven decision-making.",
                ],
            },
        ],
        "projects": [
            {
                "name": "Lex Toolkit",
                "subtitle": "AI agents for legal workflows (Next.js + FastAPI)",
                "period": "Nov 2025 – Present",
                "url": "https://github.com/MikeAthie/Lex-Toolkit",
                "bullets": [
                    "Built a full-stack application with Next.js and FastAPI, designed to scale for real-world professional workflows.",
                ],
            },
            {
                "name": "Forgegraph",
                "subtitle": "AI-native backend platform for agentic workflows",
                "period": "2026 – Present",
                "url": "https://github.com/MikeAthie/ForgeGraph",
                "bullets": [
                    "Built an end-to-end backend platform exploring how AI agents can interact with structured project knowledge, memory, summaries, and operational workflows.",
                ],
            },
        ],
        "skills": [
            {
                "category": "Backend / APIs",
                "items": "Python, FastAPI, Django, Go, REST APIs, service architecture, schema design, clean interfaces, production deployment",
            },
            {
                "category": "AI Engineering",
                "items": "RAG, LangGraph, agentic workflows, AI-assisted development, LLM integration, grounded outputs, prompt/workflow design",
            },
        ],
        "education": [
            {
                "institution": "ITAM",
                "degree": "BSc in Law",
                "graduation_year": "2017",
                "location": "Mexico City, Mexico",
            }
        ],
    }


def test_professional_resume_header_uses_requested_contact_line_without_eu_remote() -> None:
    artifacts = render_career_ops_ats_resume(
        tailored_resume=_minimal_tailored_resume(),
        candidate_identity=_candidate_profile(),
    )

    assert "MIGUEL ATHIE" in artifacts.text
    assert "Mexico City, MX • miguel.athien@gmail.com • +52 55 3900 3599 • GitHub: https://github.com/GreyCrossX" in artifacts.text
    assert "EU Remote" not in artifacts.text
    assert "Mexico / Spain" not in artifacts.text


def test_professional_resume_uses_source_cv_summary_as_intro_not_two_fragments() -> None:
    artifacts = render_career_ops_ats_resume(
        tailored_resume=_minimal_tailored_resume(),
        candidate_identity=_candidate_profile(),
    )

    summary_start = artifacts.text.index("SUMMARY")
    skills_start = artifacts.text.index("TECHNICAL SKILLS")
    summary_block = artifacts.text[summary_start:skills_start]
    assert SOURCE_SUMMARY in summary_block
    assert "Thin generated summary" not in summary_block
    assert summary_block.count("- ") == 0


def test_professional_resume_renders_experience_and_projects_as_cards() -> None:
    artifacts = render_career_ops_ats_resume(
        tailored_resume=_minimal_tailored_resume(),
        candidate_identity=_candidate_profile(),
    )

    text = artifacts.text
    assert "Grey Cross Developments — Product Engineer" in text
    assert "Jul 2022 – Present" in text
    assert "Owned backend products end-to-end" in text
    assert "Vittahouse — Automation & Data Consultant" in text
    assert "Lex Toolkit — AI agents for legal workflows (Next.js + FastAPI)" in text
    assert "Nov 2025 – Present | https://github.com/MikeAthie/Lex-Toolkit" in text
    assert "Forgegraph — AI-native backend platform for agentic workflows" in text
    assert "Thin experience bullet" not in text
    assert "Thin project bullet" not in text


def test_professional_resume_groups_skills_in_dense_category_lines() -> None:
    artifacts = render_career_ops_ats_resume(
        tailored_resume=_minimal_tailored_resume(),
        candidate_identity=_candidate_profile(),
    )

    text = artifacts.text
    assert "Backend / APIs: Python, FastAPI, Django, Go" in text
    assert "AI Engineering: RAG, LangGraph, agentic workflows" in text
    skills_block = text[text.index("TECHNICAL SKILLS"): text.index("SELECTED EXPERIENCE")]
    assert skills_block.count("\n- ") <= 3
