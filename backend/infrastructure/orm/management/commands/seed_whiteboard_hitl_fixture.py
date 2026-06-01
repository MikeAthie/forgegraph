from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid5

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    ApprovalTask,
    CompanyAccessPolicy,
    CompanyAssignment,
    DepartmentMembership,
    DepartmentRegistry,
    EvaluationRun,
    EvaluationScorecard,
    Graph,
    GraphVersion,
    Organization,
    OrganizationMembership,
    Run,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

FIXTURE_NAMESPACE = UUID("438ee1a1-8c26-4a3d-94ed-7d7efe55344e")
DEFAULT_PASSWORD = "ForgeGraphTest!12345"


def fixture_uuid(prefix: str, label: str) -> UUID:
    return uuid5(FIXTURE_NAMESPACE, f"{prefix}:{label}")


class Command(BaseCommand):
    help = "Seed a generic whiteboard HITL review fixture for Playwright."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--prefix", required=True)
        parser.add_argument("--password", default=DEFAULT_PASSWORD)
        parser.add_argument("--json", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        prefix = str(options["prefix"]).strip().lower()
        if not prefix:
            raise ValueError("--prefix is required")
        password = str(options["password"] or DEFAULT_PASSWORD)
        output_json = bool(options["json"])
        now = timezone.now()

        with transaction.atomic():
            routing_user = self._user(f"{prefix}-routing@example.com", password)
            ensure_default_organization(routing_user)
            routing_user.refresh_from_db()
            organization = routing_user.default_organization
            if organization is None:
                raise RuntimeError("Routing user did not receive a default organization.")

            department_user = self._user(
                f"{prefix}-department@example.com", password, organization=organization
            )
            approver_user = self._user(
                f"{prefix}-approver@example.com", password, organization=organization
            )
            customer_user = self._user(
                f"{prefix}-customer@example.com", password, organization=organization
            )

            for user, role in (
                (routing_user, "owner"),
                (department_user, "member"),
                (approver_user, "member"),
                (customer_user, "viewer"),
            ):
                OrganizationMembership.objects.update_or_create(
                    organization=organization,
                    user=user,
                    defaults={"role": role, "is_default": user.id == routing_user.id},
                )

            company, _ = Graph.objects.update_or_create(
                id=fixture_uuid(prefix, "company"),
                defaults={
                    "owner": routing_user,
                    "organization": organization,
                    "name": f"HITL Simulation {prefix}",
                    "description": "Generic whiteboard HITL review simulation company.",
                    "external_source": "playwright-hitl",
                    "external_ref": prefix,
                },
            )
            CompanyAccessPolicy.objects.update_or_create(
                company=company,
                defaults={
                    "organization": organization,
                    "assignment_required": True,
                    "org_admin_access_enabled": True,
                    "metadata_json": {"fixture": "whiteboard-hitl"},
                },
            )
            for user, role in (
                (routing_user, "admin"),
                (department_user, "member"),
                (approver_user, "member"),
                (customer_user, "viewer"),
            ):
                CompanyAssignment.objects.update_or_create(
                    organization=organization,
                    company=company,
                    user=user,
                    defaults={"role": role, "status": "active", "created_by": routing_user},
                )

            routing_department, _ = DepartmentRegistry.objects.update_or_create(
                id=fixture_uuid(prefix, "department-routing"),
                defaults={
                    "organization": organization,
                    "slug": f"hitl-routing-{prefix}",
                    "name": "Routing",
                    "department_type": "traffic",
                    "lead_user": routing_user,
                    "service_tags_json": ["routing"],
                    "active": True,
                },
            )
            review_department, _ = DepartmentRegistry.objects.update_or_create(
                id=fixture_uuid(prefix, "department-review"),
                defaults={
                    "organization": organization,
                    "slug": f"hitl-review-{prefix}",
                    "name": "Review Desk",
                    "department_type": "strategy",
                    "lead_user": department_user,
                    "active": True,
                },
            )
            for department, user, role in (
                (routing_department, routing_user, "lead"),
                (review_department, department_user, "member"),
            ):
                DepartmentMembership.objects.update_or_create(
                    organization=organization,
                    department=department,
                    user=user,
                    defaults={"role": role, "status": "active", "created_by": routing_user},
                )

            graph_version, _ = GraphVersion.objects.update_or_create(
                id=fixture_uuid(prefix, "company-version"),
                defaults={
                    "graph": company,
                    "version": 1,
                    "graph_json": {
                        "nodes": [
                            {"id": "human_gate", "type": "human_gate", "name": "HITL approval"},
                            {"id": "output", "type": "output", "name": "Output"},
                        ],
                        "edges": [
                            {"from": "START", "to": "human_gate"},
                            {"from": "human_gate", "to": "output"},
                        ],
                    },
                },
            )
            approval_run, _ = Run.objects.update_or_create(
                id=fixture_uuid(prefix, "approval-run"),
                defaults={
                    "owner": routing_user,
                    "organization": organization,
                    "graph_version": graph_version,
                    "status": "paused",
                    "started_at": now - timedelta(minutes=5),
                    "input_json": {"whiteboard_hitl": True},
                    "pause_state_json": {
                        "node_id": "human_gate",
                        "node_name": "HITL approval",
                        "prompt_message": "Approve the board card after department review.",
                    },
                    "paused_node_id": "human_gate",
                },
            )
            approval_task, _ = ApprovalTask.objects.update_or_create(
                id=fixture_uuid(prefix, "approval-task"),
                defaults={
                    "run": approval_run,
                    "node_id": "human_gate",
                    "assignee": approver_user,
                    "status": "pending",
                    "payload": {
                        "whiteboard_id": str(fixture_uuid(prefix, "whiteboard")),
                        "prompt_message": "Approve the board card after department review.",
                        "required_fields": [],
                    },
                    "result": None,
                    "resolved_at": None,
                },
            )
            evaluation_run, _ = EvaluationRun.objects.update_or_create(
                id=fixture_uuid(prefix, "evaluation-run"),
                defaults={
                    "organization": organization,
                    "company": company,
                    "operation": approval_run,
                    "profile_key": "hitl-readiness",
                    "status": "RUNNING",
                    "score": None,
                    "grade": "",
                    "input_refs_json": [
                        {"kind": "whiteboard", "id": str(fixture_uuid(prefix, "whiteboard"))}
                    ],
                    "result_json": {
                        "summary": "Internal evaluation gate details must stay internal."
                    },
                    "created_by": routing_user,
                    "evaluated_at": None,
                },
            )
            scorecard, _ = EvaluationScorecard.objects.update_or_create(
                evaluation=evaluation_run,
                defaults={
                    "organization": organization,
                    "company": company,
                    "dimensions_json": {"readiness": {"score": 0.72}},
                    "composite_score": 72.0,
                    "grade": "B",
                },
            )
            whiteboard, _ = WorkWhiteboard.objects.update_or_create(
                id=fixture_uuid(prefix, "whiteboard"),
                defaults={
                    "organization": organization,
                    "company": company,
                    "status": WorkWhiteboard.STATUS_ONBOARDING,
                    "request_type": "service_request",
                    "client_name": company.name,
                    "request_summary": "Run a generic human-in-the-loop board review simulation.",
                    "objective": "Prove department review, human approval, and automated gate semantics.",
                    "completion_score": 40.0,
                    "created_by": routing_user,
                },
            )
            human_card, _ = TaskRoutingRecord.objects.update_or_create(
                id=fixture_uuid(prefix, "human-card"),
                defaults={
                    "organization": organization,
                    "company": company,
                    "operation": approval_run,
                    "approval_task": approval_task,
                    "to_department": review_department,
                    "assigned_user": department_user,
                    "reason": "Department work requires human approval after review.",
                    "status": "assigned",
                    "priority": "high",
                    "due_at": now + timedelta(hours=4),
                    "resolution_json": {},
                    "idempotency_key": f"whiteboard-hitl:{prefix}:human-card",
                    "metadata_json": {
                        "whiteboard_id": str(whiteboard.id),
                        "title": "HITL approval card",
                        "customer_visible": True,
                        "links": {},
                        "board_card": True,
                    },
                },
            )
            evaluation_card, _ = TaskRoutingRecord.objects.update_or_create(
                id=fixture_uuid(prefix, "evaluation-card"),
                defaults={
                    "organization": organization,
                    "company": company,
                    "operation": approval_run,
                    "to_department": review_department,
                    "reason": "Automated evaluation gate is waiting on scorecard completion.",
                    "status": "ready_for_review",
                    "priority": "normal",
                    "due_at": now + timedelta(hours=6),
                    "resolution_json": {},
                    "idempotency_key": f"whiteboard-hitl:{prefix}:evaluation-card",
                    "metadata_json": {
                        "whiteboard_id": str(whiteboard.id),
                        "title": "Automated evaluation gate",
                        "customer_visible": True,
                        "links": {"evaluation_run_id": str(evaluation_run.id)},
                        "board_card": True,
                    },
                },
            )

        payload = {
            "company_id": str(company.id),
            "whiteboard_id": str(whiteboard.id),
            "human_card_id": str(human_card.id),
            "evaluation_card_id": str(evaluation_card.id),
            "approval_task_id": str(approval_task.id),
            "evaluation_run_id": str(evaluation_run.id),
            "scorecard_id": str(scorecard.id),
            "users": {
                "routing": {"email": routing_user.email, "password": password},
                "department": {"email": department_user.email, "password": password},
                "approver": {"email": approver_user.email, "password": password},
                "customer": {"email": customer_user.email, "password": password},
            },
        }
        if output_json:
            self.stdout.write(json.dumps(payload, sort_keys=True))
        else:
            self.stdout.write(self.style.SUCCESS(f"Seeded whiteboard HITL fixture {prefix}"))

    def _user(
        self,
        email: str,
        password: str,
        *,
        organization: Organization | None = None,
    ) -> User:
        user, created = User.objects.get_or_create(email=email, defaults={"is_active": True})
        user.is_active = True
        if organization is not None:
            user.default_organization = organization
        needs_password_update = created or not user.check_password(password)
        if needs_password_update:
            user.set_password(password)
        update_fields = ["is_active", "default_organization"]
        if needs_password_update:
            update_fields.append("password")
        user.save(update_fields=update_fields)
        return user
