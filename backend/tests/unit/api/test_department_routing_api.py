from __future__ import annotations

from typing import cast

import pytest
from django.test import override_settings
from django.utils import timezone

from application.projections.tasks import apply as apply_task_projection
from application.services.communication_kafka import build_communication_kafka_payload
from application.services.communications import create_message, create_thread
from application.services.department_routing import (
    create_or_update_routing_policy,
    register_department,
    resolve_department_for_work,
    route_communication_message,
    route_communication_receipt,
)
from infrastructure.orm.models import (
    CommunicationEventReceipt,
    CommunicationMessage,
    CommunicationThread,
    CompanyAccessPolicy,
    CompanyAssignment,
    CompanySignal,
    DepartmentMembership,
    DepartmentRegistry,
    DomainEvent,
    DomainEventOutbox,
    Graph,
    GraphVersion,
    Organization,
    OrganizationMembership,
    RoutingPolicy,
    Run,
    TaskLifecycleRecord,
    TaskRecord,
    TaskRoutingRecord,
    ToolExecution,
    User,
)

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str, role: str = "member") -> User:
    user = User.objects.create_user(email=email, password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(organization=org, user=user, role=role, is_default=True)
    return user


def _company(
    org: Organization,
    owner: User,
    *,
    name: str = "Legacy Eyewear",
    org_admin_access_enabled: bool = True,
) -> Graph:
    company = cast(
        Graph,
        Graph.objects.create(owner=owner, organization=org, name=name, description="Test company"),
    )
    CompanyAccessPolicy.objects.create(
        organization=org,
        company=company,
        assignment_required=True,
        org_admin_access_enabled=org_admin_access_enabled,
    )
    return company


def _assign(org: Organization, company: Graph, user: User, role: str = "member") -> None:
    CompanyAssignment.objects.create(
        organization=org,
        company=company,
        user=user,
        role=role,
        status="active",
    )


def _department(org: Organization, slug: str, name: str) -> DepartmentRegistry:
    return DepartmentRegistry.objects.create(
        organization=org,
        slug=slug,
        name=name,
        department_type=slug,
    )


def _department_member(
    org: Organization,
    department: DepartmentRegistry,
    user: User,
    role: str,
) -> None:
    DepartmentMembership.objects.create(
        organization=org,
        department=department,
        user=user,
        role=role,
        status="active",
    )


def _task(
    org: Organization,
    company: Graph,
    owner: User,
) -> tuple[Run, TaskLifecycleRecord, TaskRecord]:
    version = GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={
            "nodes": [{"id": "creative", "type": "agent", "name": "Creative"}],
            "edges": [],
        },
    )
    run = Run.objects.create(
        owner=owner,
        organization=org,
        graph_version=version,
        status="running",
        started_at=timezone.now(),
    )
    lifecycle = TaskLifecycleRecord.objects.create(
        organization=org,
        run=run,
        source_node_id="creative",
        node_type="agent",
        external_key=f"{run.id}:creative",
        title="Creative task",
        status="queued",
        priority="normal",
        last_transition_at=timezone.now(),
    )
    task = TaskRecord.objects.create(
        organization=org,
        execution=run,
        lifecycle_task=lifecycle,
        source_node_id="creative",
        external_key=f"task-record:{run.id}:creative",
        title="Creative task",
        status="queued",
        priority="normal",
        summary="Needs routing.",
    )
    return run, lifecycle, task


def _communication_message(
    org: Organization,
    company: Graph,
    sender: User,
) -> CommunicationMessage:
    _ = org
    thread = create_thread(
        company=company,
        user=sender,
        data={
            "title": "Legacy consult",
            "thread_type": "support",
            "visibility_mode": "mixed",
            "source_key": f"consult:{company.id}:primary",
        },
    )
    return create_message(
        thread=thread,
        sender_user=sender,
        message_kind="request",
        body="Can you explain why WhatsApp is recommended if the connector is missing?",
        visibility="customer",
        idempotency_key=f"routing-message:{company.id}",
        metadata={"channel": "whatsapp", "service_type": "support"},
    )


def test_department_member_without_company_access_cannot_read_inbox(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "owner-routing@example.com", "owner")
    department_user = _user(org, "department-only@example.com", "member")
    company = _company(org, owner)
    department = _department(org, "creative", "Creative")
    _department_member(org, department, department_user, "viewer")
    _assign(org, company, owner, "member")
    _run, lifecycle, _task_record = _task(org, company, owner)
    TaskRoutingRecord.objects.create(
        organization=org,
        company=company,
        task_lifecycle=lifecycle,
        to_department=department,
        status="queued",
    )

    api_client.force_authenticate(user=department_user)
    response = api_client.get(
        "/api/routing/inbox",
        data={"department_id": str(department.id), "company_id": str(company.id)},
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


def test_company_member_without_department_membership_cannot_read_or_route(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "owner-no-dept@example.com", "owner")
    company_member = _user(org, "company-only@example.com", "member")
    company = _company(org, owner)
    department = _department(org, "creative", "Creative")
    _assign(org, company, owner, "member")
    _assign(org, company, company_member, "member")
    _run, lifecycle, task_record = _task(org, company, owner)
    TaskRoutingRecord.objects.create(
        organization=org,
        company=company,
        task_lifecycle=lifecycle,
        to_department=department,
        status="queued",
    )

    api_client.force_authenticate(user=company_member)
    inbox = api_client.get(
        "/api/routing/inbox",
        data={"department_id": str(department.id), "company_id": str(company.id)},
    )
    route = api_client.post(
        f"/api/tasks/{task_record.id}/route",
        data={"to_department_id": str(department.id), "reason": "Company access is not enough."},
        format="json",
    )

    assert inbox.status_code == 200
    assert inbox.json()["data"]["items"] == []
    assert route.status_code == 403


def test_department_lead_with_company_access_can_route_and_projection_is_idempotent(
    api_client,
) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "owner-lead@example.com", "owner")
    lead = _user(org, "creative-lead@example.com", "member")
    company = _company(org, owner)
    department = _department(org, "creative", "Creative")
    _assign(org, company, owner, "member")
    _assign(org, company, lead, "member")
    _department_member(org, department, lead, "lead")
    _run, lifecycle, task_record = _task(org, company, owner)

    api_client.force_authenticate(user=lead)
    response = api_client.post(
        f"/api/tasks/{task_record.id}/route",
        data={
            "to_department_id": str(department.id),
            "reason": "Creative owns the next handoff.",
            "metadata": {"sla_minutes": 15},
        },
        format="json",
    )

    assert response.status_code == 201, response.json()
    routing_record = TaskRoutingRecord.objects.get(
        id=response.json()["data"]["routing_record"]["id"]
    )
    assert routing_record.to_department_id == department.id
    assert routing_record.due_at is not None

    lifecycle.refresh_from_db()
    task_record.refresh_from_db()
    assert lifecycle.current_department_id == department.id
    assert task_record.department_id == department.id

    event = DomainEvent.objects.get(
        event_type="task.routing_created", aggregate_id=routing_record.id
    )
    apply_task_projection(event)
    apply_task_projection(event)
    task_record.refresh_from_db()
    assert task_record.department_id == department.id


def test_org_admin_override_still_respects_company_access_policy(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "locked-owner@example.com", "owner")
    admin = _user(org, "blocked-admin@example.com", "admin")
    company = _company(org, owner, org_admin_access_enabled=False)
    department = _department(org, "traffic", "Traffic")
    _assign(org, company, owner, "member")
    _department_member(org, department, admin, "lead")
    _run, _lifecycle, task_record = _task(org, company, owner)

    api_client.force_authenticate(user=admin)
    response = api_client.post(
        f"/api/tasks/{task_record.id}/route",
        data={"to_department_id": str(department.id)},
        format="json",
    )

    assert response.status_code == 404


def test_assigned_user_must_belong_to_target_department_and_company(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "owner-assign@example.com", "owner")
    lead = _user(org, "lead-assign@example.com", "member")
    company_only = _user(org, "company-no-department@example.com", "member")
    department_only = _user(org, "department-no-company@example.com", "member")
    company = _company(org, owner)
    department = _department(org, "creative", "Creative")
    _assign(org, company, owner, "member")
    _assign(org, company, lead, "member")
    _assign(org, company, company_only, "member")
    _department_member(org, department, lead, "lead")
    _department_member(org, department, department_only, "viewer")
    _run, _lifecycle, task_record = _task(org, company, owner)

    api_client.force_authenticate(user=lead)
    no_department = api_client.post(
        f"/api/tasks/{task_record.id}/route",
        data={
            "to_department_id": str(department.id),
            "assigned_user_id": str(company_only.id),
        },
        format="json",
    )
    no_company = api_client.post(
        f"/api/tasks/{task_record.id}/route",
        data={
            "to_department_id": str(department.id),
            "assigned_user_id": str(department_only.id),
        },
        format="json",
    )

    assert no_department.status_code == 400
    assert no_department.json()["error"]["code"] == "ASSIGNED_USER_DEPARTMENT_MEMBER_REQUIRED"
    assert no_company.status_code == 400
    assert no_company.json()["error"]["code"] == "ASSIGNED_USER_COMPANY_ACCESS_REQUIRED"


def test_missing_connector_records_signal_and_internal_note_without_fake_execution(
    api_client,
) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "owner-gap@example.com", "owner")
    lead = _user(org, "lead-gap@example.com", "member")
    customer = _user(org, "customer-gap@example.com", "viewer")
    company = _company(org, owner)
    department = _department(org, "channel-ops", "Channel Ops")
    _assign(org, company, owner, "member")
    _assign(org, company, lead, "member")
    _assign(org, company, customer, "viewer")
    _department_member(org, department, lead, "lead")
    _run, _lifecycle, task_record = _task(org, company, owner)

    api_client.force_authenticate(user=lead)
    response = api_client.post(
        f"/api/tasks/{task_record.id}/route",
        data={
            "to_department_id": str(department.id),
            "status": "blocked",
            "reason": "WhatsApp connector is missing.",
            "missing_capability": {
                "channel": "whatsapp",
                "capability": "whatsapp_business_connector",
                "summary": "WhatsApp execution is blocked until credentials are configured.",
            },
        },
        format="json",
    )

    assert response.status_code == 201, response.json()
    signal = CompanySignal.objects.get(company=company, source="department_routing")
    assert signal.channel == "whatsapp"
    assert signal.metadata_json["execution_status"] == "blocked_until_missing_capabilities_resolved"
    thread = CommunicationThread.objects.get(thread_type="capability_gap")
    assert thread.visibility_mode == "operator"
    assert thread.department_id == department.id
    message = CommunicationMessage.objects.get(thread=thread)
    assert message.visibility == "internal"
    assert ToolExecution.objects.count() == 0

    api_client.force_authenticate(user=customer)
    customer_threads = api_client.get(
        "/api/communication/threads",
        data={"company_id": str(company.id)},
    )
    assert customer_threads.status_code == 200
    assert customer_threads.json()["data"]["threads"] == []


def test_company_policy_precedes_organization_policy() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "owner-policy@example.com", "owner")
    company = _company(org, owner)
    traffic = _department(org, "traffic", "Traffic")
    media = _department(org, "media", "Media")
    RoutingPolicy.objects.create(
        organization=org,
        department=traffic,
        service_type="campaign",
        channel="ads",
        active=True,
    )
    RoutingPolicy.objects.create(
        organization=org,
        company=company,
        department=media,
        service_type="campaign",
        channel="ads",
        active=True,
    )

    resolved = resolve_department_for_work(
        company=company,
        service_type="campaign",
        channel="ads",
    )

    assert resolved == media


def test_register_department_is_unique_per_organization() -> None:
    org = Organization.objects.create(name="ATLAS")
    lead = _user(org, "department-lead@example.com", "member")

    first = register_department(
        organization=org,
        slug="traffic",
        name="Traffic",
        department_type="operations",
        lead_user=lead,
        service_tags=["handoff"],
    )
    second = register_department(
        organization=org,
        slug="traffic",
        name="Traffic Desk",
        department_type="operations",
        lead_user=lead,
        service_tags=["handoff", "triage"],
    )

    assert first.id == second.id
    second.refresh_from_db()
    assert second.name == "Traffic Desk"
    assert second.lead_user_id == lead.id
    assert DepartmentRegistry.objects.filter(organization=org, slug="traffic").count() == 1


def test_communication_message_routes_to_policy_department_idempotently() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "owner-comm-route@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    department = _department(org, "channel-ops", "Channel Ops")
    create_or_update_routing_policy(
        organization=org,
        company=company,
        department=department,
        event_type="communication.message.created",
        trigger_type="communication.message.created",
        channel="whatsapp",
        priority_rules={"default": "high"},
        sla={"target_minutes": 20},
    )
    message = _communication_message(org, company, owner)
    before_body = message.body
    before_thread_status = message.thread.status

    first = route_communication_message(message=message, user=owner)
    second = route_communication_message(message=message, user=owner)
    message.refresh_from_db()
    message.thread.refresh_from_db()

    assert first.id == second.id
    assert first.to_department_id == department.id
    assert first.communication_message_id == message.id
    assert first.communication_thread_id == message.thread_id
    assert first.priority == "high"
    assert first.due_at is not None
    assert message.body == before_body
    assert message.thread.status == before_thread_status
    assert (
        TaskRoutingRecord.objects.filter(
            idempotency_key=f"routing:communication-message:{message.id}"
        ).count()
        == 1
    )
    event = DomainEvent.objects.get(event_type="task.routing_created", aggregate_id=first.id)
    event_text = str(event.payload)
    assert "Can you explain why WhatsApp" not in event_text


def test_missing_communication_policy_creates_blocked_unrouted_record() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "owner-missing-policy@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    message = _communication_message(org, company, owner)

    record = route_communication_message(message=message, user=owner)

    assert record.status == "blocked"
    assert record.to_department.slug == "unrouted"
    assert "No active routing policy" in record.reason


def test_authorized_operator_sees_department_inbox_and_other_client_does_not(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "owner-inbox@example.com", "owner")
    lead = _user(org, "lead-inbox@example.com", "member")
    other_user = _user(org, "other-client-inbox@example.com", "member")
    company = _company(org, owner, name="Legacy Eyewear")
    other_company = _company(org, owner, name="Other Client")
    _assign(org, company, owner, "member")
    _assign(org, company, lead, "member")
    _assign(org, other_company, other_user, "member")
    department = _department(org, "channel-ops", "Channel Ops")
    _department_member(org, department, lead, "lead")
    create_or_update_routing_policy(
        organization=org,
        company=company,
        department=department,
        event_type="communication.message.created",
        trigger_type="communication.message.created",
    )
    message = _communication_message(org, company, owner)
    record = route_communication_message(message=message, user=owner)

    api_client.force_authenticate(user=lead)
    allowed = api_client.get(
        "/api/routing/inbox",
        data={"department_id": str(department.id), "company_id": str(company.id)},
    )
    api_client.force_authenticate(user=other_user)
    denied = api_client.get(
        "/api/routing/inbox",
        data={"department_id": str(department.id), "company_id": str(company.id)},
    )

    assert allowed.status_code == 200
    assert [item["id"] for item in allowed.json()["data"]["items"]] == [str(record.id)]
    assert denied.status_code == 200
    assert denied.json()["data"]["items"] == []


def test_routing_record_patch_requires_department_and_company_access(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "owner-patch-route@example.com", "owner")
    lead = _user(org, "lead-patch-route@example.com", "member")
    department_only = _user(org, "dept-only-patch-route@example.com", "member")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, lead, "member")
    department = _department(org, "traffic", "Traffic")
    _department_member(org, department, lead, "lead")
    _department_member(org, department, department_only, "lead")
    message = _communication_message(org, company, owner)
    record = route_communication_message(
        message=message,
        user=owner,
        idempotency_key="routing-record-patch-test",
    )

    api_client.force_authenticate(user=department_only)
    blocked = api_client.patch(
        f"/api/routing/records/{record.id}",
        data={"status": "completed"},
        format="json",
    )
    api_client.force_authenticate(user=lead)
    allowed = api_client.patch(
        f"/api/routing/records/{record.id}",
        data={"status": "completed", "resolution": {"result": "done"}},
        format="json",
    )

    assert blocked.status_code == 404
    assert allowed.status_code == 200, allowed.json()
    record.refresh_from_db()
    assert record.status == "completed"
    assert record.resolution_json == {"result": "done"}


@override_settings(COMMUNICATION_ROUTING_FROM_KAFKA_ENABLED=True)
def test_optional_kafka_receipt_handler_routes_once() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "owner-receipt-route@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    department = _department(org, "traffic", "Traffic")
    create_or_update_routing_policy(
        organization=org,
        company=company,
        department=department,
        event_type="communication.message.created",
        trigger_type="communication.message.created",
    )
    message = _communication_message(org, company, owner)
    outbox = DomainEventOutbox.objects.get(
        event_type="communication.message.created",
        aggregate_id=message.id,
    )
    payload = build_communication_kafka_payload(outbox)
    receipt = CommunicationEventReceipt.objects.create(
        consumer_group="routing-consumer",
        event_id=payload["event_id"],
        idempotency_key=payload["idempotency_key"],
        topic=payload["topic"],
        organization=org,
        company=company,
        outbox_event=outbox,
        event_type=payload["event_type"],
        schema_version=payload["schema_version"],
        aggregate_type=payload["aggregate_type"],
        aggregate_id=payload["aggregate_id"],
        status="handled",
        payload_json=payload,
        handled_at=timezone.now(),
    )

    first = route_communication_receipt(receipt=receipt)
    second = route_communication_receipt(receipt=receipt)

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.to_department_id == department.id
    assert (
        TaskRoutingRecord.objects.filter(
            idempotency_key=f"routing:communication-receipt:{receipt.id}"
        ).count()
        == 1
    )
