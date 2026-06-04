"""Backend-owned Atlas operator onboarding contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from application.services.agency_connector_readiness import build_connector_readiness
from application.services.agency_onboarding import build_virtual_onboarding_checklist
from infrastructure.orm.models import Graph, ServiceCatalogItem, ServiceEngagement, User

CONTRACT_VERSION = "atlas_onboarding.v1"
CATALOG_SLUG = "atlas-operator-onboarding"
CATALOG_SOURCE_KEY = "atlas-catalog:atlas-operator-onboarding"
CATALOG_TITLE = "Atlas Operator Onboarding"
ENGAGEMENT_SOURCE_PREFIX = "atlas-onboarding"
SOURCE = "atlas_onboarding"
DEFAULT_INTAKE_SOURCE = "operator"
FORBIDDEN_KEY_TOKENS = (
    "api_key",
    "apikey",
    "client_secret",
    "credential",
    "password",
    "private",
    "secret",
    "token",
)


@dataclass(frozen=True, slots=True)
class IntakeFieldDefinition:
    slug: str
    label: str
    required: bool = False


INTAKE_FIELD_DEFINITIONS: tuple[IntakeFieldDefinition, ...] = (
    IntakeFieldDefinition("client_name", "Client name", required=True),
    IntakeFieldDefinition("contact_name", "Contact name", required=True),
    IntakeFieldDefinition("contact_email", "Contact email", required=True),
    IntakeFieldDefinition("website_url", "Website URL"),
    IntakeFieldDefinition("business_summary", "Business summary", required=True),
    IntakeFieldDefinition("goals", "Goals", required=True),
    IntakeFieldDefinition("target_audience", "Target audience", required=True),
    IntakeFieldDefinition("brand_voice", "Brand voice"),
    IntakeFieldDefinition("constraints", "Constraints"),
    IntakeFieldDefinition("approved_channels", "Approved channels", required=True),
    IntakeFieldDefinition("blocked_channels", "Blocked channels"),
    IntakeFieldDefinition("success_metrics", "Success metrics", required=True),
    IntakeFieldDefinition("budget_range", "Budget range"),
    IntakeFieldDefinition("timeline", "Timeline", required=True),
    IntakeFieldDefinition("service_slug", "Service slug", required=True),
    IntakeFieldDefinition("service_package", "Service package"),
    IntakeFieldDefinition("notes", "Notes"),
    IntakeFieldDefinition("source", "Source"),
)

INTAKE_FIELD_SLUGS = {field.slug for field in INTAKE_FIELD_DEFINITIONS}
LIST_FIELDS = {
    "approved_channels",
    "blocked_channels",
    "constraints",
    "goals",
    "success_metrics",
}
TEXT_FIELDS = INTAKE_FIELD_SLUGS - LIST_FIELDS - {"target_audience"}


class AtlasOnboardingError(Exception):
    """Domain error for Atlas onboarding contract operations."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def build_atlas_onboarding_contract(company: Graph) -> dict[str, Any]:
    connector_readiness = build_connector_readiness(company)
    onboarding = build_virtual_onboarding_checklist(
        company,
        connector_readiness=connector_readiness,
    )
    latest_engagement = _latest_engagement(company)
    intake_data = (
        dict(latest_engagement.intake_data_json or {}) if latest_engagement is not None else {}
    )
    missing_required_fields = _missing_required_fields(intake_data)
    operator_next_steps = _operator_next_steps(
        missing_required_fields=missing_required_fields,
        connector_readiness=connector_readiness,
        onboarding_items=onboarding["items"],
        has_engagement=latest_engagement is not None,
    )
    return {
        "company_id": str(company.id),
        "generated_at": timezone.now().isoformat(),
        "contract_version": CONTRACT_VERSION,
        "onboarding": {
            "summary": onboarding["summary"],
            "items": onboarding["items"],
        },
        "connector_readiness": connector_readiness,
        "required_fields": [
            _field_payload(field) for field in INTAKE_FIELD_DEFINITIONS if field.required
        ],
        "missing_required_fields": missing_required_fields,
        "operator_next_steps": operator_next_steps,
        "next_actions": operator_next_steps,
        "latest_engagement": (
            _engagement_summary(latest_engagement) if latest_engagement is not None else None
        ),
        "latest_intake_summary": _safe_intake_summary(intake_data) if intake_data else None,
    }


def upsert_atlas_onboarding_engagement(
    *,
    company: Graph,
    actor: User,
    intake_updates: dict[str, Any],
    operator_metadata: dict[str, Any] | None = None,
) -> tuple[ServiceEngagement, bool]:
    organization = company.organization
    if organization is None:
        raise AtlasOnboardingError(
            "company_organization_required",
            "Atlas onboarding requires a company organization.",
        )
    source_key = atlas_onboarding_source_key(company)
    sanitized_updates = sanitize_intake_updates(intake_updates)
    sanitized_operator_metadata = (
        safe_metadata(operator_metadata) if operator_metadata is not None else None
    )
    with transaction.atomic():
        catalog = ensure_atlas_onboarding_catalog(company=company, actor=actor)
        existing = (
            ServiceEngagement.objects.select_for_update()
            .select_related("catalog_item")
            .filter(company=company, source_key=source_key)
            .first()
        )
        if existing is None:
            intake_data = _merged_intake({}, sanitized_updates)
            engagement = ServiceEngagement.objects.create(
                organization=organization,
                company=company,
                catalog_item=catalog,
                status="intake",
                customer_status="intake_needed",
                intake_data_json=intake_data,
                public_summary=_public_summary(intake_data),
                source_key=source_key,
                required_pack_ids_json=[],
                metadata_json=_engagement_metadata(
                    actor=actor,
                    operator_metadata=sanitized_operator_metadata or {},
                ),
                requested_by=actor,
            )
            return engagement, True

        intake_data = _merged_intake(existing.intake_data_json or {}, sanitized_updates)
        metadata = {
            **(existing.metadata_json or {}),
            "source": SOURCE,
            "contract_version": CONTRACT_VERSION,
            "last_submitted_by_user_id": str(actor.id),
        }
        if sanitized_operator_metadata is not None:
            metadata["operator_metadata"] = sanitized_operator_metadata
        existing.catalog_item = catalog
        existing.status = _updated_status(existing.status)
        existing.customer_status = _updated_customer_status(existing.customer_status)
        existing.intake_data_json = intake_data
        existing.public_summary = _public_summary(intake_data)
        existing.required_pack_ids_json = []
        existing.metadata_json = metadata
        if existing.requested_by_id is None:
            existing.requested_by = actor
        existing.save(
            update_fields=[
                "catalog_item",
                "status",
                "customer_status",
                "intake_data_json",
                "public_summary",
                "required_pack_ids_json",
                "metadata_json",
                "requested_by",
                "updated_at",
            ]
        )
        return existing, False


def ensure_atlas_onboarding_catalog(*, company: Graph, actor: User | None) -> ServiceCatalogItem:
    organization = company.organization
    if organization is None:
        raise AtlasOnboardingError(
            "company_organization_required",
            "Atlas onboarding catalog requires a company organization.",
        )
    defaults = _catalog_defaults(actor=actor)
    catalog, created = ServiceCatalogItem.objects.get_or_create(
        organization=organization,
        slug=CATALOG_SLUG,
        defaults=defaults,
    )
    if not created:
        _update_catalog_defaults(catalog, defaults)
    return catalog


def atlas_onboarding_source_key(company: Graph) -> str:
    return f"{ENGAGEMENT_SOURCE_PREFIX}:{company.id}"


def sanitize_intake_updates(updates: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in updates.items():
        key_text = str(key)
        if key_text not in INTAKE_FIELD_SLUGS or forbidden_key(key_text):
            continue
        sanitized[key_text] = _sanitize_intake_value(key_text, value)
    return sanitized


def safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        key_text = str(key)
        if forbidden_key(key_text):
            continue
        safe[key_text] = _safe_metadata_value(value)
    return safe


def forbidden_key(key: object) -> bool:
    normalized = str(key or "").strip().lower().replace("-", "_")
    return any(token in normalized for token in FORBIDDEN_KEY_TOKENS)


def _catalog_defaults(*, actor: User | None) -> dict[str, Any]:
    return {
        "title": CATALOG_TITLE,
        "description": "Operator-mediated Atlas onboarding intake contract.",
        "status": "active",
        "visibility": "organization",
        "audience": "atlas_operators",
        "required_pack_ids_json": [],
        "optional_pack_ids_json": [],
        "intake_schema_json": _intake_schema(),
        "deliverables_schema_json": [],
        "default_operation_templates_json": [],
        "metadata_json": {
            "source": SOURCE,
            "source_key": CATALOG_SOURCE_KEY,
            "contract_version": CONTRACT_VERSION,
        },
        "created_by": actor,
    }


def _update_catalog_defaults(catalog: ServiceCatalogItem, defaults: dict[str, Any]) -> None:
    changed_fields: list[str] = []
    for attr in (
        "title",
        "description",
        "status",
        "visibility",
        "audience",
        "required_pack_ids_json",
        "optional_pack_ids_json",
        "intake_schema_json",
        "deliverables_schema_json",
        "default_operation_templates_json",
        "metadata_json",
    ):
        value = defaults[attr]
        if getattr(catalog, attr) != value:
            setattr(catalog, attr, value)
            changed_fields.append(attr)
    if catalog.created_by_id is None and defaults.get("created_by") is not None:
        catalog.created_by = defaults["created_by"]
        changed_fields.append("created_by")
    if changed_fields:
        catalog.save(update_fields=sorted(set(changed_fields + ["updated_at"])))


def _intake_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "contract_version": CONTRACT_VERSION,
        "required": [field.slug for field in INTAKE_FIELD_DEFINITIONS if field.required],
        "properties": {
            field.slug: {
                "label": field.label,
                "required": field.required,
            }
            for field in INTAKE_FIELD_DEFINITIONS
        },
        "forbidden_key_tokens": list(FORBIDDEN_KEY_TOKENS),
    }


def _merged_intake(existing: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = {key: value for key, value in existing.items() if key in INTAKE_FIELD_SLUGS}
    merged.update(updates)
    merged.setdefault("source", DEFAULT_INTAKE_SOURCE)
    return merged


def _engagement_metadata(*, actor: User, operator_metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": SOURCE,
        "contract_version": CONTRACT_VERSION,
        "last_submitted_by_user_id": str(actor.id),
        "operator_metadata": operator_metadata,
    }


def _updated_status(status: str) -> str:
    if status in {"requested", "cancelled", "archived"}:
        return "intake"
    return status or "intake"


def _updated_customer_status(status: str) -> str:
    if status in {"requested", "cancelled"}:
        return "intake_needed"
    return status or "intake_needed"


def _public_summary(intake_data: dict[str, Any]) -> str:
    values = [
        intake_data.get("client_name"),
        intake_data.get("business_summary"),
        ", ".join(intake_data.get("goals") or [])
        if isinstance(intake_data.get("goals"), list)
        else intake_data.get("goals"),
    ]
    summary = " ".join(str(value).strip() for value in values if str(value or "").strip())
    return summary[:1000]


def _latest_engagement(company: Graph) -> ServiceEngagement | None:
    atlas_engagement = (
        ServiceEngagement.objects.filter(
            company=company,
            source_key=atlas_onboarding_source_key(company),
        )
        .select_related("catalog_item", "company")
        .order_by("-updated_at")
        .first()
    )
    if atlas_engagement is not None:
        return atlas_engagement
    return (
        ServiceEngagement.objects.filter(company=company)
        .select_related("catalog_item", "company")
        .order_by("-updated_at")
        .first()
    )


def _field_payload(field: IntakeFieldDefinition) -> dict[str, Any]:
    return {"slug": field.slug, "label": field.label, "required": field.required}


def _missing_required_fields(intake_data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _field_payload(field)
        for field in INTAKE_FIELD_DEFINITIONS
        if field.required and not _has_value(intake_data.get(field.slug))
    ]


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _operator_next_steps(
    *,
    missing_required_fields: list[dict[str, Any]],
    connector_readiness: dict[str, Any],
    onboarding_items: list[dict[str, Any]],
    has_engagement: bool,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not has_engagement:
        actions.append(
            {
                "slug": "record_atlas_intake",
                "label": "Record Atlas intake",
                "priority": "high",
                "owner_department_slug": "client_approval_ops",
                "reason": "No Atlas onboarding service engagement is recorded.",
            }
        )
    for field in missing_required_fields:
        actions.append(
            {
                "slug": f"collect_{field['slug']}",
                "label": f"Collect {field['label']}",
                "priority": "high",
                "owner_department_slug": "client_approval_ops",
                "reason": "Required Atlas onboarding intake is missing.",
            }
        )
    for connector in _missing_required_connectors(connector_readiness):
        actions.append(
            {
                "slug": f"configure_{connector['slug']}",
                "label": f"Configure {connector['label']}",
                "priority": "high",
                "owner_department_slug": connector["owner_department_slug"],
                "reason": connector["message"],
            }
        )
    for item in onboarding_items:
        if item["status"] in {"blocked", "not_started"} and item["slug"] != "connector_setup":
            actions.append(
                {
                    "slug": f"complete_{item['slug']}",
                    "label": f"Complete {item['label']}",
                    "priority": "medium" if item["status"] == "not_started" else "high",
                    "owner_department_slug": item["owner_department_slug"],
                    "reason": item["message"],
                }
            )
    return _dedupe_actions(actions)


def _missing_required_connectors(connector_readiness: dict[str, Any]) -> list[dict[str, Any]]:
    connectors = connector_readiness.get("connectors")
    if not isinstance(connectors, list):
        return []
    return [
        item
        for item in connectors
        if isinstance(item, dict) and item.get("required") and item.get("status") != "ready"
    ]


def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for action in actions:
        deduped.setdefault(str(action["slug"]), action)
    return list(deduped.values())


def _engagement_summary(engagement: ServiceEngagement) -> dict[str, Any]:
    intake_data = dict(engagement.intake_data_json or {})
    metadata = engagement.metadata_json if isinstance(engagement.metadata_json, dict) else {}
    return {
        "id": str(engagement.id),
        "status": engagement.status,
        "customer_status": engagement.customer_status,
        "source_key": engagement.source_key,
        "service_slug": engagement.catalog_item.slug,
        "service_title": engagement.catalog_item.title,
        "public_summary": engagement.public_summary,
        "intake_data_summary": _safe_intake_summary(intake_data),
        "operator_metadata_summary": safe_metadata(
            metadata.get("operator_metadata")
            if isinstance(metadata.get("operator_metadata"), dict)
            else {}
        ),
        "created_at": engagement.created_at.isoformat(),
        "updated_at": engagement.updated_at.isoformat(),
    }


def _safe_intake_summary(intake_data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _sanitize_intake_value(key, value)
        for key, value in intake_data.items()
        if key in INTAKE_FIELD_SLUGS and not forbidden_key(key)
    }


def _sanitize_intake_value(key: str, value: Any) -> Any:
    if key in LIST_FIELDS:
        return _string_list(value)
    if key == "target_audience":
        if isinstance(value, dict):
            return safe_metadata(value)
        if isinstance(value, list):
            return [_safe_metadata_value(item) for item in value]
        return str(value or "").strip()
    if key == "contact_email":
        return str(value or "").strip().lower()
    if key in TEXT_FIELDS:
        return str(value or "").strip()
    return _safe_metadata_value(value)


def _string_list(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item or "").strip()]


def _safe_metadata_value(value: Any) -> Any:
    if isinstance(value, dict):
        return safe_metadata(value)
    if isinstance(value, list):
        return [_safe_metadata_value(item) for item in value]
    return value
