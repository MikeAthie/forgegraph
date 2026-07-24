"""Deterministic CareerOps A-G evaluation helpers.

This module is deliberately source-bounded and fake-safe: it mirrors the shape of
santifer/career-ops evaluations without inventing candidate facts or performing
external research/submission side effects.
"""

from __future__ import annotations

import re
from typing import Any

from application.services.career_ops_liveness import classify_career_ops_liveness

ARCHETYPES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "AI Platform / LLMOps",
        ("observability", "eval", "pipeline", "monitoring", "reliability", "llmops"),
    ),
    (
        "Agentic / Automation",
        ("agent", "hitl", "orchestration", "workflow", "multi-agent", "automation"),
    ),
    ("Technical AI PM", ("prd", "roadmap", "discovery", "stakeholder", "product manager")),
    ("AI Solutions Architect", ("architecture", "enterprise", "integration", "design", "systems")),
    ("AI Forward Deployed", ("client-facing", "deploy", "prototype", "fast delivery", "field")),
    ("AI Transformation", ("change management", "adoption", "enablement", "transformation")),
)

GENERIC_QUESTIONS = (
    "Why are you interested in this role?",
    "Why do you want to work at this company?",
    "Tell us about a relevant project or achievement.",
    "What makes you a good fit for this position?",
    "How did you hear about this role?",
)


def evaluate_career_ops_posting(
    *,
    posting: dict[str, Any],
    candidate_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a source-bounded A-G evaluation payload for one posting."""

    facts = candidate_facts or {}
    title = str(posting.get("title") or "Untitled role")
    company = str(posting.get("company") or posting.get("employer") or "Unknown employer")
    description = _posting_text(posting)
    liveness = classify_career_ops_liveness(
        status=_int_or_default(posting.get("http_status"), 0),
        final_url=str(posting.get("final_url") or posting.get("url") or ""),
        body_text=description,
        apply_controls=[str(control) for control in posting.get("apply_controls", []) or []],
    )
    archetype = _detect_archetype(f"{title}\n{description}")
    proof_points = [str(point) for point in facts.get("proof_points", []) if str(point).strip()]
    cv_summary = str(facts.get("summary") or "").strip()
    matched_requirements = _match_requirements(
        description=description, proof_points=proof_points, cv_summary=cv_summary
    )
    score = _score_posting(
        description=description,
        matched_requirements=matched_requirements,
        liveness_result=liveness.result,
    )
    recommendation, tracker_status = _recommendation_for_score(
        score=score, liveness_result=liveness.result
    )
    source_refs = _source_refs(posting=posting, matched_requirements=matched_requirements)
    evaluation = {
        "status": "evaluated" if liveness.result != "expired" else "blocked",
        "score": score,
        "score_label": f"{score:.1f}/5" if liveness.result != "expired" else "N/A",
        "tracker_status": tracker_status,
        "recommendation": recommendation,
        "archetype": archetype,
        "blocks": {
            "A_role_summary": _role_summary(
                title=title, company=company, description=description, archetype=archetype
            ),
            "B_cv_match": {
                "matched_requirements": matched_requirements,
                "gaps": _gaps(description=description, matched_requirements=matched_requirements),
                "source": "cv_source metadata" if facts else "missing cv_source",
            },
            "C_level_strategy": _level_strategy(title=title, description=description),
            "D_comp_research": _comp_research(description=description),
            "E_customization_plan": _customization_plan(
                archetype=archetype, matched_requirements=matched_requirements
            ),
            "F_interview_plan": _interview_plan(
                archetype=archetype, matched_requirements=matched_requirements
            ),
            "G_posting_legitimacy": _legitimacy_block(liveness=liveness, description=description),
        },
        "draft_application_answers": _draft_application_answers(
            company=company, title=title, matched_requirements=matched_requirements
        )
        if score >= 4.5 and liveness.result != "expired"
        else [],
        "source_refs": source_refs,
        "quality": {
            "source_backed_claims": bool(source_refs),
            "no_invented_candidate_facts": True,
            "external_side_effects_allowed": False,
            "live_ready": False,
        },
    }
    return evaluation


def _posting_text(posting: dict[str, Any]) -> str:
    return str(
        posting.get("description") or posting.get("body_text") or posting.get("jd_text") or ""
    ).strip()


def _detect_archetype(text: str) -> dict[str, Any]:
    haystack = text.casefold()
    scores = []
    for name, keywords in ARCHETYPES:
        hits = sorted({keyword for keyword in keywords if keyword.casefold() in haystack})
        scores.append((len(hits), name, hits))
    scores.sort(key=lambda item: (-item[0], item[1]))
    primary_hits, primary, hits = scores[0]
    secondary = [name for count, name, _ in scores[1:3] if count > 0]
    return {
        "primary": primary if primary_hits else "General AI / Software",
        "secondary": secondary,
        "signals": hits,
    }


def _match_requirements(
    *, description: str, proof_points: list[str], cv_summary: str
) -> list[dict[str, str]]:
    jd_keywords = _keywords(description)
    fact_texts = [cv_summary, *proof_points]
    matches: list[dict[str, str]] = []
    for keyword in jd_keywords[:8]:
        source = next((fact for fact in fact_texts if keyword.casefold() in fact.casefold()), "")
        if source:
            matches.append({"requirement": keyword, "cv_evidence": source, "source": "cv_source"})
    return matches


def _score_posting(
    *, description: str, matched_requirements: list[dict[str, str]], liveness_result: str
) -> float:
    if liveness_result == "expired":
        return 0.0
    score = 3.0
    score += min(len(matched_requirements), 5) * 0.25
    text = description.casefold()
    if any(word in text for word in ("senior", "staff", "lead", "principal")):
        score += 0.2
    if any(word in text for word in ("remote", "hybrid")):
        score += 0.15
    if any(word in text for word in ("compensation", "salary", "$", "€", "£")):
        score += 0.15
    if any(word in text for word in ("apply now", "submit application", "start application")):
        score += 0.25
    if len(description) > 250:
        score += 0.25
    return round(max(1.0, min(score, 5.0)), 1)


def _recommendation_for_score(*, score: float, liveness_result: str) -> tuple[str, str]:
    if liveness_result == "expired":
        return "do_not_evaluate", "discarded"
    if score >= 4.5:
        return "apply", "evaluated"
    if score >= 4.0:
        return "worth_applying", "evaluated"
    if score >= 3.5:
        return "maybe", "evaluated"
    return "skip", "skip"


def _role_summary(
    *, title: str, company: str, description: str, archetype: dict[str, Any]
) -> dict[str, Any]:
    lowered = description.casefold()
    remote = (
        "remote"
        if "remote" in lowered
        else "hybrid"
        if "hybrid" in lowered
        else "onsite_or_unspecified"
    )
    seniority = (
        "senior"
        if re.search(r"\b(senior|staff|lead|principal)\b", f"{title} {description}", re.I)
        else "unspecified"
    )
    return {
        "company": company,
        "role_title": title,
        "archetype": archetype["primary"],
        "seniority": seniority,
        "remote_policy": remote,
        "tldr": f"{company} is hiring for {title} with {archetype['primary']} signals.",
    }


def _gaps(*, description: str, matched_requirements: list[dict[str, str]]) -> list[dict[str, str]]:
    matched = {match["requirement"].casefold() for match in matched_requirements}
    gaps = []
    for keyword in _keywords(description):
        if keyword.casefold() not in matched:
            gaps.append(
                {
                    "requirement": keyword,
                    "mitigation": "Address only with real adjacent evidence or leave unclaimed.",
                }
            )
        if len(gaps) == 5:
            break
    return gaps


def _level_strategy(*, title: str, description: str) -> dict[str, str]:
    level = (
        "senior"
        if re.search(r"\b(senior|staff|lead|principal)\b", f"{title} {description}", re.I)
        else "unspecified"
    )
    return {
        "detected_level": level,
        "positioning": "Sell seniority through concrete shipped systems and decision quality; do not inflate titles.",
        "downlevel_plan": "Accept only with fair compensation, explicit scope, and a written review path.",
    }


def _comp_research(description: str) -> dict[str, Any]:
    salary = re.search(
        r"(?:\$|€|£)\s?\d{2,3}[kK]?(?:\s?[-–]\s?(?:\$|€|£)?\s?\d{2,3}[kK]?)?", description
    )
    return {
        "status": "in_jd" if salary else "not_researched",
        "jd_salary_signal": salary.group(0) if salary else None,
        "note": "External comp research is not performed in this backend-safe deterministic slice.",
    }


def _customization_plan(
    *, archetype: dict[str, Any], matched_requirements: list[dict[str, str]]
) -> list[dict[str, str]]:
    return [
        {
            "section": "Summary",
            "proposed_change": f"Lead with {archetype['primary']} systems evidence.",
            "why": "Mirrors the role archetype without inventing new facts.",
        },
        {
            "section": "Selected achievements",
            "proposed_change": "Prioritize matched proof points: "
            + ", ".join(match["requirement"] for match in matched_requirements[:3]),
            "why": "Career-Ops emphasizes exact JD requirement to CV evidence mapping.",
        },
    ]


def _interview_plan(
    *, archetype: dict[str, Any], matched_requirements: list[dict[str, str]]
) -> list[dict[str, str]]:
    if not matched_requirements:
        return [
            {
                "requirement": "general",
                "story_prompt": "Prepare a STAR+R story from verified cv_source evidence.",
            }
        ]
    return [
        {
            "requirement": match["requirement"],
            "story_prompt": f"Prepare a STAR+R story for {match['requirement']} using: {match['cv_evidence']}",
            "archetype_frame": archetype["primary"],
        }
        for match in matched_requirements[:6]
    ]


def _legitimacy_block(*, liveness: Any, description: str) -> dict[str, Any]:
    quality_signals = []
    if len(description) > 300:
        quality_signals.append(
            {
                "signal": "description_quality",
                "finding": "specific content present",
                "weight": "Positive",
            }
        )
    else:
        quality_signals.append(
            {
                "signal": "description_quality",
                "finding": "short or missing JD content",
                "weight": "Concerning",
            }
        )
    quality_signals.append(
        {
            "signal": "liveness",
            "finding": liveness.reason,
            "weight": "Positive" if liveness.result == "active" else "Concerning",
        }
    )
    tier = (
        "High Confidence"
        if liveness.result == "active"
        else "Suspicious"
        if liveness.result == "expired"
        else "Proceed with Caution"
    )
    return {
        "assessment": tier,
        "liveness": liveness.as_dict(),
        "signals": quality_signals,
        "ethical_note": "Signals prioritize candidate time; they are not accusations.",
    }


def _draft_application_answers(
    *, company: str, title: str, matched_requirements: list[dict[str, str]]
) -> list[dict[str, str]]:
    evidence = (
        matched_requirements[0]["cv_evidence"] if matched_requirements else "verified CV evidence"
    )
    return [
        {
            "question": GENERIC_QUESTIONS[0],
            "answer": f"This {title} role maps directly to work I can evidence: {evidence}.",
        },
        {
            "question": GENERIC_QUESTIONS[1],
            "answer": f"I am evaluating {company} because the role shows concrete overlap with my verified experience.",
        },
        {"question": GENERIC_QUESTIONS[2], "answer": f"A relevant proof point is: {evidence}."},
        {
            "question": GENERIC_QUESTIONS[3],
            "answer": "The fit comes from the intersection of the JD requirements and the cited CV evidence above.",
        },
        {
            "question": GENERIC_QUESTIONS[4],
            "answer": "Found through a CareerOps-style opportunity review and selected after scoring against my criteria.",
        },
    ]


def _source_refs(
    *, posting: dict[str, Any], matched_requirements: list[dict[str, str]]
) -> list[dict[str, str]]:
    refs = []
    if posting.get("url"):
        refs.append({"type": "job_url", "url": str(posting["url"])})
    refs.extend(
        {"type": "cv_source", "requirement": match["requirement"]} for match in matched_requirements
    )
    return refs


def _keywords(text: str) -> list[str]:
    candidates = [
        "multi-agent",
        "orchestration",
        "HITL",
        "workflow",
        "LLM",
        "evaluation",
        "evals",
        "observability",
        "reliability",
        "automation",
        "platform",
        "production",
        "architecture",
        "integration",
        "roadmap",
        "stakeholder",
    ]
    found = []
    haystack = text.casefold()
    for candidate in candidates:
        if candidate.casefold() in haystack:
            found.append(candidate)
    return found


def _int_or_default(value: object, default: int) -> int:
    if not isinstance(value, str | bytes | bytearray | int | float):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
