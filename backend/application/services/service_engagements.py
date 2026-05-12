"""Generic customer-facing service offer and engagement helpers."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from infrastructure.orm.models import (
    Asset,
    Graph,
    ReportRun,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    User,
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
        "pricing_metadata": dict(item.pricing_metadata_json or {}),
        "metadata": dict(item.metadata_json or {}),
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
        payload["metadata"] = dict(engagement.metadata_json or {})
    return payload


def service_deliverable_payload(deliverable: ServiceDeliverable) -> dict[str, Any]:
    return {
        "id": str(deliverable.id),
        "organization_id": str(deliverable.organization_id),
        "company_id": str(deliverable.company_id),
        "engagement_id": str(deliverable.engagement_id),
        "title": deliverable.title,
        "deliverable_type": deliverable.deliverable_type,
        "status": deliverable.status,
        "visibility": deliverable.visibility,
        "artifact_id": str(deliverable.artifact_id) if deliverable.artifact_id else None,
        "report_run_id": str(deliverable.report_run_id) if deliverable.report_run_id else None,
        "summary": deliverable.summary,
        "created_by_id": str(deliverable.created_by_id) if deliverable.created_by_id else None,
        "delivered_at": deliverable.delivered_at.isoformat() if deliverable.delivered_at else None,
        "created_at": deliverable.created_at.isoformat(),
        "updated_at": deliverable.updated_at.isoformat(),
    }


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
        pricing_metadata_json=dict(data.get("pricing_metadata") or {}),
        metadata_json=dict(data.get("metadata") or {}),
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
            setattr(item, attr, str(data[input_key]).strip() if input_key in {"slug", "title"} else str(data[input_key] or ""))
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
            setattr(item, attr, caster(data.get(input_key) or caster()))
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
    required_pack_ids = data.get("required_pack_ids")
    if required_pack_ids is None:
        required_pack_ids = list(catalog_item.required_pack_ids_json or [])
    return ServiceEngagement.objects.create(
        organization=company.organization,
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
    if "status" in data:
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
    if "customer_status" in data:
        engagement.customer_status = str(data["customer_status"])
        update_fields.append("customer_status")
    for input_key, attr in {
        "intake_data": "intake_data_json",
        "required_pack_ids": "required_pack_ids_json",
        "operation_ids": "operation_ids_json",
        "metadata": "metadata_json",
    }.items():
        if input_key in data:
            value = data.get(input_key) or ([] if input_key.endswith("_ids") else {})
            setattr(
                engagement,
                attr,
                _json_id_list(value) if input_key.endswith("_ids") else dict(value),
            )
            update_fields.append(attr)
    for input_key, attr in {
        "public_summary": "public_summary",
        "internal_notes": "internal_notes",
        "source_key": "source_key",
    }.items():
        if input_key in data:
            setattr(engagement, attr, str(data.get(input_key) or ""))
            update_fields.append(attr)
    if "assigned_operator" in data:
        engagement.assigned_operator = data["assigned_operator"]
        update_fields.append("assigned_operator")
    engagement.save(update_fields=sorted(set(update_fields)))
    return engagement


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
    return ServiceDeliverable.objects.create(
        organization=engagement.organization,
        company=engagement.company,
        engagement=engagement,
        title=str(data["title"]).strip(),
        deliverable_type=str(data.get("deliverable_type") or ""),
        status=status,
        visibility=str(data.get("visibility") or "customer"),
        artifact=artifact,
        report_run=report_run,
        summary=str(data.get("summary") or ""),
        metadata_json=dict(data.get("metadata") or {}),
        created_by=user,
        delivered_at=timezone.now() if status == "delivered" else None,
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
