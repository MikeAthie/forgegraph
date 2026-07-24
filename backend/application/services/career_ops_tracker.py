"""CareerOps tracker integrity helpers over ForgeGraph durable opportunity state."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from infrastructure.orm.models import CompanyOpportunity, Graph

CANONICAL_STATUSES = (
    "evaluated",
    "applied",
    "responded",
    "interview",
    "offer",
    "rejected",
    "discarded",
    "skip",
)

STATUS_ALIASES = {
    "evaluada": "evaluated",
    "condicional": "evaluated",
    "hold": "evaluated",
    "evaluar": "evaluated",
    "verificar": "evaluated",
    "aplicado": "applied",
    "enviada": "applied",
    "aplicada": "applied",
    "sent": "applied",
    "respondido": "responded",
    "entrevista": "interview",
    "oferta": "offer",
    "rechazado": "rejected",
    "rechazada": "rejected",
    "descartado": "discarded",
    "descartada": "discarded",
    "cerrada": "discarded",
    "cancelada": "discarded",
    "no aplicar": "skip",
    "no_aplicar": "skip",
    "monitor": "skip",
    "geo blocker": "skip",
}


def normalize_career_ops_status(raw: object) -> str | None:
    """Normalize a status using the reference Career-Ops canonical state contract."""

    if raw is None:
        return None
    cleaned = re.sub(r"\*\*", "", str(raw)).strip().casefold()
    cleaned = re.sub(r"\s+\d{4}-\d{2}-\d{2}.*$", "", cleaned).strip()
    if cleaned in CANONICAL_STATUSES:
        return cleaned
    return STATUS_ALIASES.get(cleaned)


def check_career_ops_pipeline_integrity(*, company: Graph) -> dict[str, Any]:
    """Validate tracker-like invariants from durable CompanyOpportunity rows."""

    opportunities = list(CompanyOpportunity.objects.filter(company=company).order_by("created_at"))
    invalid_statuses: list[dict[str, str]] = []
    duplicates: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    groups: dict[tuple[str, str], list[CompanyOpportunity]] = defaultdict(list)

    for opportunity in opportunities:
        career_ops = _career_ops_metadata(opportunity.metadata_json)
        employer = str(career_ops.get("employer_name") or opportunity.contact_alias or "").strip()
        role = str(career_ops.get("role_title") or opportunity.title or "").strip()
        raw_status = (
            career_ops.get("tracker_status") or career_ops.get("application_status") or "evaluated"
        )
        canonical = normalize_career_ops_status(raw_status)
        if canonical is None:
            invalid_statuses.append(
                {"opportunity_id": str(opportunity.id), "status": str(raw_status)}
            )
            counts["invalid"] += 1
        else:
            counts[canonical] += 1
        groups[(_normalize_match_text(employer), _normalize_match_text(role))].append(opportunity)

    for (employer_key, role_key), group in groups.items():
        if employer_key and role_key and len(group) > 1:
            first_meta = _career_ops_metadata(group[0].metadata_json)
            duplicates.append(
                {
                    "employer_name": str(
                        first_meta.get("employer_name") or group[0].contact_alias or ""
                    ),
                    "role_title": str(first_meta.get("role_title") or group[0].title or ""),
                    "opportunity_ids": [str(opportunity.id) for opportunity in group],
                }
            )

    errors = {"invalid_statuses": invalid_statuses}
    warnings = {"duplicates": duplicates}
    return {
        "status": "error" if invalid_statuses else "ok",
        "total": len(opportunities),
        "canonical_counts": dict(counts),
        "errors": errors,
        "warnings": warnings,
    }


def _career_ops_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    career_ops = (metadata or {}).get("career_ops", {})
    return dict(career_ops) if isinstance(career_ops, dict) else {}


def _normalize_match_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())
