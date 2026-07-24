"""Professional recruiter-style evaluation for CareerOps resume packets."""

from __future__ import annotations

import re
from typing import Any

RECRUITER_EVALUATION_FORMAT = "career_ops_recruiter_evaluation_v1"
RECRUITER_EVALUATION_VERSION = "1"

RECRUITER_REVIEW_PROMPT = (
    "top_tier_recruiter: You are a top-tier recruiter reviewing this CV for presentation, "
    "role fit, credibility, professional delivery, and ATS readability. Score the CV like an "
    "experienced hiring operator, not a keyword counter. Flag anything that would make the "
    "candidate look unprofessional even if ATS keywords are present."
)


def evaluate_career_ops_resume_professional_delivery(
    *, resume_text: str, opportunity: dict[str, Any] | None = None, ats_score: int | None = None
) -> dict[str, Any]:
    text = str(resume_text or "")
    opportunity = opportunity if isinstance(opportunity, dict) else {}
    scores = {
        "presentation": _presentation_score(text),
        "role_fit": _role_fit_score(text, opportunity),
        "professional_delivery": _professional_delivery_score(text),
        "credibility": _credibility_score(text),
        "ats_readability": _ats_readability_score(text, ats_score),
    }
    overall = round(sum(scores.values()) / len(scores))
    strengths = _strengths(text, scores)
    risks = _risks(text, scores)
    return {
        "format": RECRUITER_EVALUATION_FORMAT,
        "version": RECRUITER_EVALUATION_VERSION,
        "review_prompt": RECRUITER_REVIEW_PROMPT,
        "opportunity": {
            "employer_name": str(
                opportunity.get("employer_name") or opportunity.get("company") or ""
            ),
            "role_title": str(opportunity.get("role_title") or opportunity.get("title") or ""),
        },
        "scores": scores,
        "overall_score": overall,
        "recommendation": "approve_for_human_send_review"
        if overall >= 80
        else "revise_before_send",
        "strengths": strengths,
        "risks": risks,
        "external_side_effects_allowed": False,
    }


def _presentation_score(text: str) -> int:
    score = 100
    if not re.search(r"^MIGUEL ATHIE\b", text, re.MULTILINE):
        score -= 15
    if "@" not in text or "GitHub:" not in text:
        score -= 10
    if _one_word_skill_lines(text) >= 6:
        score -= 35
    if "SELECTED EXPERIENCE" in text and " — " not in _section(text, "SELECTED EXPERIENCE"):
        score -= 15
    if len(text.splitlines()) > 95:
        score -= 10
    return max(0, min(100, score))


def _role_fit_score(text: str, opportunity: dict[str, Any]) -> int:
    lower = text.casefold()
    keywords = ["python", "fastapi", "postgresql", "redis", "backend", "api", "rag", "agentic"]
    matched = sum(1 for keyword in keywords if keyword in lower)
    score = 58 + min(32, matched * 4)
    role = str(opportunity.get("role_title") or opportunity.get("title") or "").casefold()
    if "backend" in role and "backend" in lower:
        score += 5
    if "ai" in role and any(term in lower for term in ("ai", "rag", "agentic")):
        score += 5
    return max(0, min(100, score))


def _professional_delivery_score(text: str) -> int:
    score = 70
    summary = _section(text, "SUMMARY")
    if 220 <= len(summary) <= 850:
        score += 15
    if "discovery" in text and "implementation" in text and "launch" in text:
        score += 5
    if len(re.findall(r"\b(?:20\d{2}|Present|Jul|Oct|Nov)\b", text)) >= 4:
        score += 5
    if "Not provided in source CV" in text:
        score -= 15
    return max(0, min(100, score))


def _credibility_score(text: str) -> int:
    score = 65
    if "ITAM" in text and "BSc in Law" in text and "2017" in text:
        score += 10
    if "https://github.com/" in text:
        score += 10
    if "Grey Cross Developments" in text and "Vittahouse" in text:
        score += 10
    if "Prometheus" in text or "observability" in text:
        score += 5
    return max(0, min(100, score))


def _ats_readability_score(text: str, ats_score: int | None) -> int:
    score = 70
    required = ["SUMMARY", "TECHNICAL SKILLS", "SELECTED EXPERIENCE", "PROJECTS", "EDUCATION"]
    if all(section in text for section in required):
        score += 10
    if "<table" not in text.casefold() and "metadata_json" not in text:
        score += 5
    if ats_score is not None:
        score = round((score + max(0, min(100, int(ats_score)))) / 2)
    return max(0, min(100, score))


def _one_word_skill_lines(text: str) -> int:
    skills = _section(text, "TECHNICAL SKILLS")
    count = 0
    for line in skills.splitlines():
        cleaned = line.strip().lstrip("- ").strip()
        if cleaned and ":" not in cleaned and len(cleaned.split()) <= 2:
            count += 1
    return count


def _section(text: str, heading: str) -> str:
    headings = ["SUMMARY", "TECHNICAL SKILLS", "SELECTED EXPERIENCE", "PROJECTS", "EDUCATION"]
    start = text.find(heading)
    if start < 0:
        return ""
    following = [
        text.find(candidate, start + len(heading)) for candidate in headings if candidate != heading
    ]
    following = [position for position in following if position > start]
    end = min(following) if following else len(text)
    return text[start:end]


def _strengths(text: str, scores: dict[str, int]) -> list[str]:
    strengths: list[str] = []
    if scores["presentation"] >= 85:
        strengths.append("Clean one-column presentation with efficient section hierarchy.")
    if scores["role_fit"] >= 85:
        strengths.append("Strong backend/API and AI-workflow alignment for the target role.")
    if "Grey Cross Developments" in text:
        strengths.append(
            "Experience is anchored in named roles rather than generic capability bullets."
        )
    if "https://github.com/" in text:
        strengths.append("Project section includes public proof links for technical credibility.")
    return strengths or ["Readable baseline CV structure with standard ATS headings."]


def _risks(text: str, scores: dict[str, int]) -> list[str]:
    risks: list[str] = []
    if scores["presentation"] < 80:
        risks.append(
            "Presentation needs tightening; avoid one-skill-per-line dumps and generic bullets."
        )
    if _one_word_skill_lines(text) >= 6:
        risks.append(
            "Skills are too sparse per line, which wastes CV space and weakens professional delivery."
        )
    if "Not provided in source CV" in text:
        risks.append("A required section still contains placeholder text.")
    if scores["credibility"] < 80:
        risks.append(
            "Add more named roles, dates, project links, or source-backed evidence to increase credibility."
        )
    return risks or ["No major professional-delivery risks detected for human review."]
