"""Backend-owned quality gates for customer-safe service deliverables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils import timezone

from application.services.agency_deliverable_catalog import get_deliverable_definition
from infrastructure.orm.models import ServiceDeliverable

QUALITY_GATE_SCHEMA_VERSION = "service_deliverable_quality_gate.v1"

_BLOCKED_CONNECTOR_DELIVERABLE_TYPES = {
    "approval_packet",
    "campaign_launch_package",
    "launch_readiness_checklist",
}
_SENSITIVE_KEY_TOKENS = (
    "api_key",
    "apikey",
    "credential",
    "internal",
    "password",
    "private",
    "secret",
    "token",
)
_CONFIDENTIAL_TEXT_TOKENS = (
    "confidential",
    "do not share",
    "internal only",
    "internal-only",
    "operator only",
    "operator-only",
    "private note",
)
_SECRET_VALUE_TOKENS = (
    "api_key=",
    "apikey=",
    "bearer ",
    "password=",
    "secret=",
    "token=",
)


@dataclass(frozen=True)
class _Check:
    id: str
    status: str
    severity: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
        }


class DeliverableQualityGate:
    """Evaluate whether a service deliverable is safe to expose to customers."""

    def evaluate(self, deliverable: ServiceDeliverable) -> dict[str, Any]:
        metadata = _metadata_without_quality_gate(deliverable.metadata_json)
        checks = [
            self._required_title_check(deliverable),
            self._required_summary_check(deliverable),
            self._required_artifact_check(deliverable),
            self._confidential_leakage_check(deliverable, metadata),
            self._secret_metadata_check(metadata),
            self._evidence_source_check(metadata),
            self._approval_requirement_check(deliverable, metadata),
            self._blocked_connectors_check(deliverable, metadata),
            self._customer_visibility_check(deliverable),
        ]
        blockers = [_issue_from_check(check) for check in checks if check.severity == "blocker"]
        warnings = [_issue_from_check(check) for check in checks if check.severity == "warning"]
        passed = not blockers
        score = max(0, 100 - (len(blockers) * 25) - (len(warnings) * 5))
        requires_approval = _requires_approval(deliverable, metadata)
        visibility = {
            "deliverable_visibility": deliverable.visibility,
            "customer_visible": deliverable.visibility == "customer",
            "client_safe": passed and deliverable.visibility == "customer",
        }
        return {
            "schema_version": QUALITY_GATE_SCHEMA_VERSION,
            "status": "pass" if passed else "fail",
            "passed": passed,
            "score": score,
            "checks": [check.as_dict() for check in checks],
            "blockers": blockers,
            "warnings": warnings,
            "visibility": visibility,
            "requires_approval": requires_approval,
            "evaluated_at": timezone.now().isoformat(),
        }

    def refresh(self, deliverable: ServiceDeliverable) -> dict[str, Any]:
        quality_gate = self.evaluate(deliverable)
        metadata = dict(deliverable.metadata_json or {})
        metadata["quality_gate"] = quality_gate
        deliverable.metadata_json = metadata
        deliverable.save(update_fields=["metadata_json", "updated_at"])
        return quality_gate

    def _required_title_check(self, deliverable: ServiceDeliverable) -> _Check:
        if deliverable.title.strip():
            return _pass("required_title", "Deliverable has a customer-facing title.")
        return _blocker("required_title", "Deliverable title is required before client delivery.")

    def _required_summary_check(self, deliverable: ServiceDeliverable) -> _Check:
        if deliverable.summary.strip():
            return _pass("required_summary", "Deliverable has a customer-facing summary.")
        return _blocker(
            "required_summary",
            "Deliverable summary is required before client delivery.",
        )

    def _required_artifact_check(self, deliverable: ServiceDeliverable) -> _Check:
        if deliverable.artifact_id or deliverable.report_run_id:
            return _pass("required_artifact", "Deliverable has a backend-owned artifact.")
        return _blocker(
            "required_artifact",
            "Deliverable requires an artifact or report before client delivery.",
        )

    def _confidential_leakage_check(
        self,
        deliverable: ServiceDeliverable,
        metadata: dict[str, Any],
    ) -> _Check:
        if _contains_confidential_text(deliverable.title) or _contains_confidential_text(
            deliverable.summary
        ):
            return _blocker(
                "internal_confidential_leakage",
                "Deliverable text contains internal or confidential language.",
            )
        if _metadata_contains_confidential_context(metadata):
            return _blocker(
                "internal_confidential_leakage",
                "Deliverable metadata contains internal or confidential context.",
            )
        return _pass(
            "internal_confidential_leakage",
            "No internal or confidential leakage was detected.",
        )

    def _secret_metadata_check(self, metadata: dict[str, Any]) -> _Check:
        if _metadata_contains_sensitive_key_or_value(metadata):
            return _blocker(
                "secret_like_metadata",
                "Deliverable metadata contains secret-like fields or values.",
            )
        return _pass("secret_like_metadata", "No secret-like metadata was detected.")

    def _evidence_source_check(self, metadata: dict[str, Any]) -> _Check:
        if "source_refs" in metadata or "evidence" in metadata:
            return _pass("evidence_source_refs", "Deliverable includes source or evidence refs.")
        return _warning(
            "evidence_source_refs",
            "Deliverable has no source or evidence refs recorded.",
        )

    def _approval_requirement_check(
        self,
        deliverable: ServiceDeliverable,
        metadata: dict[str, Any],
    ) -> _Check:
        if _requires_approval(deliverable, metadata):
            return _pass(
                "approval_requirement",
                "Deliverable is marked as requiring approval.",
            )
        return _pass("approval_requirement", "Deliverable does not require approval.")

    def _blocked_connectors_check(
        self,
        deliverable: ServiceDeliverable,
        metadata: dict[str, Any],
    ) -> _Check:
        blocked_by = _blocked_connectors(metadata)
        if not blocked_by:
            return _pass("blocked_connectors", "No blocked connectors were detected.")
        if deliverable.deliverable_type in _BLOCKED_CONNECTOR_DELIVERABLE_TYPES:
            return _blocker(
                "blocked_connectors",
                "Launch deliverable has blocked connector dependencies.",
            )
        return _warning(
            "blocked_connectors",
            "Blocked connectors are recorded for this deliverable.",
        )

    def _customer_visibility_check(self, deliverable: ServiceDeliverable) -> _Check:
        if deliverable.visibility == "customer":
            return _pass("customer_visibility", "Deliverable visibility is customer-safe.")
        return _blocker(
            "customer_visibility",
            "Deliverable must have customer visibility before client delivery.",
        )


def refresh_deliverable_quality_gate(deliverable: ServiceDeliverable) -> dict[str, Any]:
    return DeliverableQualityGate().refresh(deliverable)


def _metadata_without_quality_gate(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    copy = dict(metadata)
    copy.pop("quality_gate", None)
    return copy


def _requires_approval(deliverable: ServiceDeliverable, metadata: dict[str, Any]) -> bool:
    if metadata.get("requires_approval") is True:
        return True
    definition = get_deliverable_definition(deliverable.deliverable_type)
    if definition is not None and definition.requires_approval:
        return True
    catalog_schema = deliverable.engagement.catalog_item.deliverables_schema_json
    if isinstance(catalog_schema, list):
        for item in catalog_schema:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "") != deliverable.deliverable_type:
                continue
            return item.get("requires_approval") is True
    return False


def _blocked_connectors(metadata: dict[str, Any]) -> list[str]:
    blocked_by = metadata.get("blocked_by")
    if not isinstance(blocked_by, list):
        return []
    return [str(item) for item in blocked_by if str(item)]


def _contains_confidential_text(value: Any) -> bool:
    text = str(value or "").lower()
    return any(token in text for token in _CONFIDENTIAL_TEXT_TOKENS)


def _metadata_contains_confidential_context(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in {"quality_gate", "lifecycle_history"}:
                continue
            if any(token in key_text for token in ("confidential", "internal", "private")):
                return True
            if _metadata_contains_confidential_context(item):
                return True
        return False
    if isinstance(value, list):
        return any(_metadata_contains_confidential_context(item) for item in value)
    return _contains_confidential_text(value)


def _metadata_contains_sensitive_key_or_value(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in {"quality_gate", "lifecycle_history"}:
                continue
            if any(token in key_text for token in _SENSITIVE_KEY_TOKENS):
                return True
            if _metadata_contains_sensitive_key_or_value(item):
                return True
        return False
    if isinstance(value, list):
        return any(_metadata_contains_sensitive_key_or_value(item) for item in value)
    text = str(value or "").lower()
    return any(token in text for token in _SECRET_VALUE_TOKENS)


def _pass(check_id: str, message: str) -> _Check:
    return _Check(id=check_id, status="pass", severity="none", message=message)


def _warning(check_id: str, message: str) -> _Check:
    return _Check(id=check_id, status="warning", severity="warning", message=message)


def _blocker(check_id: str, message: str) -> _Check:
    return _Check(id=check_id, status="fail", severity="blocker", message=message)


def _issue_from_check(check: _Check) -> dict[str, str]:
    return {"code": check.id, "message": check.message}
