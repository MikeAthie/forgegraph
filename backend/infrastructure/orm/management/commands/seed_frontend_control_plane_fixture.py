from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from application.services.os_projection_rebuild import rebuild_os_projections_for_organization
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    AgentRegistryEntry,
    ApprovalTask,
    Graph,
    GraphVersion,
    LLMUsage,
    MemoryObservation,
    NodeRun,
    OrganizationMembership,
    Run,
    RunQueueEntry,
    TenantPolicy,
    User,
)

FIXTURE_NAMESPACE = UUID("b9d940db-1ad4-4ef1-9097-e72a8863a201")
DEFAULT_EMAIL = "playwright-control@example.com"
DEFAULT_PASSWORD = "ForgeGraphTest!12345"


def fixture_uuid(email: str, label: str) -> UUID:
    return uuid5(FIXTURE_NAMESPACE, f"{email}:{label}")


def paused_workflow_graph_json() -> dict:
    return {
        "nodes": [
            {
                "id": "ops_agent",
                "type": "agent",
                "name": "Ops Conductor",
                "data": {
                    "config": {
                        "model": "gpt-4.1-mini",
                        "tools": ["risk_screen", "vendor_ledger"],
                        "policy": {"requires_approval": True},
                    }
                },
            },
            {"id": "output", "type": "output", "name": "Output"},
        ],
        "edges": [
            {"id": "e0", "from": "START", "to": "ops_agent"},
            {"id": "e1", "from": "ops_agent", "to": "output"},
        ],
    }


def running_workflow_graph_json() -> dict:
    return {
        "nodes": [
            {
                "id": "finance_agent",
                "type": "agent",
                "name": "Billing Sentinel",
                "data": {
                    "config": {
                        "model": "gpt-4.1-mini",
                        "tools": ["budget_check", "invoice_lookup"],
                    }
                },
            },
            {"id": "output", "type": "output", "name": "Output"},
        ],
        "edges": [
            {"id": "e0", "from": "START", "to": "finance_agent"},
            {"id": "e1", "from": "finance_agent", "to": "output"},
        ],
    }


def failure_workflow_graph_json() -> dict:
    return {
        "nodes": [
            {"id": "collect_signal", "type": "prompt", "name": "Collect signal"},
            {"id": "write_ticket", "type": "transform", "name": "Write ticket"},
            {"id": "output", "type": "output", "name": "Output"},
        ],
        "edges": [
            {"id": "e0", "from": "START", "to": "collect_signal"},
            {"id": "e1", "from": "collect_signal", "to": "write_ticket"},
            {"id": "e2", "from": "write_ticket", "to": "output"},
        ],
    }


class Command(BaseCommand):
    help = (
        "Seed frontend control-plane fixtures aligned to the observer/control-surface architecture."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--password", default=DEFAULT_PASSWORD)
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        email = str(options["email"]).strip().lower() or DEFAULT_EMAIL
        password = str(options["password"]) or DEFAULT_PASSWORD
        output_json = bool(options["json"])
        now = timezone.now()

        paused_graph_id = fixture_uuid(email, "graph-paused")
        paused_version_id = fixture_uuid(email, "graph-paused-version")
        paused_run_id = fixture_uuid(email, "run-paused")
        paused_node_run_id = fixture_uuid(email, "node-run-paused")
        paused_queue_id = fixture_uuid(email, "queue-paused")
        approval_id = fixture_uuid(email, "approval-pending")
        paused_usage_id = fixture_uuid(email, "usage-paused")

        running_graph_id = fixture_uuid(email, "graph-running")
        running_version_id = fixture_uuid(email, "graph-running-version")
        running_run_id = fixture_uuid(email, "run-running")
        running_node_run_id = fixture_uuid(email, "node-run-running")
        running_queue_id = fixture_uuid(email, "queue-running")
        running_usage_id = fixture_uuid(email, "usage-running")

        failed_graph_id = fixture_uuid(email, "graph-failed")
        failed_version_id = fixture_uuid(email, "graph-failed-version")
        failed_run_id = fixture_uuid(email, "run-failed")
        failed_collect_node_run_id = fixture_uuid(email, "node-run-failed-collect")
        failed_write_node_run_id = fixture_uuid(email, "node-run-failed-write")
        failed_queue_id = fixture_uuid(email, "queue-failed")

        ops_agent_id = fixture_uuid(email, "agent-ops")
        finance_agent_id = fixture_uuid(email, "agent-finance")
        ops_memory_id = fixture_uuid(email, "memory-ops")
        finance_memory_id = fixture_uuid(email, "memory-finance")

        with transaction.atomic():
            user, created = User.objects.get_or_create(email=email, defaults={"is_active": True})
            user.is_active = True
            needs_password_update = created or not user.check_password(password)
            if needs_password_update:
                user.set_password(password)
            user.save(
                update_fields=["password", "is_active"] if needs_password_update else ["is_active"]
            )

            organization = user.default_organization
            if organization is None:
                ensure_default_organization(user)
                user.refresh_from_db()
                organization = user.default_organization
            if organization is None:
                raise RuntimeError(f"User {email} does not have a default organization.")

            OrganizationMembership.objects.update_or_create(
                organization=organization,
                user=user,
                defaults={"role": "owner", "is_default": True},
            )
            OrganizationMembership.objects.filter(user=user).exclude(
                organization=organization
            ).update(is_default=False)

            TenantPolicy.objects.update_or_create(
                tenant_id=organization.id,
                defaults={
                    "http_allowlist": ["https://api.forgegraph.dev"],
                    "http_denylist": [],
                    "http_default_deny": True,
                    "allowed_providers": ["openai"],
                    "allowed_models": ["gpt-4.1-mini"],
                },
            )

            paused_graph, _ = Graph.objects.update_or_create(
                id=paused_graph_id,
                defaults={
                    "owner": user,
                    "name": "Vendor payment review",
                    "description": "Paused operator review fixture.",
                },
            )
            paused_version, _ = GraphVersion.objects.update_or_create(
                id=paused_version_id,
                defaults={
                    "graph": paused_graph,
                    "version": 1,
                    "graph_json": paused_workflow_graph_json(),
                },
            )

            running_graph, _ = Graph.objects.update_or_create(
                id=running_graph_id,
                defaults={
                    "owner": user,
                    "name": "Invoice monitoring",
                    "description": "Running supervision fixture.",
                },
            )
            running_version, _ = GraphVersion.objects.update_or_create(
                id=running_version_id,
                defaults={
                    "graph": running_graph,
                    "version": 1,
                    "graph_json": running_workflow_graph_json(),
                },
            )

            failed_graph, _ = Graph.objects.update_or_create(
                id=failed_graph_id,
                defaults={
                    "owner": user,
                    "name": "Failure escalation",
                    "description": "Failed execution inspection fixture.",
                },
            )
            failed_version, _ = GraphVersion.objects.update_or_create(
                id=failed_version_id,
                defaults={
                    "graph": failed_graph,
                    "version": 1,
                    "graph_json": failure_workflow_graph_json(),
                },
            )

            paused_run, _ = Run.objects.update_or_create(
                id=paused_run_id,
                defaults={
                    "owner": user,
                    "graph_version": paused_version,
                    "status": "paused",
                    "started_at": now - timedelta(minutes=12),
                    "input_json": {
                        "approval_reason": "Vendor payment exceeded the automatic approval limit."
                    },
                    "output_json": None,
                    "error_message": "",
                    "trace_id": "frontend-paused-trace",
                    "pause_state_json": {
                        "node_id": "ops_agent",
                        "node_name": "Ops Conductor",
                        "prompt_message": "Approve vendor payment above the automatic threshold?",
                        "summary": "Vendor payment over the safety threshold requires operator confirmation.",
                        "reasoning_summary": "The payment is valid, but policy requires a human to approve amounts above the configured risk limit.",
                    },
                    "paused_node_id": "ops_agent",
                },
            )

            running_run, _ = Run.objects.update_or_create(
                id=running_run_id,
                defaults={
                    "owner": user,
                    "graph_version": running_version,
                    "status": "running",
                    "started_at": now,
                    "last_progress_at": now,
                    "input_json": {"queue": "accounts-payable"},
                    "output_json": None,
                    "error_message": "",
                    "trace_id": "frontend-running-trace",
                    "pause_state_json": None,
                    "paused_node_id": None,
                },
            )

            failed_run, _ = Run.objects.update_or_create(
                id=failed_run_id,
                defaults={
                    "owner": user,
                    "graph_version": failed_version,
                    "status": "failed",
                    "started_at": now - timedelta(minutes=18),
                    "ended_at": now - timedelta(minutes=17, seconds=18),
                    "input_json": {"source": "incident-monitor"},
                    "output_json": None,
                    "error_message": "Downstream escalation ticket could not be created.",
                    "trace_id": "frontend-failed-trace",
                    "pause_state_json": None,
                    "paused_node_id": None,
                },
            )

            RunQueueEntry.objects.update_or_create(
                id=paused_queue_id,
                defaults={
                    "run": paused_run,
                    "tenant_id": organization.id,
                    "status": "processing",
                    "priority": 5,
                    "attempts": 1,
                    "max_attempts": 3,
                    "available_at": now - timedelta(minutes=12),
                    "locked_at": now - timedelta(minutes=12),
                    "locked_by": "frontend-fixture",
                    "last_error": "",
                },
            )
            RunQueueEntry.objects.update_or_create(
                id=running_queue_id,
                defaults={
                    "run": running_run,
                    "tenant_id": organization.id,
                    "status": "processing",
                    "priority": 4,
                    "attempts": 1,
                    "max_attempts": 3,
                    "available_at": now,
                    "locked_at": now,
                    "locked_by": "frontend-fixture",
                    "last_error": "",
                },
            )
            RunQueueEntry.objects.update_or_create(
                id=failed_queue_id,
                defaults={
                    "run": failed_run,
                    "tenant_id": organization.id,
                    "status": "failed",
                    "priority": 8,
                    "attempts": 3,
                    "max_attempts": 3,
                    "available_at": now - timedelta(minutes=18),
                    "locked_at": now - timedelta(minutes=17, seconds=18),
                    "locked_by": "frontend-fixture",
                    "last_error": "Escalation API rejected the payload.",
                },
            )

            AgentRegistryEntry.objects.update_or_create(
                organization=organization,
                source_workflow=paused_graph,
                source_node_id="ops_agent",
                defaults={
                    "id": ops_agent_id,
                    "slug": "ops-conductor",
                    "display_name": "Ops Conductor",
                    "source_workflow_revision": paused_version,
                    "status": "attention",
                    "policy_snapshot_json": {"requires_approval": True, "limit": "5000"},
                    "capabilities_json": {
                        "tools": ["risk_screen", "vendor_ledger"],
                        "memory": {"mode": "curated"},
                    },
                    "default_model": "gpt-4.1-mini",
                    "last_execution": paused_run,
                    "last_seen_at": now - timedelta(minutes=10),
                },
            )
            AgentRegistryEntry.objects.update_or_create(
                organization=organization,
                source_workflow=running_graph,
                source_node_id="finance_agent",
                defaults={
                    "id": finance_agent_id,
                    "slug": "billing-sentinel",
                    "display_name": "Billing Sentinel",
                    "source_workflow_revision": running_version,
                    "status": "active",
                    "policy_snapshot_json": {"budget_mode": "warning"},
                    "capabilities_json": {"tools": ["budget_check", "invoice_lookup"]},
                    "default_model": "gpt-4.1-mini",
                    "last_execution": running_run,
                    "last_seen_at": now - timedelta(minutes=2),
                },
            )

            NodeRun.objects.update_or_create(
                id=paused_node_run_id,
                defaults={
                    "run": paused_run,
                    "node_id": "ops_agent",
                    "node_type": "agent",
                    "status": "waiting",
                    "attempt": 1,
                    "started_at": now - timedelta(minutes=11, seconds=30),
                    "ended_at": None,
                    "input_json": {
                        "task": "Review vendor payment risk and request approval if needed."
                    },
                    "output_json": {
                        "summary": "Awaiting operator approval before issuing payment."
                    },
                    "error_json": None,
                    "trace_id": "frontend-paused-trace",
                    "span_id": "pausedspan000001",
                },
            )
            NodeRun.objects.update_or_create(
                id=running_node_run_id,
                defaults={
                    "run": running_run,
                    "node_id": "finance_agent",
                    "node_type": "agent",
                    "status": "running",
                    "attempt": 1,
                    "started_at": now,
                    "ended_at": None,
                    "input_json": {
                        "task": "Monitor invoice anomalies and keep the ledger summary current."
                    },
                    "output_json": {
                        "summary": "Invoice queue is being processed with no active anomalies."
                    },
                    "error_json": None,
                    "trace_id": "frontend-running-trace",
                    "span_id": "runningspan00001",
                },
            )
            NodeRun.objects.update_or_create(
                id=failed_collect_node_run_id,
                defaults={
                    "run": failed_run,
                    "node_id": "collect_signal",
                    "node_type": "prompt",
                    "status": "succeeded",
                    "attempt": 1,
                    "started_at": now - timedelta(minutes=18),
                    "ended_at": now - timedelta(minutes=17, seconds=42),
                    "input_json": {"task": "Collect the latest incident context."},
                    "output_json": {"summary": "Incident signal classified as urgent."},
                    "error_json": None,
                    "trace_id": "frontend-failed-trace",
                    "span_id": "failedspan000001",
                },
            )
            NodeRun.objects.update_or_create(
                id=failed_write_node_run_id,
                defaults={
                    "run": failed_run,
                    "node_id": "write_ticket",
                    "node_type": "transform",
                    "status": "failed",
                    "attempt": 3,
                    "started_at": now - timedelta(minutes=17, seconds=41),
                    "ended_at": now - timedelta(minutes=17, seconds=18),
                    "input_json": {"ticket_payload": {"severity": "high", "service": "billing"}},
                    "output_json": None,
                    "error_json": {
                        "error": "Escalation API rejected the payload.",
                        "code": "DOWNSTREAM_400",
                    },
                    "trace_id": "frontend-failed-trace",
                    "span_id": "failedspan000002",
                },
            )

            ApprovalTask.objects.update_or_create(
                id=approval_id,
                defaults={
                    "run": paused_run,
                    "node_id": "ops_agent",
                    "assignee": user,
                    "status": "pending",
                    "payload": {
                        "summary": "Vendor payment over the safety threshold requires operator confirmation.",
                        "prompt_message": "Approve vendor payment above the automatic threshold?",
                        "reasoning_summary": "The payment is valid, but policy requires a human to approve amounts above the configured risk limit.",
                    },
                    "result": None,
                    "resolved_at": None,
                },
            )

            MemoryObservation.objects.update_or_create(
                id=ops_memory_id,
                defaults={
                    "tenant_id": organization.id,
                    "graph_id": paused_graph.id,
                    "run_id": paused_run.id,
                    "session_id": None,
                    "agent_id": ops_agent_id,
                    "type": "operator_note",
                    "title": "Payment escalation guidance",
                    "content": "Escalate vendor payments above the automatic threshold unless the invoice matches a pre-approved contract.",
                    "scope": "run",
                    "topic_key": "vendor-payment-policy",
                    "tool_name": "risk_screen",
                    "revision_count": 1,
                    "duplicate_count": 0,
                    "last_seen_at": now - timedelta(minutes=9),
                    "memory_chunk": None,
                    "deleted_at": None,
                },
            )
            MemoryObservation.objects.update_or_create(
                id=finance_memory_id,
                defaults={
                    "tenant_id": organization.id,
                    "graph_id": running_graph.id,
                    "run_id": running_run.id,
                    "session_id": None,
                    "agent_id": finance_agent_id,
                    "type": "system_observation",
                    "title": "Invoice monitoring baseline",
                    "content": "Billing Sentinel prefers summarized anomaly digests over raw invoice logs.",
                    "scope": "graph",
                    "topic_key": "invoice-monitoring",
                    "tool_name": "budget_check",
                    "revision_count": 1,
                    "duplicate_count": 0,
                    "last_seen_at": now - timedelta(minutes=3),
                    "memory_chunk": None,
                    "deleted_at": None,
                },
            )

            LLMUsage.objects.update_or_create(
                id=paused_usage_id,
                defaults={
                    "tenant_id": organization.id,
                    "run": paused_run,
                    "node_id": "ops_agent",
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "prompt_tokens": 1100,
                    "completion_tokens": 350,
                    "total_tokens": 1450,
                    "cost_usd": Decimal("1.750000"),
                },
            )
            LLMUsage.objects.update_or_create(
                id=running_usage_id,
                defaults={
                    "tenant_id": organization.id,
                    "run": running_run,
                    "node_id": "finance_agent",
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "prompt_tokens": 1600,
                    "completion_tokens": 500,
                    "total_tokens": 2100,
                    "cost_usd": Decimal("2.250000"),
                },
            )

        rebuild_os_projections_for_organization(organization)

        ops_agent = AgentRegistryEntry.objects.filter(
            organization=organization,
            source_workflow=paused_graph,
            source_node_id="ops_agent",
        ).first()
        finance_agent = AgentRegistryEntry.objects.filter(
            organization=organization,
            source_workflow=running_graph,
            source_node_id="finance_agent",
        ).first()
        ops_agent_id = ops_agent.id if ops_agent is not None else ops_agent_id
        finance_agent_id = finance_agent.id if finance_agent is not None else finance_agent_id

        payload = {
            "organizationId": str(organization.id),
            "agentIds": {
                "ops": str(ops_agent_id),
                "finance": str(finance_agent_id),
            },
            "runIds": {
                "paused": str(paused_run_id),
                "running": str(running_run_id),
                "failed": str(failed_run_id),
            },
            "approval": {
                "id": str(approval_id),
                "runId": str(paused_run_id),
                "nodeId": "ops_agent",
                "nodeName": "Ops Conductor",
                "graphName": "Vendor payment review",
                "promptMessage": "Approve vendor payment above the automatic threshold?",
                "createdAt": (now - timedelta(minutes=10)).isoformat(),
            },
        }

        if output_json:
            self.stdout.write(json.dumps(payload))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded frontend control-plane fixture for {email} "
                f"(org={organization.id}, paused_run={paused_run_id}, running_run={running_run_id}, failed_run={failed_run_id})"
            )
        )
