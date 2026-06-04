"""Safe Atlas connector readiness normalization."""

from __future__ import annotations

from typing import Any

from application.services.agency_account_catalog import (
    ConnectorDefinition,
    connector_slug_for_value,
    list_connector_definitions,
)
from infrastructure.orm.models import GatewayConnection, Graph, StateProjection

READY_STATUSES = {"active", "available", "connected", "enabled", "healthy", "ok", "ready"}
MISSING_STATUSES = {"missing", "not_configured", "unavailable"}
DEGRADED_STATUSES = {"degraded", "error", "expired", "revoked", "warning"}


def build_connector_readiness(company: Graph) -> dict[str, Any]:
    """Return a redacted connector readiness snapshot for one company."""

    definitions = list_connector_definitions()
    inventory = _projection_inventory(company)
    connections = _gateway_connection_inventory(company, definitions)
    connector_payloads = [
        _connector_payload(definition, inventory=inventory, connections=connections)
        for definition in definitions
    ]
    summary = _summary(connector_payloads)
    return {
        "status": _overall_status(summary),
        "summary": summary,
        "connectors": connector_payloads,
    }


def _connector_payload(
    definition: ConnectorDefinition,
    *,
    inventory: dict[str, dict[str, Any]],
    connections: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    state = _best_state(connections.get(definition.slug), inventory.get(definition.slug))
    status = str(state.get("status") or "missing")
    return {
        "slug": definition.slug,
        "label": definition.label,
        "category": definition.category,
        "required": definition.required,
        "status": status,
        "readiness": "ready" if status == "ready" else "action_required",
        "owner_department_slug": definition.owner_department_slug,
        "source": str(state.get("source") or "catalog"),
        "last_seen_at": state.get("last_seen_at"),
        "last_health_check_at": state.get("last_health_check_at"),
        "message": _message(definition, status),
    }


def _best_state(*states: dict[str, Any] | None) -> dict[str, Any]:
    priority = {"ready": 4, "degraded": 3, "disabled": 2, "missing": 1}
    candidates = [state for state in states if state]
    if not candidates:
        return {"status": "missing", "source": "catalog"}
    return max(candidates, key=lambda item: priority.get(str(item.get("status")), 0))


def _gateway_connection_inventory(
    company: Graph,
    definitions: tuple[ConnectorDefinition, ...],
) -> dict[str, dict[str, Any]]:
    if company.organization_id is None:
        return {}
    inventory: dict[str, dict[str, Any]] = {}
    queryset = (
        GatewayConnection.objects.filter(organization_id=company.organization_id)
        .select_related("graph_version__graph")
        .order_by("-updated_at")
    )
    for connection in queryset:
        if not _connection_applies_to_company(connection, company):
            continue
        slug = _slug_for_connection(connection, definitions)
        if not slug:
            continue
        inventory[slug] = _best_state(inventory.get(slug), _connection_state(connection))
    return inventory


def _connection_applies_to_company(connection: GatewayConnection, company: Graph) -> bool:
    graph_version = connection.graph_version
    if graph_version is None:
        return True
    return graph_version.graph_id == company.id


def _slug_for_connection(
    connection: GatewayConnection,
    definitions: tuple[ConnectorDefinition, ...],
) -> str:
    values = {
        _normalize(connection.platform),
        _normalize(connection.provider),
        connector_slug_for_value(connection.platform),
        connector_slug_for_value(connection.provider),
    }
    for definition in definitions:
        candidates = {
            _normalize(definition.slug),
            *(_normalize(alias) for alias in definition.aliases),
            *(_normalize(platform) for platform in definition.platforms),
        }
        if values & candidates:
            return definition.slug
    return ""


def _connection_state(connection: GatewayConnection) -> dict[str, Any]:
    status = _status_from_value(connection.status)
    return {
        "status": status,
        "source": "gateway_connection",
        "last_seen_at": connection.last_seen_at.isoformat() if connection.last_seen_at else None,
        "last_health_check_at": (
            connection.last_health_check_at.isoformat()
            if connection.last_health_check_at
            else None
        ),
    }


def _projection_inventory(company: Graph) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    queryset = StateProjection.objects.filter(company=company).order_by("-updated_at")
    for projection in queryset:
        state = projection.json_state if isinstance(projection.json_state, dict) else {}
        for raw_item in _raw_connector_items(state):
            slug = _slug_from_raw_item(raw_item)
            if not slug:
                continue
            inventory[slug] = _best_state(
                inventory.get(slug),
                {"status": _status_from_raw_item(raw_item), "source": "backend_projection"},
            )
    return inventory


def _raw_connector_items(state: dict[str, Any]) -> list[Any]:
    items: list[Any] = []
    for key in ("available_connectors", "connector_inventory", "connectors"):
        raw = state.get(key)
        if isinstance(raw, list):
            items.extend(raw)
        elif isinstance(raw, dict):
            items.extend(_items_from_dict(raw))
    return items


def _items_from_dict(raw: dict[str, Any]) -> list[Any]:
    items: list[Any] = []
    for key, value in raw.items():
        if isinstance(value, dict):
            items.append({"id": key, **value})
        else:
            items.append({"id": key, "active": bool(value), "status": "ready" if value else "missing"})
    return items


def _slug_from_raw_item(item: Any) -> str:
    if isinstance(item, str):
        return connector_slug_for_value(item)
    if not isinstance(item, dict):
        return ""
    raw_slug = (
        item.get("slug")
        or item.get("id")
        or item.get("connector")
        or item.get("required_connector")
        or item.get("platform")
        or item.get("name")
    )
    return connector_slug_for_value(raw_slug)


def _status_from_raw_item(item: Any) -> str:
    if isinstance(item, str):
        return "ready"
    if not isinstance(item, dict):
        return "missing"
    if item.get("active") is False:
        return "missing"
    return _status_from_value(item.get("status") or item.get("readiness") or item.get("state"))


def _status_from_value(value: Any) -> str:
    normalized = _normalize(value)
    if normalized in READY_STATUSES:
        return "ready"
    if normalized == "disabled":
        return "disabled"
    if normalized in DEGRADED_STATUSES:
        return "degraded"
    if normalized in MISSING_STATUSES:
        return "missing"
    return "missing"


def _summary(connectors: list[dict[str, Any]]) -> dict[str, int]:
    required = [item for item in connectors if item["required"]]
    return {
        "total": len(connectors),
        "required": len(required),
        "ready": sum(1 for item in connectors if item["status"] == "ready"),
        "missing": sum(1 for item in connectors if item["status"] == "missing"),
        "degraded": sum(1 for item in connectors if item["status"] == "degraded"),
        "disabled": sum(1 for item in connectors if item["status"] == "disabled"),
    }


def _overall_status(summary: dict[str, int]) -> str:
    if summary["missing"]:
        return "blocked"
    if summary["degraded"] or summary["disabled"]:
        return "degraded"
    return "ready"


def _message(definition: ConnectorDefinition, status: str) -> str:
    if status == "ready":
        return f"{definition.label} is ready for agency workflows."
    if status == "degraded":
        return f"{definition.label} needs review before live delivery."
    if status == "disabled":
        return f"{definition.label} is disabled."
    return f"{definition.label} is not connected."


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")
