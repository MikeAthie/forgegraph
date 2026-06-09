"""Backend-owned Atlas launch readiness evaluation."""

from __future__ import annotations

import json
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder

from application.services.agency_connector_readiness import build_connector_readiness
from application.services.agency_deliverable_catalog import MVP_DELIVERABLE_TYPES
from application.services.agency_deliverables import ensure_atlas_service_engagement
from application.services.company_archive import ArchiveService
from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.service_engagements import service_deliverable_payload
from infrastructure.orm.models import (
    Asset,
    ServiceDeliverable,
    ServiceEngagement,
    StateProjection,
    User,
    WorkWhiteboard,
)

READINESS_SCHEMA_VERSION = "atlas_campaign_launch_readiness_v1"
READINESS_SOURCE = "atlas_launch_readiness"
RECEIPT_DELIVERABLE_TYPE = "campaign_launch_receipt"
RECEIPT_TITLE = "Campaign Launch Readiness Receipt"
PASSING_STATUSES = {"accepted", "approved", "complete", "completed", "pass", "passed", "ready"}
TRACKING_READY_STATUSES = {"active", "configured", "enabled", "ready", "tracked"}
DELIVERABLE_READY_STATUSES = {"accepted", "delivered", "ready"}


class CampaignLaunchReadiness:
    """Evaluate Atlas launch safety without external execution."""

    def evaluate(
        self,
        *,
        whiteboard: WorkWhiteboard,
        user: User | None = None,
        live_mode: bool = False,
        idempotency_key: str = "",
        create_receipt: bool = False,
    ) -> dict[str, Any]:
        connector_readiness = build_connector_readiness(whiteboard.company)
        approval_state = _approval_state(whiteboard)
        deliverable_state = _deliverable_state(whiteboard)
        qa_state = _qa_state(whiteboard)
        tracking_state = _tracking_state(whiteboard)
        side_effect_readiness = _side_effect_readiness(
            whiteboard=whiteboard,
            live_mode=live_mode,
            idempotency_key=idempotency_key,
        )

        blockers: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        blockers.extend(_connector_blockers(connector_readiness))
        blockers.extend(_approval_blockers(approval_state))
        blockers.extend(_deliverable_blockers(deliverable_state))
        blockers.extend(_qa_blockers(qa_state))
        _apply_tracking_findings(
            tracking_state=tracking_state,
            live_mode=live_mode,
            blockers=blockers,
            warnings=warnings,
        )
        blockers.extend(_side_effect_blockers(side_effect_readiness))

        required_checks = _required_checks(
            connector_readiness=connector_readiness,
            approval_state=approval_state,
            deliverable_state=deliverable_state,
            qa_state=qa_state,
            tracking_state=tracking_state,
            side_effect_readiness=side_effect_readiness,
            live_mode=live_mode,
        )
        status = "blocked" if blockers else "warning" if warnings else "ready"
        payload = sanitize_outbox_payload(
            {
                "schema_version": READINESS_SCHEMA_VERSION,
                "source": READINESS_SOURCE,
                "whiteboard_id": str(whiteboard.id),
                "company_id": str(whiteboard.company_id),
                "requested_execution_mode": "live" if live_mode else "dry_run",
                "dry_run": not live_mode,
                "live_execution_enabled": False,
                "status": status,
                "passed": status == "ready",
                "blockers": blockers,
                "warnings": warnings,
                "required_checks": required_checks,
                "connector_readiness": connector_readiness,
                "approval_state": approval_state,
                "deliverable_state": deliverable_state,
                "qa_state": qa_state,
                "tracking_state": tracking_state,
                "side_effect_readiness": side_effect_readiness,
            }
        )
        if create_receipt:
            receipt = _upsert_launch_receipt(
                whiteboard=whiteboard,
                user=user,
                readiness=payload,
            )
            payload["receipt_deliverable"] = service_deliverable_payload(receipt)
        return sanitize_outbox_payload(payload)


def _projection_state(whiteboard: WorkWhiteboard, suffix: str) -> dict[str, Any]:
    projection = (
        StateProjection.objects.filter(
            organization=whiteboard.organization,
            company=whiteboard.company,
            program=None,
            projection_type=f"whiteboard_{suffix}:{whiteboard.id}",
        )
        .order_by("-updated_at")
        .first()
    )
    if projection is None or not isinstance(projection.json_state, dict):
        return {}
    return sanitize_outbox_payload(
        {
            **projection.json_state,
            "projection_id": str(projection.id),
            "projection_type": projection.projection_type,
        }
    )


def _approval_state(whiteboard: WorkWhiteboard) -> dict[str, Any]:
    state = _projection_state(whiteboard, "approval")
    if not state:
        return {"status": "missing", "approved": False, "source": "backend_projection"}
    status = _status_value(state, default="missing")
    approved = _truthy(state.get("approved")) or status in {"accepted", "approved"}
    return {
        "status": "approved" if approved else status,
        "approved": approved,
        "approval_id": str(state.get("approval_id") or state.get("id") or ""),
        "projection_id": state.get("projection_id"),
        "source": "backend_projection",
    }


def _qa_state(whiteboard: WorkWhiteboard) -> dict[str, Any]:
    state = _projection_state(whiteboard, "qa")
    if not state:
        return {"status": "missing", "passed": False, "source": "backend_projection"}
    status = _status_value(state, default="missing")
    passed = _truthy(state.get("passed")) or status in PASSING_STATUSES
    return {
        "status": "passed" if passed else status,
        "passed": passed,
        "projection_id": state.get("projection_id"),
        "source": "backend_projection",
    }


def _tracking_state(whiteboard: WorkWhiteboard) -> dict[str, Any]:
    state = _projection_state(whiteboard, "tracking")
    if not state:
        return {"status": "missing", "configured": False, "source": "backend_projection"}
    status = _status_value(state, default="missing")
    configured = (
        _truthy(state.get("configured"))
        or _truthy(state.get("tracking_configured"))
        or status in TRACKING_READY_STATUSES
    )
    return {
        "status": "ready" if configured else status,
        "configured": configured,
        "tracking_plan_id": str(state.get("tracking_plan_id") or ""),
        "projection_id": state.get("projection_id"),
        "source": "backend_projection",
    }


def _deliverable_state(whiteboard: WorkWhiteboard) -> dict[str, Any]:
    engagement = _atlas_engagement(whiteboard)
    queryset = ServiceDeliverable.objects.filter(
        company=whiteboard.company,
        deliverable_type__in=MVP_DELIVERABLE_TYPES,
    )
    if engagement is not None:
        queryset = queryset.filter(engagement=engagement)
    else:
        queryset = queryset.filter(metadata_json__whiteboard_id=str(whiteboard.id))
    deliverables = list(queryset.select_related("artifact").order_by("created_at"))
    by_type = {deliverable.deliverable_type: deliverable for deliverable in deliverables}
    items: list[dict[str, Any]] = []
    missing_types: list[str] = []
    not_ready_types: list[str] = []
    for deliverable_type in MVP_DELIVERABLE_TYPES:
        deliverable = by_type.get(deliverable_type)
        if deliverable is None:
            missing_types.append(deliverable_type)
            items.append({"type": deliverable_type, "status": "missing", "ready": False})
            continue
        ready = (
            deliverable.status in DELIVERABLE_READY_STATUSES and deliverable.artifact_id is not None
        )
        if not ready:
            not_ready_types.append(deliverable_type)
        items.append(
            {
                "id": str(deliverable.id),
                "type": deliverable.deliverable_type,
                "title": deliverable.title,
                "status": deliverable.status,
                "ready": ready,
                "artifact_id": str(deliverable.artifact_id) if deliverable.artifact_id else "",
            }
        )
    ready_count = sum(1 for item in items if bool(item.get("ready")))
    return {
        "status": "ready" if not missing_types and not not_ready_types else "blocked",
        "required_count": len(MVP_DELIVERABLE_TYPES),
        "ready_count": ready_count,
        "missing_types": missing_types,
        "not_ready_types": not_ready_types,
        "launch_package_present": "campaign_launch_package" not in missing_types,
        "deliverables": items,
        "engagement_id": str(engagement.id) if engagement is not None else "",
    }


def _atlas_engagement(whiteboard: WorkWhiteboard) -> ServiceEngagement | None:
    source_key = f"atlas-engagement:{whiteboard.id}"
    engagement = (
        ServiceEngagement.objects.filter(company=whiteboard.company, source_key=source_key)
        .select_related("catalog_item", "company")
        .first()
    )
    if engagement is not None:
        return engagement
    if whiteboard.service_engagement_id:
        return (
            ServiceEngagement.objects.filter(
                company=whiteboard.company,
                id=whiteboard.service_engagement_id,
            )
            .select_related("catalog_item", "company")
            .first()
        )
    return None


def _side_effect_readiness(
    *,
    whiteboard: WorkWhiteboard,
    live_mode: bool,
    idempotency_key: str,
) -> dict[str, Any]:
    key_present = bool(str(idempotency_key or whiteboard.idempotency_key or "").strip())
    if not live_mode:
        return {
            "status": "dry_run",
            "idempotency_key_present": key_present,
            "idempotency_key_required_for_live": True,
            "live_execution_enabled": False,
            "external_side_effects": "disabled",
        }
    return {
        "status": "ready" if key_present else "blocked",
        "idempotency_key_present": key_present,
        "idempotency_key_required_for_live": True,
        "live_execution_enabled": False,
        "external_side_effects": "disabled",
    }


def _connector_blockers(connector_readiness: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for connector in list(connector_readiness.get("connectors") or []):
        if not isinstance(connector, dict) or not bool(connector.get("required")):
            continue
        if str(connector.get("status") or "") == "ready":
            continue
        blockers.append(
            {
                "code": "connector_not_ready",
                "message": f"{connector.get('label') or connector.get('slug')} is not ready.",
                "connector_slug": str(connector.get("slug") or ""),
                "status": str(connector.get("status") or "missing"),
            }
        )
    return blockers


def _approval_blockers(approval_state: dict[str, Any]) -> list[dict[str, Any]]:
    if bool(approval_state.get("approved")):
        return []
    code = (
        "approval_missing" if approval_state.get("status") == "missing" else "approval_not_approved"
    )
    return [
        {
            "code": code,
            "message": "Client approval is required before launch.",
            "status": str(approval_state.get("status") or "missing"),
        }
    ]


def _deliverable_blockers(deliverable_state: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    missing_types = list(deliverable_state.get("missing_types") or [])
    not_ready_types = list(deliverable_state.get("not_ready_types") or [])
    if missing_types:
        blockers.append(
            {
                "code": "deliverables_missing",
                "message": "Launch package deliverables are missing.",
                "deliverable_types": missing_types,
            }
        )
    if not_ready_types:
        blockers.append(
            {
                "code": "deliverables_not_ready",
                "message": "Launch package deliverables must be ready, delivered, or accepted.",
                "deliverable_types": not_ready_types,
            }
        )
    return blockers


def _qa_blockers(qa_state: dict[str, Any]) -> list[dict[str, Any]]:
    if bool(qa_state.get("passed")):
        return []
    return [
        {
            "code": "qa_not_passing",
            "message": "Launch QA must pass before live spend, send, or publish.",
            "status": str(qa_state.get("status") or "missing"),
        }
    ]


def _apply_tracking_findings(
    *,
    tracking_state: dict[str, Any],
    live_mode: bool,
    blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    if bool(tracking_state.get("configured")):
        return
    item = {
        "code": "tracking_missing",
        "message": "Tracking must be configured before live launch.",
        "status": str(tracking_state.get("status") or "missing"),
    }
    if live_mode:
        blockers.append(item)
    else:
        warnings.append(item)


def _side_effect_blockers(side_effect_readiness: dict[str, Any]) -> list[dict[str, Any]]:
    if str(side_effect_readiness.get("status") or "") != "blocked":
        return []
    return [
        {
            "code": "idempotency_key_required",
            "message": "Live launch checks require an idempotency key.",
        }
    ]


def _required_checks(
    *,
    connector_readiness: dict[str, Any],
    approval_state: dict[str, Any],
    deliverable_state: dict[str, Any],
    qa_state: dict[str, Any],
    tracking_state: dict[str, Any],
    side_effect_readiness: dict[str, Any],
    live_mode: bool,
) -> list[dict[str, Any]]:
    return [
        _check(
            code="connectors_ready",
            label="Required connectors ready",
            passed=str(connector_readiness.get("status") or "") == "ready",
            status=str(connector_readiness.get("status") or "missing"),
        ),
        _check(
            code="approval_approved",
            label="Client approval approved",
            passed=bool(approval_state.get("approved")),
            status=str(approval_state.get("status") or "missing"),
        ),
        _check(
            code="deliverables_ready",
            label="Launch package deliverables ready",
            passed=str(deliverable_state.get("status") or "") == "ready",
            status=str(deliverable_state.get("status") or "missing"),
        ),
        _check(
            code="qa_passed",
            label="Launch QA passed",
            passed=bool(qa_state.get("passed")),
            status=str(qa_state.get("status") or "missing"),
        ),
        _check(
            code="tracking_ready",
            label="Tracking configured",
            passed=bool(tracking_state.get("configured")),
            status=str(tracking_state.get("status") or "missing"),
            severity="blocker" if live_mode else "warning",
        ),
        _check(
            code="side_effect_safety",
            label="Idempotent side-effect safety",
            passed=str(side_effect_readiness.get("status") or "") != "blocked",
            status=str(side_effect_readiness.get("status") or "missing"),
        ),
    ]


def _check(
    *,
    code: str,
    label: str,
    passed: bool,
    status: str,
    severity: str = "blocker",
) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "status": "passed" if passed else status,
        "passed": passed,
        "severity": severity,
    }


def _upsert_launch_receipt(
    *,
    whiteboard: WorkWhiteboard,
    user: User | None,
    readiness: dict[str, Any],
) -> ServiceDeliverable:
    engagement = ensure_atlas_service_engagement(whiteboard=whiteboard, user=user)
    content = json.dumps(readiness, sort_keys=True, cls=DjangoJSONEncoder, separators=(",", ":"))
    metadata = _receipt_metadata(whiteboard=whiteboard, readiness=readiness)
    asset = _upsert_receipt_asset(whiteboard=whiteboard, user=user, metadata=metadata)
    version = ArchiveService().create_asset_version(
        asset=asset,
        content_uri=f"forgegraph://atlas-launch-readiness/{whiteboard.id}/receipt.json",
        content=content.encode("utf-8"),
        mime_type="application/json",
        provenance={
            "source": READINESS_SOURCE,
            "whiteboard_id": str(whiteboard.id),
            "inline_content": content,
        },
    )
    metadata["asset_version_id"] = str(version.id)
    deliverable = (
        ServiceDeliverable.objects.filter(
            engagement=engagement,
            deliverable_type=RECEIPT_DELIVERABLE_TYPE,
        )
        .order_by("created_at")
        .first()
    )
    status = "ready" if bool(metadata["ready"]) else "in_review"
    summary = _receipt_summary(readiness)
    if deliverable is None:
        return ServiceDeliverable.objects.create(
            organization=engagement.organization,
            company=engagement.company,
            engagement=engagement,
            title=RECEIPT_TITLE,
            deliverable_type=RECEIPT_DELIVERABLE_TYPE,
            status=status,
            visibility="operator",
            artifact=asset,
            summary=summary,
            metadata_json=metadata,
            created_by=user,
        )
    deliverable.title = RECEIPT_TITLE
    deliverable.status = status
    deliverable.visibility = "operator"
    deliverable.artifact = asset
    deliverable.summary = summary
    deliverable.metadata_json = metadata
    deliverable.save(
        update_fields=[
            "title",
            "status",
            "visibility",
            "artifact",
            "summary",
            "metadata_json",
            "updated_at",
        ]
    )
    return deliverable


def _upsert_receipt_asset(
    *,
    whiteboard: WorkWhiteboard,
    user: User | None,
    metadata: dict[str, Any],
) -> Asset:
    asset = ArchiveService().create_asset(
        company=whiteboard.company,
        title=RECEIPT_TITLE,
        asset_type="deliverable",
        source_key=f"atlas-launch-readiness:{whiteboard.id}:receipt",
        created_by_type="user" if user is not None else "system",
        created_by_id=user.id if user is not None else None,
        metadata=metadata,
    )
    updates: list[str] = []
    if asset.title != RECEIPT_TITLE:
        asset.title = RECEIPT_TITLE
        updates.append("title")
    if asset.metadata_json != metadata:
        asset.metadata_json = metadata
        updates.append("metadata_json")
    if asset.status != "active":
        asset.status = "active"
        updates.append("status")
    if updates:
        asset.save(update_fields=updates + ["updated_at"])
    return asset


def _receipt_metadata(*, whiteboard: WorkWhiteboard, readiness: dict[str, Any]) -> dict[str, Any]:
    blocked = bool(readiness.get("blockers"))
    ready = str(readiness.get("status") or "") == "ready"
    return {
        "source": READINESS_SOURCE,
        "whiteboard_id": str(whiteboard.id),
        "deliverable_type": RECEIPT_DELIVERABLE_TYPE,
        "dry_run": bool(readiness.get("dry_run")),
        "ready": ready,
        "blocked": blocked,
        "readiness_status": str(readiness.get("status") or ""),
        "live_execution_enabled": False,
        "blocker_codes": [
            str(item.get("code") or "") for item in list(readiness.get("blockers") or [])
        ],
        "warning_codes": [
            str(item.get("code") or "") for item in list(readiness.get("warnings") or [])
        ],
    }


def _receipt_summary(readiness: dict[str, Any]) -> str:
    status = str(readiness.get("status") or "unknown")
    if status == "ready":
        return "Dry-run launch readiness passed. Live execution remains disabled."
    if status == "blocked":
        blockers = list(readiness.get("blockers") or [])
        return f"Dry-run launch readiness blocked by {len(blockers)} check(s)."
    warnings = list(readiness.get("warnings") or [])
    return f"Dry-run launch readiness has {len(warnings)} warning(s)."


def _status_value(state: dict[str, Any], *, default: str) -> str:
    return (
        str(
            state.get("status")
            or state.get("readiness")
            or state.get("state")
            or state.get("result")
            or default
        )
        .strip()
        .lower()
    )


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "ready", "approved"}
