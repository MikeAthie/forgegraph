"""Deterministic quality gates for formatted deliverable artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from application.services.deliverable_format_profiles import FormatProfile

_PLACEHOLDER_RE = re.compile(r"({{.*?}}|{%.*?%}|\$\{[^}]+}|<<[^>]+>>|\bTODO\b|\bTBD\b)")
_AI_META_TOKENS = (
    "as an ai",
    "i am an ai",
    "language model",
    "chatgpt",
    "i cannot",
)
_APPROVAL_TOKENS = (
    "approval required",
    "requires approval",
    "approved before",
    "approve the next",
)


@dataclass(frozen=True)
class RenderedSection:
    id: str
    title: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "title": self.title, "content": self.content}


@dataclass(frozen=True)
class QualityCheck:
    id: str
    status: str
    severity: str
    message: str
    evidence: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class QualityGateResult:
    gate_set: str
    status: str
    checks: tuple[QualityCheck, ...]
    blocked_reasons: tuple[dict[str, str], ...]
    warnings: tuple[dict[str, str], ...]
    gate_result_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate_set": self.gate_set,
            "status": self.status,
            "checks": [check.as_dict() for check in self.checks],
            "blocked_reasons": list(self.blocked_reasons),
            "warnings": list(self.warnings),
            "gate_result_id": self.gate_result_id,
        }


def evaluate_render_quality(
    *,
    profile: FormatProfile,
    rendered_text: str,
    sections: list[RenderedSection] | tuple[RenderedSection, ...],
    source_metadata: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> QualityGateResult:
    text = str(rendered_text or "")
    section_tuple = tuple(sections)
    source_metadata_tuple = tuple(source_metadata)
    checks = (
        _no_placeholders_check(text),
        _no_ai_meta_language_check(profile, text),
        _required_sections_check(profile, section_tuple),
        _naming_consistency_check(profile, text, source_metadata_tuple),
        _evidence_recommendation_separation_check(profile, section_tuple),
        _connector_caveats_check(profile, text, source_metadata_tuple),
        _approval_language_check(profile, text, source_metadata_tuple),
    )
    blocked = tuple(_issue_from_check(check) for check in checks if check.status == "failed")
    warnings = tuple(_issue_from_check(check) for check in checks if check.status == "warning")
    status = "blocked" if blocked else "passed"
    payload = {
        "profile_ref": profile.profile_ref,
        "profile_sha256": profile.profile_sha256,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "checks": [check.as_dict() for check in checks],
    }
    gate_result_id = (
        "qgr_"
        + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
    )
    gate_set = profile.quality_gates[0] if profile.quality_gates else "format_quality@1"
    return QualityGateResult(
        gate_set=gate_set,
        status=status,
        checks=checks,
        blocked_reasons=blocked,
        warnings=warnings,
        gate_result_id=gate_result_id,
    )


def _no_placeholders_check(text: str) -> QualityCheck:
    match = _PLACEHOLDER_RE.search(text)
    if match:
        return _failed(
            "no_placeholders",
            "Rendered text contains unresolved placeholder or template tokens.",
            (match.group(0),),
        )
    return _passed("no_placeholders", "No unresolved placeholder or template tokens detected.")


def _no_ai_meta_language_check(profile: FormatProfile, text: str) -> QualityCheck:
    lower = text.lower()
    tokens = [*list(_AI_META_TOKENS), *[phrase.lower() for phrase in profile.forbidden_phrases]]
    matched = tuple(token for token in tokens if token and token in lower)
    if matched:
        return _failed(
            "no_ai_meta_language",
            "Rendered text contains AI/meta or forbidden language.",
            matched,
        )
    return _passed("no_ai_meta_language", "No AI/meta or forbidden language detected.")


def _required_sections_check(
    profile: FormatProfile,
    sections: tuple[RenderedSection, ...],
) -> QualityCheck:
    present = {section.id for section in sections if section.content.strip()}
    missing = tuple(
        section.id for section in profile.required_sections if section.id not in present
    )
    if missing:
        return _failed("required_sections", "Required sections are missing.", missing)
    return _passed("required_sections", "All required sections are present.")


def _naming_consistency_check(
    profile: FormatProfile,
    text: str,
    source_metadata: tuple[dict[str, Any], ...],
) -> QualityCheck:
    configured = profile.naming
    expected_names = tuple(
        str(configured.get(key) or "").strip()
        for key in ("client_display_name", "provider_display_name")
        if str(configured.get(key) or "").strip()
    )
    missing = tuple(name for name in expected_names if name not in text)
    metadata_drift: list[str] = []
    for metadata in source_metadata:
        for key in ("client_display_name", "provider_display_name"):
            metadata_name = str(metadata.get(key) or "").strip()
            configured_name = str(configured.get(key) or "").strip()
            if metadata_name and configured_name and metadata_name != configured_name:
                metadata_drift.append(f"{key}:{metadata_name}")
    evidence = (*missing, *tuple(metadata_drift))
    if evidence:
        return _failed(
            "naming_consistency",
            "Configured client/provider naming is missing or inconsistent.",
            evidence,
        )
    return _passed("naming_consistency", "Configured client/provider naming is consistent.")


def _evidence_recommendation_separation_check(
    profile: FormatProfile,
    sections: tuple[RenderedSection, ...],
) -> QualityCheck:
    if not profile.layout.get("require_evidence_recommendation_separation", True):
        return _passed(
            "evidence_recommendation_separation",
            "Evidence and recommendation separation is not required by profile.",
        )
    section_ids = {section.id for section in sections if section.content.strip()}
    required = {"evidence", "recommendations"}
    if not required <= section_ids:
        return _failed(
            "evidence_recommendation_separation",
            "Evidence/facts and recommendations must be separate sections.",
            tuple(sorted(required - section_ids)),
        )
    return _passed(
        "evidence_recommendation_separation",
        "Evidence/facts and recommendations are separated.",
        tuple(sorted(required)),
    )


def _connector_caveats_check(
    profile: FormatProfile,
    text: str,
    source_metadata: tuple[dict[str, Any], ...],
) -> QualityCheck:
    if not profile.connector_policy.get("require_caveats_for_unverified_sources"):
        return _passed("connector_caveats", "Connector caveats are not required by profile.")
    if not _has_unverified_source(source_metadata):
        return _passed("connector_caveats", "No unverified connector source requires a caveat.")
    if "connector caveat" in text.lower() or "source-system" in text.lower():
        return _passed("connector_caveats", "Connector caveat language is present.")
    return _failed(
        "connector_caveats",
        "Connector caveat language is required for unverified sources.",
        ("unverified_source",),
    )


def _approval_language_check(
    profile: FormatProfile,
    text: str,
    source_metadata: tuple[dict[str, Any], ...],
) -> QualityCheck:
    approval_required = profile.connector_policy.get("require_approval_language") is True or any(
        metadata.get("requires_approval") is True for metadata in source_metadata
    )
    if not approval_required:
        return _passed("approval_language", "Approval language is not required.")
    lower = text.lower()
    if any(token in lower for token in _APPROVAL_TOKENS):
        return _passed("approval_language", "Approval language is present.")
    return _failed(
        "approval_language",
        "Approval language is required before production delivery.",
        ("approval_required",),
    )


def _has_unverified_source(source_metadata: tuple[dict[str, Any], ...]) -> bool:
    return any(
        metadata.get("requires_connector_caveat") is True
        or str(metadata.get("connector_status") or "").lower()
        in {"unverified", "blocked", "missing"}
        for metadata in source_metadata
    )


def _passed(check_id: str, message: str, evidence: tuple[str, ...] = ()) -> QualityCheck:
    return QualityCheck(
        id=check_id,
        status="passed",
        severity="none",
        message=message,
        evidence=evidence,
    )


def _failed(check_id: str, message: str, evidence: tuple[str, ...] = ()) -> QualityCheck:
    return QualityCheck(
        id=check_id,
        status="failed",
        severity="blocker",
        message=message,
        evidence=evidence,
    )


def _issue_from_check(check: QualityCheck) -> dict[str, str]:
    return {"code": check.id, "message": check.message}
