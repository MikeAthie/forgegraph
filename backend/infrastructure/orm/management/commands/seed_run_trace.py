"""
Seed a deterministic Run + NodeRun trace for a given GraphVersion.

This is a developer utility for Phase 4 (Observability MVP) so the UI can be
validated without the Go engine.
"""

from __future__ import annotations

from collections import deque
from datetime import timedelta
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
        try:
            graph_version_id = UUID(options["graph_version_id"])
        except ValueError as exc:
            raise CommandError("graph_version_id must be a valid UUID.") from exc

        try:
            graph_version = GraphVersion.objects.select_related("graph__owner").get(
                id=graph_version_id
            )
        except GraphVersion.DoesNotExist as exc:
            raise CommandError(f"GraphVersion '{graph_version_id}' does not exist.") from exc

        owner_email: str | None = options.get("owner_email")
        if owner_email:
            owner_email = owner_email.strip().lower()
            owner = User.objects.filter(email=owner_email).first()
            if not owner:
                raise CommandError(f"No user found with email '{owner_email}'.")
        else:
            owner = graph_version.graph.owner

        run_status: str = options["run_status"]
        fail_node_id: str | None = options.get("fail_node_id")
        paused_node_id: str | None = options.get("paused_node_id")
        fail_message: str = options["fail_message"]

        graph_json = graph_version.graph_json or {}
        nodes = list(graph_json.get("nodes") or [])
        edges = list(graph_json.get("edges") or [])

        node_order = self._toposort(nodes, edges)
        node_ids_in_order = [
            str(node.get("id") or f"node_{index}") for index, node in enumerate(node_order)
        ]

        fail_index: int | None = None
        paused_index: int | None = None

        if run_status == "failed":
            if fail_node_id is None:
                fail_node_id = node_ids_in_order[-1] if node_ids_in_order else None

            if fail_node_id and fail_node_id not in node_ids_in_order:
                raise CommandError(
                    f"--fail-node-id '{fail_node_id}' is not present in graph_json.nodes[].id"
                )
            if fail_node_id:
                fail_index = node_ids_in_order.index(fail_node_id)
        elif run_status == "paused":
            if paused_node_id is None:
                # Prefer pausing at a Human Gate if present, otherwise pause at the last node.
                human_gate = next(
                    (n for n in node_order if str(n.get("type")) == "human_gate"), None
                )
                paused_node_id = (
                    str(human_gate.get("id")) if human_gate and human_gate.get("id") else None
                )

            if paused_node_id is None:
                paused_node_id = node_ids_in_order[-1] if node_ids_in_order else None

            if paused_node_id and paused_node_id not in node_ids_in_order:
                raise CommandError(
                    f"--paused-node-id '{paused_node_id}' is not present in graph_json.nodes[].id"
                )
            if paused_node_id:
                paused_index = node_ids_in_order.index(paused_node_id)

        now = timezone.now()
        started_at = None
        ended_at = None

        if run_status in {"running", "paused", "succeeded", "failed"}:
            started_at = now - timedelta(seconds=max(1, len(node_order)))

        with transaction.atomic():
            run = Run.objects.create(
                owner=owner,
                graph_version=graph_version,
                status=run_status,
                started_at=started_at,
                ended_at=ended_at,
                input_json={"seeded": True},
                output_json=None,
                error_message="",
            )

            offset_ms = 0
            last_finished_at = started_at

            for index, node in enumerate(node_order):
                node_id = node_ids_in_order[index]
                node_type = str(node.get("type") or "unknown")

                node_status = "pending"
                node_started_at = None
                node_ended_at = None
                node_output_json = None
                node_error_json = None

                if run_status == "pending":
                    node_status = "pending"
                elif run_status == "running":
                    node_status = "running" if index == len(node_order) - 1 else "succeeded"
                elif run_status == "paused":
                    if paused_index is None:
                        node_status = "waiting"
                    elif index < paused_index:
                        node_status = "succeeded"
                    elif index == paused_index:
                        node_status = "waiting"
                    else:
                        node_status = "pending"
                elif run_status == "succeeded":
                    node_status = "succeeded"
                elif run_status == "failed":
                    if fail_index is None:
                        node_status = "failed"
                    elif index < fail_index:
                        node_status = "succeeded"
                    elif index == fail_index:
                        node_status = "failed"
                    else:
                        node_status = "skipped"

                if run_status in {"running", "paused", "succeeded", "failed"} and node_status in {
                    "succeeded",
                    "running",
                    "failed",
                    "waiting",
                }:
                    node_started_at = (started_at or now) + timedelta(milliseconds=offset_ms)
                    duration_ms = 250 + (index * 50)
                    offset_ms += duration_ms

                    if node_status in {"succeeded", "failed"}:
                        node_ended_at = (started_at or now) + timedelta(milliseconds=offset_ms)
                        last_finished_at = node_ended_at

                if node_status == "succeeded":
                    node_output_json = {"ok": True}
                elif node_status == "failed":
                    node_error_json = {
                        "message": fail_message,
                        "node_id": node_id,
                        "node_type": node_type,
                    }
                elif node_status == "waiting":
                    config = node.get("config") or {}
                    prompt_message = config.get("prompt_message") or "Awaiting human approval."
                    required_fields = config.get("required_fields") or []
                    node_output_json = {
                        "pause_payload": {
                            "node_id": node_id,
                            "node_name": node.get("name") or node_id,
                            "prompt_message": prompt_message,
                            "required_fields": required_fields,
                        }
                    }

                NodeRun.objects.create(
                    run=run,
                    node_id=node_id,
                    node_type=node_type,
                    status=node_status,
                    attempt=1,
                    started_at=node_started_at,
                    ended_at=node_ended_at,
                    input_json={"seeded": True, "node_id": node_id},
                    output_json=node_output_json,
                    error_json=node_error_json,
                )

            if run_status == "paused":
                run.paused_node_id = paused_node_id
                run.pause_state_json = {"seeded": True, "paused_node_id": paused_node_id}
                run.save(update_fields=["paused_node_id", "pause_state_json"])

            if run_status == "succeeded":
                run.output_json = {"seeded": True}
                run.ended_at = last_finished_at
                run.save(update_fields=["output_json", "ended_at"])
            elif run_status == "failed":
                run.error_message = fail_message
                run.ended_at = last_finished_at
                run.save(update_fields=["error_message", "ended_at"])

        self.stdout.write(
            self.style.SUCCESS(f"Created run {run.id} for graph_version {graph_version.id}")
        )

    def _toposort(self, nodes: list[dict], edges: list[dict]) -> list[dict]:
        node_by_id: dict[str, dict] = {}
        for node in nodes:
            node_id = node.get("id")
            if not node_id:
                continue
            node_by_id[str(node_id)] = node

        if not node_by_id:
            return nodes

        adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_by_id}
        indegree: dict[str, int] = dict.fromkeys(node_by_id, 0)

        for edge in edges:
            from_id = edge.get("from")
            to_id = edge.get("to")
            if not from_id or not to_id:
                continue
            from_id = str(from_id)
            to_id = str(to_id)
            if from_id not in node_by_id or to_id not in node_by_id:
                continue
            if to_id in adjacency[from_id]:
                continue
            adjacency[from_id].add(to_id)
            indegree[to_id] += 1

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
