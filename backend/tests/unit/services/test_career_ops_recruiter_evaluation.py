from __future__ import annotations

from application.services.career_ops_recruiter_evaluation import (
    evaluate_career_ops_resume_professional_delivery,
)


def test_recruiter_evaluation_scores_presentation_fit_and_professional_delivery() -> None:
    report = evaluate_career_ops_resume_professional_delivery(
        resume_text=(
            "MIGUEL ATHIE\n"
            "Mexico City, MX • miguel.athien@gmail.com • +52 55 3900 3599 • GitHub: https://github.com/GreyCrossX\n\n"
            "SUMMARY\n"
            "Backend-leaning Software Engineer with strong end-to-end ownership building production APIs, data systems, AI-native workflows, and async service architectures.\n\n"
            "TECHNICAL SKILLS\n"
            "Backend / APIs: Python, FastAPI, Django, Go, REST APIs\n"
            "AI Engineering: RAG, LangGraph, agentic workflows\n\n"
            "SELECTED EXPERIENCE\n"
            "Grey Cross Developments — Product Engineer\n"
            "Jul 2022 – Present\n"
            "- Owned backend products end-to-end.\n\n"
            "PROJECTS\n"
            "Lex Toolkit — AI agents for legal workflows (Next.js + FastAPI)\n"
            "Nov 2025 – Present | https://github.com/MikeAthie/Lex-Toolkit\n"
            "- Built a full-stack application.\n\n"
            "EDUCATION\n"
            "ITAM — BSc in Law — 2017\n"
        ),
        opportunity={"role_title": "Backend Engineer", "employer_name": "Example AI"},
        ats_score=89,
    )

    assert report["format"] == "career_ops_recruiter_evaluation_v1"
    assert report["external_side_effects_allowed"] is False
    assert report["overall_score"] >= 80
    assert set(report["scores"]) >= {
        "presentation",
        "role_fit",
        "professional_delivery",
        "credibility",
        "ats_readability",
    }
    assert "top_tier_recruiter" in report["review_prompt"]
    assert report["recommendation"] in {"approve_for_human_send_review", "revise_before_send"}
    assert report["strengths"]
    assert report["risks"]


def test_recruiter_evaluation_penalizes_one_word_per_line_skill_dump() -> None:
    report = evaluate_career_ops_resume_professional_delivery(
        resume_text=(
            "MIGUEL ATHIE\nSUMMARY\nBackend engineer.\nTECHNICAL SKILLS\n"
            "- Python\n- FastAPI\n- PostgreSQL\n- Redis\n- Django\n- Go\n- RAG\n- API\n"
            "SELECTED EXPERIENCE\n- Built systems.\nPROJECTS\n- Built project.\nEDUCATION\nITAM — BSc in Law — 2017\n"
        ),
        opportunity={},
        ats_score=86,
    )

    assert report["scores"]["presentation"] < 80
    assert any("skill" in risk.lower() for risk in report["risks"])
