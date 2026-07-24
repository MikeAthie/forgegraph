"""CareerOps opportunity normalization, dedupe, and application cooldown helpers."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from application.services.career_ops_graph_contract import CAREER_OPS_APPLIED_COOLDOWN_DAYS
from infrastructure.orm.models import CompanyOpportunity, CompanySignal, Graph, User

CAREER_OPS_SCAN_SOURCE = "career_ops_scan"
CAREER_OPS_DOMAIN_CONTEXT = "career_ops"


def normalize_job_key(*, company_name: str, role_title: str, url: str) -> str:
    """Return a stable key for a job URL and employer/role pair."""

    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    normalized_url = f"{host}{path}".lower()
    return ":".join(
        (
            _slugify(company_name),
            _slugify(role_title),
            normalized_url,
        )
    )


def record_scanned_job(
    *,
    company: Graph,
    user: User | None,
    posting: dict[str, Any],
    source: str = CAREER_OPS_SCAN_SOURCE,
    cooldown_days: int = CAREER_OPS_APPLIED_COOLDOWN_DAYS,
) -> CompanySignal:
    """Persist a scanned job as an idempotent backend-owned company signal."""

    organization = company.organization
    if organization is None:
        raise ValueError("CareerOps scanned jobs require an organization-scoped company.")

    career_ops = _career_ops_metadata_for_posting(posting)
    external_key = normalize_job_key(
        company_name=career_ops["employer_name"],
        role_title=career_ops["role_title"],
        url=career_ops["job_url"],
    )
    cooldown = should_skip_due_to_recent_application(
        company=company, posting=posting, cooldown_days=cooldown_days
    )
    career_ops["application_status"] = "discovered"
    career_ops["recent_application_cooldown"] = cooldown

    signal, created = CompanySignal.objects.get_or_create(
        company=company,
        source=source,
        external_key=external_key,
        defaults={
            "organization": organization,
            "created_by": user,
            "signal_type": "lead",
            "signal_kind": "opportunity",
            "domain_context": CAREER_OPS_DOMAIN_CONTEXT,
            "status": "new",
            "title": f"{career_ops['employer_name']} — {career_ops['role_title']}",
            "summary": _summary_for_posting(career_ops),
            "channel": career_ops["provider"],
            "contact_alias": career_ops["employer_name"],
            "metadata_json": {"career_ops": career_ops},
        },
    )
    if not created:
        metadata = dict(signal.metadata_json or {})
        metadata["career_ops"] = {**metadata.get("career_ops", {}), **career_ops}
        signal.metadata_json = metadata
        signal.title = f"{career_ops['employer_name']} — {career_ops['role_title']}"
        signal.summary = _summary_for_posting(career_ops)
        signal.channel = career_ops["provider"]
        signal.contact_alias = career_ops["employer_name"]
        signal.save(
            update_fields=[
                "title",
                "summary",
                "channel",
                "contact_alias",
                "metadata_json",
                "updated_at",
            ]
        )
    return signal


def ensure_opportunity_for_signal(
    *, signal: CompanySignal, user: User | None
) -> CompanyOpportunity | None:
    """Create or replay a job opportunity derived from a CareerOps scanned signal."""

    career_ops = _career_ops_metadata(signal.metadata_json)
    if not career_ops:
        return None
    organization = signal.organization
    opportunity, created = CompanyOpportunity.objects.get_or_create(
        company=signal.company,
        external_key=signal.external_key,
        defaults={
            "organization": organization,
            "signal": signal,
            "owner_user": user,
            "status": "qualified",
            "title": f"{career_ops['employer_name']} — {career_ops['role_title']}",
            "summary": _summary_for_posting(career_ops),
            "contact_alias": career_ops["employer_name"],
            "channel": career_ops["provider"],
            "currency": "usd",
            "next_action": "Run CareerOps liveness and A-G evaluation.",
            "metadata_json": {"career_ops": career_ops},
        },
    )
    if not created:
        metadata = dict(opportunity.metadata_json or {})
        metadata["career_ops"] = {**metadata.get("career_ops", {}), **career_ops}
        opportunity.metadata_json = metadata
        opportunity.signal = opportunity.signal or signal
        opportunity.owner_user = opportunity.owner_user or user
        opportunity.title = f"{career_ops['employer_name']} — {career_ops['role_title']}"
        opportunity.summary = _summary_for_posting(career_ops)
        opportunity.contact_alias = career_ops["employer_name"]
        opportunity.channel = career_ops["provider"]
        opportunity.save(
            update_fields=[
                "signal",
                "owner_user",
                "title",
                "summary",
                "contact_alias",
                "channel",
                "metadata_json",
                "updated_at",
            ]
        )
    signal.status = "qualified"
    signal.save(update_fields=["status", "updated_at"])
    return opportunity


def update_application_status(
    *,
    opportunity: CompanyOpportunity,
    status: str,
    user: User | None,
    metadata: dict[str, Any] | None = None,
    applied_at: datetime | None = None,
) -> CompanyOpportunity:
    """Update CareerOps application status metadata without performing side effects."""

    del user
    career_ops = _career_ops_metadata(opportunity.metadata_json)
    career_ops["application_status"] = status
    if status == "applied":
        career_ops["applied_at"] = (applied_at or timezone.now()).isoformat()
        opportunity.status = "converted"
    elif status in {"skip", "rejected", "discarded"}:
        opportunity.status = "lost"
    if metadata:
        career_ops.update(metadata)
    opportunity.metadata_json = {**(opportunity.metadata_json or {}), "career_ops": career_ops}
    opportunity.save(update_fields=["status", "metadata_json", "updated_at"])
    return opportunity


def should_skip_due_to_recent_application(
    *,
    company: Graph,
    posting: dict[str, Any],
    cooldown_days: int = CAREER_OPS_APPLIED_COOLDOWN_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return whether a posting is inside the same employer/role application cooldown."""

    reference_time = now or timezone.now()
    employer_name = _normalize_match_text(str(posting.get("company", "")))
    role_title = _normalize_match_text(str(posting.get("title", "")))
    cutoff = reference_time - timedelta(days=cooldown_days)

    for opportunity in CompanyOpportunity.objects.filter(company=company):
        career_ops = _career_ops_metadata(opportunity.metadata_json)
        if career_ops.get("application_status") != "applied":
            continue
        if _normalize_match_text(str(career_ops.get("employer_name", ""))) != employer_name:
            continue
        if _normalize_match_text(str(career_ops.get("role_title", ""))) != role_title:
            continue
        applied_at = _coerce_datetime(career_ops.get("applied_at"))
        if applied_at is not None and applied_at >= cutoff:
            return {
                "skip": True,
                "reason": "recent_application_cooldown",
                "cooldown_days": cooldown_days,
                "matched_opportunity_id": str(opportunity.id),
                "applied_at": applied_at.isoformat(),
            }
    return {
        "skip": False,
        "reason": "cooldown_expired_or_no_match",
        "cooldown_days": cooldown_days,
    }


def _career_ops_metadata_for_posting(posting: dict[str, Any]) -> dict[str, Any]:
    title = str(posting.get("title") or "Untitled role").strip()
    employer = str(posting.get("company") or posting.get("employer") or "Unknown employer").strip()
    url = str(posting.get("url") or "").strip()
    if not url:
        raise ValueError("CareerOps scanned jobs require a posting URL.")
    return {
        "role_title": title,
        "employer_name": employer,
        "job_url": url,
        "location": str(posting.get("location") or "").strip(),
        "provider": str(posting.get("provider") or "manual_url").strip(),
        "salary": posting.get("salary"),
        "score": posting.get("score"),
        "description": str(
            posting.get("description") or posting.get("body_text") or posting.get("jd_text") or ""
        ).strip(),
        "apply_controls": list(posting.get("apply_controls") or []),
        "http_status": posting.get("http_status"),
        "final_url": str(posting.get("final_url") or url).strip(),
        "liveness_status": str(posting.get("liveness_status") or "unchecked"),
    }


def _career_ops_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    career_ops = (metadata or {}).get("career_ops", {})
    return dict(career_ops) if isinstance(career_ops, dict) else {}


def _summary_for_posting(career_ops: dict[str, Any]) -> str:
    parts = [career_ops["role_title"], career_ops["employer_name"]]
    if career_ops.get("location"):
        parts.append(str(career_ops["location"]))
    return " | ".join(parts)


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return normalized.strip("-") or "unknown"


def _normalize_match_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value)
    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed is None:
            return None
        return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)
    return None
