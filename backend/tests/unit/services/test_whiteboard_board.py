from __future__ import annotations

from datetime import timedelta
from typing import cast
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.utils import timezone

from application.services.whiteboard_boards import (
    WhiteboardBoardError,
    attach_card_evidence,
    build_whiteboard_board_snapshot,
    create_whiteboard_card,
    rebuild_whiteboard_board_snapshot_from_db,
    update_whiteboard_card,
    whiteboard_board_snapshot_key,
)
from infrastructure.orm.models import (
    ApprovalTask,
    CompanyAccessPolicy,
    CompanyAssignment,
    DecisionRecord,
    DepartmentMembership,
    DepartmentRegistry,
    DomainEventOutbox,
    EvaluationRun,
    EvaluationScorecard,
    Graph,
    GraphVersion,
    Organization,
    OrganizationMembership,
    Run,
    TaskLifecycleRecord,
    TaskRecord,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)
from tests.helpers.idempotency import assert_queryset_count
from tests.helpers.organizations import required_company_organization

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str, role: str = "member") -> User:
    local, _, domain = email.partition("@")
    user = User.objects.create_user(
        email=f"{local}-{uuid4().hex}@{domain or 'example.com'}",
        password="testpassword123",
    )
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(organization=org, user=user, role=role, is_default=True)
    return user


def _company(org: Organization, owner: User, *, name: str = "Legacy Eyewear") -> Graph:
    company = cast(
        Graph,
        Graph.objects.create(owner=owner, organization=org, name=name, description="Test company"),
    )
    CompanyAccessPolicy.objects.create(
        organization=org,
        company=company,
        assignment_required=True,
        org_admin_access_enabled=True,
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


def _department(
    org: Organization,
    slug: str,
    *,
    name: str | None = None,
    department_type: str = "",
    tags: list[str] | None = None,
) -> DepartmentRegistry:
    return DepartmentRegistry.objects.create(
        organization=org,
        slug=slug,
        name=name or slug.replace("-", " ").title(),
        department_type=department_type,
        service_tags_json=tags or [],
    )


def _department_member(
    org: Organization, department: DepartmentRegistry, user: User, role: str = "member"
) -> None:
    DepartmentMembership.objects.create(
        organization=org,
        department=department,
        user=user,
        role=role,
        status="active",
    )


def _whiteboard(company: Graph, owner: User) -> WorkWhiteboard:
    return WorkWhiteboard.objects.create(
        organization=required_company_organization(company),
        company=company,
        status=WorkWhiteboard.STATUS_ONBOARDING,
        request_type="service_request",
        client_name=company.name,
        request_summary="Build a durable project plan without leaking client evidence.",
        objective="Launch the project safely.",
        completion_score=64.0,
        created_by=owner,
    )


def _run(company: Graph, owner: User) -> Run:
    version = GraphVersion.objects.create(
        graph=company,
        version=GraphVersion.objects.filter(graph=company).count() + 1,
        graph_json={"nodes": [], "edges": []},
    )
    return Run.objects.create(
        owner=owner,
        organization=required_company_organization(company),
        graph_version=version,
        status="paused",
    )


def _card(
    whiteboard: WorkWhiteboard,
    department: DepartmentRegistry,
    *,
    title: str = "Strategy intake",
    status: str = "queued",
    priority: str = "normal",
    customer_visible: bool = False,
    approval_task: ApprovalTask | None = None,
    links: dict[str, str] | None = None,
    customer_visible_links: list[str] | None = None,
) -> TaskRoutingRecord:
    safe_links = {
        "run_id": "11111111-1111-1111-1111-111111111111",
        "asset_id": "22222222-2222-2222-2222-222222222222",
        "report_run_id": "33333333-3333-3333-3333-333333333333",
        "evaluation_run_id": "44444444-4444-4444-4444-444444444444",
    }
    if links is not None:
        safe_links = links
    metadata = {
        "whiteboard_id": str(whiteboard.id),
        "title": title,
        "customer_visible": customer_visible,
        "links": safe_links,
    }
    if customer_visible_links is not None:
        metadata["customer_visible_links"] = customer_visible_links
    return TaskRoutingRecord.objects.create(
        organization=whiteboard.organization,
        company=whiteboard.company,
        to_department=department,
        approval_task=approval_task,
        reason=f"{title} because internal request body must stay private.",
        status=status,
        priority=priority,
        due_at=timezone.now() + timedelta(hours=8),
        metadata_json=metadata,
    )


def test_snapshot_groups_task_routing_records_by_department_and_filters_customer_view() -> None:
    org = Organization.objects.create(name="Atlas")
    operator = _user(org, "board-operator@example.com", "owner")
    customer = _user(org, "board-customer@example.com", "viewer")
    company = _company(org, operator)
    _assign(org, company, operator, "member")
    _assign(org, company, customer, "viewer")
    strategy = _department(org, "strategy", department_type="strategy")
    deployment = _department(org, "deployment", department_type="deployment")
    whiteboard = _whiteboard(company, operator)
    internal_card = _card(whiteboard, strategy, title="Internal strategy")
    visible_card = _card(whiteboard, deployment, title="Customer update", customer_visible=True)

    operator_snapshot = build_whiteboard_board_snapshot(whiteboard, user=operator)
    customer_snapshot = build_whiteboard_board_snapshot(whiteboard, user=customer)

    assert operator_snapshot["event_version"] == "whiteboard_board_v1"
    assert operator_snapshot["project"]["project_name"] == company.name
    assert operator_snapshot["project"]["work_status"] == WorkWhiteboard.WORK_STATUS_INTAKE
    assert operator_snapshot["project"]["legacy_status"] == WorkWhiteboard.STATUS_ONBOARDING
    assert operator_snapshot["project"]["ultimate_goal"] == "Launch the project safely."
    assert {lane["department_slug"] for lane in operator_snapshot["lanes"]} == {
        "strategy",
        "deployment",
    }
    assert {card["id"] for card in operator_snapshot["cards"]} == {
        str(internal_card.id),
        str(visible_card.id),
    }
    assert operator_snapshot["cards"][0]["links"]
    assert customer_snapshot["allowed_actions"]["can_view_internal"] is False
    assert [card["id"] for card in customer_snapshot["cards"]] == [str(visible_card.id)]
    assert customer_snapshot["cards"][0]["reason"] == ""
    assert customer_snapshot["cards"][0]["links"] == {}


def test_snapshot_ignores_task_record_projection_without_routing_record() -> None:
    org = Organization.objects.create(name="Atlas")
    owner = _user(org, "board-projection-owner@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    strategy = _department(org, "strategy", department_type="strategy")
    whiteboard = _whiteboard(company, owner)
    run = _run(company, owner)
    lifecycle = TaskLifecycleRecord.objects.create(
        organization=org,
        run=run,
        source_node_id="strategy-node",
        node_type="agent",
        external_key=f"{run.id}:strategy-node",
        title="Projected task",
        status="running",
        priority="normal",
        summary="Projection-only task.",
    )
    projected_task = TaskRecord.objects.create(
        organization=org,
        execution=run,
        lifecycle_task=lifecycle,
        department=strategy,
        source_node_id="strategy-node",
        external_key=f"projection:{run.id}:strategy-node",
        title="Projection-only task",
        status="running",
        priority="normal",
        summary="This must not become a board card.",
    )

    empty_snapshot = build_whiteboard_board_snapshot(whiteboard, user=owner)

    assert empty_snapshot["cards"] == []

    routing_record = TaskRoutingRecord.objects.create(
        organization=org,
        company=company,
        task_lifecycle=lifecycle,
        operation=run,
        to_department=strategy,
        reason="Routing record owns the board card.",
        status="queued",
        metadata_json={
            "whiteboard_id": str(whiteboard.id),
            "title": "Routing-owned card",
        },
    )
    snapshot = build_whiteboard_board_snapshot(whiteboard, user=owner)

    assert [card["routing_record_id"] for card in snapshot["cards"]] == [
        str(routing_record.id)
    ]
    assert str(projected_task.id) not in str(snapshot)


def test_routing_department_can_create_and_reassign_cards_but_other_department_cannot() -> None:
    org = Organization.objects.create(name="Atlas")
    routing_user = _user(org, "board-routing@example.com", "member")
    strategy_user = _user(org, "board-strategy@example.com", "member")
    company = _company(org, routing_user)
    _assign(org, company, routing_user, "member")
    _assign(org, company, strategy_user, "member")
    routing = _department(org, "traffic", department_type="traffic")
    strategy = _department(org, "strategy")
    deployment = _department(org, "deployment")
    _department_member(org, routing, routing_user, "member")
    _department_member(org, strategy, strategy_user, "member")
    whiteboard = _whiteboard(company, routing_user)

    card = create_whiteboard_card(
        user=routing_user,
        whiteboard=whiteboard,
        department_id=strategy.id,
        title="Prepare strategy",
        priority="high",
        idempotency_key="create-strategy",
    )
    duplicate = create_whiteboard_card(
        user=routing_user,
        whiteboard=whiteboard,
        department_id=strategy.id,
        title="Prepare strategy",
        priority="high",
        idempotency_key="create-strategy",
    )

    assert duplicate.id == card.id
    assert card.priority == "high"
    assert_queryset_count(
        TaskRoutingRecord.objects.filter(
            organization=org,
            idempotency_key=f"whiteboard-board:{whiteboard.id}:create:create-strategy",
        ),
        1,
        label="whiteboard create idempotency record",
    )
    assert_queryset_count(
        DomainEventOutbox.objects.filter(event_type="whiteboard.card.created"),
        1,
        label="whiteboard card created events",
    )

    with pytest.raises(WhiteboardBoardError, match="different board mutation"):
        create_whiteboard_card(
            user=routing_user,
            whiteboard=whiteboard,
            department_id=strategy.id,
            title="Prepare strategy with changed body",
            priority="high",
            idempotency_key="create-strategy",
        )

    with pytest.raises(WhiteboardBoardError, match="Only routing"):
        create_whiteboard_card(
            user=strategy_user,
            whiteboard=whiteboard,
            department_id=deployment.id,
            title="Unauthorized structure",
        )

    update_whiteboard_card(
        user=routing_user,
        whiteboard=whiteboard,
        card_id=card.id,
        department_id=deployment.id,
        priority="urgent",
        idempotency_key="route-reassign",
    )
    card.refresh_from_db()
    assert card.to_department_id == deployment.id
    assert card.priority == "urgent"


def test_assigned_department_updates_progress_and_evidence_without_structure_access() -> None:
    org = Organization.objects.create(name="Atlas")
    owner = _user(org, "board-owner@example.com", "owner")
    department_user = _user(org, "board-dept@example.com", "member")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, department_user, "member")
    strategy = _department(org, "strategy")
    deployment = _department(org, "deployment")
    _department_member(org, strategy, department_user, "member")
    whiteboard = _whiteboard(company, owner)
    card = _card(whiteboard, strategy, status="assigned")

    update_whiteboard_card(
        user=department_user,
        whiteboard=whiteboard,
        card_id=card.id,
        status="in_progress",
        idempotency_key="start-card",
    )
    attach_card_evidence(
        user=department_user,
        whiteboard=whiteboard,
        card_id=card.id,
        evidence_type="asset",
        target_id="55555555-5555-5555-5555-555555555555",
        summary="Sanitized evidence reference only.",
        metadata={"raw_evidence": "must drop", "safe": "ok"},
        idempotency_key="evidence-1",
    )
    card.refresh_from_db()

    assert card.status == "in_progress"
    assert card.resolution_json["evidence"][-1]["summary"] == "Sanitized evidence reference only."
    assert "raw_evidence" not in card.resolution_json["evidence"][-1]["metadata"]

    with pytest.raises(WhiteboardBoardError, match="Only routing"):
        update_whiteboard_card(
            user=department_user,
            whiteboard=whiteboard,
            card_id=card.id,
            department_id=deployment.id,
        )


def test_ready_for_review_without_gate_is_department_review_and_can_complete() -> None:
    org = Organization.objects.create(name="Atlas")
    owner = _user(org, "board-review-owner@example.com", "owner")
    department_user = _user(org, "board-review-dept@example.com", "member")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, department_user, "member")
    strategy = _department(org, "strategy")
    _department_member(org, strategy, department_user, "member")
    whiteboard = _whiteboard(company, owner)
    card = _card(
        whiteboard,
        strategy,
        title="Department review",
        status="ready_for_review",
        links={},
    )

    snapshot = build_whiteboard_board_snapshot(whiteboard, user=owner)
    serialized = snapshot["cards"][0]

    assert serialized["review_kind"] == "department"
    assert serialized["review"]["kind"] == "department"
    assert serialized["review"]["department_id"] == str(strategy.id)

    update_whiteboard_card(
        user=department_user,
        whiteboard=whiteboard,
        card_id=card.id,
        status="completed",
    )
    card.refresh_from_db()
    assert card.status == "completed"


def test_human_approval_ready_for_review_requires_approval_or_decision_before_completion() -> None:
    org = Organization.objects.create(name="Atlas")
    owner = _user(org, "board-human-review-owner@example.com", "owner")
    department_user = _user(org, "board-human-review-dept@example.com", "member")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, department_user, "member")
    strategy = _department(org, "strategy")
    _department_member(org, strategy, department_user, "member")
    whiteboard = _whiteboard(company, owner)
    run = _run(company, owner)
    approval = ApprovalTask.objects.create(
        run=run,
        node_id="human-gate",
        assignee=owner,
        status="pending",
        payload={"whiteboard_id": str(whiteboard.id), "prompt": "must not leak"},
    )
    card = _card(
        whiteboard,
        strategy,
        title="Human approval review",
        status="ready_for_review",
        approval_task=approval,
        links={},
    )

    snapshot = build_whiteboard_board_snapshot(whiteboard, user=owner)
    serialized = snapshot["cards"][0]

    assert serialized["review_kind"] == "human_approval"
    assert serialized["review"]["approval_task_id"] == str(approval.id)
    assert serialized["review"]["satisfied"] is False
    assert serialized["links"]["approval_task_id"] == str(approval.id)
    assert "complete" not in serialized["allowed_actions"]

    with pytest.raises(WhiteboardBoardError, match="Human approval"):
        update_whiteboard_card(
            user=department_user,
            whiteboard=whiteboard,
            card_id=card.id,
            status="completed",
        )

    DecisionRecord.objects.create(
        organization=org,
        execution=run,
        decision_type="human_approval",
        status="approved",
        source_approval_task=approval,
        external_key=f"approval:{approval.id}",
        requested_at=timezone.now(),
        resolved_at=timezone.now(),
    )
    update_whiteboard_card(
        user=department_user,
        whiteboard=whiteboard,
        card_id=card.id,
        status="completed",
    )
    card.refresh_from_db()
    assert card.status == "completed"


def test_automated_gate_review_links_evaluation_run_and_customer_hides_internal_details() -> None:
    org = Organization.objects.create(name="Atlas")
    owner = _user(org, "board-auto-review-owner@example.com", "owner")
    customer = _user(org, "board-auto-review-customer@example.com", "viewer")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, customer, "viewer")
    strategy = _department(org, "strategy")
    whiteboard = _whiteboard(company, owner)
    evaluation = EvaluationRun.objects.create(
        organization=org,
        company=company,
        profile_key="project-readiness",
        status="RUNNING",
        created_by=owner,
    )
    EvaluationScorecard.objects.create(
        organization=org,
        company=company,
        evaluation=evaluation,
        composite_score=71.5,
        grade="B",
    )
    _card(
        whiteboard,
        strategy,
        title="Evaluation gate",
        status="ready_for_review",
        customer_visible=True,
        links={"evaluation_run_id": str(evaluation.id)},
    )

    operator_snapshot = build_whiteboard_board_snapshot(whiteboard, user=owner)
    customer_snapshot = build_whiteboard_board_snapshot(whiteboard, user=customer)
    operator_card = operator_snapshot["cards"][0]
    customer_card = customer_snapshot["cards"][0]

    assert operator_card["review_kind"] == "automated_gate"
    assert operator_card["review"]["evaluation_run_id"] == str(evaluation.id)
    assert operator_card["review"]["evaluation_status"] == "RUNNING"
    assert operator_card["review"]["scorecard_id"]
    assert operator_card["links"]["evaluation_run_id"] == str(evaluation.id)
    assert customer_card["review_kind"] == "department"
    assert "evaluation_run_id" not in customer_card["links"]
    assert str(evaluation.id) not in str(customer_card)


def test_customer_visible_approval_review_hides_unmarked_decision_details() -> None:
    org = Organization.objects.create(name="Atlas")
    owner = _user(org, "board-customer-approval-owner@example.com", "owner")
    customer = _user(org, "board-customer-approval-viewer@example.com", "viewer")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, customer, "viewer")
    strategy = _department(org, "strategy")
    whiteboard = _whiteboard(company, owner)
    run = _run(company, owner)
    approval = ApprovalTask.objects.create(
        run=run,
        node_id="human-gate",
        assignee=owner,
        status="approved",
        payload={"whiteboard_id": str(whiteboard.id), "prompt": "must not leak"},
    )
    decision = DecisionRecord.objects.create(
        organization=org,
        execution=run,
        decision_type="human_approval",
        status="approved",
        source_approval_task=approval,
        external_key=f"approval:{approval.id}",
        requested_at=timezone.now(),
        resolved_at=timezone.now(),
    )
    _card(
        whiteboard,
        strategy,
        title="Customer-visible approval gate",
        status="ready_for_review",
        customer_visible=True,
        approval_task=approval,
        links={},
        customer_visible_links=["approval_task_id"],
    )

    customer_snapshot = build_whiteboard_board_snapshot(whiteboard, user=customer)
    customer_card = customer_snapshot["cards"][0]

    assert customer_card["review_kind"] == "human_approval"
    assert customer_card["links"] == {"approval_task_id": str(approval.id)}
    assert customer_card["review"]["approval_task_id"] == str(approval.id)
    assert "decision_record_id" not in customer_card["review"]
    assert str(decision.id) not in str(customer_card)
    assert "must not leak" not in str(customer_card)


def test_customer_visible_evaluation_review_hides_unmarked_scorecard_details() -> None:
    org = Organization.objects.create(name="Atlas")
    owner = _user(org, "board-customer-eval-owner@example.com", "owner")
    customer = _user(org, "board-customer-eval-viewer@example.com", "viewer")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, customer, "viewer")
    strategy = _department(org, "strategy")
    whiteboard = _whiteboard(company, owner)
    evaluation = EvaluationRun.objects.create(
        organization=org,
        company=company,
        profile_key="project-readiness",
        status="PASS",
        created_by=owner,
    )
    scorecard = EvaluationScorecard.objects.create(
        organization=org,
        company=company,
        evaluation=evaluation,
        composite_score=92.0,
        grade="A",
    )
    _card(
        whiteboard,
        strategy,
        title="Customer-visible evaluation gate",
        status="ready_for_review",
        customer_visible=True,
        links={"evaluation_run_id": str(evaluation.id)},
        customer_visible_links=["evaluation_run_id"],
    )

    customer_snapshot = build_whiteboard_board_snapshot(whiteboard, user=customer)
    customer_card = customer_snapshot["cards"][0]

    assert customer_card["review_kind"] == "automated_gate"
    assert customer_card["links"] == {"evaluation_run_id": str(evaluation.id)}
    assert customer_card["review"]["evaluation_run_id"] == str(evaluation.id)
    assert "scorecard_id" not in customer_card["review"]
    assert str(scorecard.id) not in str(customer_card)


def test_invalid_stale_and_idempotency_conflict_updates_are_rejected() -> None:
    org = Organization.objects.create(name="Atlas")
    owner = _user(org, "board-conflict-owner@example.com", "owner")
    department_user = _user(org, "board-conflict-dept@example.com", "member")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, department_user, "member")
    strategy = _department(org, "strategy")
    _department_member(org, strategy, department_user, "member")
    whiteboard = _whiteboard(company, owner)
    card = _card(whiteboard, strategy, status="assigned")

    with pytest.raises(WhiteboardBoardError, match="Assigned departments cannot"):
        update_whiteboard_card(
            user=department_user,
            whiteboard=whiteboard,
            card_id=card.id,
            status="completed",
        )

    with pytest.raises(WhiteboardBoardError, match="updated by another writer"):
        update_whiteboard_card(
            user=department_user,
            whiteboard=whiteboard,
            card_id=card.id,
            status="in_progress",
            expected_updated_at="2020-01-01T00:00:00+00:00",
        )

    update_whiteboard_card(
        user=department_user,
        whiteboard=whiteboard,
        card_id=card.id,
        status="in_progress",
        idempotency_key="same-key",
    )
    update_whiteboard_card(
        user=department_user,
        whiteboard=whiteboard,
        card_id=card.id,
        status="in_progress",
        idempotency_key="same-key",
    )
    with pytest.raises(WhiteboardBoardError, match="different board mutation"):
        update_whiteboard_card(
            user=department_user,
            whiteboard=whiteboard,
            card_id=card.id,
            status="blocked",
            blocker_reason="Waiting on sanitized input.",
            idempotency_key="same-key",
        )


def test_redis_snapshot_rebuilds_from_db_and_events_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache.clear()
    monkeypatch.setattr(
        "application.services.whiteboard_boards._use_cache_snapshot_store", lambda: True
    )
    org = Organization.objects.create(name="Atlas")
    owner = _user(org, "board-redis-owner@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    routing = _department(org, "routing", department_type="routing")
    strategy = _department(org, "strategy")
    _department_member(org, routing, owner, "lead")
    whiteboard = _whiteboard(company, owner)

    card = create_whiteboard_card(
        user=owner,
        whiteboard=whiteboard,
        department_id=strategy.id,
        title="No raw body",
        reason="Safe board reason",
        links={
            "communication_message_id": "66666666-6666-6666-6666-666666666666",
            "raw_prompt": "must not persist",
        },
        idempotency_key="redis-event",
    )
    snapshot = rebuild_whiteboard_board_snapshot_from_db(whiteboard.id)
    cached = cache.get(whiteboard_board_snapshot_key(whiteboard))
    outbox = DomainEventOutbox.objects.filter(event_type="whiteboard.card.created").latest(
        "created_at"
    )

    assert snapshot is not None
    assert snapshot["whiteboard_id"] == str(whiteboard.id)
    assert cached
    assert str(card.id) in cached
    assert outbox.topic == "forgegraph.whiteboard.board.events.v1"
    assert outbox.schema_version == "whiteboard_board_event_v1"
    payload_text = str(outbox.payload_json).lower()
    assert outbox.payload_json["whiteboard_id"] == str(whiteboard.id)
    assert outbox.payload_json["routing_record_id"] == str(card.id)
    assert "raw_prompt" not in payload_text
    assert "safe board reason" not in payload_text


def test_other_client_cards_are_excluded_by_company_scope() -> None:
    org = Organization.objects.create(name="Atlas")
    owner = _user(org, "board-scope-owner@example.com", "owner")
    company = _company(org, owner)
    other_company = _company(org, owner, name="Other Client")
    _assign(org, company, owner, "member")
    _assign(org, other_company, owner, "member")
    strategy = _department(org, "strategy")
    whiteboard = _whiteboard(company, owner)
    _card(whiteboard, strategy)
    TaskRoutingRecord.objects.create(
        organization=org,
        company=other_company,
        to_department=strategy,
        reason="Wrong company card",
        metadata_json={"whiteboard_id": str(whiteboard.id), "title": "Wrong company"},
    )

    snapshot = build_whiteboard_board_snapshot(whiteboard, user=owner)

    assert [card["title"] for card in snapshot["cards"]] == ["Strategy intake"]
