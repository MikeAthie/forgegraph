"""Generic assertion register services."""

from __future__ import annotations

import re
from typing import Any, cast

from application.services.audit_log import record_audit_log
from infrastructure.orm.models import AssertionRecord, CompanyProgram, Graph, User


def create_assertion(
    *,
    company: Graph,
    user: User,
    kind: str,
    statement: str,
    program: CompanyProgram | None = None,
    category: str = "",
    source: str = "",
    confidence: float = 0.5,
    validation_status: str = "unvalidated",
    evidence_refs: list[Any] | None = None,
    metadata: dict[str, Any] | None = None,
    pack_label: str = "",
) -> AssertionRecord:
    normalized_kind = str(kind or "").strip().upper()
    if normalized_kind not in {"FACT", "OPINION", "ASSUMPTION", "QUESTION"}:
        normalized_kind = "ASSUMPTION"
    if (
        normalized_kind in {"OPINION", "ASSUMPTION", "QUESTION"}
        and validation_status == "validated"
    ):
        # Validated opinions are allowed, but stay typed as opinions. Projection services decide
        # whether they can be used as currently true state.
        pass
    assertion = AssertionRecord.objects.create(
        organization=cast(Any, company.organization),
        company=company,
        program=program,
        kind=normalized_kind,
        pack_label=_safe_text(pack_label, 80),
        category=_safe_text(category, 120),
        statement=_safe_text(statement, 4000),
        source=_safe_text(source, 4000),
        confidence=max(0.0, min(1.0, float(confidence))),
        validation_status=str(validation_status or "unvalidated"),
        evidence_refs_json=evidence_refs or [],
        metadata_json=metadata or {},
        created_by=user,
    )
    record_audit_log(
        actor=user,
        tenant_id=str(company.organization_id),
        action="assertion.created",
        resource_type="assertion",
        resource_id=str(assertion.id),
        metadata={"company_id": str(company.id), "kind": assertion.kind},
    )
    return assertion


def assertion_payload(assertion: AssertionRecord) -> dict[str, Any]:
    return {
        "id": str(assertion.id),
        "company_id": str(assertion.company_id),
        "program_id": str(assertion.program_id) if assertion.program_id else None,
        "kind": assertion.kind,
        "pack_label": assertion.pack_label,
        "category": assertion.category,
        "statement": assertion.statement,
        "source": assertion.source,
        "confidence": assertion.confidence,
        "validation_status": assertion.validation_status,
        "evidence_refs": assertion.evidence_refs_json,
        "metadata": assertion.metadata_json,
        "created_at": assertion.created_at.isoformat(),
        "updated_at": assertion.updated_at.isoformat(),
    }


def _safe_text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]
