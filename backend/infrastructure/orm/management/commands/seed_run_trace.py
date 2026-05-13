"""
Seed a deterministic Run + NodeRun trace for a given GraphVersion.

This is a developer utility for Phase 4 (Observability MVP) so the UI can be
validated without the Go engine.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from infrastructure.orm.models import GraphVersion, NodeRun, Run, User


class Command(BaseCommand):
    help = "Create a sample Run + NodeRuns for a GraphVersion (deterministic timings)."

    def add_arguments(self, parser):
        parser.add_argument("graph_version_id", type=str, help="GraphVersion UUID")
        parser.add_argument(
            "--owner-email",
            type=str,
            default=None,
            help="Override run owner (defaults to graph owner).",
        )
        parser.add_argument(
            "--run-status",
            type=str,
            choices=["pending", "running", "paused", "succeeded", "failed"],
            default="succeeded",
            help="Overall run status to generate.",
        )
        parser.add_argument(
            "--paused-node-id",
            type=str,
            default=None,
            help="Node id to pause at when run-status=paused (defaults to the first human_gate node, or the last node).",
        )
        parser.add_argument(
            "--fail-node-id",
            type=str,
            default=None,
            help="Node id to fail (defaults to the last node when run-status=failed).",
        )
        parser.add_argument(
            "--fail-message",
            type=str,
            default="Sample node failure (seed_run_trace).",
            help="Error message to attach when failing.",
        )

    def handle(self, *args, **options):
        graph_version = self._get_graph_version(options["graph_version_id"])
        owner = self._get_owner(graph_version, options.get("owner_email"))
        trace_plan = self._build_trace_plan(graph_version, options)
        run = self._create_run_trace(
            graph_version=graph_version,
            owner=owner,
            run_status=options["run_status"],
            fail_message=options["fail_message"],
            trace_plan=trace_plan,
        )

        self.stdout.write(
            self.style.SUCCESS(f"Created run {run.id} for graph_version {graph_version.id}")
        )

    def _get_graph_version(self, raw_graph_version_id: str) -> GraphVersion:
        try:
            graph_version_id = UUID(raw_graph_version_id)
        except ValueError as exc:
            raise CommandError("graph_version_id must be a valid UUID.") from exc

        try:
            graph_version = GraphVersion.objects.select_related("graph__owner").get(
                id=graph_version_id
            )
            return cast(GraphVersion, graph_version)
        except GraphVersion.DoesNotExist as exc:
            raise CommandError(f"GraphVersion '{graph_version_id}' does not exist.") from exc

    def _get_owner(self, graph_version: GraphVersion, owner_email: str | None) -> User:
        if not owner_email:
            return graph_version.graph.owner

        normalized_email = owner_email.strip().lower()
        owner = User.objects.filter(email=normalized_email).first()
        if not owner:
            raise CommandError(f"No user found with email '{normalized_email}'.")
        return owner

    def _build_trace_plan(
        self,
        graph_version: GraphVersion,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        graph_json = graph_version.graph_json or {}
        node_order = self._toposort(
            list(graph_json.get("nodes") or []),
            list(graph_json.get("edges") or []),
        )
        node_ids = [str(node.get("id") or f"node_{index}") for index, node in enumerate(node_order)]
        fail_node_id, fail_index = self._resolve_fail_node(options["run_status"], node_ids, options)
        paused_node_id, paused_index = self._resolve_paused_node(
            options["run_status"], node_order, node_ids, options
        )
        return {
            "node_order": node_order,
            "node_ids": node_ids,
            "fail_node_id": fail_node_id,
            "fail_index": fail_index,
            "paused_node_id": paused_node_id,
            "paused_index": paused_index,
        }

    def _resolve_fail_node(
        self,
        run_status: str,
        node_ids: list[str],
        options: dict[str, Any],
    ) -> tuple[str | None, int | None]:
        if run_status != "failed":
            return None, None
        fail_node_id: str | None = options.get("fail_node_id")
        if fail_node_id is None:
            fail_node_id = node_ids[-1] if node_ids else None
        if fail_node_id and fail_node_id not in node_ids:
            raise CommandError(
                f"--fail-node-id '{fail_node_id}' is not present in graph_json.nodes[].id"
            )
        return fail_node_id, node_ids.index(fail_node_id) if fail_node_id else None

    def _resolve_paused_node(
        self,
        run_status: str,
        node_order: list[dict[str, Any]],
        node_ids: list[str],
        options: dict[str, Any],
    ) -> tuple[str | None, int | None]:
        if run_status != "paused":
            return None, None
        paused_node_id = options.get("paused_node_id") or self._default_paused_node_id(
            node_order, node_ids
        )
        if paused_node_id and paused_node_id not in node_ids:
            raise CommandError(
                f"--paused-node-id '{paused_node_id}' is not present in graph_json.nodes[].id"
            )
        return paused_node_id, node_ids.index(paused_node_id) if paused_node_id else None

    def _default_paused_node_id(
        self, node_order: list[dict[str, Any]], node_ids: list[str]
    ) -> str | None:
        human_gate = next((n for n in node_order if str(n.get("type")) == "human_gate"), None)
        if human_gate and human_gate.get("id"):
            return str(human_gate.get("id"))
        return node_ids[-1] if node_ids else None

    def _create_run_trace(
        self,
        *,
        graph_version: GraphVersion,
        owner: User,
        run_status: str,
        fail_message: str,
        trace_plan: dict[str, Any],
    ) -> Run:
        now = timezone.now()
        node_order = trace_plan["node_order"]
        started_at = self._started_at_for_run(run_status, now, len(node_order))
        with transaction.atomic():
            run = Run.objects.create(
                owner=owner,
                graph_version=graph_version,
                status=run_status,
                started_at=started_at,
                ended_at=None,
                input_json={"seeded": True},
                output_json=None,
                error_message="",
            )
            last_finished_at = self._create_node_runs(
                run=run,
                run_status=run_status,
                started_at=started_at,
                now=now,
                fail_message=fail_message,
                trace_plan=trace_plan,
            )
            self._finalize_seed_run(run, run_status, fail_message, trace_plan, last_finished_at)
            return run

    def _started_at_for_run(
        self, run_status: str, now: datetime, node_count: int
    ) -> datetime | None:
        if run_status not in {"running", "paused", "succeeded", "failed"}:
            return None
        return now - timedelta(seconds=max(1, node_count))

    def _create_node_runs(
        self,
        *,
        run: Run,
        run_status: str,
        started_at: datetime | None,
        now: datetime,
        fail_message: str,
        trace_plan: dict[str, Any],
    ) -> datetime | None:
        offset_ms = 0
        last_finished_at = started_at
        for index, node in enumerate(trace_plan["node_order"]):
            node_status = self._node_status_for_index(run_status, index, trace_plan)
            node_started_at, node_ended_at, offset_ms = self._node_timing(
                run_status, node_status, index, started_at, now, offset_ms
            )
            last_finished_at = node_ended_at or last_finished_at
            self._create_node_run(
                run=run,
                node=node,
                node_id=trace_plan["node_ids"][index],
                node_status=node_status,
                node_started_at=node_started_at,
                node_ended_at=node_ended_at,
                fail_message=fail_message,
            )
        return last_finished_at

    def _node_status_for_index(
        self, run_status: str, index: int, trace_plan: dict[str, Any]
    ) -> str:
        if run_status == "running":
            return "running" if index == len(trace_plan["node_order"]) - 1 else "succeeded"
        if run_status == "paused":
            paused_index = trace_plan["paused_index"]
            if paused_index is None or index == paused_index:
                return "waiting"
            return "succeeded" if index < paused_index else "pending"
        if run_status == "succeeded":
            return "succeeded"
        if run_status == "failed":
            fail_index = trace_plan["fail_index"]
            if fail_index is None or index == fail_index:
                return "failed"
            return "succeeded" if index < fail_index else "skipped"
        return "pending"

    def _node_timing(
        self,
        run_status: str,
        node_status: str,
        index: int,
        started_at: datetime | None,
        now: datetime,
        offset_ms: int,
    ) -> tuple[datetime | None, datetime | None, int]:
        if run_status not in {"running", "paused", "succeeded", "failed"}:
            return None, None, offset_ms
        if node_status not in {"succeeded", "running", "failed", "waiting"}:
            return None, None, offset_ms
        node_started_at = (started_at or now) + timedelta(milliseconds=offset_ms)
        offset_ms += 250 + (index * 50)
        node_ended_at = None
        if node_status in {"succeeded", "failed"}:
            node_ended_at = (started_at or now) + timedelta(milliseconds=offset_ms)
        return node_started_at, node_ended_at, offset_ms

    def _create_node_run(
        self,
        *,
        run: Run,
        node: dict[str, Any],
        node_id: str,
        node_status: str,
        node_started_at: datetime | None,
        node_ended_at: datetime | None,
        fail_message: str,
    ) -> None:
        node_type = str(node.get("type") or "unknown")
        output_json, error_json = self._node_payloads(
            node, node_id, node_type, node_status, fail_message
        )
        NodeRun.objects.create(
            run=run,
            node_id=node_id,
            node_type=node_type,
            status=node_status,
            attempt=1,
            started_at=node_started_at,
            ended_at=node_ended_at,
            input_json={"seeded": True, "node_id": node_id},
            output_json=output_json,
            error_json=error_json,
        )

    def _node_payloads(
        self,
        node: dict[str, Any],
        node_id: str,
        node_type: str,
        node_status: str,
        fail_message: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if node_status == "succeeded":
            return {"ok": True}, None
        if node_status == "failed":
            return None, {"message": fail_message, "node_id": node_id, "node_type": node_type}
        if node_status != "waiting":
            return None, None

        config = node.get("config") or {}
        return {
            "pause_payload": {
                "node_id": node_id,
                "node_name": node.get("name") or node_id,
                "prompt_message": config.get("prompt_message") or "Awaiting human approval.",
                "required_fields": config.get("required_fields") or [],
            }
        }, None

    def _finalize_seed_run(
        self,
        run: Run,
        run_status: str,
        fail_message: str,
        trace_plan: dict[str, Any],
        last_finished_at: datetime | None,
    ) -> None:
        if run_status == "paused":
            run.paused_node_id = trace_plan["paused_node_id"]
            run.pause_state_json = {"seeded": True, "paused_node_id": trace_plan["paused_node_id"]}
            run.save(update_fields=["paused_node_id", "pause_state_json"])
        if run_status == "succeeded":
            run.output_json = {"seeded": True}
            run.ended_at = last_finished_at
            run.save(update_fields=["output_json", "ended_at"])
        elif run_status == "failed":
            run.error_message = fail_message
            run.ended_at = last_finished_at
            run.save(update_fields=["error_message", "ended_at"])

    def _toposort(
        self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        node_by_id = self._node_map(nodes)
        if not node_by_id:
            return nodes

        adjacency, indegree = self._edge_graph(node_by_id, edges)
        queue: deque[str] = deque(
            sorted([node_id for node_id, deg in indegree.items() if deg == 0])
        )
        ordered: list[str] = []

        while queue:
            current = queue.popleft()
            ordered.append(current)
            for neighbor in sorted(adjacency[current]):
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered) != len(node_by_id):
            return nodes

        return [node_by_id[node_id] for node_id in ordered]

    def _node_map(self, nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {str(node["id"]): node for node in nodes if node.get("id")}

    def _edge_graph(
        self,
        node_by_id: dict[str, dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> tuple[dict[str, set[str]], dict[str, int]]:
        adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_by_id}
        indegree: dict[str, int] = dict.fromkeys(node_by_id, 0)
        for edge in edges:
            from_id = str(edge.get("from") or "")
            to_id = str(edge.get("to") or "")
            if from_id in node_by_id and to_id in node_by_id and to_id not in adjacency[from_id]:
                adjacency[from_id].add(to_id)
                indegree[to_id] += 1
        return adjacency, indegree
