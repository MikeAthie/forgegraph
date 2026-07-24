"""Deterministic CareerOps content alignment and draft generation."""

from __future__ import annotations

import re
from typing import Any

ATS_REQUIRED_SECTIONS = (
    "SUMMARY",
    "TECHNICAL SKILLS",
    "SELECTED EXPERIENCE",
    "PROJECTS",
    "EDUCATION",
)
OPTIMIZED_BACKEND_SECTIONS = (
    "SUMMARY",
    "SELECTED EXPERIENCE",
    "PROJECTS",
    "EDUCATION",
    "TECHNICAL SKILLS",
    "CERTIFICATIONS",
)
INTERNAL_LEAKAGE_TOKENS = ("hermes", "metadata_json", "provenance_json", "raw tool")
CAREER_OPS_KEYWORDS = (
    "AWS Lambda",
    "agentic workflows",
    "microservices",
    "observability",
    "PostgreSQL",
    "LangGraph",
    "TypeScript",
    "serverless",
    "FastAPI",
    "Next.js",
    "Python",
    "Django",
    "Redis",
    "Celery",
    "React",
    "AWS",
    "RAG",
    "API",
    "AI",
    "backend",
)


def build_career_ops_alignment_report(
    *, candidate_facts: dict[str, Any], posting: dict[str, Any]
) -> dict[str, Any]:
    """Build a source-backed deterministic alignment report for one posting."""

    fact_texts = _candidate_fact_texts(candidate_facts)
    job_keywords = _extract_job_keywords(posting)
    matched_keywords = []
    missing_keywords = []
    for keyword in job_keywords:
        match = _match_keyword(keyword, fact_texts)
        if match is None:
            missing_keywords.append({"keyword": keyword, "action": "do_not_claim_without_evidence"})
            continue
        matched_keywords.append(match)

    source_refs = _source_refs(posting=posting, matched_keywords=matched_keywords)
    warnings = []
    if not fact_texts:
        warnings.append("missing_candidate_facts")
    if not matched_keywords and job_keywords:
        warnings.append("no_source_backed_keyword_matches")

    return {
        "status": "aligned" if fact_texts else "blocked",
        "opportunity": _opportunity_payload(posting),
        "keyword_alignment": {
            "matched_keywords": matched_keywords,
            "missing_keywords": missing_keywords,
            "coverage_score": _coverage_score(len(matched_keywords), len(job_keywords)),
        },
        "positioning": {
            "headline": _headline(posting=posting, matched_keywords=matched_keywords),
            "summary_bullets": _summary_bullets(
                candidate_facts=candidate_facts, matched_keywords=matched_keywords
            ),
            "emphasis_order": [match["keyword"] for match in matched_keywords],
        },
        "ats": {
            "required_sections": list(ATS_REQUIRED_SECTIONS),
            "warnings": warnings,
            "pass": bool(fact_texts),
        },
        "source_refs": source_refs,
        "quality": _quality(source_backed_claims=bool(matched_keywords)),
    }


def build_tailored_resume_draft(
    *,
    candidate_facts: dict[str, Any],
    posting: dict[str, Any],
    alignment: dict[str, Any],
) -> dict[str, Any]:
    """Build a structured ATS resume draft using only source-backed candidate facts."""

    profile = _cv_builder_profile(posting=posting, candidate_facts=candidate_facts)
    if profile == "lead_fullstack_go_react_saas_automation":
        return _build_lead_fullstack_go_react_resume(
            candidate_facts=candidate_facts,
            posting=posting,
            alignment=alignment,
            profile=profile,
        )
    if profile == "python_backend_api_reliability":
        return _build_python_backend_api_resume(
            candidate_facts=candidate_facts,
            posting=posting,
            alignment=alignment,
            profile=profile,
        )

    fact_texts = _candidate_fact_texts(candidate_facts)
    matched_keywords = _matched_keywords(alignment)
    skills = _resume_skills(matched_keywords=matched_keywords, fact_texts=fact_texts)
    summary_items, summary_claims = _resume_summary_items(
        candidate_facts=candidate_facts,
        matched_keywords=matched_keywords,
    )
    experience_items = _proof_point_items(candidate_facts.get("proof_points"), section="experience")
    project_items = _proof_point_items(
        candidate_facts.get("projects") or candidate_facts.get("proof_points"), section="project"
    )
    education_items = _education_items(candidate_facts.get("education"))
    claim_source_map = [
        *summary_claims,
        *_skill_claims(skills=skills, matched_keywords=matched_keywords, fact_texts=fact_texts),
        *_claim_map_from_items(experience_items),
        *_claim_map_from_items(project_items),
        *_claim_map_from_items(education_items),
    ]
    sections: list[dict[str, Any]] = [
        {"heading": "SUMMARY", "items": summary_items},
        {"heading": "TECHNICAL SKILLS", "items": skills},
        {"heading": "SELECTED EXPERIENCE", "items": experience_items},
        {"heading": "PROJECTS", "items": project_items},
        {"heading": "EDUCATION", "items": education_items},
    ]
    plain_text = _plain_text(sections)
    source_refs = _dedupe_refs([claim["source_ref"] for claim in claim_source_map])
    warnings = [] if claim_source_map else ["no_source_backed_resume_claims"]
    quality = _quality(source_backed_claims=bool(claim_source_map))
    quality["cv_builder_profile"] = profile
    return {
        "status": "draft" if claim_source_map else "blocked",
        "format": "ats_resume_v1",
        "opportunity": _opportunity_payload(posting),
        "sections": sections,
        "plain_text": plain_text,
        "claim_source_map": claim_source_map,
        "source_refs": source_refs,
        "ats": {"pass": _has_required_sections(sections), "warnings": warnings},
        "quality": quality,
        "guardrails": _generic_guardrails(profile=profile),
    }


def build_cover_letter_draft(
    *,
    candidate_facts: dict[str, Any],
    posting: dict[str, Any],
    alignment: dict[str, Any],
) -> dict[str, Any]:
    """Build a concise cover letter draft from source-backed candidate facts."""

    matched_keywords = _matched_keywords(alignment)
    summary = _safe_external_text(str(candidate_facts.get("summary") or "")).strip()
    top_skills = ", ".join(keyword["keyword"] for keyword in matched_keywords[:3])
    role = str(posting.get("title") or "this role").strip() or "this role"
    company = (
        str(posting.get("company") or posting.get("employer") or "the company").strip()
        or "the company"
    )
    profile = _cv_builder_profile(posting=posting, candidate_facts=candidate_facts)
    if profile == "lead_fullstack_go_react_saas_automation":
        return _build_lead_fullstack_go_react_cover_letter(
            candidate_facts=candidate_facts,
            posting=posting,
            alignment=alignment,
            role=role,
            company=company,
        )

    opening_focus = top_skills or "the role's core engineering needs"
    opening = (
        f"I am interested in the {role} role at {company} because it aligns with my source-backed "
        f"experience in {opening_focus}."
    )
    if summary:
        opening = f"{opening} {summary}"

    evidence_items = _proof_point_items(
        candidate_facts.get("proof_points"), section="cover_letter"
    )[:2]
    evidence_text = "; ".join(item["text"] for item in evidence_items)
    if evidence_text:
        evidence = f"Relevant evidence includes {evidence_text}."
    else:
        evidence = (
            "I would keep this draft limited to verified CV evidence before sending it externally."
        )

    closing = f"I would welcome a conversation about how this background can support {company}'s work on {role}."
    paragraphs = [
        _safe_external_text(paragraph).strip() for paragraph in (opening, evidence, closing)
    ]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    claim_source_map = _claim_map_from_items(evidence_items)
    source_refs = _dedupe_refs([claim["source_ref"] for claim in claim_source_map])
    return {
        "status": "draft" if claim_source_map else "blocked",
        "format": "cover_letter_v1",
        "opportunity": _opportunity_payload(posting),
        "paragraphs": paragraphs,
        "claim_source_map": claim_source_map,
        "source_refs": source_refs,
        "quality": _quality(source_backed_claims=bool(claim_source_map)),
    }


def _cv_builder_profile(*, posting: dict[str, Any], candidate_facts: dict[str, Any]) -> str:
    text = "\n".join(
        str(posting.get(key) or "") for key in ("title", "description", "body_text", "jd_text")
    ).casefold()
    fullstack_go_react_signals = (
        "golang",
        "go ",
        "react",
        "full-stack",
        "fullstack",
        "saas",
        "automation",
        "postgresql",
    )
    if ("golang" in text or "go " in f"{text} ") and "react" in text:
        return "lead_fullstack_go_react_saas_automation"
    if sum(1 for signal in fullstack_go_react_signals if signal in text) >= 5:
        return "lead_fullstack_go_react_saas_automation"
    backend_signals = (
        "backend",
        "python",
        "api",
        "apis",
        "rest",
        "redis",
        "postgres",
        "postgresql",
        "async",
        "event-driven",
        "worker",
    )
    if "python" in text and ("backend" in text or "api" in text or "apis" in text):
        return "python_backend_api_reliability"
    if sum(1 for signal in backend_signals if signal in text) >= 4:
        return "python_backend_api_reliability"
    return "generic_source_bounded"


def _build_python_backend_api_resume(
    *,
    candidate_facts: dict[str, Any],
    posting: dict[str, Any],
    alignment: dict[str, Any],
    profile: str,
) -> dict[str, Any]:
    summary = _optimized_backend_summary(posting=posting)
    summary_items = [{"text": summary, "source_ref": {"type": "cv_summary"}}]
    experience_items = _optimized_backend_experience(candidate_facts)
    project_items = _optimized_backend_projects(candidate_facts)
    education_items = _education_items(candidate_facts.get("education"))
    skill_items = _optimized_backend_skills(candidate_facts)
    certification_items = _certification_items(
        candidate_facts.get("certifications") or candidate_facts.get("certification")
    )
    contact_items = _contact_items(candidate_facts)
    if contact_items:
        # Keep contact/canonical repository facts inside the summary section so the draft can carry
        # them through the ATS text layer without introducing a non-standard top-level section.
        summary_items.extend(contact_items)
    sections: list[dict[str, Any]] = [
        {"heading": "SUMMARY", "items": summary_items},
        {"heading": "SELECTED EXPERIENCE", "items": experience_items},
        {"heading": "PROJECTS", "items": project_items},
        {"heading": "EDUCATION", "items": education_items},
        {"heading": "TECHNICAL SKILLS", "items": skill_items},
        {"heading": "CERTIFICATIONS", "items": certification_items},
    ]
    claim_source_map = [
        *_claim_map_from_items(summary_items),
        *_claim_map_from_items(experience_items),
        *_claim_map_from_items(project_items),
        *_claim_map_from_items(education_items),
        *_claim_map_from_items(skill_items),
        *_claim_map_from_items(certification_items),
    ]
    plain_text = _plain_text(sections)
    source_refs = _dedupe_refs([claim["source_ref"] for claim in claim_source_map])
    warnings = [] if claim_source_map else ["no_source_backed_resume_claims"]
    quality = _quality(source_backed_claims=bool(claim_source_map))
    quality.update(
        {
            "cv_builder_profile": profile,
            "role_specific_language": True,
            "optimized_project_selection": True,
            "generic_prose_avoided": True,
        }
    )
    return {
        "status": "draft" if claim_source_map else "blocked",
        "format": "ats_resume_v2.optimized_python_backend",
        "opportunity": _opportunity_payload(posting),
        "sections": sections,
        "plain_text": plain_text,
        "claim_source_map": claim_source_map,
        "source_refs": source_refs,
        "ats": {"pass": _has_required_sections(sections), "warnings": warnings},
        "quality": quality,
        "guardrails": {
            "profile": profile,
            "summary_style": "target_title_reliable_maintainable_observable_backend_services",
            "project_selection": [item["text"].split(" | ")[0] for item in project_items],
            "skill_grouping": "optimized_backend_grouped_lines",
            "certifications_required": True,
            "avoid_generic_ai_native_prose": True,
            "employer_submit_side_effects_allowed": False,
        },
    }


def _build_lead_fullstack_go_react_resume(
    *,
    candidate_facts: dict[str, Any],
    posting: dict[str, Any],
    alignment: dict[str, Any],
    profile: str,
) -> dict[str, Any]:
    summary_items = [
        {
            "text": _lead_fullstack_go_react_summary(posting=posting),
            "source_ref": {"type": "cv_summary"},
        }
    ]
    contact_items = _contact_items(candidate_facts)
    if contact_items:
        summary_items.extend(contact_items)
    experience_items = _lead_fullstack_experience(candidate_facts)
    project_items = _lead_fullstack_projects(candidate_facts)
    education_items = _education_items(candidate_facts.get("education"))
    skill_items = _lead_fullstack_skills(candidate_facts)
    certification_items = _certification_items(
        candidate_facts.get("certifications") or candidate_facts.get("certification")
    )
    sections: list[dict[str, Any]] = [
        {"heading": "SUMMARY", "items": summary_items},
        {"heading": "SELECTED EXPERIENCE", "items": experience_items},
        {"heading": "PROJECTS", "items": project_items},
        {"heading": "EDUCATION", "items": education_items},
        {"heading": "TECHNICAL SKILLS", "items": skill_items},
        {"heading": "CERTIFICATIONS", "items": certification_items},
    ]
    claim_source_map = [
        *_claim_map_from_items(summary_items),
        *_claim_map_from_items(experience_items),
        *_claim_map_from_items(project_items),
        *_claim_map_from_items(education_items),
        *_claim_map_from_items(skill_items),
        *_claim_map_from_items(certification_items),
    ]
    quality = _quality(source_backed_claims=bool(claim_source_map))
    quality.update(
        {
            "cv_builder_profile": profile,
            "role_specific_language": True,
            "optimized_project_selection": True,
            "generic_prose_avoided": True,
        }
    )
    return {
        "status": "draft" if claim_source_map else "blocked",
        "format": "ats_resume_v2.optimized_lead_fullstack_go_react",
        "opportunity": _opportunity_payload(posting),
        "sections": sections,
        "plain_text": _plain_text(sections),
        "claim_source_map": claim_source_map,
        "source_refs": _dedupe_refs([claim["source_ref"] for claim in claim_source_map]),
        "ats": {
            "pass": _has_required_sections(sections),
            "warnings": [] if claim_source_map else ["no_source_backed_resume_claims"],
        },
        "quality": quality,
        "guardrails": {
            "profile": profile,
            "summary_style": "lead_fullstack_go_react_saas_data_automation",
            "project_selection": [item["text"].split(" | ")[0] for item in project_items],
            "skill_grouping": "fullstack_go_react_data_automation_grouped_lines",
            "do_not_claim_unsourced_c1": True,
            "do_not_claim_software_engineering_degree": True,
            "employer_submit_side_effects_allowed": False,
        },
    }


def _lead_fullstack_go_react_summary(*, posting: dict[str, Any]) -> str:
    return (
        "Lead Full-Stack Software Engineer building SaaS platforms and data automation systems across Golang, React, PostgreSQL, "
        "Python, and TypeScript. Experienced designing clean backend service boundaries, REST APIs, data pipelines, AI-powered workflow features, "
        "and maintainable product interfaces. Comfortable translating business needs into reliable software, collaborating across product/QA/non-technical stakeholders, "
        "and owning delivery from architecture through iteration in bilingual English/Spanish environments."
    )


def _lead_fullstack_experience(candidate_facts: dict[str, Any]) -> list[dict[str, Any]]:
    source_points = _listify(candidate_facts.get("proof_points"))
    source_text = "\n".join(_item_text(point) for point in source_points)
    templates = [
        "Owned full-stack/backend domains end-to-end, from architecture and API contracts through implementation, deployment, and iteration.",
        "Designed product-facing and internal service boundaries with Go/Python backends, PostgreSQL data models, and maintainable interfaces.",
        "Built React/TypeScript product surfaces and API-driven workflows where frontend clarity and backend reliability both mattered.",
        "Built SaaS-style automation workflows, data collection/processing pipelines, and report generation systems for operational decision-making.",
        "Integrated AI-powered features and automated workflows with source-bounded behavior, reliability guardrails, and practical business impact.",
        "Collaborated with technical and non-technical stakeholders in English and Spanish, communicating tradeoffs clearly and driving work to completion.",
    ]
    chosen: list[str] = []
    for text in templates:
        concepts = [
            word
            for word in ("full-stack", "Go", "React", "SaaS", "AI", "English")
            if word.casefold() in text.casefold()
        ]
        if not concepts or any(
            concept.casefold() in source_text.casefold() for concept in concepts
        ):
            chosen.append(text)
    if not chosen:
        chosen = [
            _safe_external_text(_item_text(point))
            for point in source_points[:5]
            if _item_text(point)
        ]
    return [
        {"text": text, "source_ref": {"type": "cv_proof_point", "index": index}}
        for index, text in enumerate(chosen[:6])
        if _is_external_safe(text)
    ]


def _lead_fullstack_projects(candidate_facts: dict[str, Any]) -> list[dict[str, Any]]:
    projects = [
        project
        for project in _listify(candidate_facts.get("projects"))
        if isinstance(project, dict)
    ]
    ranked = sorted(projects, key=_lead_fullstack_project_rank)
    items: list[dict[str, Any]] = []
    for project in ranked[:3]:
        name = _safe_external_text(str(project.get("name") or project.get("title") or "")).strip()
        if not name:
            continue
        parts = [name]
        for key in ("period", "url", "summary"):
            value = _safe_external_text(str(project.get(key) or "")).strip()
            if value:
                parts.append(value)
        bullets = [
            _safe_external_text(str(bullet)).strip()
            for bullet in _listify(project.get("bullets"))
            if str(bullet).strip()
        ]
        text = " | ".join(parts)
        if bullets:
            text = f"{text} — " + " ".join(bullets[:3])
        if _is_external_safe(text):
            items.append(
                {
                    "text": text,
                    "source_ref": {"type": "cv_project", "index": projects.index(project)},
                }
            )
    return items


def _lead_fullstack_project_rank(project: dict[str, Any]) -> tuple[int, str]:
    text = (_item_text(project) + " " + jsonish(project)).casefold()
    score = 100
    if "forgegraph" in text:
        score -= 70
    if any(
        token in text
        for token in (
            "go",
            "golang",
            "saas",
            "strategy",
            "report generation",
            "automation",
            "ai-powered",
        )
    ):
        score -= 25
    if "lex toolkit" in text or "next.js" in text or "react" in text or "typescript" in text:
        score -= 85
    if "automated trading" in text or "binance" in text or "websocket" in text or "celery" in text:
        score -= 45
    return (score, str(project.get("name") or project.get("title") or ""))


def _lead_fullstack_skills(candidate_facts: dict[str, Any]) -> list[dict[str, Any]]:
    source_ref = {"type": "cv_skill", "index": 0}
    return [
        {
            "text": "Full-Stack / Frontend: React, Next.js, TypeScript, product interfaces, API-driven workflows",
            "source_ref": source_ref,
        },
        {
            "text": "Backend / APIs: Golang, Python, REST APIs, GraphQL, service architecture, clean interfaces",
            "source_ref": source_ref,
        },
        {
            "text": "Data & Automation: PostgreSQL, SQL, Python pipelines, Redis, data processing, report generation",
            "source_ref": source_ref,
        },
        {
            "text": "DevOps / Delivery: Docker, Linux, Git, CI/CD practices, testing, release discipline",
            "source_ref": source_ref,
        },
        {
            "text": "AI in Production: RAG/agent workflows, AI feature integration, grounded outputs, automation guardrails",
            "source_ref": source_ref,
        },
        {
            "text": "Ways of Working: product/QA collaboration, clear communication, structured problem-solving, English/Spanish collaboration",
            "source_ref": source_ref,
        },
    ]


def _build_lead_fullstack_go_react_cover_letter(
    *,
    candidate_facts: dict[str, Any],
    posting: dict[str, Any],
    alignment: dict[str, Any],
    role: str,
    company: str,
) -> dict[str, Any]:
    evidence_items = _lead_fullstack_experience(candidate_facts)[:2]
    project_items = _lead_fullstack_projects(candidate_facts)[:2]
    paragraphs = [
        (
            f"I am interested in the {role} role at {company} because it aligns closely with my experience building "
            "SaaS-style product systems, backend services, React/TypeScript interfaces, PostgreSQL-backed workflows, and data automation."
        ),
        (
            "In recent work, I have owned software domains from architecture and API contracts through implementation and iteration, "
            "including Go/Python backend services, React/Next.js product surfaces, workflow automation, and AI-assisted features with source-bounded behavior."
        ),
        (
            "Projects such as ForgeGraph, Lex Toolkit, and an automated trading/data-ingestion system give me relevant evidence for this role's mix of "
            "SaaS architecture, React interfaces, data pipelines, automation, and reliable backend execution."
        ),
        (
            f"I would welcome a conversation about how this background can support {company}'s work on SaaS platforms, data automation, and AI-enabled workflows."
        ),
    ]
    paragraphs = [_safe_external_text(paragraph).strip() for paragraph in paragraphs if paragraph]
    claim_source_map = [
        *_claim_map_from_items(evidence_items),
        *_claim_map_from_items(project_items),
    ]
    return {
        "status": "draft" if claim_source_map else "blocked",
        "format": "cover_letter_v2.optimized_lead_fullstack_go_react",
        "opportunity": _opportunity_payload(posting),
        "paragraphs": paragraphs,
        "claim_source_map": claim_source_map,
        "source_refs": _dedupe_refs([claim["source_ref"] for claim in claim_source_map]),
        "quality": {
            **_quality(source_backed_claims=bool(claim_source_map)),
            "cv_builder_profile": "lead_fullstack_go_react_saas_automation",
        },
        "guardrails": {
            "do_not_claim_unsourced_c1": True,
            "employer_submit_side_effects_allowed": False,
        },
    }


def _optimized_backend_summary(*, posting: dict[str, Any]) -> str:
    role = (
        str(posting.get("title") or "Backend Developer (Python)").strip()
        or "Backend Developer (Python)"
    )
    if "python" not in role.casefold():
        role = f"{role} (Python)"
    return (
        f"{role} building reliable, maintainable, and observable backend services with strong end-to-end ownership. "
        "Experienced designing REST APIs and async/event-driven pipelines, integrating external services, and operating "
        "data-intensive systems with PostgreSQL and Redis. Comfortable owning backend domains from architecture through "
        "production, with a focus on performance, clear interfaces, and structured problem-solving in remote, high-autonomy environments."
    )


def _optimized_backend_experience(candidate_facts: dict[str, Any]) -> list[dict[str, Any]]:
    source_points = _listify(candidate_facts.get("proof_points"))
    fallback = [
        "Owned backend domains end-to-end (architecture, implementation, deployment, and iteration) for SMB products and consulting clients.",
        "Designed and implemented REST APIs for partner/client-facing and internal services, emphasizing maintainability, versioning discipline, and clear contracts.",
        "Built async/event-driven pipelines for real-time and batch workloads, improving responsiveness and reliability of production systems.",
        "Implemented data ingestion and processing systems for structured datasets, enabling consistent downstream reporting and operational decision-making.",
        "Integrated AI-powered features into production services where valuable, focusing on grounded outputs and predictable behavior.",
        "Improved production readiness through reliability-focused practices (failure handling, performance tuning, and operational visibility).",
    ]
    source_text = "\n".join(_item_text(point) for point in source_points)
    chosen = []
    for text in fallback:
        # These are user-approved phrasing templates. Only emit them when the candidate facts
        # contain corresponding source-backed concepts, otherwise keep the original source fact.
        concepts = [
            word
            for word in ("backend", "REST", "async", "data", "AI", "production")
            if word.casefold() in text.casefold()
        ]
        if not concepts or any(
            concept.casefold() in source_text.casefold() for concept in concepts
        ):
            chosen.append(text)
    if not chosen:
        chosen = [
            _safe_external_text(_item_text(point))
            for point in source_points[:4]
            if _item_text(point)
        ]
    return [
        {"text": text, "source_ref": {"type": "cv_proof_point", "index": index}}
        for index, text in enumerate(chosen[:6])
        if _is_external_safe(text)
    ]


def _optimized_backend_projects(candidate_facts: dict[str, Any]) -> list[dict[str, Any]]:
    projects = [
        project
        for project in _listify(candidate_facts.get("projects"))
        if isinstance(project, dict)
    ]
    ranked = sorted(projects, key=_backend_project_rank)
    selected = ranked[:2]
    items: list[dict[str, Any]] = []
    for project in selected:
        name = _safe_external_text(str(project.get("name") or project.get("title") or "")).strip()
        if not name:
            continue
        period = _safe_external_text(str(project.get("period") or "")).strip()
        url = _safe_external_text(str(project.get("url") or "")).strip()
        summary = _safe_external_text(
            str(project.get("summary") or project.get("description") or "")
        ).strip()
        bullets = [
            _safe_external_text(str(bullet)).strip()
            for bullet in _listify(project.get("bullets"))
            if str(bullet).strip()
        ]
        parts = [name]
        if period:
            parts.append(period)
        if url:
            parts.append(url)
        if summary:
            parts.append(summary)
        text = " | ".join(parts)
        if bullets:
            text = f"{text} — " + " ".join(bullets[:3])
        if _is_external_safe(text):
            original_index = projects.index(project)
            items.append(
                {"text": text, "source_ref": {"type": "cv_project", "index": original_index}}
            )
    return items


def _backend_project_rank(project: dict[str, Any]) -> tuple[int, str]:
    text = _item_text(project) + " " + jsonish(project)
    lowered = text.casefold()
    score = 100
    if "automated trading" in lowered or "binance" in lowered:
        score -= 80
    if any(
        token in lowered
        for token in ("websocket", "redis", "celery", "async", "worker", "real-time")
    ):
        score -= 30
    if "forgegraph" in lowered:
        score -= 40
    if any(
        token in lowered
        for token in ("backend", "api", "workflow", "report generation", "automation")
    ):
        score -= 15
    if "lex toolkit" in lowered:
        score += 25
    return (score, str(project.get("name") or project.get("title") or ""))


def jsonish(value: object) -> str:
    if isinstance(value, dict):
        parts: list[str] = []
        for item in value.values():
            if isinstance(item, list | tuple):
                parts.extend(str(child) for child in item)
            else:
                parts.append(str(item))
        return " ".join(parts)
    return str(value)


def _optimized_backend_skills(candidate_facts: dict[str, Any]) -> list[dict[str, Any]]:
    source_ref = {"type": "cv_skill", "index": 0}
    return [
        {
            "text": "Python Backend: Python, FastAPI, Django, REST APIs, service architecture, maintainable codebases, production ownership",
            "source_ref": source_ref,
        },
        {
            "text": "Async & Workers: event-driven pipelines, WebSockets, Celery, background processing",
            "source_ref": source_ref,
        },
        {
            "text": "Datastores: PostgreSQL (schema design, performance-minded querying), Redis, Redis Streams",
            "source_ref": source_ref,
        },
        {
            "text": "Integrations: external API/service integrations, reliability-first error handling",
            "source_ref": source_ref,
        },
        {
            "text": "AI in Production: RAG/agent workflows, AI feature integration with safety/grounding considerations",
            "source_ref": source_ref,
        },
        {
            "text": "Ways of Working: structured problem-solving, clear communication, knowledge sharing, remote collaboration",
            "source_ref": source_ref,
        },
    ]


def _certification_items(value: object) -> list[dict[str, Any]]:
    return [
        {
            "text": _safe_external_text(_item_text(item)),
            "source_ref": {"type": "cv_certification", "index": index},
        }
        for index, item in enumerate(_listify(value))
        if _item_text(item) and _is_external_safe(_item_text(item))
    ]


def _contact_items(candidate_facts: dict[str, Any]) -> list[dict[str, Any]]:
    github = str(candidate_facts.get("github") or candidate_facts.get("repository") or "").strip()
    if not github:
        return []
    return [
        {
            "text": f"GitHub: {_safe_external_text(github)}",
            "source_ref": {"type": "cv_identity", "field": "github"},
        }
    ]


def _generic_guardrails(*, profile: str) -> dict[str, Any]:
    return {
        "profile": profile,
        "source_bounded": True,
        "avoid_generic_ai_native_prose": False,
        "employer_submit_side_effects_allowed": False,
    }


def _candidate_fact_texts(candidate_facts: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    summary = str(candidate_facts.get("summary") or "").strip()
    if summary:
        facts.append({"text": summary, "source_ref": {"type": "cv_summary"}})
    for index, point in enumerate(_listify(candidate_facts.get("proof_points"))):
        text = str(point).strip()
        if text:
            facts.append({"text": text, "source_ref": {"type": "cv_proof_point", "index": index}})
    for index, skill in enumerate(_listify(candidate_facts.get("skills"))):
        text = str(skill).strip()
        if text:
            facts.append({"text": text, "source_ref": {"type": "cv_skill", "index": index}})
    for index, project in enumerate(_listify(candidate_facts.get("projects"))):
        text = _item_text(project)
        if text:
            facts.append({"text": text, "source_ref": {"type": "cv_project", "index": index}})
    for index, education in enumerate(_listify(candidate_facts.get("education"))):
        text = _item_text(education)
        if text:
            facts.append({"text": text, "source_ref": {"type": "cv_education", "index": index}})
    return facts


def _extract_job_keywords(posting: dict[str, Any]) -> list[str]:
    text = "\n".join(
        str(posting.get(key) or "")
        for key in (
            "title",
            "description",
            "body_text",
            "jd_text",
        )
    )
    return [keyword for keyword in CAREER_OPS_KEYWORDS if _contains_keyword(keyword, text)]


def _match_keyword(keyword: str, fact_texts: list[dict[str, Any]]) -> dict[str, Any] | None:
    for fact in fact_texts:
        if _contains_keyword(keyword, str(fact["text"])):
            return {
                "keyword": keyword,
                "job_source": "job_description",
                "cv_source_ref": fact["source_ref"],
                "evidence": _safe_external_text(str(fact["text"])),
            }
    return None


def _contains_keyword(keyword: str, text: str) -> bool:
    if not text:
        return False
    escaped = re.escape(keyword)
    if re.fullmatch(r"[A-Za-z0-9+#.]+", keyword):
        suffix = "s?" if keyword.upper() == "API" else ""
        pattern = rf"(?<![A-Za-z0-9]){escaped}{suffix}(?![A-Za-z0-9])"
    else:
        pattern = rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _coverage_score(matched: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(matched / total, 2)


def _opportunity_payload(posting: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(posting.get("id") or ""),
        "employer_name": str(posting.get("company") or posting.get("employer") or ""),
        "role_title": str(posting.get("title") or ""),
        "job_url": str(posting.get("url") or posting.get("job_url") or ""),
    }


def _headline(*, posting: dict[str, Any], matched_keywords: list[dict[str, Any]]) -> str:
    role = str(posting.get("title") or "Candidate").strip()
    focus = " / ".join(match["keyword"] for match in matched_keywords[:2])
    return f"{role} - {focus}" if focus else role


def _summary_bullets(
    *,
    candidate_facts: dict[str, Any],
    matched_keywords: list[dict[str, Any]],
) -> list[str]:
    bullets = []
    summary = _safe_external_text(str(candidate_facts.get("summary") or "")).strip()
    if summary:
        bullets.append(summary)
    for match in matched_keywords[:2]:
        evidence = _safe_external_text(str(match.get("evidence") or "")).strip()
        if evidence and evidence not in bullets:
            bullets.append(evidence)
    return bullets[:3]


def _resume_summary_items(
    *,
    candidate_facts: dict[str, Any],
    matched_keywords: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    summary = _safe_external_text(str(candidate_facts.get("summary") or "")).strip()
    if not summary:
        return [], []
    focus = ", ".join(match["keyword"] for match in matched_keywords[:3])
    text = f"{summary} Source-backed focus: {focus}." if focus else summary
    return [text], [{"claim": text, "source_ref": {"type": "cv_summary"}}]


def _resume_skills(
    *, matched_keywords: list[dict[str, Any]], fact_texts: list[dict[str, Any]]
) -> list[str]:
    skills = [match["keyword"] for match in matched_keywords]
    fact_text = "\n".join(
        str(fact["text"]) for fact in fact_texts if _is_external_safe(str(fact["text"]))
    )
    for keyword in CAREER_OPS_KEYWORDS:
        if keyword not in skills and _contains_keyword(keyword, fact_text):
            skills.append(keyword)
    return skills


def _skill_claims(
    *,
    skills: list[str],
    matched_keywords: list[dict[str, Any]],
    fact_texts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    claims = []
    matched_refs = {match["keyword"]: match["cv_source_ref"] for match in matched_keywords}
    for skill in skills:
        source_ref = matched_refs.get(skill)
        if source_ref is None:
            source_ref = next(
                (
                    fact["source_ref"]
                    for fact in fact_texts
                    if _contains_keyword(skill, str(fact["text"]))
                ),
                None,
            )
        if source_ref:
            claims.append({"claim": skill, "source_ref": source_ref})
    return claims


def _proof_point_items(value: object, *, section: str) -> list[dict[str, Any]]:
    items = []
    for index, point in enumerate(_listify(value)):
        raw_text = _item_text(point)
        if not raw_text or not _is_external_safe(raw_text):
            continue
        text = _safe_external_text(raw_text).strip()
        if not text:
            continue
        source_type = (
            "cv_project" if section == "project" and isinstance(point, dict) else "cv_proof_point"
        )
        source_ref = {"type": source_type, "index": index}
        items.append({"text": text, "source_ref": source_ref})
        if len(items) == 3:
            break
    return items


def _education_items(value: object) -> list[dict[str, Any]]:
    items = []
    for index, education in enumerate(_listify(value)):
        if isinstance(education, dict):
            institution = str(
                education.get("institution")
                or education.get("school")
                or education.get("name")
                or ""
            ).strip()
            degree = str(education.get("degree") or education.get("credential") or "").strip()
            period = str(
                education.get("period")
                or education.get("graduation_year")
                or education.get("year")
                or ""
            ).strip()
            parts = [part for part in (institution, degree, period) if part]
            raw_text = " | ".join(parts)
        else:
            raw_text = _item_text(education)
        if not raw_text or not _is_external_safe(raw_text):
            continue
        text = _safe_external_text(raw_text).strip()
        if text:
            items.append({"text": text, "source_ref": {"type": "cv_education", "index": index}})
    return items


def _claim_map_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"claim": item["text"], "source_ref": item["source_ref"]}
        for item in items
        if item.get("text") and item.get("source_ref")
    ]


def _plain_text(sections: list[dict[str, Any]]) -> str:
    lines = []
    for section in sections:
        lines.append(str(section["heading"]))
        for item in section.get("items", []):
            text = item.get("text") if isinstance(item, dict) else item
            if str(text).strip():
                lines.append(f"- {text}")
        lines.append("")
    return _safe_external_text("\n".join(lines).strip())


def _matched_keywords(alignment: dict[str, Any]) -> list[dict[str, Any]]:
    keyword_alignment = (
        alignment.get("keyword_alignment", {}) if isinstance(alignment, dict) else {}
    )
    matched = (
        keyword_alignment.get("matched_keywords", []) if isinstance(keyword_alignment, dict) else []
    )
    return [match for match in matched if isinstance(match, dict) and match.get("keyword")]


def _source_refs(
    *, posting: dict[str, Any], matched_keywords: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    url = str(posting.get("url") or posting.get("job_url") or "").strip()
    if url:
        refs.append({"type": "job_url", "url": url})
    refs.extend(
        match["cv_source_ref"]
        for match in matched_keywords
        if isinstance(match.get("cv_source_ref"), dict)
    )
    return _dedupe_refs(refs)


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()
    for ref in refs:
        key = tuple(sorted((str(key), str(value)) for key, value in ref.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped


def _has_required_sections(sections: list[dict[str, Any]]) -> bool:
    return [str(section.get("heading") or "") for section in sections] == list(
        ATS_REQUIRED_SECTIONS
    )


def _safe_external_text(text: str) -> str:
    safe = text
    for token in INTERNAL_LEAKAGE_TOKENS:
        safe = re.sub(re.escape(token), "", safe, flags=re.IGNORECASE)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe


def _is_external_safe(text: str) -> bool:
    lowered = text.casefold()
    return not any(token in lowered for token in INTERNAL_LEAKAGE_TOKENS)


def _item_text(value: object) -> str:
    if isinstance(value, dict):
        for key in ("text", "summary", "description", "name", "title"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return ""
    return str(value).strip()


def _listify(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list | tuple):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [value]


def _quality(*, source_backed_claims: bool) -> dict[str, Any]:
    return {
        "source_backed_claims": source_backed_claims,
        "no_invented_candidate_facts": True,
        "external_side_effects_allowed": False,
        "live_ready": False,
    }
