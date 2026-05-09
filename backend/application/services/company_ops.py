"""Generic company operating-loop services."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, cast

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from application.services.company_archive import context_pack_payload
from application.services.interaction import current_brief_payload
from application.services.run_state_machine import create_backend_owned_run, merge_run_input_json
from application.services.stock_state import stock_state_summary_for_products
from application.services.task_lifecycle import (
    create_backend_approval_task,
    initialize_lifecycle_tasks_for_run,
)
from infrastructure.orm.models import (
    Asset,
    CommerceCashLedgerEntry,
    CommerceFulfillment,
    CommercePayment,
    CommerceProcurementDraft,
    CommerceProcurementDraftLine,
    CompanyOperationObjective,
    CompanyOpportunity,
    CompanySignal,
    ContextPack,
    DecisionRecord,
    Graph,
    GraphVersion,
    InventoryOrderShell,
    InventoryProduct,
    MediaGenerationJob,
    Organization,
    PolicyRule,
    PublicationDraft,
    Run,
    User,
)

OPERATION_TEMPLATES = {
    "daily_operating_brief": "Review current company state and produce the next operating brief.",
    "content_drop_planning": "Draft a content drop plan from current inventory, media, demand, and policies.",
    "paid_order_follow_up": "Prepare safe follow-up work for a paid order without exposing private buyer data.",
    "fulfillment_exception_review": "Review a fulfillment issue and propose the next operator-safe action.",
    "sold_out_demand_capture": "Capture sold-out demand and summarize reorder evidence.",
    "reorder_procurement_approval": "Draft a procurement recommendation and request human approval.",
}

SELL_THROUGH_LEARNING_OBJECTIVE = (
    "Turn limited inventory into validated sell-through learning while preserving "
    "stock, cash, approval, and customer-data integrity."
)

FIRST_REHEARSAL_GOAL = (
    "Produce the first sell-through operating brief from real inventory, identify "
    "the best first drop, generate draft content direction, surface stock/cash/"
    "reorder risks, and define the next action without touching real buyers."
)

DEFAULT_INTEGRITY_GATES: dict[str, dict[str, str | int]] = {
    "stock_drift": {"target": 0, "status": "pending"},
    "duplicate_reservation_order_cash": {"target": 0, "status": "pending"},
    "private_data_to_gemini": {"target": 0, "status": "pending"},
    "ungated_publication_or_procurement": {"target": 0, "status": "pending"},
    "raw_log_dependency": {"target": 0, "status": "pending"},
}

DEPARTMENT_OBJECTIVE_ACTION_PLAN: list[dict[str, str]] = [
    {
        "department": "Operating System",
        "responsibility": "Frame the run goal, score success, explain misses, and choose the next decision.",
    },
    {
        "department": "Content Studio",
        "responsibility": "Turn inventory and scarcity into draft content direction and media-safe briefs.",
    },
    {
        "department": "Social Desk",
        "responsibility": "Prepare publication and demand-capture work without external posting by default.",
    },
    {
        "department": "Sales Desk",
        "responsibility": "Translate demand into qualified opportunities and safe checkout follow-up work.",
    },
    {
        "department": "Ops & Inventory",
        "responsibility": "Protect stock truth, reservations, fulfillment visibility, and stockout evidence.",
    },
    {
        "department": "Finance & Procurement",
        "responsibility": "Explain cash/reorder implications and draft human-gated procurement work when justified.",
    },
]


class CompanyOpsError(ValueError):
    """Domain error for company operating-loop commands."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def company_ops_overview_payload(company: Graph) -> dict[str, Any]:
    """Return business-neutral operating-loop state for the company workspace."""

    signals = _signals_queryset(company)
    opportunities = _opportunities_queryset(company)
    publication_drafts = _publication_drafts_queryset(company)
    procurement_drafts = _procurement_drafts_queryset(company)
    objective_contracts = _operation_objectives_queryset(company)
    policies = PolicyRule.objects.filter(company=company).order_by("-updated_at")[:20]
    decisions = _decision_queryset(company)[:20]
    orders = InventoryOrderShell.objects.filter(company=company)
    paid_orders = orders.filter(status="paid")
    stuck_orders = orders.filter(status__in=["payment_expired", "payment_review_required"])
    cash_total = CommerceCashLedgerEntry.objects.filter(
        company=company, entry_type="sale"
    ).aggregate(total=Sum("amount_mxn"))["total"] or Decimal("0.00")
    stock_state_products = list(
        InventoryProduct.objects.filter(company=company)
        .annotate(
            available_units=Count("stock_units", filter=Q(stock_units__status="available")),
            held_units=Count("stock_units", filter=Q(stock_units__status="reserved")),
            sold_units=Count("stock_units", filter=Q(stock_units__status="sold")),
        )
        .order_by("model", "sku")
    )
    stock_state_summary = stock_state_summary_for_products(stock_state_products)
    return {
        "company_id": str(company.id),
        "generated_at": timezone.now().isoformat(),
        "summary": {
            "signals_new": signals.filter(status="new").count(),
            "signals_qualified": signals.filter(status="qualified").count(),
            "opportunities_open": opportunities.exclude(status__in=["converted", "lost"]).count(),
            "publication_drafts": publication_drafts.exclude(
                status__in=["published", "cancelled"]
            ).count(),
            "procurement_drafts": procurement_drafts.exclude(
                status__in=["ordered", "cancelled"]
            ).count(),
            "paid_orders": paid_orders.count(),
            "stuck_orders": stuck_orders.count(),
            "low_stock_products": int(stock_state_summary["low_stock_count"]),
            "cash_sales_mxn": str(Decimal(cash_total).quantize(Decimal("0.01"))),
        },
        "stock_state_summary": stock_state_summary,
        "recommended_operations": recommended_operations(company),
        "signals": [company_signal_payload(signal) for signal in signals[:20]],
        "opportunities": [
            company_opportunity_payload(opportunity) for opportunity in opportunities[:20]
        ],
        "publication_drafts": [
            publication_draft_payload(draft) for draft in publication_drafts[:20]
        ],
        "procurement_drafts": [
            procurement_draft_payload(draft) for draft in procurement_drafts[:20]
        ],
        "objective_contracts": [
            operation_objective_payload(contract) for contract in objective_contracts[:20]
        ],
        "recent_decisions": [_decision_payload(decision) for decision in decisions],
        "policies": [_policy_payload(policy) for policy in policies],
    }


def recommended_operations(company: Graph) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = [
        {
            "operation_type": "daily_operating_brief",
            "label": "Daily operating brief",
            "reason": "Refresh the company state and decide the next move.",
        }
    ]
    if CompanySignal.objects.filter(company=company, signal_type="stockout").exists():
        recommendations.append(
            {
                "operation_type": "sold_out_demand_capture",
                "label": "Sold-out demand capture",
                "reason": "Stockout signals can become reorder evidence.",
            }
        )
    if InventoryOrderShell.objects.filter(company=company, status="paid").exists():
        recommendations.append(
            {
                "operation_type": "paid_order_follow_up",
                "label": "Paid-order follow-up",
                "reason": "Paid orders need safe follow-through and learnings.",
            }
        )
    if CommerceFulfillment.objects.filter(company=company, status="blocked").exists():
        recommendations.append(
            {
                "operation_type": "fulfillment_exception_review",
                "label": "Fulfillment exception review",
                "reason": "Blocked fulfillment needs an operator-visible resolution.",
            }
        )
    if PublicationDraft.objects.filter(company=company, status="draft").exists():
        recommendations.append(
            {
                "operation_type": "content_drop_planning",
                "label": "Content drop planning",
                "reason": "Draft content is ready for review and packaging.",
            }
        )
    if CompanySignal.objects.filter(company=company, status="qualified").exists():
        recommendations.append(
            {
                "operation_type": "reorder_procurement_approval",
                "label": "Procurement approval",
                "reason": "Qualified demand can support a human-gated procurement draft.",
            }
        )
    return recommendations[:6]


def create_company_signal(
    *,
    company: Graph,
    actor: User | None = None,
    signal_type: str,
    title: str,
    summary: str = "",
    source: str = "manual",
    external_key: str = "",
    channel: str = "",
    contact_alias: str = "",
    product_id: str | None = None,
    order_id: str | None = None,
    fulfillment_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> CompanySignal:
    """Create or replay a sanitized company signal."""

    _assert_choice(signal_type, dict(CompanySignal.SIGNAL_TYPE_CHOICES), "signal_type")
    organization = _organization_for_company(company)
    product = _resolve_product(company=company, product_id=product_id)
    order = _resolve_order(company=company, order_id=order_id)
    fulfillment = _resolve_fulfillment(company=company, fulfillment_id=fulfillment_id)
    clean_source = _clean_key(source or "manual", limit=64)
    clean_external_key = _safe_text(external_key, limit=255)
    defaults = {
        "organization": organization,
        "created_by": actor,
        "product": product,
        "order": order,
        "fulfillment": fulfillment,
        "signal_type": signal_type,
        "status": "new",
        "title": _safe_text(title or signal_type.replace("_", " ").title(), limit=255),
        "summary": _safe_text(summary, limit=2000),
        "channel": _safe_text(channel, limit=64),
        "contact_alias": _safe_text(contact_alias, limit=120),
        "metadata_json": _sanitized_metadata(metadata or {}),
        "occurred_at": timezone.now(),
    }
    if clean_external_key:
        signal, created = CompanySignal.objects.get_or_create(
            company=company,
            source=clean_source,
            external_key=clean_external_key,
            defaults=defaults,
        )
        if not created:
            return signal
        return signal
    return CompanySignal.objects.create(
        company=company,
        source=clean_source,
        external_key="",
        **defaults,
    )


def qualify_signal(
    *,
    signal: CompanySignal,
    actor: User | None = None,
    title: str = "",
    summary: str = "",
    next_action: str = "",
) -> CompanyOpportunity:
    """Convert a signal into one qualified opportunity exactly once."""

    _assert_company(signal.company)
    with transaction.atomic():
        signal = (
            CompanySignal.objects.select_for_update().select_related("company").get(id=signal.id)
        )
        external_key = f"signal:{signal.id}"
        opportunity, _ = CompanyOpportunity.objects.get_or_create(
            company=signal.company,
            external_key=external_key,
            defaults={
                "organization": signal.organization,
                "signal": signal,
                "product": signal.product,
                "order": signal.order,
                "owner_user": actor,
                "status": "qualified",
                "title": _safe_text(title or signal.title, limit=255),
                "summary": _safe_text(summary or signal.summary, limit=2000),
                "contact_alias": signal.contact_alias,
                "channel": signal.channel,
                "estimated_value_amount": _estimated_value_for_signal(signal),
                "currency": _currency_for_signal(signal),
                "next_action": _safe_text(next_action, limit=255),
                "metadata_json": {"source_signal_id": str(signal.id)},
            },
        )
        if signal.status == "new":
            signal.status = "qualified"
            signal.save(update_fields=["status", "updated_at"])
        return opportunity


def update_opportunity_status(
    *,
    opportunity: CompanyOpportunity,
    status: str,
    next_action: str = "",
) -> CompanyOpportunity:
    _assert_choice(status, dict(CompanyOpportunity.STATUS_CHOICES), "status")
    opportunity.status = status
    if next_action:
        opportunity.next_action = _safe_text(next_action, limit=255)
    opportunity.save(update_fields=["status", "next_action", "updated_at"])
    return opportunity


def create_publication_draft(
    *,
    company: Graph,
    actor: User | None,
    idempotency_key: str,
    title: str,
    channel: str = "",
    audience: str = "",
    body: str = "",
    call_to_action: str = "",
    signal_id: str | None = None,
    opportunity_id: str | None = None,
    asset_id: str | None = None,
    asset_version_id: str | None = None,
    media_job_id: str | None = None,
) -> PublicationDraft:
    if not idempotency_key:
        raise CompanyOpsError("idempotency_key_required", "Idempotency-Key is required.")
    signal = _resolve_signal(company=company, signal_id=signal_id)
    opportunity = _resolve_opportunity(company=company, opportunity_id=opportunity_id)
    asset = _resolve_asset(company=company, asset_id=asset_id)
    asset_version = _resolve_asset_version(asset=asset, asset_version_id=asset_version_id)
    media_job = _resolve_media_job(company=company, media_job_id=media_job_id)
    draft, _ = PublicationDraft.objects.get_or_create(
        company=company,
        idempotency_key=idempotency_key,
        defaults={
            "organization": _organization_for_company(company),
            "signal": signal,
            "opportunity": opportunity,
            "requested_by": actor,
            "asset": asset,
            "asset_version": asset_version,
            "media_job": media_job,
            "title": _safe_text(title, limit=255),
            "channel": _safe_text(channel, limit=64),
            "audience": _safe_text(audience, limit=255),
            "body": _safe_text(body, limit=5000),
            "call_to_action": _safe_text(call_to_action, limit=255),
            "status": "draft",
            "metadata_json": {},
        },
    )
    return draft


def request_publication_approval(
    *,
    draft: PublicationDraft,
    actor: User | None,
    note: str = "",
) -> PublicationDraft:
    if draft.status in {"approved", "published"}:
        return draft
    with transaction.atomic():
        draft = (
            PublicationDraft.objects.select_for_update().select_related("company").get(id=draft.id)
        )
        if draft.approval_task_id:
            return draft
        run = launch_company_operation(
            company=draft.company,
            actor=actor,
            operation_type="content_drop_planning",
            context_note=note or f"Review publication draft {draft.title}.",
        )
        approval = create_backend_approval_task(
            run=run,
            node_id="publication-approval",
            assignee=actor,
            status="pending",
            payload={
                "approval_type": "publication_draft",
                "publication_draft_id": str(draft.id),
                "title": draft.title,
                "channel": draft.channel,
                "body": draft.body,
                "call_to_action": draft.call_to_action,
                "note": _safe_text(note, limit=1000),
            },
        )
        DecisionRecord.objects.get_or_create(
            organization=draft.organization,
            external_key=f"publication:{draft.id}:approval",
            defaults={
                "execution": run,
                "decision_type": "human_approval",
                "status": "pending",
                "source_approval_task": approval,
                "context_json": {
                    "publication_draft_id": str(draft.id),
                    "title": draft.title,
                    "channel": draft.channel,
                },
                "requested_at": timezone.now(),
            },
        )
        draft.origin_operation = run
        draft.approval_task = approval
        draft.status = "approval_requested"
        draft.save(update_fields=["origin_operation", "approval_task", "status", "updated_at"])
        return draft


def create_procurement_draft(
    *,
    company: Graph,
    actor: User | None,
    idempotency_key: str,
    title: str,
    rationale: str = "",
    budget_amount: Decimal | str | int = Decimal("0.00"),
    currency: str = "mxn",
    lines: list[dict[str, Any]] | None = None,
) -> CommerceProcurementDraft:
    if not idempotency_key:
        raise CompanyOpsError("idempotency_key_required", "Idempotency-Key is required.")
    organization = _organization_for_company(company)
    with transaction.atomic():
        draft, created = CommerceProcurementDraft.objects.get_or_create(
            company=company,
            idempotency_key=idempotency_key,
            defaults={
                "organization": organization,
                "requested_by": actor,
                "title": _safe_text(title, limit=255),
                "rationale": _safe_text(rationale, limit=5000),
                "budget_amount": _decimal_value(budget_amount),
                "currency": _clean_key(currency or "mxn", limit=8),
                "status": "draft",
                "metadata_json": {},
            },
        )
        if created:
            for line in lines or []:
                product = _resolve_product(company=company, product_id=line.get("product_id"))
                CommerceProcurementDraftLine.objects.create(
                    draft=draft,
                    product=product,
                    sku=_safe_text(line.get("sku") or getattr(product, "sku", ""), limit=128),
                    description=_safe_text(
                        line.get("description") or getattr(product, "model", ""), limit=255
                    ),
                    quantity=max(1, int(line.get("quantity") or 1)),
                    unit_cost_amount=_decimal_value(line.get("unit_cost_amount") or 0),
                    currency=_clean_key(line.get("currency") or draft.currency, limit=8),
                    metadata_json=_sanitized_metadata(line.get("metadata") or {}),
                )
        return draft


def request_procurement_approval(
    *,
    draft: CommerceProcurementDraft,
    actor: User | None,
    note: str = "",
) -> CommerceProcurementDraft:
    if draft.status in {"approved", "ordered"}:
        return draft
    with transaction.atomic():
        draft = (
            CommerceProcurementDraft.objects.select_for_update()
            .select_related("company")
            .prefetch_related("lines")
            .get(id=draft.id)
        )
        if draft.approval_task_id:
            return draft
        run = launch_company_operation(
            company=draft.company,
            actor=actor,
            operation_type="reorder_procurement_approval",
            context_note=note or f"Review procurement draft {draft.title}.",
        )
        approval = create_backend_approval_task(
            run=run,
            node_id="procurement-approval",
            assignee=actor,
            status="pending",
            payload={
                "approval_type": "procurement_draft",
                "procurement_draft_id": str(draft.id),
                "title": draft.title,
                "rationale": draft.rationale,
                "budget_amount": str(draft.budget_amount),
                "currency": draft.currency,
                "lines": [procurement_line_payload(line) for line in draft.lines.all()],
                "note": _safe_text(note, limit=1000),
            },
        )
        DecisionRecord.objects.get_or_create(
            organization=draft.organization,
            external_key=f"procurement:{draft.id}:approval",
            defaults={
                "execution": run,
                "decision_type": "human_approval",
                "status": "pending",
                "source_approval_task": approval,
                "context_json": {
                    "procurement_draft_id": str(draft.id),
                    "title": draft.title,
                    "budget_amount": str(draft.budget_amount),
                    "currency": draft.currency,
                },
                "requested_at": timezone.now(),
            },
        )
        draft.origin_operation = run
        draft.approval_task = approval
        draft.status = "approval_requested"
        draft.save(update_fields=["origin_operation", "approval_task", "status", "updated_at"])
        return draft


def build_operation_objective_contract(
    *,
    operation_type: str,
    run_type: str = "rehearsal",
    run_goal: str = "",
    hypothesis: str = "",
    target_signal: str = "",
) -> dict[str, Any]:
    """Return a sanitized objective contract for a company operation."""

    _assert_choice(operation_type, OPERATION_TEMPLATES, "operation_type")
    _assert_choice(run_type, dict(CompanyOperationObjective.RUN_TYPE_CHOICES), "run_type")
    return {
        "run_type": run_type,
        "run_goal": _safe_text(
            run_goal or _default_run_goal(operation_type=operation_type, run_type=run_type),
            limit=2000,
        ),
        "hypothesis": _safe_text(
            hypothesis or _default_hypothesis(operation_type=operation_type),
            limit=2000,
        ),
        "target_signal": _safe_text(
            target_signal
            or _default_target_signal(operation_type=operation_type, run_type=run_type),
            limit=2000,
        ),
        "action_plan_json": [
            {
                "department": _safe_text(item["department"], limit=120),
                "responsibility": _safe_text(item["responsibility"], limit=500),
            }
            for item in DEPARTMENT_OBJECTIVE_ACTION_PLAN
        ],
        "integrity_gates_json": _sanitized_metadata(DEFAULT_INTEGRITY_GATES),
    }


def evaluate_company_operation_objective(
    *,
    objective: CompanyOperationObjective,
    success_score: int,
    miss_analysis: str,
    next_decision: str,
    integrity_gates: dict[str, Any] | None = None,
) -> CompanyOperationObjective:
    """Record objective evaluation for a completed or reviewed company operation."""

    if success_score < 0 or success_score > 100:
        raise CompanyOpsError(
            "invalid_success_score",
            "success_score must be between 0 and 100.",
        )
    objective.success_score = success_score
    objective.miss_analysis = _safe_text(miss_analysis, limit=3000)
    objective.next_decision = _safe_text(next_decision, limit=1000)
    if integrity_gates is not None:
        objective.integrity_gates_json = _sanitized_metadata(integrity_gates)
    objective.status = "evaluated"
    objective.evaluated_at = timezone.now()
    objective.save(
        update_fields=[
            "success_score",
            "miss_analysis",
            "next_decision",
            "integrity_gates_json",
            "status",
            "evaluated_at",
            "updated_at",
        ]
    )
    DecisionRecord.objects.get_or_create(
        organization=objective.organization,
        external_key=f"objective:{objective.id}:evaluation",
        defaults={
            "execution": objective.operation,
            "decision_type": "objective_evaluation",
            "status": "resolved",
            "context_json": operation_objective_payload(objective),
            "resolution_json": {
                "success_score": success_score,
                "next_decision": objective.next_decision,
            },
            "requested_at": objective.created_at,
            "resolved_at": objective.evaluated_at,
        },
    )
    return objective


def launch_company_operation(
    *,
    company: Graph,
    actor: User | None,
    operation_type: str,
    source_signal: CompanySignal | None = None,
    context_note: str = "",
    run_type: str = "rehearsal",
    run_goal: str = "",
    hypothesis: str = "",
    target_signal: str = "",
) -> Run:
    """Create an inspectable company operation run with a backend-owned context pack."""

    _assert_choice(operation_type, OPERATION_TEMPLATES, "operation_type")
    _assert_choice(
        run_type,
        dict(CompanyOperationObjective.RUN_TYPE_CHOICES),
        "run_type",
    )
    organization = _organization_for_company(company)
    if source_signal is not None and source_signal.operation_id:
        return cast(Run, source_signal.operation)
    graph_version = GraphVersion.objects.filter(graph=company).order_by("-version").first()
    if graph_version is None:
        raise CompanyOpsError(
            "graph_version_missing",
            "Company operations require a graph version to launch work.",
        )
    objective_contract = build_operation_objective_contract(
        operation_type=operation_type,
        run_type=run_type,
        run_goal=run_goal,
        hypothesis=hypothesis,
        target_signal=target_signal,
    )
    context_pack = build_company_ops_context_pack(
        company=company,
        operation_type=operation_type,
        context_note=context_note,
        objective_contract=objective_contract,
    )
    input_json = {
        "company_name": company.name,
        "operation_type": operation_type,
        "operation_brief": OPERATION_TEMPLATES[operation_type],
        "company_ops_context_pack_id": str(context_pack.id),
        "objective_contract": _objective_contract_input_payload(objective_contract),
        "company_ops": {
            "operation_type": operation_type,
            "source_signal_id": str(source_signal.id) if source_signal else None,
            "context_note": _safe_text(context_note, limit=1000),
            "run_type": run_type,
        },
    }
    dispatch_graph_json = dict(graph_version.graph_json or {})
    metadata = dict(dispatch_graph_json.get("metadata") or {})
    metadata["context_pack_id"] = str(context_pack.id)
    metadata["context_pack"] = context_pack_payload(context_pack)
    metadata["company_ops_operation_type"] = operation_type
    metadata["objective_contract"] = _objective_contract_input_payload(objective_contract)
    dispatch_graph_json["metadata"] = metadata
    run = create_backend_owned_run(
        owner=actor or company.owner,
        organization=organization,
        graph_version=graph_version,
        status="pending",
        started_at=timezone.now(),
        input_json=input_json,
        dispatch_graph_json=dispatch_graph_json,
        output_json=None,
        error_message="",
    )
    objective = CompanyOperationObjective.objects.create(
        organization=organization,
        company=company,
        operation=run,
        source_signal=source_signal,
        created_by=actor,
        **objective_contract,
    )
    run = merge_run_input_json(run, {"company_ops_objective_id": str(objective.id)})
    context_pack.operation = run
    context_pack.save(update_fields=["operation"])
    initialize_lifecycle_tasks_for_run(
        run,
        source="company_ops",
        initial_status="created",
        reason="company operating-loop operation created",
    )
    if source_signal is not None:
        source_signal.operation = run
        source_signal.save(update_fields=["operation", "updated_at"])
    return run


def trigger_paid_order_follow_up(
    *,
    order: InventoryOrderShell,
    actor: User | None = None,
) -> tuple[CompanySignal, Run]:
    signal = create_company_signal(
        company=order.company,
        actor=actor,
        signal_type="paid_order",
        source="commerce",
        external_key=f"paid_order:{order.id}",
        title=f"Paid order {order.public_reference or order.order_number}",
        summary="A paid order is ready for safe follow-up.",
        order_id=str(order.id),
        product_id=str(order.reservation.product_id),
        channel=order.reservation.channel,
        contact_alias=order.reservation.buyer_alias,
    )
    run = launch_company_operation(
        company=order.company,
        actor=actor,
        operation_type="paid_order_follow_up",
        source_signal=signal,
    )
    return signal, run


def trigger_fulfillment_exception(
    *,
    fulfillment: CommerceFulfillment,
    actor: User | None = None,
) -> tuple[CompanySignal, Run]:
    signal = create_company_signal(
        company=fulfillment.company,
        actor=actor,
        signal_type="fulfillment_issue",
        source="commerce",
        external_key=f"fulfillment_issue:{fulfillment.id}",
        title=f"Fulfillment issue for {fulfillment.order.public_reference or fulfillment.order.order_number}",
        summary=fulfillment.reason_code or "Fulfillment needs operator review.",
        order_id=str(fulfillment.order_id),
        fulfillment_id=str(fulfillment.id),
        product_id=str(fulfillment.reservation.product_id),
        channel=fulfillment.reservation.channel,
        contact_alias=fulfillment.reservation.buyer_alias,
    )
    run = launch_company_operation(
        company=fulfillment.company,
        actor=actor,
        operation_type="fulfillment_exception_review",
        source_signal=signal,
    )
    return signal, run


def build_company_ops_context_pack(
    *,
    company: Graph,
    operation_type: str = "daily_operating_brief",
    context_note: str = "",
    objective_contract: dict[str, Any] | None = None,
) -> ContextPack:
    _assert_choice(operation_type, OPERATION_TEMPLATES, "operation_type")
    organization = _organization_for_company(company)
    brief = current_brief_payload(company=company).get("brief")
    scope = {
        "operation_type": operation_type,
        "context_note": _safe_text(context_note, limit=1000),
        "objective_contract": _objective_contract_input_payload(objective_contract or {}),
        "business_context": _business_context(company),
        "privacy": {
            "sanitized": True,
            "excluded_fields": [
                "customer_email",
                "customer_name",
                "shipping_json",
                "operator_note",
                "stripe_session_id",
                "stripe_payment_intent_id",
                "checkout_url",
                "public_status_token",
            ],
        },
    }
    return ContextPack.objects.create(
        organization=organization,
        company=company,
        scope_json=scope,
        brief_snapshot_json=brief if isinstance(brief, dict) else {},
        created_for="operation_planning",
    )


def company_signal_payload(signal: CompanySignal) -> dict[str, Any]:
    return {
        "id": str(signal.id),
        "company_id": str(signal.company_id),
        "product_id": str(signal.product_id) if signal.product_id else None,
        "order_id": str(signal.order_id) if signal.order_id else None,
        "fulfillment_id": str(signal.fulfillment_id) if signal.fulfillment_id else None,
        "operation_id": str(signal.operation_id) if signal.operation_id else None,
        "signal_type": signal.signal_type,
        "status": signal.status,
        "source": signal.source,
        "external_key": signal.external_key,
        "title": signal.title,
        "summary": signal.summary,
        "channel": signal.channel,
        "contact_alias": signal.contact_alias,
        "metadata": signal.metadata_json,
        "occurred_at": signal.occurred_at.isoformat(),
        "created_at": signal.created_at.isoformat(),
        "updated_at": signal.updated_at.isoformat(),
    }


def company_opportunity_payload(opportunity: CompanyOpportunity) -> dict[str, Any]:
    return {
        "id": str(opportunity.id),
        "company_id": str(opportunity.company_id),
        "signal_id": str(opportunity.signal_id) if opportunity.signal_id else None,
        "product_id": str(opportunity.product_id) if opportunity.product_id else None,
        "reservation_id": str(opportunity.reservation_id) if opportunity.reservation_id else None,
        "order_id": str(opportunity.order_id) if opportunity.order_id else None,
        "status": opportunity.status,
        "title": opportunity.title,
        "summary": opportunity.summary,
        "contact_alias": opportunity.contact_alias,
        "channel": opportunity.channel,
        "estimated_value_amount": str(opportunity.estimated_value_amount),
        "currency": opportunity.currency,
        "next_action": opportunity.next_action,
        "metadata": opportunity.metadata_json,
        "created_at": opportunity.created_at.isoformat(),
        "updated_at": opportunity.updated_at.isoformat(),
    }


def publication_draft_payload(draft: PublicationDraft) -> dict[str, Any]:
    return {
        "id": str(draft.id),
        "company_id": str(draft.company_id),
        "signal_id": str(draft.signal_id) if draft.signal_id else None,
        "opportunity_id": str(draft.opportunity_id) if draft.opportunity_id else None,
        "origin_operation_id": str(draft.origin_operation_id)
        if draft.origin_operation_id
        else None,
        "asset_id": str(draft.asset_id) if draft.asset_id else None,
        "asset_version_id": str(draft.asset_version_id) if draft.asset_version_id else None,
        "media_job_id": str(draft.media_job_id) if draft.media_job_id else None,
        "approval_task_id": str(draft.approval_task_id) if draft.approval_task_id else None,
        "title": draft.title,
        "channel": draft.channel,
        "audience": draft.audience,
        "body": draft.body,
        "call_to_action": draft.call_to_action,
        "status": draft.status,
        "approved_at": draft.approved_at.isoformat() if draft.approved_at else None,
        "published_at": draft.published_at.isoformat() if draft.published_at else None,
        "metadata": draft.metadata_json,
        "created_at": draft.created_at.isoformat(),
        "updated_at": draft.updated_at.isoformat(),
    }


def procurement_draft_payload(draft: CommerceProcurementDraft) -> dict[str, Any]:
    lines = list(getattr(draft, "_prefetched_objects_cache", {}).get("lines", draft.lines.all()))
    return {
        "id": str(draft.id),
        "company_id": str(draft.company_id),
        "origin_operation_id": str(draft.origin_operation_id)
        if draft.origin_operation_id
        else None,
        "approval_task_id": str(draft.approval_task_id) if draft.approval_task_id else None,
        "title": draft.title,
        "rationale": draft.rationale,
        "budget_amount": str(draft.budget_amount),
        "currency": draft.currency,
        "status": draft.status,
        "approved_at": draft.approved_at.isoformat() if draft.approved_at else None,
        "metadata": draft.metadata_json,
        "lines": [procurement_line_payload(line) for line in lines],
        "created_at": draft.created_at.isoformat(),
        "updated_at": draft.updated_at.isoformat(),
    }


def procurement_line_payload(line: CommerceProcurementDraftLine) -> dict[str, Any]:
    return {
        "id": str(line.id),
        "product_id": str(line.product_id) if line.product_id else None,
        "sku": line.sku,
        "description": line.description,
        "quantity": line.quantity,
        "unit_cost_amount": str(line.unit_cost_amount),
        "currency": line.currency,
        "metadata": line.metadata_json,
    }


def operation_payload(run: Run) -> dict[str, Any]:
    input_json = run.input_json if isinstance(run.input_json, dict) else {}
    try:
        objective = run.company_objective
    except CompanyOperationObjective.DoesNotExist:
        objective = None
    return {
        "id": str(run.id),
        "company_id": str(run.graph_version.graph_id),
        "graph_version_id": str(run.graph_version_id),
        "status": run.status,
        "operation_type": input_json.get("operation_type"),
        "operation_brief": input_json.get("operation_brief"),
        "context_pack_id": input_json.get("company_ops_context_pack_id"),
        "objective_contract_id": input_json.get("company_ops_objective_id"),
        "objective_contract": operation_objective_payload(objective) if objective else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "created_at": run.started_at.isoformat() if run.started_at else None,
    }


def operation_objective_payload(objective: CompanyOperationObjective) -> dict[str, Any]:
    return {
        "id": str(objective.id),
        "company_id": str(objective.company_id),
        "operation_id": str(objective.operation_id),
        "source_signal_id": str(objective.source_signal_id) if objective.source_signal_id else None,
        "run_type": objective.run_type,
        "status": objective.status,
        "run_goal": objective.run_goal,
        "hypothesis": objective.hypothesis,
        "target_signal": objective.target_signal,
        "action_plan": objective.action_plan_json,
        "integrity_gates": objective.integrity_gates_json,
        "success_score": objective.success_score,
        "miss_analysis": objective.miss_analysis,
        "next_decision": objective.next_decision,
        "evaluated_at": objective.evaluated_at.isoformat() if objective.evaluated_at else None,
        "created_at": objective.created_at.isoformat(),
        "updated_at": objective.updated_at.isoformat(),
    }


def _objective_contract_input_payload(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "primary_objective": SELL_THROUGH_LEARNING_OBJECTIVE,
        "run_type": contract.get("run_type") or "rehearsal",
        "run_goal": contract.get("run_goal") or "",
        "hypothesis": contract.get("hypothesis") or "",
        "target_signal": contract.get("target_signal") or "",
        "action_plan": contract.get("action_plan_json") or [],
        "integrity_gates": contract.get("integrity_gates_json") or {},
    }


def _default_run_goal(*, operation_type: str, run_type: str) -> str:
    if run_type == "rehearsal" and operation_type == "daily_operating_brief":
        return FIRST_REHEARSAL_GOAL
    return (
        f"Move the company toward sell-through learning by completing "
        f"{OPERATION_TEMPLATES[operation_type].lower()}"
    )


def _default_hypothesis(*, operation_type: str) -> str:
    if operation_type == "daily_operating_brief":
        return (
            "A structured operating brief from current backend-owned company state will "
            "make the next sell-through action clearer than fixing isolated issues."
        )
    if operation_type == "content_drop_planning":
        return (
            "A content drop grounded in stock, scarcity, and demand context will create "
            "a stronger sales learning loop than generic content output."
        )
    if operation_type == "paid_order_follow_up":
        return (
            "Paid-order follow-up can capture fulfillment learning and reduce missed "
            "repeat demand without exposing private buyer data."
        )
    if operation_type == "fulfillment_exception_review":
        return (
            "Explicit exception review will explain blocked work and produce a safe next "
            "operator action."
        )
    if operation_type == "sold_out_demand_capture":
        return (
            "Stockout and low-stock signals can become reorder evidence when captured "
            "as qualified business demand."
        )
    return (
        "Procurement proposals should come from observed demand, stock risk, cash, and "
        "human approval rather than guesswork."
    )


def _default_target_signal(*, operation_type: str, run_type: str) -> str:
    if run_type == "rehearsal":
        return (
            "Integrity gates pass, no external buyer-facing action occurs, and the "
            "operator gets a concrete next action from real inventory context."
        )
    if operation_type == "content_drop_planning":
        return "At least one human-gated publication draft or content direction exists."
    if operation_type == "sold_out_demand_capture":
        return "Sold-out or low-stock evidence becomes a signal, opportunity, or reorder input."
    if operation_type == "reorder_procurement_approval":
        return "A procurement draft is created or updated and remains human-gated."
    if operation_type == "paid_order_follow_up":
        return "Paid order follow-up work is visible once without duplicate decisions."
    if operation_type == "fulfillment_exception_review":
        return "The fulfillment issue has an operator-visible reason and next action."
    return "The operation creates inspectable progress toward sell-through learning."


def _business_context(company: Graph) -> dict[str, Any]:
    products = list(
        InventoryProduct.objects.filter(company=company, status="active")
        .annotate(
            available_units=Count("stock_units", filter=Q(stock_units__status="available")),
            sold_units=Count("stock_units", filter=Q(stock_units__status="sold")),
        )
        .order_by("model", "sku")[:20]
    )
    payments = CommercePayment.objects.filter(company=company)
    cash_total = CommerceCashLedgerEntry.objects.filter(
        company=company, entry_type="sale"
    ).aggregate(total=Sum("amount_mxn"))["total"] or Decimal("0.00")
    return {
        "inventory": {
            "products": [
                {
                    "product_id": str(product.id),
                    "sku": product.sku,
                    "model": product.model,
                    "available_units": int(getattr(product, "available_units", 0) or 0),
                    "sold_units": int(getattr(product, "sold_units", 0) or 0),
                    "scarcity_tag": product.scarcity_tag,
                    "currency": product.currency,
                    "price_amount": str(product.price_amount),
                }
                for product in products
            ],
        },
        "commerce": {
            "orders_paid": InventoryOrderShell.objects.filter(
                company=company, status="paid"
            ).count(),
            "payments_succeeded": payments.filter(status="succeeded").count(),
            "cash_sales_amount": str(Decimal(cash_total).quantize(Decimal("0.01"))),
            "recent_orders": [
                _safe_order_context(order)
                for order in InventoryOrderShell.objects.filter(company=company)
                .select_related("reservation", "reservation__product", "commerce_payment")
                .order_by("-created_at")[:10]
            ],
        },
        "signals": [
            {
                "id": str(signal.id),
                "type": signal.signal_type,
                "status": signal.status,
                "title": signal.title,
                "summary": signal.summary,
                "channel": signal.channel,
            }
            for signal in _signals_queryset(company)[:20]
        ],
        "publication_drafts": [
            {
                "id": str(draft.id),
                "title": draft.title,
                "channel": draft.channel,
                "status": draft.status,
            }
            for draft in _publication_drafts_queryset(company)[:10]
        ],
        "procurement_drafts": [
            {
                "id": str(draft.id),
                "title": draft.title,
                "status": draft.status,
                "budget_amount": str(draft.budget_amount),
                "currency": draft.currency,
            }
            for draft in _procurement_drafts_queryset(company)[:10]
        ],
    }


def _safe_order_context(order: InventoryOrderShell) -> dict[str, Any]:
    payment = getattr(order, "commerce_payment", None)
    return {
        "reference": order.public_reference or order.order_number,
        "status": order.status,
        "product": {
            "sku": order.reservation.product.sku,
            "model": order.reservation.product.model,
        },
        "quantity": order.reservation.quantity,
        "channel": order.reservation.channel,
        "payment_status": payment.status if payment is not None else "pending",
        "amount": str(payment.amount_mxn) if payment is not None else "0.00",
        "currency": payment.currency if payment is not None else order.reservation.product.currency,
    }


def _signals_queryset(company: Graph) -> Any:
    return (
        CompanySignal.objects.filter(company=company)
        .select_related("product", "order", "fulfillment", "operation")
        .order_by("-occurred_at", "-created_at")
    )


def _opportunities_queryset(company: Graph) -> Any:
    return (
        CompanyOpportunity.objects.filter(company=company)
        .select_related("signal", "product", "reservation", "order", "owner_user")
        .order_by("-updated_at", "-created_at")
    )


def _publication_drafts_queryset(company: Graph) -> Any:
    return (
        PublicationDraft.objects.filter(company=company)
        .select_related("signal", "opportunity", "origin_operation", "asset", "asset_version")
        .order_by("-updated_at", "-created_at")
    )


def _procurement_drafts_queryset(company: Graph) -> Any:
    return (
        CommerceProcurementDraft.objects.filter(company=company)
        .select_related("origin_operation", "approval_task")
        .prefetch_related("lines")
        .order_by("-updated_at", "-created_at")
    )


def _operation_objectives_queryset(company: Graph) -> Any:
    return (
        CompanyOperationObjective.objects.filter(company=company)
        .select_related("operation", "source_signal")
        .order_by("-created_at")
    )


def _decision_queryset(company: Graph) -> Any:
    return (
        DecisionRecord.objects.filter(organization=company.organization)
        .filter(
            Q(execution__graph_version__graph=company)
            | Q(task__execution__graph_version__graph=company)
            | Q(source_approval_task__run__graph_version__graph=company)
        )
        .select_related("execution", "source_approval_task")
        .order_by("-requested_at", "-created_at")
    )


def _decision_payload(decision: DecisionRecord) -> dict[str, Any]:
    return {
        "id": str(decision.id),
        "operation_id": str(decision.execution_id) if decision.execution_id else None,
        "approval_task_id": str(decision.source_approval_task_id)
        if decision.source_approval_task_id
        else None,
        "decision_type": decision.decision_type,
        "status": decision.status,
        "context": decision.context_json,
        "resolution": decision.resolution_json,
        "requested_at": decision.requested_at.isoformat() if decision.requested_at else None,
        "resolved_at": decision.resolved_at.isoformat() if decision.resolved_at else None,
    }


def _policy_payload(policy: PolicyRule) -> dict[str, Any]:
    return {
        "id": str(policy.id),
        "title": policy.title,
        "scope_type": policy.scope_type,
        "scope_id": policy.scope_id,
        "status": policy.status,
        "confidence": policy.confidence,
        "condition": policy.condition_json,
        "recommendation": policy.recommendation_json,
    }


def _resolve_product(*, company: Graph, product_id: Any | None) -> InventoryProduct | None:
    if not product_id:
        return None
    product = InventoryProduct.objects.filter(company=company, id=product_id).first()
    if product is None:
        raise CompanyOpsError("product_not_found", "Inventory product was not found.")
    return product


def _resolve_order(*, company: Graph, order_id: Any | None) -> InventoryOrderShell | None:
    if not order_id:
        return None
    order = InventoryOrderShell.objects.filter(company=company, id=order_id).first()
    if order is None:
        raise CompanyOpsError("order_not_found", "Commerce order was not found.")
    return order


def _resolve_fulfillment(
    *, company: Graph, fulfillment_id: Any | None
) -> CommerceFulfillment | None:
    if not fulfillment_id:
        return None
    fulfillment = CommerceFulfillment.objects.filter(company=company, id=fulfillment_id).first()
    if fulfillment is None:
        raise CompanyOpsError("fulfillment_not_found", "Commerce fulfillment was not found.")
    return fulfillment


def _resolve_signal(*, company: Graph, signal_id: Any | None) -> CompanySignal | None:
    if not signal_id:
        return None
    signal = CompanySignal.objects.filter(company=company, id=signal_id).first()
    if signal is None:
        raise CompanyOpsError("signal_not_found", "Company signal was not found.")
    return signal


def _resolve_opportunity(
    *, company: Graph, opportunity_id: Any | None
) -> CompanyOpportunity | None:
    if not opportunity_id:
        return None
    opportunity = CompanyOpportunity.objects.filter(company=company, id=opportunity_id).first()
    if opportunity is None:
        raise CompanyOpsError("opportunity_not_found", "Company opportunity was not found.")
    return opportunity


def _resolve_asset(*, company: Graph, asset_id: Any | None) -> Asset | None:
    if not asset_id:
        return None
    asset = Asset.objects.filter(company=company, id=asset_id).first()
    if asset is None:
        raise CompanyOpsError("asset_not_found", "Archive asset was not found.")
    return asset


def _resolve_asset_version(*, asset: Asset | None, asset_version_id: Any | None) -> Any | None:
    if not asset_version_id:
        return None
    if asset is None:
        raise CompanyOpsError(
            "asset_required", "asset_id is required when asset_version_id is provided."
        )
    version = asset.versions.filter(id=asset_version_id).first()
    if version is None:
        raise CompanyOpsError("asset_version_not_found", "Archive asset version was not found.")
    return version


def _resolve_media_job(*, company: Graph, media_job_id: Any | None) -> MediaGenerationJob | None:
    if not media_job_id:
        return None
    job = MediaGenerationJob.objects.filter(company=company, id=media_job_id).first()
    if job is None:
        raise CompanyOpsError("media_job_not_found", "Media generation job was not found.")
    return job


def _organization_for_company(company: Graph) -> Organization:
    _assert_company(company)
    return cast(Organization, company.organization)


def _assert_company(company: Graph) -> None:
    if company.organization_id is None:
        raise CompanyOpsError(
            "organization_required", "Company operations require an organization."
        )


def _assert_choice(value: str, choices: dict[str, Any], field: str) -> None:
    if value not in choices:
        raise CompanyOpsError(f"invalid_{field}", f"{field} is not supported.")


def _estimated_value_for_signal(signal: CompanySignal) -> Decimal:
    product = signal.product if signal.product_id else None
    if product is not None:
        return Decimal(product.price_amount or product.price_mxn or 0)
    if signal.order_id:
        payment = getattr(signal.order, "commerce_payment", None)
        if payment is not None:
            return Decimal(payment.amount_mxn or 0)
    return Decimal("0.00")


def _currency_for_signal(signal: CompanySignal) -> str:
    product = signal.product if signal.product_id else None
    if product is not None:
        return str(product.currency)
    if signal.order_id:
        payment = getattr(signal.order, "commerce_payment", None)
        if payment is not None:
            return str(payment.currency)
    return "mxn"


def _sanitized_metadata(value: dict[str, Any]) -> dict[str, Any]:
    blocked = {
        "customer_email",
        "customer_name",
        "shipping_json",
        "address",
        "payment",
        "stripe_session_id",
        "stripe_payment_intent_id",
        "checkout_url",
        "public_status_token",
        "operator_note",
        "note",
    }
    result: dict[str, Any] = {}
    for key, item in value.items():
        key_text = _safe_text(key, limit=80)
        if key_text in blocked:
            continue
        if isinstance(item, dict):
            result[key_text] = _sanitized_metadata(item)
        elif isinstance(item, list):
            result[key_text] = [_safe_text(entry, limit=500) for entry in item[:20]]
        elif isinstance(item, (str, int, float, bool)) or item is None:
            result[key_text] = _safe_text(item, limit=500) if isinstance(item, str) else item
        else:
            result[key_text] = _safe_text(item, limit=500)
    return result


def _safe_text(value: Any, *, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"[\w.\-+]+@[\w.\-]+\.\w+", "[redacted-email]", text)
    text = re.sub(r"\b\d[\d\s\-]{5,}\d\b", "[redacted-number]", text)
    return text[:limit]


def _clean_key(value: Any, *, limit: int) -> str:
    text = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(value or "").strip().lower()).strip("_")
    return (text or "manual")[:limit]


def _decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")
