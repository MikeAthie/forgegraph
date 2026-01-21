"""
Seed Phase 4 (Observability MVP) demo data.

Creates a demo user (if none exist), a graph + version, and several runs so the
Runs list + trace viewer can be explored without the Go engine.
"""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max

from infrastructure.orm.models import Graph, GraphVersion, User


class Command(BaseCommand):
    help = "Seed a Phase 4 observability demo graph + runs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner-email",
            type=str,
            default=None,
            help="Email of the user that should own the demo graph/runs (defaults to first user or demo user).",
        )
        parser.add_argument(
            "--owner-password",
            type=str,
            default="ForgeGraphDemo!12345",
            help="Password to use if a demo user is created.",
        )
        parser.add_argument(
            "--graph-name",
            type=str,
            default="Phase 4 Observability Demo",
            help="Name for the demo graph.",
        )

    def handle(self, *args, **options):
        owner_email: str | None = options.get("owner_email")
        owner_password: str = options["owner_password"]
        graph_name: str = options["graph_name"]

        owner: User | None = None
        if owner_email:
            owner_email = owner_email.strip().lower()
            owner = User.objects.filter(email=owner_email).first()

        if owner is None:
            owner = User.objects.order_by("date_joined").first()

        if owner is None:
            demo_email = (owner_email or "demo@example.com").strip().lower()
            owner, _ = User.objects.get_or_create(email=demo_email)
            owner.set_password(owner_password)
            owner.save(update_fields=["password"])
            self.stdout.write(self.style.WARNING(f"Created demo user {owner.email}"))
            self.stdout.write(self.style.WARNING(f"Demo password: {owner_password}"))

        graph_json = {
            "metadata": {
                "name": graph_name,
                "description": "Seeded by seed_phase4_demo (Phase 4 Observability MVP).",
            },
            "nodes": [
                {"id": "start", "type": "prompt", "name": "Start", "config": {}},
                {
                    "id": "http_1",
                    "type": "http",
                    "name": "HTTP Call",
                    "config": {"method": "GET", "url": "https://example.com"},
                },
                {
                    "id": "transform_1",
                    "type": "transform",
                    "name": "Transform",
                    "config": {"expression": "state"},
                },
                {"id": "end", "type": "output", "name": "End", "config": {}},
            ],
            "edges": [
                {"id": "e1", "from": "start", "to": "http_1"},
                {"id": "e2", "from": "http_1", "to": "transform_1"},
                {"id": "e3", "from": "transform_1", "to": "end"},
            ],
        }

        with transaction.atomic():
            graph = Graph.objects.create(
                owner=owner,
                name=graph_name,
                description="Phase 4 demo graph (seeded).",
            )
            latest_version = (
                GraphVersion.objects.filter(graph=graph)
                .aggregate(Max("version"))
                .get("version__max")
                or 0
            )
            version = GraphVersion.objects.create(
                graph=graph,
                version=latest_version + 1,
                graph_json=graph_json,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created demo graph {graph.id} (graph_version {version.id}, v{version.version})"
            )
        )
        self.stdout.write(self.style.SUCCESS("Seeding demo runs..."))

        # A few distinct statuses help validate the Runs list + viewer quickly.
        call_command(
            "seed_run_trace",
            str(version.id),
            owner_email=owner.email,
            run_status="succeeded",
        )
        call_command(
            "seed_run_trace",
            str(version.id),
            owner_email=owner.email,
            run_status="failed",
            fail_message="Demo failure (seed_phase4_demo).",
        )
        call_command(
            "seed_run_trace",
            str(version.id),
            owner_email=owner.email,
            run_status="running",
        )

        self.stdout.write(self.style.SUCCESS("Done. Open /runs to view the demo executions."))
