from __future__ import annotations

import json
from argparse import ArgumentParser
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from infrastructure.orm.models import (
    ApprovalTask,
    Graph,
    MemoryObservation,
    NodeRun,
    Run,
    TaskRecord,
    User,
)

FIXTURE_NAMESPACE = UUID("3d4f7f61-48e6-48a8-99eb-799181e9e0cc")


def fixture_uuid(*parts: object) -> UUID:
    return uuid5(FIXTURE_NAMESPACE, ":".join(str(part) for part in parts))


def parse_timestamp(value: object) -> Any:
    if not isinstance(value, str) or not value.strip():
        return timezone.now()
    parsed = parse_datetime(value)
    if parsed is None:
        return timezone.now()
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed)
    return parsed


class Command(BaseCommand):
    help = "Seed a completed backend-owned operation for Playwright strategy report tests."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--input", required=True)
        parser.add_argument("--json", action="store_true")

    def _load_payload(self, input_value: object) -> dict[str, Any]:
        input_path = Path(str(input_value))
        if not input_path.exists():
            raise CommandError(f"Input file not found: {input_path}")
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise CommandError("Input payload must be a JSON object.")
        return payload

    def _fixture_identity(self, payload: dict[str, Any]) -> tuple[str, str]:
        email = str(payload.get("email") or "").strip().lower()
        company_id = str(payload.get("company_id") or "").strip()
        if not email or not company_id:
            raise CommandError("email and company_id are required.")
        return email, company_id

    def _fixture_context(self, *, email: str, company_id: str) -> tuple[User, Graph, Any]:
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist as exc:
            raise CommandError(f"User not found: {email}") from exc
        organization = user.default_organization
        if organization is None:
            raise CommandError(f"User {email} does not have a default organization.")
        try:
            company = Graph.objects.get(id=company_id, organization=organization)
        except Graph.DoesNotExist as exc:
            raise CommandError(f"Company not found for user organization: {company_id}") from exc
        version = company.versions.order_by("-version").first()
        if version is None:
            raise CommandError(f"Company {company_id} does not have a setup version.")
        return user, company, version

    def handle(self, *args: Any, **options: Any) -> None:
        payload = self._load_payload(options["input"])
        email, company_id = self._fixture_identity(payload)

        with transaction.atomic():
            user, company, version = self._fixture_context(email=email, company_id=company_id)
            organization = user.default_organization

            operation_payload = payload.get("operation")
            if not isinstance(operation_payload, dict):
                raise CommandError("operation payload is required.")

            operation_id = UUID(
                str(
                    operation_payload.get("id")
                    or fixture_uuid(company.id, operation_payload.get("name", "strategy-report"))
                )
            )
            input_json = _dict(operation_payload.get("input_json"))
            output_json = _dict(operation_payload.get("output_json"))
            client_context = _dict(payload.get("client_context"))
            if client_context:
                input_json.setdefault("client_context", client_context)
                output_json.setdefault("client_context", client_context)

            operation, _ = Run.objects.update_or_create(
                id=operation_id,
                defaults={
                    "owner": user,
                    "organization": organization,
                    "graph_version": version,
                    "status": "succeeded",
                    "started_at": parse_timestamp(operation_payload.get("started_at")),
                    "ended_at": parse_timestamp(operation_payload.get("ended_at")),
                    "input_json": input_json,
                    "output_json": output_json,
                    "error_message": "",
                    "last_progress_at": timezone.now(),
                },
            )

            _seed_tasks(operation=operation, payload=payload)
            _seed_approvals(operation=operation, payload=payload)
            memory_count = _seed_memory(
                operation=operation,
                company=company,
                payload=payload,
            )

        result = {
            "company_id": str(company.id),
            "operation_id": str(operation.id),
            "memory_count": memory_count,
        }
        if options["json"]:
            self.stdout.write(json.dumps(result))
        else:
            self.stdout.write(f"Seeded strategy report operation {operation.id}")


def _seed_tasks(*, operation: Run, payload: dict[str, Any]) -> None:
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        return
    for index, item in enumerate(tasks):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or f"Task {index + 1}")
        node_id = str(item.get("department_id") or item.get("source_id") or f"task-{index + 1}")
        node_run_id = fixture_uuid(operation.id, "node-run", index, title)
        started_at = parse_timestamp(item.get("started_at"))
        ended_at = parse_timestamp(item.get("ended_at"))
        node_run, _ = NodeRun.objects.update_or_create(
            id=node_run_id,
            defaults={
                "run": operation,
                "node_id": node_id,
                "node_type": "agent",
                "status": "succeeded" if item.get("status") != "failed" else "failed",
                "attempt": 1,
                "started_at": started_at,
                "ended_at": ended_at,
                "input_json": {
                    "task": title,
                    "department": item.get("department_name"),
                    "skill": item.get("skill"),
                    "tool": item.get("tool"),
                },
                "output_json": {
                    "summary": item.get("summary"),
                    "deliverable": item.get("deliverable"),
                },
            },
        )
        TaskRecord.objects.update_or_create(
            organization=operation.organization,
            external_key=f"strategy-report-fixture:{operation.id}:{index}",
            defaults={
                "execution": operation,
                "agent": None,
                "source_node_id": node_id,
                "title": title,
                "status": "succeeded" if item.get("status") != "failed" else "failed",
                "priority": str(item.get("priority") or "normal"),
                "summary": str(item.get("summary") or ""),
                "current_step": node_run,
                "started_at": started_at,
                "ended_at": ended_at,
            },
        )


def _seed_approvals(*, operation: Run, payload: dict[str, Any]) -> None:
    approvals = payload.get("approvals")
    if not isinstance(approvals, list):
        return
    for index, item in enumerate(approvals):
        if not isinstance(item, dict):
            continue
        approval_id = fixture_uuid(operation.id, "approval", item.get("id") or index)
        ApprovalTask.objects.update_or_create(
            id=approval_id,
            defaults={
                "run": operation,
                "node_id": str(item.get("department_id") or item.get("node_id") or "approval"),
                "assignee": operation.owner,
                "status": str(item.get("status") or "approved"),
                "payload": _dict(item.get("payload")),
                "result": _dict(item.get("result")) or None,
                "resolved_at": parse_timestamp(item.get("resolved_at")),
            },
        )


def _seed_memory(*, operation: Run, company: Graph, payload: dict[str, Any]) -> int:
    memories = payload.get("memory")
    if not isinstance(memories, list):
        return 0
    count = 0
    for index, item in enumerate(memories):
        if not isinstance(item, dict):
            continue
        memory_id = fixture_uuid(operation.id, "memory", item.get("id") or index)
        MemoryObservation.objects.update_or_create(
            id=memory_id,
            defaults={
                "tenant_id": operation.organization_id,
                "graph_id": company.id,
                "run_id": operation.id,
                "session_id": None,
                "agent_id": None,
                "type": str(item.get("type") or item.get("kind") or "case"),
                "title": str(item.get("title") or "Strategy learning"),
                "content": str(item.get("content") or ""),
                "scope": "run",
                "topic_key": str(item.get("topic") or item.get("topic_key") or ""),
                "tool_name": str(item.get("tool_name") or ""),
                "last_seen_at": parse_timestamp(item.get("created_at")),
                "deleted_at": None,
            },
        )
        count += 1
    return count


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
