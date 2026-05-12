"""Generic validation packet and decision services."""

from __future__ import annotations

import re
from typing import Any, cast
from uuid import UUID

from django.db import transaction

from application.services.assertions import assertion_payload
from application.services.audit_log import record_audit_log
from application.services.state_projections import materialize_current_truth_projection
from application.services.work_artifacts import artifact_payload
from infrastructure.orm.models import (
    AssertionRecord,
    Asset,
    CompanyProgram,
    EvaluationFinding,
    Graph,
    User,
    ValidationDecision,
)


class ValidationDecisionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def validation_packet_payload(*, company: Graph, program: CompanyProgram) -> dict[str, Any]:
    """Build an inspectable validation packet from backend-owned company state."""

    assertions = AssertionRecord.objects.filter(company=company, program=program).order_by(
        "kind", "category", "-updated_at"
    )
    artifacts = Asset.objects.filter(company=company, metadata_json__program_id=str(program.id))
    findings = EvaluationFinding.objects.filter(company=company).filter(
        evaluation__program=program
    ) | EvaluationFinding.objects.filter(company=company).filter(evaluation__asset__in=artifacts)
    return {
        "company_id": str(company.id),
        "program_id": str(program.id),
        "program_label": program.display_label,
        "current_stage_id": program.current_stage_id,
        "assertions": [assertion_payload(item) for item in assertions[:200]],
        "artifacts": [artifact_payload(item, include_versions=True) for item in artifacts[:100]],
        "findings": [
            {
                "id": str(item.id),
                "evaluation_id": str(item.evaluation_id),
                "severity": item.severity,
                "issue_type": item.issue_type,
                "message": item.message,
                "suggested_fix": item.suggested_fix,
                "blocking": item.blocking,
                "evidence_refs": item.evidence_refs_json,
            }
            for item in findings.order_by("-blocking", "severity", "created_at")[:100]
        ],
        "decision_options": ["ACCEPT", "REJECT", "EDIT", "DEFER", "NEEDS_RESEARCH"],
    }


def create_validation_decision(
    *,
    company: Graph,
    user: User,
    decision: str,
    program: CompanyProgram | None = None,
    assertion_id: UUID | None = None,
    asset_id: UUID | None = None,
    asset_version_id: UUID | None = None,
    category: str = "",
    rationale: str = "",
    proposed_change: dict[str, Any] | None = None,
) -> ValidationDecision:
    clean_decision = str(decision or "").strip().upper()
    if clean_decision not in {"ACCEPT", "REJECT", "EDIT", "DEFER", "NEEDS_RESEARCH"}:
        raise ValidationDecisionError("invalid_decision", "Validation decision is not supported.")
    assertion = _assertion(company=company, assertion_id=assertion_id)
    asset = _asset(company=company, asset_id=asset_id)
    if (
        asset_version_id
        and asset is not None
        and not asset.versions.filter(id=asset_version_id).exists()
    ):
        raise ValidationDecisionError(
            "asset_revision_not_found", "Artifact revision was not found."
        )
    change = proposed_change or {}
    with transaction.atomic():
        validation = ValidationDecision.objects.create(
            organization=cast(Any, company.organization),
            company=company,
            program=program,
            assertion=assertion,
            asset=asset,
            asset_version_id=asset_version_id,
            decision=clean_decision,
            category=_safe_text(category, 120),
            rationale=_safe_text(rationale, 4000),
            proposed_change_json=change,
            created_by=user,
        )
        if assertion is not None:
            _apply_assertion_decision(assertion=assertion, decision=clean_decision, change=change)
        if asset is not None:
            _record_asset_decision(asset=asset, validation=validation)
    if program is not None:
        materialize_current_truth_projection(company=company, program=program)
    record_audit_log(
        actor=user,
        tenant_id=str(company.organization_id),
        action="validation_decision.created",
        resource_type="validation_decision",
        resource_id=str(validation.id),
        metadata={
            "company_id": str(company.id),
            "program_id": str(program.id) if program else None,
            "assertion_id": str(assertion.id) if assertion else None,
            "asset_id": str(asset.id) if asset else None,
            "decision": clean_decision,
        },
    )
    return validation


def validation_decision_payload(decision: ValidationDecision) -> dict[str, Any]:
    return {
        "id": str(decision.id),
        "company_id": str(decision.company_id),
        "program_id": str(decision.program_id) if decision.program_id else None,
        "assertion_id": str(decision.assertion_id) if decision.assertion_id else None,
        "asset_id": str(decision.asset_id) if decision.asset_id else None,
        "asset_version_id": str(decision.asset_version_id) if decision.asset_version_id else None,
        "decision": decision.decision,
        "category": decision.category,
        "rationale": decision.rationale,
        "proposed_change": decision.proposed_change_json,
        "created_at": decision.created_at.isoformat(),
    }


def _assertion(*, company: Graph, assertion_id: UUID | None) -> AssertionRecord | None:
    if assertion_id is None:
        return None
    assertion = AssertionRecord.objects.filter(company=company, id=assertion_id).first()
    if assertion is None:
        raise ValidationDecisionError("assertion_not_found", "Assertion was not found.")
    return assertion


def _asset(*, company: Graph, asset_id: UUID | None) -> Asset | None:
    if asset_id is None:
        return None
    asset = Asset.objects.filter(company=company, id=asset_id).first()
    if asset is None:
        raise ValidationDecisionError("artifact_not_found", "Artifact was not found.")
    return asset


def _apply_assertion_decision(
    *, assertion: AssertionRecord, decision: str, change: dict[str, Any]
) -> None:
    update_fields: list[str] = ["updated_at"]
    if decision == "ACCEPT":
        assertion.validation_status = "validated"
        update_fields.append("validation_status")
    elif decision == "REJECT":
        assertion.validation_status = "rejected"
        update_fields.append("validation_status")
    elif decision == "DEFER":
        assertion.validation_status = "pending"
        update_fields.append("validation_status")
    elif decision == "NEEDS_RESEARCH":
        assertion.validation_status = "open"
        update_fields.append("validation_status")
    elif decision == "EDIT":
        assertion.validation_status = "corrected"
        update_fields.append("validation_status")
        statement = _safe_text(change.get("statement"), 4000)
        if statement:
            assertion.statement = statement
            update_fields.append("statement")
        category = _safe_text(change.get("category"), 120)
        if category:
            assertion.category = category
            update_fields.append("category")
        source = _safe_text(change.get("source"), 4000)
        if source:
            assertion.source = source
            update_fields.append("source")
        confidence = change.get("confidence")
        if confidence is not None:
            assertion.confidence = max(0.0, min(1.0, float(confidence)))
            update_fields.append("confidence")
    assertion.save(update_fields=sorted(set(update_fields)))


def _record_asset_decision(*, asset: Asset, validation: ValidationDecision) -> None:
    decisions = list((asset.metadata_json or {}).get("validation_decision_ids") or [])
    decisions.append(str(validation.id))
    asset.metadata_json = {
        **(asset.metadata_json or {}),
        "validation_decision_ids": sorted(set(decisions)),
        "last_validation_decision": validation.decision,
    }
    asset.save(update_fields=["metadata_json", "updated_at"])


def _safe_text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]
