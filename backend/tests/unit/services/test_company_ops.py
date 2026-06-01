from __future__ import annotations

from decimal import Decimal
from typing import cast

import pytest

from application.services.company_ops import (
    build_company_ops_context_pack,
    create_company_signal,
    create_procurement_draft,
    create_publication_draft,
    evaluate_company_operation_objective,
    launch_company_operation,
    qualify_signal,
    request_procurement_approval,
    request_publication_approval,
    trigger_paid_order_follow_up,
)
from application.services.inventory import create_order_shell, create_reservation
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    ApprovalTask,
    CommercePayment,
    CompanyOperationObjective,
    CompanyOpportunity,
    CompanySignal,
    Graph,
    GraphVersion,
    InventoryOrderShell,
    InventoryProduct,
    InventoryStockUnit,
    Organization,
    PublicationDraft,
    Run,
    User,
)

pytestmark = pytest.mark.django_db


def _create_company(user: User, *, name: str = "Operating Loop Test Company") -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description="Company ops test company.",
        ),
    )
    GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return company


def _organization(company: Graph) -> Organization:
    organization = company.organization
    assert organization is not None
    return organization


def _create_product(company: Graph, *, quantity: int = 2) -> InventoryProduct:
    product = InventoryProduct.objects.create(
        organization=_organization(company),
        company=company,
        sku="SKU-1",
        model="Model 1",
        name="Model 1",
        price_amount=Decimal("700.00"),
        cost_amount=Decimal("350.00"),
        price_mxn=Decimal("700.00"),
        cost_mxn=Decimal("350.00"),
    )
    for unit_number in range(1, quantity + 1):
        InventoryStockUnit.objects.create(
            organization=_organization(company),
            company=company,
            product=product,
            unit_number=unit_number,
            status="available",
        )
    return product


def _paid_order(company: Graph, user: User) -> InventoryOrderShell:
    product = _create_product(company)
    reservation = create_reservation(
        company=company,
        product_id=str(product.id),
        actor=user,
        idempotency_key="reserve-paid",
    )
    order = create_order_shell(
        reservation=reservation,
        actor=user,
        idempotency_key="order-paid",
    )
    order.status = "paid"
    order.customer_email = "buyer@example.com"
    order.customer_name = "Private Buyer"
    order.shipping_json = {"street": "Private Street 123", "city": "CDMX"}
    order.save(
        update_fields=["status", "customer_email", "customer_name", "shipping_json", "updated_at"]
    )
    CommercePayment.objects.create(
        organization=_organization(company),
        company=company,
        reservation=reservation,
        order=order,
        product=product,
        requested_by=user,
        status="succeeded",
        amount_mxn=Decimal("700.00"),
        currency="mxn",
        quantity=1,
        stripe_session_id="cs_private",
        stripe_payment_intent_id="pi_private",
        checkout_url="https://checkout.stripe.test/private",
        customer_email="buyer@example.com",
        customer_name="Private Buyer",
        shipping_json={"street": "Private Street 123"},
    )
    return order


def test_company_signal_creation_is_idempotent_by_source_external_key(user):
    company = _create_company(user)

    first = create_company_signal(
        company=company,
        actor=user,
        signal_type="demand",
        source="manual",
        external_key="dm-1",
        title="Buyer asked about SKU",
    )
    second = create_company_signal(
        company=company,
        actor=user,
        signal_type="demand",
        source="manual",
        external_key="dm-1",
        title="Different title should not duplicate",
    )

    assert second.id == first.id
    assert CompanySignal.objects.filter(company=company).count() == 1


def test_company_signal_persists_explicit_generic_semantics(user):
    company = _create_company(user)

    signal = create_company_signal(
        company=company,
        actor=user,
        signal_type="manual",
        signal_kind="capability_gap",
        domain_context="connector",
        source="manual",
        external_key="capability-gap-1",
        title="Connector missing",
    )

    assert signal.signal_kind == "capability_gap"
    assert signal.domain_context == "connector"


def test_legacy_signal_type_derives_generic_semantics(user):
    company = _create_company(user)

    signal = create_company_signal(
        company=company,
        actor=user,
        signal_type="stockout",
        source="manual",
        external_key="legacy-stockout-1",
        title="Legacy compatibility signal",
    )

    assert signal.signal_kind == "risk"
    assert signal.domain_context == "inventory"


def test_qualify_signal_creates_one_opportunity(user):
    company = _create_company(user)
    signal = create_company_signal(
        company=company,
        actor=user,
        signal_type="lead",
        source="manual",
        external_key="lead-1",
        title="Qualified interest",
    )

    first = qualify_signal(signal=signal, actor=user, next_action="Follow up")
    second = qualify_signal(signal=signal, actor=user, next_action="Do not duplicate")

    signal.refresh_from_db()
    assert first.id == second.id
    assert signal.status == "qualified"
    assert CompanyOpportunity.objects.filter(company=company).count() == 1


def test_company_ops_context_pack_excludes_private_order_fields(user):
    company = _create_company(user)
    _paid_order(company, user)

    context_pack = build_company_ops_context_pack(
        company=company,
        operation_type="paid_order_follow_up",
    )
    serialized = str(context_pack.scope_json)

    assert "buyer@example.com" not in serialized
    assert "Private Street" not in serialized
    assert "cs_private" not in serialized
    assert "pi_private" not in serialized
    assert "checkout.stripe" not in serialized


def test_publication_draft_requires_human_approval_before_approved(user):
    company = _create_company(user)
    draft = create_publication_draft(
        company=company,
        actor=user,
        idempotency_key="pub-1",
        title="Content draft",
        body="Draft copy.",
    )

    requested = request_publication_approval(draft=draft, actor=user)
    duplicate = request_publication_approval(draft=requested, actor=user)

    assert requested.status == "approval_requested"
    assert duplicate.approval_task_id == requested.approval_task_id
    assert PublicationDraft.objects.get(id=draft.id).status != "approved"
    assert ApprovalTask.objects.filter(run=requested.origin_operation).count() == 1


def test_procurement_draft_cannot_become_approved_without_approval(user):
    company = _create_company(user)
    product = _create_product(company)
    draft = create_procurement_draft(
        company=company,
        actor=user,
        idempotency_key="proc-1",
        title="Reorder draft",
        budget_amount=Decimal("1000.00"),
        lines=[
            {
                "product_id": str(product.id),
                "quantity": 3,
                "unit_cost_amount": "100.00",
            }
        ],
    )

    requested = request_procurement_approval(draft=draft, actor=user)
    duplicate = request_procurement_approval(draft=requested, actor=user)

    assert requested.status == "approval_requested"
    assert duplicate.approval_task_id == requested.approval_task_id
    assert requested.lines.count() == 1
    assert requested.status != "approved"


def test_paid_order_follow_up_trigger_is_idempotent(user):
    company = _create_company(user)
    order = _paid_order(company, user)

    first_signal, first_run = trigger_paid_order_follow_up(order=order, actor=user)
    second_signal, second_run = trigger_paid_order_follow_up(order=order, actor=user)

    assert second_signal.id == first_signal.id
    assert second_run.id == first_run.id
    assert first_signal.signal_kind == "milestone"
    assert first_signal.domain_context == "commerce"
    assert first_run.company_objective.operation_family == "follow_up"
    assert first_run.company_objective.domain_context == "commerce"
    assert CompanySignal.objects.filter(company=company, signal_type="paid_order").count() == 1
    assert Run.objects.filter(graph_version__graph=company).count() == 1


def test_company_operation_launch_records_objective_contract(user):
    company = _create_company(user)
    _create_product(company)

    run = launch_company_operation(
        company=company,
        actor=user,
        operation_type="daily_operating_brief",
        run_type="rehearsal",
    )

    objective = CompanyOperationObjective.objects.get(operation=run)
    context_pack = run.context_packs.get()

    assert objective.run_type == "rehearsal"
    assert objective.operation_family == "brief"
    assert objective.domain_context == "general"
    assert "backend-owned company context" in objective.run_goal
    assert "sell-through" not in objective.run_goal.lower()
    assert len(objective.action_plan_json) == 7
    assert objective.action_plan_json[0]["department"] == "Routing Department"
    assert "without executing" in objective.action_plan_json[0]["responsibility"]
    assert "state_drift" in objective.integrity_gates_json
    assert run.input_json["company_ops_objective_id"] == str(objective.id)
    assert run.input_json["operation_family"] == "brief"
    assert context_pack.scope_json["objective_contract"]["run_goal"] == objective.run_goal


def test_objective_evaluation_records_score_miss_and_next_decision(user):
    company = _create_company(user)
    run = launch_company_operation(
        company=company,
        actor=user,
        operation_type="content_drop_planning",
    )
    objective = CompanyOperationObjective.objects.get(operation=run)

    evaluated = evaluate_company_operation_objective(
        objective=objective,
        success_score=82,
        miss_analysis="Draft direction was useful but no buyer-facing demand was tested.",
        next_decision="Run a rehearsal content drop review before publishing.",
        integrity_gates={"state_drift": {"observed": 0, "status": "pass"}},
    )

    assert evaluated.status == "evaluated"
    assert evaluated.success_score == 82
    assert "rehearsal content" in evaluated.next_decision
    assert evaluated.integrity_gates_json["state_drift"]["status"] == "pass"
