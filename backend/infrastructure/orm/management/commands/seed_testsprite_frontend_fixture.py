"""
Seed deterministic frontend fixtures for hosted TestSprite browser runs.

The generated TestSprite frontend cases currently log in as ``test@example.com``
and then look for specific visible strings without always performing the
described mutation. This command creates a stable dataset for that user so the
hosted suite exercises the intended pages instead of failing on empty-state
fixtures or selecting non-editable records.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from application.services.tenancy import ensure_default_organization
from infrastructure.crypto.encryption import encrypt_api_key
from infrastructure.orm.models import (
    APIKey,
    ApprovalTask,
    Graph,
    GraphVersion,
    MemoryObservation,
    OrganizationMembership,
    PromptTemplate,
    Run,
    User,
)

DEFAULT_EMAIL = "test@example.com"
DEFAULT_PASSWORD = "WY3QGTJ7@q5eYq3"
PROMPT_ID = UUID("00000000-0000-0000-0000-00000000f101")
GRAPH_ID = UUID("00000000-0000-0000-0000-00000000f102")
GRAPH_VERSION_ID = UUID("00000000-0000-0000-0000-00000000f103")
RUN_ID = UUID("00000000-0000-0000-0000-00000000f104")
APPROVAL_ID = UUID("00000000-0000-0000-0000-00000000f105")
OBSERVATION_ID = UUID("00000000-0000-0000-0000-00000000f106")


def _frontend_fixture_graph_json() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "START", "type": "start", "name": "Start", "position": {"x": 80, "y": 120}},
            {
                "id": "human_gate_1",
                "type": "human_gate",
                "name": "Approval successfully submitted",
                "position": {"x": 320, "y": 120},
                "config": {
                    "approval_message": "Approval successfully submitted",
                    "required_fields": [],
                },
            },
            {"id": "output", "type": "output", "name": "Output", "position": {"x": 560, "y": 120}},
        ],
        "edges": [
            {"id": "e-start-gate", "source": "START", "target": "human_gate_1"},
            {"id": "e-gate-output", "source": "human_gate_1", "target": "output"},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


class Command(BaseCommand):
    help = "Seed deterministic frontend TestSprite fixtures for the shared test user."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--password", default=DEFAULT_PASSWORD)

    def handle(self, *args, **options):
        email = str(options["email"]).strip().lower() or DEFAULT_EMAIL
        password = str(options["password"]) or DEFAULT_PASSWORD
        now = timezone.now()
        prompt_timestamp = now + timedelta(minutes=2)

        with transaction.atomic():
            user, created = User.objects.get_or_create(
                email=email,
                defaults={"is_active": True},
            )
            user.is_active = True
            if created or not user.check_password(password):
                user.set_password(password)
                user.save(update_fields=["password", "is_active"])
            else:
                user.save(update_fields=["is_active"])

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
            OrganizationMembership.objects.filter(user=user).exclude(organization=organization).update(
                is_default=False
            )

            prompt_defaults = {
                "owner": user,
                "title": "TC001 editable prompt",
                "description": "Seeded prompt for hosted TestSprite prompt editing coverage.",
                "category": "other",
                "content": "Original prompt content - TC001",
                "variables_schema": {},
                "version": "1.0.0",
                "license": "MIT",
                "visibility": "private",
            }
            prompt, _ = PromptTemplate.objects.update_or_create(id=PROMPT_ID, defaults=prompt_defaults)
            PromptTemplate.objects.filter(id=prompt.id).update(
                created_at=prompt_timestamp,
                updated_at=prompt_timestamp,
            )

            graph_defaults = {
                "owner": user,
                "name": "Frontend TestSprite Approval Fixture",
                "description": "Stable graph used to back approvals and memory fixture data.",
                "external_source": "testsprite",
                "external_ref": "frontend-fixture",
            }
            graph, _ = Graph.objects.update_or_create(id=GRAPH_ID, defaults=graph_defaults)

            graph_version_defaults = {
                "graph": graph,
                "version": 1,
                "graph_json": _frontend_fixture_graph_json(),
            }
            graph_version, _ = GraphVersion.objects.update_or_create(
                id=GRAPH_VERSION_ID,
                defaults=graph_version_defaults,
            )

            run_defaults = {
                "owner": user,
                "graph_version": graph_version,
                "status": "paused",
                "started_at": now - timedelta(minutes=10),
                "input_json": {"source": "testsprite"},
                "output_json": None,
                "error_message": "",
                "trace_id": "testsprite-frontend-fixture",
                "pause_state_json": {
                    "waiting_for_approval": True,
                    "node_id": "human_gate_1",
                },
                "paused_node_id": "human_gate_1",
            }
            run, _ = Run.objects.update_or_create(id=RUN_ID, defaults=run_defaults)

            ApprovalTask.objects.update_or_create(
                id=APPROVAL_ID,
                defaults={
                    "run": run,
                    "node_id": "human_gate_1",
                    "assignee": user,
                    "status": "pending",
                    "payload": {
                        "prompt_message": "Approval successfully submitted",
                        "required_fields": [],
                    },
                    "result": None,
                    "resolved_at": None,
                },
            )

            MemoryObservation.objects.update_or_create(
                id=OBSERVATION_ID,
                defaults={
                    "tenant_id": organization.id,
                    "graph_id": graph.id,
                    "run_id": run.id,
                    "session_id": None,
                    "agent_id": None,
                    "type": "validation_error",
                    "title": "Validation Error: Invalid tags or metadata",
                    "content": "Hosted TestSprite fixture observation for tc004-tag visibility.",
                    "scope": "run",
                    "topic_key": "tc004-tag",
                    "tool_name": "testsprite_frontend_fixture",
                    "revision_count": 1,
                    "duplicate_count": 0,
                    "last_seen_at": now + timedelta(minutes=1),
                    "memory_chunk": None,
                    "deleted_at": None,
                },
            )

            APIKey.objects.update_or_create(
                organization=organization,
                user=user,
                provider="openai",
                name="TC002 metadata update",
                defaults={
                    "encrypted_key": encrypt_api_key("sk-testsprite-frontend-fixture-0001"),
                    "encrypted_refresh_token": None,
                    "token_expires_at": None,
                    "token_metadata": {"source": "testsprite_frontend_fixture"},
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded frontend TestSprite fixture "
                f"(user={email}, org={organization.id}, prompt={PROMPT_ID}, run={RUN_ID})"
            )
        )
