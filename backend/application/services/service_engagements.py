"""Generic customer-facing service offer and engagement helpers."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from application.services.agency_deliverable_quality import DeliverableQualityGate
from application.services.audit_log import record_audit_log
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    Graph,
    ReportRun,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    User,
)

SERVICE_DELIVERABLE_ACTIONS = {
    "accept",
    "deliver_to_client",
    "mark_ready",
    "submit_for_approval",
}
_OMIT_METADATA_VALUE = object()
_BLOCKED_METADATA_KEY_TOKENS = (
    "api-key",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "bearer",
    "confidential",
    "cookie",
    "credential",
    "internal",
    "password",
    "private",
    "secret",
    "session",
    "token",
)
_SECRET_METADATA_KEY_TOKENS = (
    "api-key",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "password",
    "secret",
    "session",
    "token",
)
_BLOCKED_METADATA_TEXT_TOKENS = (
    "api-key",
    "api_key",
    "api_key=",
    "apikey",
    "apikey=",
    "authorization:",
    "authorization=",
    "bearer ",
    "cookie:",
    "cookie=",
    "confidential",
    "credential",
    "credential=",
    "do not share",
    "internal only",
    "internal-only",
    "operator only",
    "operator-only",
    "password",
    "password=",
    "private",
    "private note",
    "secret",
    "secret=",
    "session:",
    "session=",
    "set-cookie",
    "token",
    "token=",
)


class ServiceEngagementError(Exception):
    """Domain error for service catalog, engagement, and deliverable actions."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []


def service_catalog_payload(item: ServiceCatalogItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "organization_id": str(item.organization_id),
        "slug": item.slug,
        "title": item.title,
        "description": item.description,
        "status": item.status,
        "visibility": item.visibility,
        "audience": item.audience,
        "required_pack_ids": list(item.required_pack_ids_json or []),
        "optional_pack_ids": list(item.optional_pack_ids_json or []),
        "intake_schema": dict(item.intake_schema_json or {}),
        "deliverables_schema": list(item.deliverables_schema_json or []),
        "default_operation_templates": list(item.default_operation_templates_json or []),
        "default_report_template_id": item.default_report_template_id,
        "pricing_metadata": _safe_metadata(dict(item.pricing_metadata_json or {})),
        "metadata": _safe_metadata(dict(item.metadata_json or {})),
        "created_by_id": str(item.created_by_id) if item.created_by_id else None,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def service_engagement_payload(
    engagement: ServiceEngagement,
    *,
    include_internal: bool = False,
) -> dict[str, Any]:
    payload = {
        "id": str(engagement.id),
        "organization_id": str(engagement.organization_id),
        "company_id": str(engagement.company_id),
        "company_name": engagement.company.name,
        "catalog_item_id": str(engagement.catalog_item_id),
        "service_slug": engagement.catalog_item.slug,
        "service_title": engagement.catalog_item.title,
        "status": engagement.status,
        "customer_status": engagement.customer_status,
        "intake_data": dict(engagement.intake_data_json or {}),
        "public_summary": engagement.public_summary,
        "required_pack_ids": list(engagement.required_pack_ids_json or []),
        "operation_ids": list(engagement.operation_ids_json or []),
        "assigned_operator_id": str(engagement.assigned_operator_id)
        if engagement.assigned_operator_id
        else None,
        "requested_by_id": str(engagement.requested_by_id) if engagement.requested_by_id else None,
        "started_at": engagement.started_at.isoformat() if engagement.started_at else None,
        "delivered_at": engagement.delivered_at.isoformat() if engagement.delivered_at else None,
        "completed_at": engagement.completed_at.isoformat() if engagement.completed_at else None,
        "created_at": engagement.created_at.isoformat(),
        "updated_at": engagement.updated_at.isoformat(),
    }
    if include_internal:
        payload["internal_notes"] = engagement.internal_notes
        payload["source_key"] = engagement.source_key
        payload["metadata"] = _safe_metadata(dict(engagement.metadata_json or {}))
    return payload


def service_deliverable_payload(
    deliverable: ServiceDeliverable,
    *,
    include_internal: bool = False,
) -> dict[str, Any]:
    latest_version = _latest_asset_version(deliverable)
    return {
        "id": str(deliverable.id),
        "organization_id": str(deliverable.organization_id),
        "company_id": str(deliverable.company_id),
        "engagement_id": str(deliverable.engagement_id),
        "title": deliverable.title,
        "deliverable_type": deliverable.deliverable_type,
        "status": deliverable.status,
        "visibility": deliverable.visibility,
        "department_id": str(deliverable.department_id) if deliverable.department_id else None,
        "artifact_id": str(deliverable.artifact_id) if deliverable.artifact_id else None,
        "report_run_id": str(deliverable.report_run_id) if deliverable.report_run_id else None,
        "summary": deliverable.summary,
        "metadata": _deliverable_metadata_payload(
            deliverable.metadata_json or {},
            include_internal=include_internal,
        ),
        "latest_asset_version_id": str(latest_version.id) if latest_version else None,
        "latest_asset_version_uri": latest_version.content_uri if latest_version else None,
        "latest_asset_version_mime_type": latest_version.mime_type if latest_version else None,
        "created_by_id": str(deliverable.created_by_id) if deliverable.created_by_id else None,
        "delivered_at": deliverable.delivered_at.isoformat() if deliverable.delivered_at else None,
        "created_at": deliverable.created_at.isoformat(),
        "updated_at": deliverable.updated_at.isoformat(),
    }


def _latest_asset_version(deliverable: ServiceDeliverable) -> AssetVersion | None:
    if deliverable.artifact_id is None:
        return None
    return (
        AssetVersion.objects.filter(asset_id=deliverable.artifact_id)
        .order_by("-version_number")
        .first()
    )


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        key_text = str(key)
        if _is_blocked_metadata_key(key_text):
            continue
        if key_text == "quality_gate" and isinstance(value, dict):
            safe[key_text] = _safe_quality_gate_metadata(value)
            continue
        sanitized = _safe_metadata_value(value)
        if sanitized is not _OMIT_METADATA_VALUE:
            safe[key_text] = sanitized
    return safe


def _safe_metadata_value(value: Any) -> Any:
    if isinstance(value, dict):
        nested: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_blocked_metadata_key(key_text):
                continue
            if key_text == "quality_gate" and isinstance(item, dict):
                nested[key_text] = _safe_quality_gate_metadata(item)
                continue
            sanitized = _safe_metadata_value(item)
            if sanitized is not _OMIT_METADATA_VALUE:
                nested[key_text] = sanitized
        return nested
    if isinstance(value, list):
        sanitized_items = [_safe_metadata_value(item) for item in value]
        return [item for item in sanitized_items if item is not _OMIT_METADATA_VALUE]
    if isinstance(value, str) and _is_blocked_metadata_text(value):
        return _OMIT_METADATA_VALUE
    return value


def _safe_quality_gate_metadata(value: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        if _is_secret_metadata_key(key_text):
            continue
        sanitized = _safe_quality_gate_value(item)
        if sanitized is not _OMIT_METADATA_VALUE:
            safe[key_text] = sanitized
    return safe


def _safe_quality_gate_value(value: Any) -> Any:
    if isinstance(value, dict):
        nested: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_secret_metadata_key(key_text):
                continue
            sanitized = _safe_quality_gate_value(item)
            if sanitized is not _OMIT_METADATA_VALUE:
                nested[key_text] = sanitized
        return nested
    if isinstance(value, list):
        sanitized_items = [_safe_quality_gate_value(item) for item in value]
        return [item for item in sanitized_items if item is not _OMIT_METADATA_VALUE]
    if isinstance(value, str) and _contains_secret_like_metadata_text(value):
        return _OMIT_METADATA_VALUE
    return value


def _is_blocked_metadata_key(key: str) -> bool:
    normalized = key.lower()
    return any(token in normalized for token in _BLOCKED_METADATA_KEY_TOKENS)


def _is_secret_metadata_key(key: str) -> bool:
    normalized = key.lower()
    return any(token in normalized for token in _SECRET_METADATA_KEY_TOKENS)


def _is_blocked_metadata_text(value: str) -> bool:
    normalized = value.lower()
    return any(token in normalized for token in _BLOCKED_METADATA_TEXT_TOKENS)


def _contains_secret_like_metadata_text(value: str) -> bool:
    normalized = value.lower()
    return any(
        token in normalized
        for token in (
            "api_key=",
            "apikey=",
            "authorization:",
            "authorization=",
            "bearer ",
            "cookie:",
            "cookie=",
            "credential=",
            "password=",
            "secret=",
            "session:",
            "session=",
            "set-cookie",
            "token=",
        )
    )


def _deliverable_metadata_payload(
    metadata: dict[str, Any],
    *,
    include_internal: bool,
) -> dict[str, Any]:
    safe = _safe_metadata(metadata)
    if include_internal:
        return safe
    safe.pop("lifecycle_history", None)
    quality_gate = safe.get("quality_gate")
    if isinstance(quality_gate, dict):
        visibility = quality_gate.get("visibility")
        safe["quality_gate"] = {
            "status": quality_gate.get("status"),
            "passed": quality_gate.get("passed"),
            "score": quality_gate.get("score"),
            "visibility": {
                "client_safe": visibility.get("client_safe") if isinstance(visibility, dict) else None,
                "customer_visible": visibility.get("customer_visible")
                if isinstance(visibility, dict)
                else None,
            },
            "requires_approval": quality_gate.get("requires_approval"),
        }
    return safe


def create_service_catalog_item(
    *,
    organization: Any,
    user: User,
    data: dict[str, Any],
) -> ServiceCatalogItem:
    return ServiceCatalogItem.objects.create(
        organization=organization,
        slug=str(data["slug"]).strip(),
        title=str(data["title"]).strip(),
        description=str(data.get("description") or ""),
        status=str(data.get("status") or "draft"),
        visibility=str(data.get("visibility") or "organization"),
        audience=str(data.get("audience") or ""),
        required_pack_ids_json=list(data.get("required_pack_ids") or []),
        optional_pack_ids_json=list(data.get("optional_pack_ids") or []),
        intake_schema_json=dict(data.get("intake_schema") or {}),
        deliverables_schema_json=list(data.get("deliverables_schema") or []),
        default_operation_templates_json=list(data.get("default_operation_templates") or []),
        default_report_template_id=str(data.get("default_report_template_id") or ""),
        pricing_metadata_json=_safe_metadata(dict(data.get("pricing_metadata") or {})),
        metadata_json=_safe_metadata(dict(data.get("metadata") or {})),
        created_by=user,
    )


def update_service_catalog_item(
    *,
    item: ServiceCatalogItem,
    data: dict[str, Any],
) -> ServiceCatalogItem:
    update_fields = ["updated_at"]
    field_map = {
        "slug": "slug",
        "title": "title",
        "description": "description",
        "status": "status",
        "visibility": "visibility",
        "audience": "audience",
        "default_report_template_id": "default_report_template_id",
    }
    for input_key, attr in field_map.items():
        if input_key in data:
            setattr(
                item,
                attr,
                str(data[input_key]).strip()
                if input_key in {"slug", "title"}
                else str(data[input_key] or ""),
            )
            update_fields.append(attr)
    json_fields = {
        "required_pack_ids": ("required_pack_ids_json", list),
        "optional_pack_ids": ("optional_pack_ids_json", list),
        "intake_schema": ("intake_schema_json", dict),
        "deliverables_schema": ("deliverables_schema_json", list),
        "default_operation_templates": ("default_operation_templates_json", list),
        "pricing_metadata": ("pricing_metadata_json", dict),
        "metadata": ("metadata_json", dict),
    }
    for input_key, (attr, caster) in json_fields.items():
        if input_key in data:
            value = caster(data.get(input_key) or caster())
            if input_key in {"pricing_metadata", "metadata"}:
                value = _safe_metadata(dict(value))
            setattr(item, attr, value)
            update_fields.append(attr)
    item.save(update_fields=sorted(set(update_fields)))
    return item


def create_service_engagement(
    *,
    company: Graph,
    catalog_item: ServiceCatalogItem,
    user: User,
    data: dict[str, Any],
) -> ServiceEngagement:
    if catalog_item.organization_id != company.organization_id:
        raise ServiceEngagementError(
            "catalog_company_mismatch",
            "Service catalog item does not belong to the company organization.",
        )
    organization = company.organization
    if organization is None:
        raise ServiceEngagementError(
            "company_organization_required",
            "Service engagements require a company organization.",
        )
    required_pack_ids = data.get("required_pack_ids")
    if required_pack_ids is None:
        required_pack_ids = list(catalog_item.required_pack_ids_json or [])
    return ServiceEngagement.objects.create(
        organization=organization,
        company=company,
        catalog_item=catalog_item,
        status=str(data.get("status") or "requested"),
        customer_status=str(data.get("customer_status") or "requested"),
        intake_data_json=dict(data.get("intake_data") or {}),
        public_summary=str(data.get("public_summary") or ""),
        internal_notes=str(data.get("internal_notes") or ""),
        source_key=str(data.get("source_key") or ""),
        required_pack_ids_json=list(required_pack_ids or []),
        operation_ids_json=_json_id_list(data.get("operation_ids") or []),
        metadata_json=dict(data.get("metadata") or {}),
        assigned_operator=data.get("assigned_operator"),
        requested_by=user,
    )


def update_service_engagement(
    *,
    engagement: ServiceEngagement,
    data: dict[str, Any],
) -> ServiceEngagement:
    update_fields = ["updated_at"]
    _apply_service_engagement_status(engagement, data, update_fields)
    if "customer_status" in data:
        engagement.customer_status = str(data["customer_status"])
        update_fields.append("customer_status")
    _apply_service_engagement_json_fields(engagement, data, update_fields)
    _apply_service_engagement_text_fields(engagement, data, update_fields)
    if "assigned_operator" in data:
        engagement.assigned_operator = data["assigned_operator"]
        update_fields.append("assigned_operator")
    engagement.save(update_fields=sorted(set(update_fields)))
    return engagement


def _apply_service_engagement_status(
    engagement: ServiceEngagement,
    data: dict[str, Any],
    update_fields: list[str],
) -> None:
    if "status" not in data:
        return
    engagement.status = str(data["status"])
    update_fields.append("status")
    now = timezone.now()
    if engagement.status == "in_progress" and engagement.started_at is None:
        engagement.started_at = now
        update_fields.append("started_at")
    if engagement.status == "delivered" and engagement.delivered_at is None:
        engagement.delivered_at = now
        update_fields.append("delivered_at")
    if engagement.status == "completed" and engagement.completed_at is None:
        engagement.completed_at = now
        update_fields.append("completed_at")


def _apply_service_engagement_json_fields(
    engagement: ServiceEngagement,
    data: dict[str, Any],
    update_fields: list[str],
) -> None:
    for input_key, attr in {
        "intake_data": "intake_data_json",
        "required_pack_ids": "required_pack_ids_json",
        "operation_ids": "operation_ids_json",
        "metadata": "metadata_json",
    }.items():
        if input_key in data:
            value: Any = data.get(input_key) or ([] if input_key.endswith("_ids") else {})
            setattr(
                engagement,
                attr,
                _json_id_list(value) if input_key.endswith("_ids") else dict(value),
            )
            update_fields.append(attr)


def _apply_service_engagement_text_fields(
    engagement: ServiceEngagement,
    data: dict[str, Any],
    update_fields: list[str],
) -> None:
    for input_key, attr in {
        "public_summary": "public_summary",
        "internal_notes": "internal_notes",
        "source_key": "source_key",
    }.items():
        if input_key in data:
            setattr(engagement, attr, str(data.get(input_key) or ""))
            update_fields.append(attr)


def create_service_deliverable(
    *,
    engagement: ServiceEngagement,
    user: User,
    data: dict[str, Any],
) -> ServiceDeliverable:
    artifact = data.get("artifact")
    report_run = data.get("report_run")
    _validate_company_owned_output(engagement=engagement, artifact=artifact, report_run=report_run)
    status = str(data.get("status") or "draft")
    deliverable = ServiceDeliverable.objects.create(
        organization=engagement.organization,
        company=engagement.company,
        engagement=engagement,
        title=str(data["title"]).strip(),
        deliverable_type=str(data.get("deliverable_type") or ""),
        status=status,
        visibility=str(data.get("visibility") or "customer"),
        department=data.get("department"),
        artifact=artifact,
        report_run=report_run,
        summary=str(data.get("summary") or ""),
        metadata_json=dict(data.get("metadata") or {}),
        created_by=user,
        delivered_at=timezone.now() if status == "delivered" else None,
    )
    DeliverableQualityGate().refresh(deliverable)
    return deliverable


def apply_service_deliverable_action(
    *,
    deliverable: ServiceDeliverable,
    action: str,
    actor: User | None,
) -> ServiceDeliverable:
    normalized_action = str(action or "").strip()
    if normalized_action not in SERVICE_DELIVERABLE_ACTIONS:
        raise ServiceEngagementError(
            "invalid_deliverable_action",
            "Unsupported service deliverable action.",
        )

    if normalized_action == "mark_ready":
        return _mark_deliverable_ready(deliverable=deliverable, actor=actor)
    if normalized_action == "submit_for_approval":
        return _submit_deliverable_for_approval(deliverable=deliverable, actor=actor)
    if normalized_action == "deliver_to_client":
        return _deliver_deliverable_to_client(deliverable=deliverable, actor=actor)
    return _accept_deliverable(deliverable=deliverable, actor=actor)


def _mark_deliverable_ready(
    *,
    deliverable: ServiceDeliverable,
    actor: User | None,
) -> ServiceDeliverable:
    if deliverable.status in {"delivered", "accepted", "archived"}:
        raise _transition_error("mark_ready", deliverable.status)
    quality_gate = _evaluate_and_store_quality_gate(deliverable)
    _raise_if_quality_blocked(quality_gate)
    from_status = deliverable.status
    _persist_deliverable_lifecycle(
        deliverable=deliverable,
        action="mark_ready",
        actor=actor,
        from_status=from_status,
        to_status="ready",
        quality_gate=quality_gate,
    )
    return deliverable


def _submit_deliverable_for_approval(
    *,
    deliverable: ServiceDeliverable,
    actor: User | None,
) -> ServiceDeliverable:
    if deliverable.status != "ready":
        raise _transition_error("submit_for_approval", deliverable.status)
    quality_gate = _evaluate_and_store_quality_gate(deliverable)
    _raise_if_quality_blocked(quality_gate)
    if not quality_gate.get("requires_approval"):
        raise ServiceEngagementError(
            "approval_not_required",
            "This deliverable does not require approval.",
        )
    from_status = deliverable.status
    _persist_deliverable_lifecycle(
        deliverable=deliverable,
        action="submit_for_approval",
        actor=actor,
        from_status=from_status,
        to_status="in_review",
        quality_gate=quality_gate,
    )
    _move_engagement_to_customer_review(deliverable.engagement)
    return deliverable


def _deliver_deliverable_to_client(
    *,
    deliverable: ServiceDeliverable,
    actor: User | None,
) -> ServiceDeliverable:
    if deliverable.status not in {"ready", "in_review"}:
        raise _transition_error("deliver_to_client", deliverable.status)
    quality_gate = _evaluate_and_store_quality_gate(deliverable)
    _raise_if_quality_blocked(quality_gate)
    if quality_gate.get("requires_approval") and deliverable.status != "in_review":
        raise ServiceEngagementError(
            "approval_required",
            "Submit this deliverable for approval before client delivery.",
        )
    from_status = deliverable.status
    _persist_deliverable_lifecycle(
        deliverable=deliverable,
        action="deliver_to_client",
        actor=actor,
        from_status=from_status,
        to_status="delivered",
        quality_gate=quality_gate,
        delivered_at=timezone.now(),
    )
    return deliverable


def _accept_deliverable(
    *,
    deliverable: ServiceDeliverable,
    actor: User | None,
) -> ServiceDeliverable:
    if deliverable.status != "delivered":
        raise _transition_error("accept", deliverable.status)
    quality_gate = _evaluate_and_store_quality_gate(deliverable)
    _raise_if_quality_blocked(quality_gate)
    from_status = deliverable.status
    _persist_deliverable_lifecycle(
        deliverable=deliverable,
        action="accept",
        actor=actor,
        from_status=from_status,
        to_status="accepted",
        quality_gate=quality_gate,
    )
    return deliverable


def _evaluate_and_store_quality_gate(deliverable: ServiceDeliverable) -> dict[str, Any]:
    quality_gate = DeliverableQualityGate().evaluate(deliverable)
    metadata = dict(deliverable.metadata_json or {})
    metadata["quality_gate"] = quality_gate
    deliverable.metadata_json = metadata
    deliverable.save(update_fields=["metadata_json", "updated_at"])
    return quality_gate


def _raise_if_quality_blocked(quality_gate: dict[str, Any]) -> None:
    blockers = quality_gate.get("blockers")
    if isinstance(blockers, list) and blockers:
        raise ServiceEngagementError(
            "quality_gate_blocked",
            "Deliverable quality gate has blockers.",
            details=[item for item in blockers if isinstance(item, dict)],
        )


def _persist_deliverable_lifecycle(
    *,
    deliverable: ServiceDeliverable,
    action: str,
    actor: User | None,
    from_status: str,
    to_status: str,
    quality_gate: dict[str, Any] | None,
    delivered_at: Any | None = None,
) -> None:
    now = timezone.now()
    metadata = dict(deliverable.metadata_json or {})
    if quality_gate is not None:
        metadata["quality_gate"] = quality_gate
    history = list(metadata.get("lifecycle_history") or [])
    history.append(
        {
            "action": action,
            "actor_id": str(actor.id) if actor else None,
            "from_status": from_status,
            "to_status": to_status,
            "at": now.isoformat(),
            "quality_gate_status": quality_gate.get("status") if quality_gate else None,
        }
    )
    metadata["lifecycle_history"] = history[-50:]
    deliverable.status = to_status
    deliverable.metadata_json = metadata
    update_fields = ["status", "metadata_json", "updated_at"]
    if delivered_at is not None:
        deliverable.delivered_at = delivered_at
        update_fields.append("delivered_at")
    deliverable.save(update_fields=update_fields)
    record_audit_log(
        actor=actor,
        tenant_id=str(deliverable.organization_id),
        action=f"service_deliverable.{action}",
        resource_type="service_deliverable",
        resource_id=str(deliverable.id),
        metadata={
            "company_id": str(deliverable.company_id),
            "engagement_id": str(deliverable.engagement_id),
            "from_status": from_status,
            "to_status": to_status,
            "quality_gate_status": quality_gate.get("status") if quality_gate else None,
        },
    )


def _move_engagement_to_customer_review(engagement: ServiceEngagement) -> None:
    engagement.status = "waiting_on_customer"
    engagement.customer_status = "review_ready"
    engagement.save(update_fields=["status", "customer_status", "updated_at"])


def _transition_error(action: str, current_status: str) -> ServiceEngagementError:
    return ServiceEngagementError(
        "invalid_deliverable_transition",
        f"Cannot apply {action} to a deliverable in {current_status} status.",
    )


def _validate_company_owned_output(
    *,
    engagement: ServiceEngagement,
    artifact: Asset | None,
    report_run: ReportRun | None,
) -> None:
    if artifact is None and report_run is None:
        return
    if artifact is not None and artifact.company_id != engagement.company_id:
        raise ServiceEngagementError(
            "artifact_company_mismatch",
            "Deliverable artifact does not belong to the engagement company.",
        )
    if report_run is not None and report_run.company_id != engagement.company_id:
        raise ServiceEngagementError(
            "report_company_mismatch",
            "Deliverable report does not belong to the engagement company.",
        )


def _json_id_list(values: Any) -> list[str]:
    return [str(value) for value in values]
