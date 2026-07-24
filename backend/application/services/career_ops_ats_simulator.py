"""Deterministic source-bounded CareerOps ATS simulator."""

from __future__ import annotations

import re
from typing import Any

from application.services.career_ops_content_alignment import (
    ATS_REQUIRED_SECTIONS,
    CAREER_OPS_KEYWORDS,
    INTERNAL_LEAKAGE_TOKENS,
    OPTIMIZED_BACKEND_SECTIONS,
)

ATS_THRESHOLDS = {"human_review": 85, "send_ready": 90, "improvement_review": 70}
ATS_SCORE_BREAKDOWN_MAX = {
    "formatting": 20,
    "keywords": 35,
    "structure": 20,
    "readability": 15,
    "risk": 10,
}
GENERIC_ATS_KEYWORDS = {"AI", "API", "Python", "backend", "remote", "automation", "workflow"}


def simulate_career_ops_ats(
    *,
    packet: dict[str, Any],
    posting: dict[str, Any],
    candidate_facts: dict[str, Any],
) -> dict[str, Any]:
    """Return deterministic ATS simulation for one CareerOps packet.

    This is deliberately no-LLM and source-bounded. It scores the current packet
    and resume payload; it does not mutate input content or invent missing facts.
    """

    artifacts = _dict_value(packet.get("artifacts"))
    resume = _dict_value(artifacts.get("tailored_resume"))
    plain_text = str(resume.get("plain_text") or "")
    sections = _resume_sections(resume)
    present_sections = [section["heading"] for section in sections]
    source_refs = _source_refs(packet=packet, resume=resume)
    job_keywords = _job_keywords(posting)
    candidate_text = _candidate_text(candidate_facts)
    keyword_analysis = _keyword_analysis(
        job_keywords=job_keywords,
        plain_text=plain_text,
        candidate_text=candidate_text,
    )
    parseability = _parseability(
        resume=resume,
        plain_text=plain_text,
        present_sections=present_sections,
        source_refs=source_refs,
    )
    hard_blocked = bool(
        not resume
        or not plain_text.strip()
        or any(
            flag["code"] in {"internal_leakage", "side_effect_guard_enabled"}
            for flag in parseability["flags"]
        )
    )
    score_breakdown = _score_breakdown(
        resume=resume,
        plain_text=plain_text,
        present_sections=present_sections,
        keyword_analysis=keyword_analysis,
        parseability=parseability,
        source_refs=source_refs,
        hard_blocked=hard_blocked,
    )
    ats_score = sum(int(item["score"]) for item in score_breakdown.values())
    if hard_blocked:
        ats_score = min(ats_score, 45)
    score_band = _score_band(ats_score=ats_score, hard_blocked=hard_blocked)
    suggestions = _suggestions(
        keyword_analysis=keyword_analysis,
        parseability=parseability,
        score_band=score_band,
        present_sections=present_sections,
    )
    strengths = _strengths(
        present_sections=present_sections,
        keyword_analysis=keyword_analysis,
        score_breakdown=score_breakdown,
    )
    report = {
        "status": "blocked" if score_band == "blocked" and hard_blocked else "simulated",
        "format": "career_ops_ats_simulation_v1",
        "opportunity": _opportunity(posting=posting, packet=packet),
        "atsScore": ats_score,
        "scoreBand": score_band,
        "thresholds": ATS_THRESHOLDS,
        "scoreBreakdown": score_breakdown,
        "keywordAnalysis": keyword_analysis,
        "parseability": parseability,
        "suggestions": suggestions,
        "strengths": strengths,
        "roast": _roast(
            score_band=score_band, keyword_analysis=keyword_analysis, parseability=parseability
        ),
        "summary": _summary(
            ats_score=ats_score, score_band=score_band, keyword_analysis=keyword_analysis
        ),
        "quality": {
            "source_backed_claims": bool(source_refs) and not hard_blocked,
            "no_invented_candidate_facts": True,
            "external_side_effects_allowed": False,
            "live_ready": False,
            "human_review_minimum_passed": ats_score >= ATS_THRESHOLDS["human_review"]
            and not hard_blocked,
            "send_minimum_passed": ats_score >= ATS_THRESHOLDS["send_ready"] and not hard_blocked,
        },
        "source_refs": source_refs,
    }
    return report


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _resume_sections(resume: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sections = resume.get("sections", [])
    sections: list[dict[str, Any]] = []
    if not isinstance(raw_sections, list):
        return sections
    for section in raw_sections:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading") or "").strip()
        sections.append({"heading": heading, "items": section.get("items", [])})
    return sections


def _source_refs(*, packet: dict[str, Any], resume: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for container in (packet.get("source_refs", []), resume.get("source_refs", [])):
        if isinstance(container, list):
            refs.extend(item for item in container if isinstance(item, dict))
    for claim in (
        resume.get("claim_source_map", [])
        if isinstance(resume.get("claim_source_map"), list)
        else []
    ):
        if isinstance(claim, dict) and isinstance(claim.get("source_ref"), dict):
            refs.append(claim["source_ref"])
    return _dedupe_refs(refs)


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen = set()
    for ref in refs:
        key = tuple(sorted((str(key), str(value)) for key, value in ref.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped


def _job_keywords(posting: dict[str, Any]) -> list[str]:
    text = "\n".join(
        str(posting.get(key) or "")
        for key in ("title", "description", "body_text", "jd_text", "location", "provider")
    )
    return [keyword for keyword in CAREER_OPS_KEYWORDS if _contains_keyword(keyword, text)]


def _candidate_text(candidate_facts: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("summary", "proof_points", "skills", "projects", "education", "constraints"):
        values.extend(_strings(candidate_facts.get(key)))
    return "\n".join(values)


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for child in value.values() for text in _strings(child)]
    if isinstance(value, list | tuple):
        return [text for child in value for text in _strings(child)]
    return []


def _keyword_analysis(
    *, job_keywords: list[str], plain_text: str, candidate_text: str
) -> dict[str, Any]:
    matched = []
    missing = []
    overused = []
    for keyword in job_keywords:
        resume_count = _keyword_count(keyword, plain_text)
        candidate_count = _keyword_count(keyword, candidate_text)
        job_count = 1
        if resume_count > 0 and candidate_count > 0:
            matched.append(
                {
                    "keyword": keyword,
                    "resume_count": resume_count,
                    "job_count": job_count,
                    "source_refs": [{"type": "cv_keyword", "keyword": keyword}],
                }
            )
        else:
            missing.append(
                {
                    "keyword": keyword,
                    "severity": "high" if keyword in {"Python", "FastAPI", "Django"} else "medium",
                    "requires_source_fact": True,
                    "recommendation": f"Do not add {keyword} unless CV source supports it.",
                }
            )
        if resume_count >= max(8, job_count * 5):
            overused.append(
                {
                    "keyword": keyword,
                    "resume_count": resume_count,
                    "job_count": job_count,
                    "recommendation": "Reduce repeated keyword use; keep evidence natural and source-backed.",
                }
            )
    coverage = round(len(matched) / len(job_keywords), 2) if job_keywords else 0.0
    evidence_confidence = _keyword_evidence_confidence(job_keywords)
    return {
        "matched": matched,
        "missing": missing,
        "overused": overused,
        "coverage": coverage,
        "evidenceConfidence": evidence_confidence,
    }


def _keyword_evidence_confidence(job_keywords: list[str]) -> dict[str, Any]:
    keyword_count = len(job_keywords)
    specific_keywords = [keyword for keyword in job_keywords if keyword not in GENERIC_ATS_KEYWORDS]
    generic_keywords = [keyword for keyword in job_keywords if keyword in GENERIC_ATS_KEYWORDS]
    if keyword_count < 4:
        level = "sparse"
    elif keyword_count < 7:
        level = "moderate"
    else:
        level = "rich"
    if specific_keywords and generic_keywords:
        specificity = "mixed"
    elif specific_keywords:
        specificity = "specific"
    else:
        specificity = "generic"
    return {
        "level": level,
        "specificity": specificity,
        "keyword_count": keyword_count,
        "specific_keyword_count": len(specific_keywords),
        "generic_keyword_count": len(generic_keywords),
    }


def _parseability(
    *,
    resume: dict[str, Any],
    plain_text: str,
    present_sections: list[str],
    source_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    flags: list[dict[str, str]] = []
    if not resume:
        flags.append(
            {"code": "missing_resume", "message": "No tailored resume artifact is present."}
        )
    if not plain_text.strip():
        flags.append({"code": "missing_plain_text", "message": "Resume plain text is missing."})
    if _has_internal_leakage(plain_text):
        flags.append(
            {
                "code": "internal_leakage",
                "message": "Resume contains internal implementation terms.",
            }
        )
    if not _has_supported_section_sequence(present_sections):
        flags.append(
            {
                "code": "section_order",
                "message": "ATS sections are missing or not in the required order.",
            }
        )
    for section in ATS_REQUIRED_SECTIONS:
        if section not in present_sections:
            flags.append(
                {"code": "missing_section", "message": f"Missing required ATS section: {section}."}
            )
    if not source_refs:
        flags.append(
            {"code": "missing_source_refs", "message": "Resume lacks source references for claims."}
        )
    if _side_effect_enabled(resume):
        flags.append(
            {
                "code": "side_effect_guard_enabled",
                "message": "Resume artifact enables external side effects.",
            }
        )
    return {
        "required_sections": list(ATS_REQUIRED_SECTIONS),
        "present_sections": present_sections,
        "flags": flags,
    }


def _score_breakdown(
    *,
    resume: dict[str, Any],
    plain_text: str,
    present_sections: list[str],
    keyword_analysis: dict[str, Any],
    parseability: dict[str, Any],
    source_refs: list[dict[str, Any]],
    hard_blocked: bool,
) -> dict[str, dict[str, Any]]:
    formatting = _score_formatting(plain_text=plain_text, parseability=parseability)
    keywords = _score_keywords(keyword_analysis=keyword_analysis)
    structure = _score_structure(
        resume=resume, present_sections=present_sections, source_refs=source_refs
    )
    readability = _score_readability(plain_text=plain_text)
    risk = _score_risk(resume=resume, parseability=parseability, hard_blocked=hard_blocked)
    return {
        "formatting": _breakdown(formatting, "formatting", _formatting_feedback(parseability)),
        "keywords": _breakdown(keywords, "keywords", _keyword_feedback(keyword_analysis)),
        "structure": _breakdown(structure, "structure", _structure_feedback(present_sections)),
        "readability": _breakdown(
            readability, "readability", "Resume text is concise and parseable."
        ),
        "risk": _breakdown(risk, "risk", _risk_feedback(parseability)),
    }


def _score_formatting(*, plain_text: str, parseability: dict[str, Any]) -> int:
    score = ATS_SCORE_BREAKDOWN_MAX["formatting"]
    codes = _flag_codes(parseability)
    if "missing_plain_text" in codes or "missing_resume" in codes:
        score -= 15
    if "internal_leakage" in codes:
        score -= 20
    if "section_order" in codes:
        score -= 5
    missing_count = sum(1 for code in codes if code == "missing_section")
    score -= min(10, missing_count * 2)
    if any(marker in plain_text for marker in ("|", "<table", "</table>", "<img")):
        score -= 3
    return max(0, score)


def _score_keywords(*, keyword_analysis: dict[str, Any]) -> int:
    matched = len(keyword_analysis["matched"])
    missing = len(keyword_analysis["missing"])
    total = matched + missing
    if total == 0:
        return 12
    score = round((matched / total) * ATS_SCORE_BREAKDOWN_MAX["keywords"])
    score = min(score, _keyword_confidence_score_cap(keyword_analysis))
    score -= min(8, len(keyword_analysis["overused"]) * 3)
    return max(0, score)


def _keyword_confidence_score_cap(keyword_analysis: dict[str, Any]) -> int:
    confidence = keyword_analysis.get("evidenceConfidence", {})
    if not isinstance(confidence, dict):
        return ATS_SCORE_BREAKDOWN_MAX["keywords"]
    level = confidence.get("level")
    specificity = confidence.get("specificity")
    if level == "sparse" and specificity == "generic":
        return 24
    if level == "sparse" and specificity == "mixed":
        return 27
    if level == "sparse":
        return 29
    if level == "moderate" and specificity == "generic":
        return 28
    if level == "moderate" and specificity == "mixed":
        return 26
    return ATS_SCORE_BREAKDOWN_MAX["keywords"]


def _score_structure(
    *, resume: dict[str, Any], present_sections: list[str], source_refs: list[dict[str, Any]]
) -> int:
    score = 0
    if _has_supported_section_sequence(present_sections):
        score += 12
    else:
        score += max(0, len(set(present_sections).intersection(ATS_REQUIRED_SECTIONS)) * 2)
    claim_map = resume.get("claim_source_map", [])
    if (
        isinstance(claim_map, list)
        and claim_map
        and all(isinstance(item, dict) and item.get("source_ref") for item in claim_map)
    ):
        score += 5
    if source_refs:
        score += 3
    return min(ATS_SCORE_BREAKDOWN_MAX["structure"], score)


def _has_supported_section_sequence(present_sections: list[str]) -> bool:
    return tuple(present_sections) in {ATS_REQUIRED_SECTIONS, OPTIMIZED_BACKEND_SECTIONS}


def _score_readability(*, plain_text: str) -> int:
    if not plain_text.strip():
        return 0
    score = ATS_SCORE_BREAKDOWN_MAX["readability"]
    words = plain_text.split()
    if len(words) < 70:
        score -= 2
    if len(words) > 900:
        score -= 5
    lines = [line.strip() for line in plain_text.splitlines() if line.strip()]
    if any(len(line.split()) > 45 for line in lines):
        score -= 3
    if not any(
        verb in plain_text.casefold()
        for verb in ("built", "delivered", "created", "led", "implemented")
    ):
        score -= 2
    return max(0, score)


def _score_risk(*, resume: dict[str, Any], parseability: dict[str, Any], hard_blocked: bool) -> int:
    if hard_blocked:
        return 0
    score = ATS_SCORE_BREAKDOWN_MAX["risk"]
    codes = _flag_codes(parseability)
    if "missing_source_refs" in codes:
        score -= 5
    if _side_effect_enabled(resume):
        score = 0
    return max(0, score)


def _breakdown(score: int, key: str, feedback: str) -> dict[str, Any]:
    return {"score": score, "max": ATS_SCORE_BREAKDOWN_MAX[key], "feedback": feedback}


def _formatting_feedback(parseability: dict[str, Any]) -> str:
    codes = _flag_codes(parseability)
    if not codes:
        return "Standard ATS sections and plain text are present."
    return "Formatting flags: " + ", ".join(codes)


def _keyword_feedback(keyword_analysis: dict[str, Any]) -> str:
    if keyword_analysis["missing"]:
        return f"Missing {len(keyword_analysis['missing'])} job keyword(s) that need source-backed evidence."
    if keyword_analysis["overused"]:
        return "Keyword coverage is good, but repeated terms should be reduced."
    return "Job keywords are represented with source-backed resume evidence."


def _structure_feedback(present_sections: list[str]) -> str:
    if present_sections == list(ATS_REQUIRED_SECTIONS):
        return "Required ATS section order is present."
    return "Resume should use the required ATS section order."


def _risk_feedback(parseability: dict[str, Any]) -> str:
    codes = _flag_codes(parseability)
    if "internal_leakage" in codes:
        return "Internal implementation leakage blocks external review."
    if "side_effect_guard_enabled" in codes:
        return "External side effects must remain disabled."
    return "No high-risk ATS or side-effect issues detected."


def _suggestions(
    *,
    keyword_analysis: dict[str, Any],
    parseability: dict[str, Any],
    score_band: str,
    present_sections: list[str],
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for flag in parseability["flags"]:
        priority = (
            "high"
            if flag["code"] in {"internal_leakage", "missing_section", "section_order"}
            else "medium"
        )
        suggestions.append(
            {
                "category": "Structure" if "section" in flag["code"] else "Formatting",
                "issue": flag["message"],
                "recommendation": "Fix this before human review."
                if priority == "high"
                else "Review before approval.",
                "priority": priority,
                "safe_to_apply_automatically": False,
                "requires_source_fact": False,
            }
        )
    for item in keyword_analysis["missing"][:6]:
        suggestions.append(
            {
                "category": "Keywords",
                "issue": f"Job keyword not source-backed in resume: {item['keyword']}",
                "recommendation": item["recommendation"],
                "priority": item["severity"],
                "safe_to_apply_automatically": False,
                "requires_source_fact": True,
            }
        )
    for item in keyword_analysis["overused"]:
        suggestions.append(
            {
                "category": "Keywords",
                "issue": f"Keyword appears too often for ATS readability: {item['keyword']}",
                "recommendation": item["recommendation"],
                "priority": "medium",
                "safe_to_apply_automatically": False,
                "requires_source_fact": False,
            }
        )
    if score_band == "human_review":
        suggestions.append(
            {
                "category": "Threshold",
                "issue": "Packet is human-review-ready but below the 90 send/apply threshold.",
                "recommendation": "Improve source-backed keyword coverage or structure before send/apply approval.",
                "priority": "medium",
                "safe_to_apply_automatically": False,
                "requires_source_fact": True,
            }
        )
    if present_sections == list(ATS_REQUIRED_SECTIONS) and not suggestions:
        suggestions.append(
            {
                "category": "Review",
                "issue": "No blocking ATS issues detected.",
                "recommendation": "Proceed to exact-version human approval if the score meets the required threshold.",
                "priority": "low",
                "safe_to_apply_automatically": False,
                "requires_source_fact": False,
            }
        )
    return suggestions


def _strengths(
    *,
    present_sections: list[str],
    keyword_analysis: dict[str, Any],
    score_breakdown: dict[str, dict[str, Any]],
) -> list[str]:
    strengths = []
    if present_sections == list(ATS_REQUIRED_SECTIONS):
        strengths.append("Standard ATS section order is present.")
    if keyword_analysis["coverage"] >= 0.8:
        strengths.append("Most job keywords are represented with source-backed evidence.")
    if score_breakdown["risk"]["score"] == score_breakdown["risk"]["max"]:
        strengths.append("No internal leakage or side-effect risk detected.")
    return strengths


def _roast(
    *, score_band: str, keyword_analysis: dict[str, Any], parseability: dict[str, Any]
) -> list[str]:
    if score_band == "send_ready":
        return [
            "Strong ATS shape: standard sections, source-backed keywords, and low operational risk."
        ]
    if score_band == "human_review":
        return [
            "Good enough for human review, but it still needs tightening before the 90+ send bar."
        ]
    if _flag_codes(parseability):
        return [
            "The resume has fixable ATS structure or safety issues before it should reach review."
        ]
    if keyword_analysis["missing"]:
        return [
            "The resume is structurally usable, but important job keywords are not source-backed yet."
        ]
    return ["The packet needs stronger source-backed alignment before review."]


def _summary(*, ats_score: int, score_band: str, keyword_analysis: dict[str, Any]) -> str:
    missing = len(keyword_analysis["missing"])
    return (
        f"ATS simulator score is {ats_score}/100 ({score_band}). "
        f"Matched {len(keyword_analysis['matched'])} keyword(s); {missing} keyword gap(s) require source-backed review."
    )


def _opportunity(*, posting: dict[str, Any], packet: dict[str, Any]) -> dict[str, str]:
    packet_opp = _dict_value(packet.get("opportunity"))
    return {
        "id": str(posting.get("id") or packet_opp.get("id") or ""),
        "employer_name": str(
            posting.get("company")
            or posting.get("employer")
            or packet_opp.get("employer_name")
            or ""
        ),
        "role_title": str(posting.get("title") or packet_opp.get("role_title") or ""),
        "job_url": str(posting.get("url") or packet_opp.get("job_url") or ""),
        "ats_provider_hint": _ats_provider_hint(posting),
    }


def _ats_provider_hint(posting: dict[str, Any]) -> str:
    text = f"{posting.get('provider', '')} {posting.get('url', '')}".casefold()
    for provider in ("greenhouse", "lever", "ashby", "workday", "linkedin"):
        if provider in text:
            return provider
    if any(marker in text for marker in ("dailyremote", "englishjobs", "job board", "aggregator")):
        return "aggregator"
    return "unknown"


def _flag_codes(parseability: dict[str, Any]) -> list[str]:
    flags = parseability.get("flags", [])
    return [str(flag.get("code")) for flag in flags if isinstance(flag, dict) and flag.get("code")]


def _score_band(*, ats_score: int, hard_blocked: bool) -> str:
    if hard_blocked or ats_score < ATS_THRESHOLDS["improvement_review"]:
        return "blocked"
    if ats_score >= ATS_THRESHOLDS["send_ready"]:
        return "send_ready"
    if ats_score >= ATS_THRESHOLDS["human_review"]:
        return "human_review"
    return "improvement_review"


def _has_internal_leakage(text: str) -> bool:
    lowered = text.casefold()
    return any(token in lowered for token in INTERNAL_LEAKAGE_TOKENS)


def _side_effect_enabled(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            (key == "external_side_effects_allowed" and child is True)
            or _side_effect_enabled(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_side_effect_enabled(child) for child in value)
    return False


def _contains_keyword(keyword: str, text: str) -> bool:
    return _keyword_count(keyword, text) > 0


def _keyword_count(keyword: str, text: str) -> int:
    if not text:
        return 0
    escaped = re.escape(keyword)
    if re.fullmatch(r"[A-Za-z0-9+#.]+", keyword):
        suffix = "s?" if keyword.upper() == "API" else ""
        pattern = rf"(?<![A-Za-z0-9]){escaped}{suffix}(?![A-Za-z0-9])"
    else:
        pattern = rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
    return len(re.findall(pattern, text, flags=re.IGNORECASE))
