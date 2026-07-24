"""ForgeGraph-owned CareerOps first-prompt discovery orchestration.

This is the fake-provider-first slice: it creates durable ForgeGraph company,
department, whiteboard, program, kanban-style task, signal, and opportunity state
for a limited list of possible jobs. It deliberately performs no live scraping,
no employer outreach, and no application submission.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, cast

from django.db import transaction
from django.utils import timezone

from application.services.career_ops_engagements import ensure_career_ops_application_engagement
from application.services.career_ops_graph_contract import CAREER_OPS_PACK_ID
from application.services.career_ops_opportunities import (
    ensure_opportunity_for_signal,
    record_scanned_job,
)
from application.services.company_run_task_routing import (
    TASK_METADATA_KEY,
    bootstrap_task_routing_for_program,
    refresh_whiteboard_task_snapshot,
)
from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.routing import register_department
from application.services.tenancy import ensure_default_organization
from application.services.work_whiteboards import create_or_resume_whiteboard
from infrastructure.orm.models import (
    CompanyOpportunity,
    CompanyProgram,
    DepartmentRegistry,
    Graph,
    GraphVersion,
    ProgramStageState,
    User,
)

CAREER_OPS_FIRST_PROMPT_TEMPLATE_ID = "career_ops_first_prompt_discovery"
CAREER_OPS_FIRST_PROMPT_PROGRAM_LABEL = "CareerOps Discovery"
CAREER_OPS_FIRST_PROMPT_COMPANY_SOURCE = "career_ops"

CAREER_OPS_DEPARTMENTS = (
    ("candidate-profile-strategy", "Candidate Profile Strategy", "candidate_profile"),
    ("market-role-discovery", "Market & Role Discovery", "market_discovery"),
    ("opportunity-evaluation", "Opportunity Evaluation", "opportunity_evaluation"),
    ("application-packet-studio", "Application Packet Studio", "application_packet"),
    ("application-operations", "Application Operations", "application_operations"),
    ("interview-negotiation-prep", "Interview & Negotiation Prep", "interview_prep"),
    ("pipeline-integrity-analytics", "Pipeline Integrity Analytics", "pipeline_integrity"),
    ("candidate-approval-governance", "Candidate Approval Governance", "approval_governance"),
)

FIRST_PROMPT_STAGES = (
    {
        "id": "candidate_profile_intake",
        "label": "Candidate profile intake",
        "department_slug": "candidate-profile-strategy",
        "task_title": "Extract candidate profile and constraints from CV/prompt",
        "status": "completed",
        "dependencies": [],
    },
    {
        "id": "market_role_discovery",
        "label": "Market role discovery",
        "department_slug": "market-role-discovery",
        "task_title": "Create limited possible-job shortlist",
        "status": "completed",
        "dependencies": ["candidate_profile_intake"],
    },
    {
        "id": "opportunity_shortlist",
        "label": "Opportunity shortlist review",
        "department_slug": "opportunity-evaluation",
        "task_title": "Evaluate shortlist fit before packet work",
        "status": "not_started",
        "dependencies": ["market_role_discovery"],
    },
    {
        "id": "candidate_review",
        "label": "Candidate review",
        "department_slug": "candidate-approval-governance",
        "task_title": "Candidate reviews shortlist and next-step policy",
        "status": "not_started",
        "dependencies": ["opportunity_shortlist"],
    },
)

LIVE_DISCOVERY_STAGES = (
    {
        "id": "review_posting",
        "label": "Review posting",
        "department_slug": "market-role-discovery",
        "task_title": "Review posting",
        "status": "completed",
        "dependencies": [],
    },
    {
        "id": "score_fit",
        "label": "Score fit",
        "department_slug": "opportunity-evaluation",
        "task_title": "Score fit",
        "status": "completed",
        "dependencies": ["review_posting"],
    },
    {
        "id": "prepare_tailored_cv",
        "label": "Prepare tailored CV",
        "department_slug": "application-packet-studio",
        "task_title": "Prepare tailored CV",
        "status": "not_started",
        "dependencies": ["score_fit"],
    },
    {
        "id": "approval_before_apply",
        "label": "Approval before apply",
        "department_slug": "candidate-approval-governance",
        "task_title": "Approval before apply",
        "status": "blocked",
        "dependencies": ["prepare_tailored_cv"],
    },
)


@dataclass(frozen=True, slots=True)
class CareerOpsFirstPromptResult:
    company_id: str
    whiteboard_id: str
    program_id: str
    engagement_id: str
    department_ids: list[str] = field(default_factory=list)
    task_ids: list[str] = field(default_factory=list)
    postings: list[dict[str, Any]] = field(default_factory=list)


def run_career_ops_first_prompt(
    *,
    actor: User,
    cv_text: str,
    constraints: dict[str, Any],
    prompt: str,
    idempotency_key: str,
    live_postings: list[dict[str, Any]] | None = None,
) -> CareerOpsFirstPromptResult:
    """Run the first CareerOps prompt as durable ForgeGraph state."""

    if actor is None:
        raise ValueError("CareerOps first prompt requires an actor.")
    if not str(idempotency_key or "").strip():
        raise ValueError("CareerOps first prompt requires an idempotency key.")
    ensure_default_organization(actor)
    organization = actor.default_organization
    if organization is None:
        raise ValueError("CareerOps first prompt requires an actor organization.")

    candidate = extract_career_ops_cv_facts(cv_text=cv_text)
    safe_constraints = normalize_career_ops_constraints(constraints)
    use_live_discovery = live_postings is not None
    source_mode = "live_url_discovery" if use_live_discovery else "deterministic_fake_provider"
    stage_definitions = LIVE_DISCOVERY_STAGES if use_live_discovery else FIRST_PROMPT_STAGES
    with transaction.atomic():
        company = ensure_career_ops_company(
            actor=actor,
            candidate=candidate,
            idempotency_key=idempotency_key,
        )
        departments = ensure_career_ops_departments(company=company)
        engagement = ensure_career_ops_application_engagement(company=company, actor=actor)
        whiteboard = create_or_resume_whiteboard(
            company=company,
            service_engagement=engagement,
            known_fields={
                "request_type": "career_ops_discovery",
                "project_name": f"CareerOps — {candidate['name']}",
                "client_name": candidate["name"],
                "request_summary": _bounded(prompt, 4000),
                "objective": "Create an initial possible-job shortlist from the candidate CV and work constraints.",
                "timeline": "first prompt / limited discovery run",
                "constraints": safe_constraints,
                "known_facts": {"candidate": candidate},
                "metadata": {
                    "career_ops": {
                        "pack_id": CAREER_OPS_PACK_ID,
                        "prompt": _bounded(prompt, 4000),
                        "source": "career_ops_first_prompt",
                        "external_side_effects_allowed": False,
                    }
                },
            },
            idempotency_key=f"career-ops:first_prompt:{idempotency_key}",
            created_by=actor,
        )
        postings = (
            build_live_possible_postings(
                candidate=candidate,
                constraints=safe_constraints,
                live_postings=live_postings or [],
            )
            if use_live_discovery
            else build_initial_possible_postings(candidate=candidate, constraints=safe_constraints)
        )
        opportunities = persist_possible_postings(
            company=company,
            actor=actor,
            postings=postings,
            whiteboard_id=str(whiteboard.id),
            source_mode=source_mode,
        )
        program = ensure_first_prompt_program(
            company=company,
            actor=actor,
            whiteboard_id=str(whiteboard.id),
            candidate=candidate,
            constraints=safe_constraints,
            idempotency_key=idempotency_key,
            source_mode=source_mode,
            stage_definitions=stage_definitions,
        )
        task_records = bootstrap_task_routing_for_program(
            program,
            whiteboard=whiteboard,
            created_by=actor,
            run_context={
                "source": "career_ops_first_prompt",
                "runtime_provider": source_mode,
                "source_mode": source_mode,
                "postings_count": len(postings),
            },
        )
        _attach_first_prompt_stage_outputs(
            program=program,
            postings=postings,
            opportunities=opportunities,
            source_mode=source_mode,
        )
        whiteboard.work_status = whiteboard.WORK_STATUS_IN_PROGRESS
        whiteboard.status = whiteboard.STATUS_IN_CONTENT
        metadata = dict(whiteboard.metadata_json or {})
        career_ops = dict(metadata.get("career_ops") or {})
        career_ops["first_prompt"] = {
            "status": "completed_limited_discovery",
            "source_mode": source_mode,
            "result_count": len(postings),
            "postings": postings,
            "company_id": str(company.id),
            "program_id": str(program.id),
            "external_side_effects_allowed": False,
        }
        metadata["career_ops"] = career_ops
        whiteboard.metadata_json = sanitize_outbox_payload(metadata)
        whiteboard.save(update_fields=["status", "work_status", "metadata_json", "updated_at"])
        refresh_whiteboard_task_snapshot(whiteboard=whiteboard, program=program)

    return CareerOpsFirstPromptResult(
        company_id=str(company.id),
        whiteboard_id=str(whiteboard.id),
        program_id=str(program.id),
        engagement_id=str(engagement.id),
        department_ids=[str(department.id) for department in departments],
        task_ids=[str(record.id) for record in task_records],
        postings=postings,
    )


def ensure_career_ops_company(
    *, actor: User, candidate: dict[str, Any], idempotency_key: str
) -> Graph:
    organization = actor.default_organization
    if organization is None:
        raise ValueError("CareerOps company requires an organization.")
    company, _created = Graph.objects.get_or_create(
        organization=organization,
        external_source=CAREER_OPS_FIRST_PROMPT_COMPANY_SOURCE,
        external_ref=idempotency_key,
        defaults={
            "owner": actor,
            "name": f"CareerOps — {candidate['name']}",
            "description": "ForgeGraph-native CareerOps workspace for candidate job-search operations.",
        },
    )
    updates: list[str] = []
    expected_name = f"CareerOps — {candidate['name']}"
    if company.name != expected_name:
        company.name = expected_name
        updates.append("name")
    if (
        company.description
        != "ForgeGraph-native CareerOps workspace for candidate job-search operations."
    ):
        company.description = (
            "ForgeGraph-native CareerOps workspace for candidate job-search operations."
        )
        updates.append("description")
    if updates:
        company.save(update_fields=[*updates, "updated_at"])
    ensure_career_ops_graph_version(company=company)
    return cast(Graph, company)


def ensure_career_ops_graph_version(*, company: Graph) -> GraphVersion:
    latest = cast(
        GraphVersion | None,
        GraphVersion.objects.filter(graph=company).order_by("-version").first(),
    )
    graph_json = {
        "nodes": [
            {"id": slug, "type": "career_ops_department", "label": name}
            for slug, name, _department_type in CAREER_OPS_DEPARTMENTS
        ],
        "edges": [
            {"source": "candidate-profile-strategy", "target": "market-role-discovery"},
            {"source": "market-role-discovery", "target": "opportunity-evaluation"},
            {"source": "opportunity-evaluation", "target": "candidate-approval-governance"},
        ],
        "metadata": {"pack_id": CAREER_OPS_PACK_ID, "source": "career_ops_first_prompt"},
    }
    if latest is not None:
        return latest
    return cast(
        GraphVersion,
        GraphVersion.objects.create(graph=company, version=1, graph_json=graph_json),
    )


def ensure_career_ops_departments(*, company: Graph) -> list[DepartmentRegistry]:
    organization = company.organization
    if organization is None:
        raise ValueError("CareerOps departments require an organization-scoped company.")
    departments = []
    for slug, name, department_type in CAREER_OPS_DEPARTMENTS:
        departments.append(
            register_department(
                organization=organization,
                slug=slug,
                name=name,
                department_type=department_type,
                service_tags=["career_ops", CAREER_OPS_PACK_ID],
                active=True,
                metadata={
                    "career_ops": {"pack_id": CAREER_OPS_PACK_ID, "company_id": str(company.id)},
                    "system_managed": True,
                    "created_via": "career_ops_first_prompt",
                },
            )
        )
    return departments


def ensure_first_prompt_program(
    *,
    company: Graph,
    actor: User,
    whiteboard_id: str,
    candidate: dict[str, Any],
    constraints: dict[str, Any],
    idempotency_key: str,
    source_mode: str = "deterministic_fake_provider",
    stage_definitions: tuple[dict[str, Any], ...] = FIRST_PROMPT_STAGES,
) -> CompanyProgram:
    organization = company.organization
    if organization is None:
        raise ValueError("CareerOps program requires an organization-scoped company.")
    external_key = f"career-ops:first-prompt:{idempotency_key}"
    current_stage_id = (
        "prepare_tailored_cv" if source_mode == "live_url_discovery" else "opportunity_shortlist"
    )
    program, created = CompanyProgram.objects.get_or_create(
        company=company,
        external_key=external_key,
        defaults={
            "organization": organization,
            "pack_id": CAREER_OPS_PACK_ID,
            "template_id": CAREER_OPS_FIRST_PROMPT_TEMPLATE_ID,
            "display_label": CAREER_OPS_FIRST_PROMPT_PROGRAM_LABEL,
            "title": f"Initial possible-job discovery — {candidate['name']}",
            "objective": "Create a limited list of possible CareerOps job opportunities and write them to the whiteboard.",
            "status": "active",
            "current_stage_id": current_stage_id,
            "metadata_json": {
                "career_ops": {
                    "candidate": candidate,
                    "constraints": constraints,
                    "whiteboard_id": whiteboard_id,
                    "source_mode": source_mode,
                    "external_side_effects_allowed": False,
                }
            },
            "created_by": actor,
        },
    )
    if not created:
        program.metadata_json = sanitize_outbox_payload(
            {
                **(program.metadata_json or {}),
                "career_ops": {
                    "candidate": candidate,
                    "constraints": constraints,
                    "whiteboard_id": whiteboard_id,
                    "source_mode": source_mode,
                    "external_side_effects_allowed": False,
                },
            }
        )
        program.status = "active"
        program.current_stage_id = current_stage_id
        program.save(update_fields=["metadata_json", "status", "current_stage_id", "updated_at"])
    ensure_first_prompt_stages(program=program, stage_definitions=stage_definitions)
    return program


def ensure_first_prompt_stages(
    *,
    program: CompanyProgram,
    stage_definitions: tuple[dict[str, Any], ...] = FIRST_PROMPT_STAGES,
) -> list[ProgramStageState]:
    stages: list[ProgramStageState] = []
    active_stage_ids = {str(stage["id"]) for stage in stage_definitions}
    ProgramStageState.objects.filter(program=program).exclude(
        stage_id__in=active_stage_ids
    ).delete()
    for sequence, stage in enumerate(stage_definitions, start=1):
        template = {
            "id": stage["id"],
            "label": stage["label"],
            "department_slug": stage["department_slug"],
            "title": stage["task_title"],
            "task_title": stage["task_title"],
            "dependencies": stage["dependencies"],
            "priority": "high" if stage["id"] == "market_role_discovery" else "normal",
        }
        obj, _created = ProgramStageState.objects.update_or_create(
            program=program,
            stage_id=str(stage["id"]),
            defaults={
                "organization": program.organization,
                "company": program.company,
                "label": str(stage["label"]),
                "sequence": sequence,
                "status": str(stage["status"]),
                "started_at": timezone.now()
                if stage["status"] in {"completed", "in_progress"}
                else None,
                "completed_at": timezone.now() if stage["status"] == "completed" else None,
                "state_json": {"template": template, "department_slug": stage["department_slug"]},
            },
        )
        stages.append(obj)
    return stages


def persist_possible_postings(
    *,
    company: Graph,
    actor: User,
    postings: list[dict[str, Any]],
    whiteboard_id: str,
    source_mode: str = "deterministic_fake_provider",
) -> list[CompanyOpportunity]:
    opportunities: list[CompanyOpportunity] = []
    for posting in postings:
        signal = record_scanned_job(company=company, user=actor, posting=posting)
        opportunity = ensure_opportunity_for_signal(signal=signal, user=actor)
        if opportunity is None:
            continue
        career_ops = dict((opportunity.metadata_json or {}).get("career_ops") or {})
        career_ops.update(
            {
                "application_status": "discovered",
                "tracker_status": "evaluated",
                "source_mode": source_mode,
                "visa_ok": True,
                "locations": list(posting.get("locations") or [posting.get("location")]),
                "salary_target_usd": posting.get("salary_target_usd"),
                "salary_range_usd": posting.get("salary_range_usd"),
                "fit_reasons": list(posting.get("fit_reasons") or []),
                "score": posting.get("score"),
                "source_url": posting.get("url"),
                "posting_source_mode": posting.get("source_mode"),
                "source_query": posting.get("source_query"),
                "source_rank": posting.get("source_rank"),
                "whiteboard_id": whiteboard_id,
                "external_side_effects_allowed": False,
            }
        )
        opportunity.metadata_json = {**(opportunity.metadata_json or {}), "career_ops": career_ops}
        opportunity.next_action = (
            "Review live posting fit before generating a tailored CV."
            if source_mode == "live_url_discovery"
            else "Review shortlist fit before generating application packet."
        )
        opportunity.save(update_fields=["metadata_json", "next_action", "updated_at"])
        opportunities.append(opportunity)
    return opportunities


def build_live_possible_postings(
    *,
    candidate: dict[str, Any],
    constraints: dict[str, Any],
    live_postings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize, filter, and score externally collected live job URL records."""

    authorized_regions = list(constraints.get("work_authorized_regions") or [])
    target_salary = float(constraints.get("target_salary_usd") or 60000)
    candidate_skills = [str(skill) for skill in candidate.get("skills") or []]
    excluded_regions = {str(item).casefold() for item in constraints.get("excluded_regions") or []}
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for index, raw in enumerate(live_postings, start=1):
        url = str(raw.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        location = str(raw.get("location") or "").strip()
        locations = _locations_from_text(location)
        if _is_excluded_location(locations=locations, excluded_regions=excluded_regions):
            continue
        if not _visa_ok(locations=locations, authorized_regions=authorized_regions):
            continue
        score, fit_reasons = _live_fit_score(
            raw=raw, candidate_skills=candidate_skills, target_salary=target_salary
        )
        if score < 4.0:
            continue
        source_mode = (
            str(raw.get("source_mode") or "live_url_discovery").strip() or "live_url_discovery"
        )
        source_query = str(raw.get("source_query") or "").strip()
        posting = {
            "title": str(raw.get("title") or "Untitled role").strip(),
            "company": str(raw.get("company") or raw.get("employer") or "Unknown employer").strip(),
            "location": location,
            "locations": locations,
            "salary_range_usd": _salary_range(raw.get("salary_range_usd")),
            "fit_reasons": fit_reasons,
            "url": url,
            "provider": str(raw.get("provider") or "career_ops_live_url").strip(),
            "score": score,
            "salary_target_usd": target_salary,
            "visa_ok": True,
            "description": _bounded(raw.get("description") or raw.get("summary") or "", 4000),
            "apply_controls": list(raw.get("apply_controls") or ["Review manually"]),
            "http_status": raw.get("http_status") or 200,
            "source_rank": _source_rank(raw.get("source_rank"), index),
            "source_mode": source_mode,
            "external_side_effects_allowed": False,
        }
        if source_query:
            posting["source_query"] = source_query
        results.append(sanitize_outbox_payload(posting))
    return sorted(
        results,
        key=lambda item: (-float(item.get("score") or 0), int(item.get("source_rank") or 0)),
    )[:10]


def build_initial_possible_postings(
    *, candidate: dict[str, Any], constraints: dict[str, Any]
) -> list[dict[str, Any]]:
    del candidate
    authorized_regions = list(constraints.get("work_authorized_regions") or [])
    target_salary = constraints.get("target_salary_usd") or 60000
    base = [
        {
            "title": "AI Platform / Backend Engineer",
            "company": "EU AI Workflow Studio",
            "location": "Spain / EU Remote",
            "locations": ["Spain", "European Union", "Remote"],
            "salary_range_usd": [55000, 75000],
            "fit_reasons": [
                "Python/FastAPI/Django backend",
                "agentic workflows",
                "PostgreSQL and Redis",
            ],
        },
        {
            "title": "Backend Engineer, Agentic Workflows",
            "company": "Mexico AI Operations Lab",
            "location": "Mexico City / Remote Mexico",
            "locations": ["Mexico", "Remote"],
            "salary_range_usd": [50000, 70000],
            "fit_reasons": ["async pipelines", "AI-native workflows", "production API ownership"],
        },
        {
            "title": "LegalTech AI Engineer",
            "company": "Iberia Legal Automation",
            "location": "Madrid / Hybrid Spain",
            "locations": ["Spain", "European Union"],
            "salary_range_usd": [52000, 68000],
            "fit_reasons": [
                "law background",
                "Lex Toolkit legal agents",
                "FastAPI/Next.js full-stack",
            ],
        },
        {
            "title": "Python Backend Engineer, Data Integrations",
            "company": "EU B2B Integrations Co",
            "location": "Europe Remote",
            "locations": ["European Union", "Remote"],
            "salary_range_usd": [60000, 80000],
            "fit_reasons": ["data ingestion", "service boundaries", "observability and retries"],
        },
        {
            "title": "AI Automation Engineer",
            "company": "Mexico Enterprise Automation",
            "location": "Mexico / Remote",
            "locations": ["Mexico", "Remote"],
            "salary_range_usd": [45000, 65000],
            "fit_reasons": [
                "automation consulting",
                "stakeholder translation",
                "RAG and LLM workflows",
            ],
        },
        {
            "title": "US-only Senior Backend Engineer",
            "company": "US Excluded Example",
            "location": "United States Remote",
            "locations": ["United States"],
            "salary_range_usd": [100000, 140000],
            "fit_reasons": ["backend"],
        },
    ]
    postings: list[dict[str, Any]] = []
    excluded_regions = {str(item).casefold() for item in constraints.get("excluded_regions") or []}
    for index, item in enumerate(base, start=1):
        locations = [str(location) for location in item["locations"]]
        if any(location.casefold() in excluded_regions for location in locations):
            continue
        posting = {
            **item,
            "url": f"https://career-ops.local/jobs/{_slugify(item['company'])}/{_slugify(item['title'])}",
            "provider": "career_ops_fake_provider",
            "score": _fit_score(item=item, target_salary=float(target_salary)),
            "salary_target_usd": target_salary,
            "visa_ok": _visa_ok(locations=locations, authorized_regions=authorized_regions),
            "description": _posting_description(item),
            "apply_controls": ["Review manually"],
            "http_status": 200,
            "source_rank": index,
        }
        if posting["visa_ok"]:
            postings.append(sanitize_outbox_payload(posting))
        if len(postings) == 5:
            break
    return postings


def extract_career_ops_cv_facts(*, cv_text: str) -> dict[str, Any]:
    text = str(cv_text or "")
    name = "Miguel Athie" if "Miguel Athie" in text else _first_nonempty_line(text) or "Candidate"
    skills = []
    for keyword in (
        "Python",
        "FastAPI",
        "Django",
        "Go",
        "PostgreSQL",
        "Redis",
        "Celery",
        "RAG",
        "LangGraph",
        "agentic workflows",
        "Prometheus",
        "React",
        "Next.js",
        "TypeScript",
    ):
        if keyword.casefold() in text.casefold():
            skills.append(keyword)
    return {
        "name": name,
        "summary": _bounded(_sentence_with(text, "Backend-leaning") or text, 1200),
        "skills": skills,
        "source": "cv_text",
        "source_backed": True,
    }


def normalize_career_ops_constraints(constraints: dict[str, Any]) -> dict[str, Any]:
    data = sanitize_outbox_payload(dict(constraints or {}))
    data.setdefault("external_side_effects_allowed", False)
    data.setdefault("manual_review_required", True)
    data.setdefault("work_authorized_regions", [])
    data.setdefault("excluded_regions", [])
    data.setdefault("target_salary_usd", 60000)
    return data


def _attach_first_prompt_stage_outputs(
    *,
    program: CompanyProgram,
    postings: list[dict[str, Any]],
    opportunities: list[CompanyOpportunity],
    source_mode: str = "deterministic_fake_provider",
) -> None:
    stage_id = "score_fit" if source_mode == "live_url_discovery" else "market_role_discovery"
    output_type = (
        "live_job_shortlist" if source_mode == "live_url_discovery" else "possible_job_list"
    )
    stage = ProgramStageState.objects.get(program=program, stage_id=stage_id)
    state = dict(stage.state_json or {})
    task = dict(state.get(TASK_METADATA_KEY) or {})
    task["outputs"] = [
        {
            "type": output_type,
            "source_mode": source_mode,
            "postings": postings,
            "opportunity_ids": [str(opportunity.id) for opportunity in opportunities],
            "external_side_effects_allowed": False,
        }
    ]
    state[TASK_METADATA_KEY] = task
    stage.state_json = sanitize_outbox_payload(state)
    stage.save(update_fields=["state_json", "updated_at"])


def _fit_score(*, item: dict[str, Any], target_salary: float) -> float:
    salary_low, salary_high = item.get("salary_range_usd", [0, 0])
    score = 4.0
    if salary_low <= target_salary <= salary_high:
        score += 0.4
    if any(
        "AI" in str(reason) or "agent" in str(reason).casefold()
        for reason in item.get("fit_reasons", [])
    ):
        score += 0.3
    return round(min(score, 5.0), 1)


def _live_fit_score(
    *,
    raw: dict[str, Any],
    candidate_skills: list[str],
    target_salary: float,
) -> tuple[float, list[str]]:
    haystack = " ".join(
        str(raw.get(key) or "")
        for key in ("title", "company", "description", "summary", "location")
    ).casefold()
    matched_skills = [skill for skill in candidate_skills if skill.casefold() in haystack]
    fit_reasons: list[str] = []
    score = 2.8
    if matched_skills:
        fit_reasons.append("Matched CV skills: " + ", ".join(matched_skills[:6]))
        score += min(1.5, 0.3 * len(matched_skills))
    if any(
        token in haystack for token in ("backend", "platform", "api", "apis", "agent", "ai", "rag")
    ):
        fit_reasons.append("Role language aligns with backend/AI platform work")
        score += 0.8
    if any(token in haystack for token in ("workflow", "workflows", "automation", "orchestration")):
        fit_reasons.append("Workflow/automation language aligns with CareerOps target work")
        score += 0.3
    salary_low, salary_high = _salary_range(raw.get("salary_range_usd"))
    if salary_low <= target_salary <= salary_high:
        fit_reasons.append("Salary range overlaps target")
        score += 0.5
    elif salary_high and salary_high >= target_salary * 0.85:
        fit_reasons.append("Salary appears near flexible target")
        score += 0.2
    elif salary_low == 0 and salary_high == 0:
        fit_reasons.append("Salary not listed; keep for manual compensation review")
        score += 0.3
    if not fit_reasons:
        fit_reasons.append("Weak match to source CV facts")
    return round(min(score, 5.0), 1), fit_reasons


def _salary_range(value: Any) -> list[int]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return [int(float(value[0])), int(float(value[1]))]
        except (TypeError, ValueError):
            return [0, 0]
    return [0, 0]


def _source_rank(value: Any, fallback: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return fallback


def _locations_from_text(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    locations: list[str] = []
    lowered = text.casefold()
    if any(token in lowered for token in ("united states", " usa", "u.s.", "us only", "us-only")):
        locations.append("United States")
    if any(token in lowered for token in ("mexico", "méxico")):
        locations.append("Mexico")
    if "spain" in lowered or "madrid" in lowered or "barcelona" in lowered:
        locations.append("Spain")
    if "europe" in lowered or " eu " in f" {lowered} " or "european union" in lowered:
        locations.append("European Union")
    if "remote" in lowered:
        locations.append("Remote")
    return locations or [text]


def _is_excluded_location(*, locations: list[str], excluded_regions: set[str]) -> bool:
    for location in locations:
        value = location.casefold()
        if value in excluded_regions:
            return True
        if "united states" in value and "united states" in excluded_regions:
            return True
    return False


def _visa_ok(*, locations: list[str], authorized_regions: list[str]) -> bool:
    authorized = {region.casefold() for region in authorized_regions}
    for location in locations:
        value = location.casefold()
        if value in authorized or value in {"remote", "european union"}:
            return True
        if "spain" in value and ("spain" in authorized or "european union" in authorized):
            return True
        if "mexico" in value and "mexico" in authorized:
            return True
    return False


def _posting_description(item: dict[str, Any]) -> str:
    return (
        f"Possible role: {item['title']} at {item['company']}. Location: {item['location']}. "
        f"Why it fits: {', '.join(item.get('fit_reasons', []))}. Manual review required before any application."
    )


def _sentence_with(text: str, needle: str) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        if needle.casefold() in sentence.casefold():
            return sentence.strip()
    return ""


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _bounded(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _slugify(value: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return slug or "unknown"
