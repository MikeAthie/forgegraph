"""Compatibility entrypoint for generic department routing services."""

from __future__ import annotations

from application.services.routing import (
    RoutingError,
    create_or_update_routing_policy,
    list_department_inbox,
    list_inbox_for_user,
    mark_routing_record_status,
    record_routing_event,
    register_department,
    resolve_department_for_work,
    resolve_routing_policy,
    route_communication_message,
    route_communication_receipt,
    route_event,
    route_event_to_department,
    route_task,
    routing_policy_payload,
    routing_record_payload,
)

__all__ = [
    "RoutingError",
    "create_or_update_routing_policy",
    "list_department_inbox",
    "list_inbox_for_user",
    "mark_routing_record_status",
    "record_routing_event",
    "register_department",
    "resolve_department_for_work",
    "resolve_routing_policy",
    "route_communication_message",
    "route_communication_receipt",
    "route_event",
    "route_event_to_department",
    "route_task",
    "routing_policy_payload",
    "routing_record_payload",
]
