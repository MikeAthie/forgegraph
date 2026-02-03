"""
Stream a live Run + NodeRun trace for a given GraphVersion.

This command is a Phase 4 developer utility for validating WebSocket delta
updates end-to-end (Django Channels + Redis) without the Go engine.

Usage:
  python manage.py stream_run_trace <graph_version_id> --run-status succeeded

Open the run detail page (`/runs/<run_id>`) before starting the command to see
nodes update in real time.
"""

from __future__ import annotations

import time
from collections import deque
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from adapters.ws.runs.broadcast import broadcast_node_run_updated, broadcast_run_updated
from infrastructure.orm.models import GraphVersion, NodeRun, Run, User


class Command(BaseCommand):
    help = "Stream a sample Run + NodeRuns over WebSockets for a GraphVersion."

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
            choices=["succeeded", "failed"],
            default="succeeded",
            help="Overall run status to generate.",
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
            default="Demo node failure (stream_run_trace).",
            help="Error message to attach when failing.",
        )
        parser.add_argument(
            "--delay-ms",
            type=int,
            default=400,
            help="Delay between updates (milliseconds).",
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
        owner: User | None
        if owner_email:
            owner_email = owner_email.strip().lower()
            owner = User.objects.filter(email=owner_email).first()
            if owner is None:
                raise CommandError(f"No user found with email '{owner_email}'.")
        else:
            owner = graph_version.graph.owner
        if owner is None:
            raise CommandError("Run owner could not be resolved.")

        run_status: str = options["run_status"]
        fail_node_id: str | None = options.get("fail_node_id")
        fail_message: str = options["fail_message"]
        delay_ms: int = int(options["delay_ms"])
        delay_s = max(0, delay_ms) / 1000

        graph_json = graph_version.graph_json or {}
        nodes = list(graph_json.get("nodes") or [])
        edges = list(graph_json.get("edges") or [])

        node_order = self._toposort(nodes, edges)
        if not node_order:
            raise CommandError("GraphVersion has no nodes to stream.")

        node_ids_in_order = [
            str(node.get("id") or f"node_{index}") for index, node in enumerate(node_order)
        ]

        fail_index: int | None = None
        if run_status == "failed":
            if fail_node_id is None:
                fail_node_id = node_ids_in_order[-1]
            if fail_node_id not in node_ids_in_order:
                raise CommandError(
                    f"--fail-node-id '{fail_node_id}' is not present in graph_json.nodes[].id"
                )
            fail_index = node_ids_in_order.index(fail_node_id)

        now = timezone.now()
        run = Run.objects.create(
            owner=owner,
            graph_version=graph_version,
            status="running",
            started_at=now,
            input_json={"seeded": True},
        )
        self.stdout.write(self.style.SUCCESS(f"Created streaming run {run.id}"))
        broadcast_run_updated(run)

        started_at = now
        last_finished_at = started_at

        for index, node in enumerate(node_order):
            node_id = node_ids_in_order[index]
            node_type = str(node.get("type") or "unknown")

            node_started_at = timezone.now()
            node_run = NodeRun.objects.create(
                run=run,
                node_id=node_id,
                node_type=node_type,
                status="running",
                attempt=1,
                started_at=node_started_at,
                input_json={"seeded": True, "node_id": node_id},
            )
            broadcast_node_run_updated(run=run, node_run=node_run)

            time.sleep(delay_s)

            node_ended_at = timezone.now()
            last_finished_at = node_ended_at

            if run_status == "failed" and fail_index is not None and index == fail_index:
                node_run.status = "failed"
                node_run.ended_at = node_ended_at
                node_run.error_json = {
                    "message": fail_message,
                    "node_id": node_id,
                    "node_type": node_type,
                }
                node_run.save(update_fields=["status", "ended_at", "error_json"])
                broadcast_node_run_updated(run=run, node_run=node_run)

                # Mark remaining nodes as skipped for a complete trace.
                for remaining_index in range(index + 1, len(node_order)):
                    remaining_node = node_order[remaining_index]
                    remaining_node_id = node_ids_in_order[remaining_index]
                    remaining_node_type = str(remaining_node.get("type") or "unknown")
                    skipped = NodeRun.objects.create(
                        run=run,
                        node_id=remaining_node_id,
                        node_type=remaining_node_type,
                        status="skipped",
                        attempt=1,
                        input_json={"seeded": True, "node_id": remaining_node_id},
                    )
                    broadcast_node_run_updated(run=run, node_run=skipped)

                run.status = "failed"
                run.ended_at = last_finished_at
                run.error_message = fail_message
                run.save(update_fields=["status", "ended_at", "error_message"])
                broadcast_run_updated(run)
                return

            node_run.status = "succeeded"
            node_run.ended_at = node_ended_at
            node_run.output_json = {"ok": True}
            node_run.save(update_fields=["status", "ended_at", "output_json"])
            broadcast_node_run_updated(run=run, node_run=node_run)

            time.sleep(delay_s)

        run.status = "succeeded"
        run.ended_at = last_finished_at
        run.output_json = {"seeded": True}
        run.save(update_fields=["status", "ended_at", "output_json"])
        broadcast_run_updated(run)

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
