"""CareerOps service catalog and engagement helpers."""

from __future__ import annotations

from application.services.career_ops_graph_contract import CAREER_OPS_PACK_ID
from infrastructure.orm.models import Graph, ServiceCatalogItem, ServiceEngagement, User

CAREER_OPS_APPLICATION_PACKET_CATALOG_SLUG = "career-ops-application-packet"


def ensure_career_ops_application_engagement(*, company: Graph, actor: User | None) -> ServiceEngagement:
    """Return the durable engagement that owns CareerOps application packet deliverables."""

    organization = company.organization
    if organization is None:
        raise ValueError("CareerOps engagement requires an organization-scoped company.")
    catalog_item, _ = ServiceCatalogItem.objects.get_or_create(
        organization=organization,
        slug=CAREER_OPS_APPLICATION_PACKET_CATALOG_SLUG,
        defaults={
            "title": "CareerOps Application Packet",
            "description": "Internal CareerOps service for evaluated job opportunities and application packets.",
            "status": "active",
            "visibility": "internal",
            "audience": "operator",
            "required_pack_ids_json": [CAREER_OPS_PACK_ID],
            "deliverables_schema_json": [
                "job_liveness_receipt",
                "job_evaluation_report",
                "application_packet",
            ],
            "created_by": actor,
            "metadata_json": {"career_ops": {"pack_id": CAREER_OPS_PACK_ID}},
        },
    )
    changed = False
    if catalog_item.status != "active":
        catalog_item.status = "active"
        changed = True
    if catalog_item.required_pack_ids_json != [CAREER_OPS_PACK_ID]:
        catalog_item.required_pack_ids_json = [CAREER_OPS_PACK_ID]
        changed = True
    if changed:
        catalog_item.save(update_fields=["status", "required_pack_ids_json", "updated_at"])

    engagement, _ = ServiceEngagement.objects.get_or_create(
        company=company,
        source_key=f"career-ops:{company.id}:application-pipeline",
        defaults={
            "organization": organization,
            "catalog_item": catalog_item,
            "status": "in_progress",
            "customer_status": "working",
            "public_summary": "CareerOps application pipeline workspace.",
            "internal_notes": "Backend-owned CareerOps URL pipeline engagement.",
            "required_pack_ids_json": [CAREER_OPS_PACK_ID],
            "assigned_operator": actor,
            "requested_by": actor,
            "metadata_json": {"career_ops": {"pack_id": CAREER_OPS_PACK_ID}},
        },
    )
    updates: list[str] = []
    if engagement.catalog_item_id != catalog_item.id:
        engagement.catalog_item = catalog_item
        updates.append("catalog_item")
    if engagement.status != "in_progress":
        engagement.status = "in_progress"
        updates.append("status")
    if engagement.customer_status != "working":
        engagement.customer_status = "working"
        updates.append("customer_status")
    if engagement.required_pack_ids_json != [CAREER_OPS_PACK_ID]:
        engagement.required_pack_ids_json = [CAREER_OPS_PACK_ID]
        updates.append("required_pack_ids_json")
    if updates:
        engagement.save(update_fields=[*updates, "updated_at"])
    return engagement
