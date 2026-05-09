from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.db.models import Q

from application.services.commerce import ensure_storefront_profile
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    MemoryConfiguration,
    Organization,
    OrganizationMembership,
    User,
)

DEFAULT_EMAIL = "legacy.glasswear.test@example.com"
DEFAULT_ORG_NAME = "Legacy Glasswear"
DEFAULT_COMPANY_NAME = "Legacy Glasswear"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
PASSWORD_ENV = "LEGACY_TEST_PASSWORD"
EXTERNAL_SOURCE = "legacy-glasswear"
EXTERNAL_REF = "phase-0-company"
EXTERNAL_IDEMPOTENCY_KEY = "legacy-glasswear:phase-0-company:v1"

COMPANY_OBJECTIVE = (
    "Operate the 62-piece Legacy Glasswear limited-frame inventory as a measured "
    "drop engine with backend-owned stock, cash, learning, and reorder discipline."
)

SOURCE_DOCS = [
    "docs/legacy-ultimate-test/legacy-report.md",
    "docs/legacy-ultimate-test/legacy-company-architecture-roadmap.md",
    "docs/architecture/runtime-invariants.md",
]

GEMINI_MEDIA_SOURCE_DOCS = [
    "https://ai.google.dev/gemini-api/docs/image-generation",
    "https://ai.google.dev/gemini-api/docs/imagen",
    "https://ai.google.dev/gemini-api/docs/video",
]

GEMINI_MEDIA_GENERATION_CONTRACT: dict[str, Any] = {
    "status": "planned_phase_1",
    "provider": "google",
    "credential_provider": "google",
    "text_model": DEFAULT_GEMINI_MODEL,
    "image_capabilities": ["gemini_native_image_generation", "imagen"],
    "video_capabilities": ["veo"],
    "artifact_types": ["image", "video"],
    "durable_artifact_owner": "backend",
    "operation_state_owner": "backend",
    "approval_required_before_publish": True,
    "source_docs": GEMINI_MEDIA_SOURCE_DOCS,
    "implementation_route": (
        "Agents request media drafts through backend-owned media generation tools. "
        "The backend persists prompts, provider/model, operation names, output URIs, "
        "asset versions, review status, and errors before any draft can be reused."
    ),
    "pii_boundary": (
        "Gemini media prompts use product, styling, and campaign context only. "
        "Do not send payment details, addresses, or private customer messages."
    ),
}

DEPARTMENTS: list[dict[str, Any]] = [
    {
        "id": "operating-system",
        "label": "Operating System",
        "responsibility": "Sets goals, policies, approvals, priorities, and daily operating rhythm.",
        "tools": ["policy_review", "daily_brief", "approval_queue"],
    },
    {
        "id": "content-studio",
        "label": "Content Studio",
        "responsibility": "Turns inventory, scarcity, and editorial positioning into content drafts.",
        "tools": [
            "caption_draft",
            "creative_brief",
            "gemini_image_draft",
            "gemini_video_brief",
            "creative_asset_review",
            "drop_plan",
        ],
    },
    {
        "id": "social-desk",
        "label": "Social Desk",
        "responsibility": "Plans publication, watches comments and mentions, and captures demand signals.",
        "tools": [
            "publication_queue",
            "approved_media_library",
            "lead_capture",
            "sold_out_interest",
        ],
    },
    {
        "id": "sales-desk",
        "label": "Sales Desk",
        "responsibility": "Qualifies buyers, recommends models, and follows up around checkout.",
        "tools": ["model_recommendation", "opportunity_qualification", "checkout_follow_up"],
    },
    {
        "id": "ops-inventory",
        "label": "Ops & Inventory",
        "responsibility": "Owns stock risk, reservations, fulfillment state, and sold-out evidence.",
        "tools": ["stock_check", "reservation_review", "fulfillment_exception"],
    },
    {
        "id": "finance-procurement",
        "label": "Finance & Procurement",
        "responsibility": "Tracks cash buckets, reorder fund, commissions, and purchase-order drafts.",
        "tools": ["cash_ledger", "reorder_rule", "po_draft"],
    },
]


def _slugify(value: str) -> str:
    return value.lower().replace("&", "and").replace("/", "-").replace(" ", "-").replace("_", "-")


def _graph_checksum(graph_json: dict[str, Any]) -> str:
    json_str = json.dumps(graph_json, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(json_str.encode()).hexdigest()


def _allowed_existing_org_names(email: str) -> set[str]:
    local_part = email.split("@")[0] or "legacy.glasswear.test"
    return {
        DEFAULT_ORG_NAME,
        f"{local_part} Org",
        f"{local_part}'s Organization",
    }


def _department_node(department: dict[str, Any], index: int) -> dict[str, Any]:
    node_id = f"department_{index + 1}_{_slugify(str(department['id']))}"
    label = str(department["label"])
    responsibility = str(department["responsibility"])
    tools = list(department["tools"])
    previous_context = (
        "Start from the company objective and current Legacy operating brief."
        if index == 0
        else "Build on the previous department output and keep the work operational."
    )
    return {
        "id": node_id,
        "type": "agent",
        "name": label,
        "config": {
            "role": label,
            "job_description": responsibility,
            "instructions": " ".join(
                [
                    f"You are the {label} inside Legacy Glasswear.",
                    f"Company objective: {COMPANY_OBJECTIVE}",
                    f"Your responsibility: {responsibility}",
                    previous_context,
                    "Return concrete business work, not commentary about the workflow.",
                    "Do not include private customer data or payment details in model prompts.",
                    "Treat generated image and video concepts as drafts until a backend asset "
                    "record and human approval exist.",
                ]
            ),
            "system_prompt": (
                f"You operate as {label} for Legacy Glasswear. Keep durable truth in "
                "ForgeGraph backend state and produce concise operator-ready work."
            ),
            "provider": "google",
            "model": DEFAULT_GEMINI_MODEL,
            "temperature": 0.35 if index == 0 else 0.25,
            "tools": tools,
            "max_steps": 4,
            "max_tool_calls": max(len(tools), 1),
        },
        "retry_policy": {
            "max_attempts": 1,
            "backoff_ms": 0,
            "backoff_strategy": "fixed",
        },
        "timeout_ms": 180000,
    }


def build_legacy_phase0_graph_json() -> dict[str, Any]:
    nodes = [_department_node(department, index) for index, department in enumerate(DEPARTMENTS)]
    output_node = {
        "id": "final_deliverable",
        "type": "output",
        "name": "Final Deliverable",
        "config": {
            "output_mapping": {
                "deliverable": f"node.{nodes[-1]['id']}.output.final_output",
                "company_objective": "input.objective",
            }
        },
    }
    edges = [{"id": "start-entry", "from": "START", "to": nodes[0]["id"]}]
    edges.extend(
        {
            "id": f"department-edge-{index + 1}",
            "from": node["id"],
            "to": nodes[index + 1]["id"],
        }
        for index, node in enumerate(nodes[:-1])
    )
    edges.extend(
        [
            {"id": "edge-output", "from": nodes[-1]["id"], "to": "final_deliverable"},
            {"id": "edge-end", "from": "final_deliverable", "to": "END"},
        ]
    )

    company_profile = {
        "schema": "company_workspace.v1",
        "companyName": DEFAULT_COMPANY_NAME,
        "companyType": "Limited Inventory Commerce Test",
        "objective": COMPANY_OBJECTIVE,
        "autonomyMode": "assisted",
        "aiAccessMode": "byok",
        "intelligenceProvider": "google",
        "intelligenceModel": DEFAULT_GEMINI_MODEL,
        "companyStatus": "Phase 0 seeded",
        "byokCredentialId": None,
        "departments": [
            {
                "id": department["id"],
                "label": department["label"],
                "responsibility": department["responsibility"],
                "tools": department["tools"],
                "category": "department",
            }
            for department in DEPARTMENTS
        ],
        "skills": [
            "inventory-discipline",
            "scarcity-aware-content",
            "checkout-follow-up",
            "cash-ledger-review",
            "reorder-governance",
            "gemini-media-draft-generation",
        ],
        "geminiMediaGeneration": GEMINI_MEDIA_GENERATION_CONTRACT,
    }

    return {
        "nodes": [*nodes, output_node],
        "edges": edges,
        "metadata": {
            "name": DEFAULT_COMPANY_NAME,
            "description": COMPANY_OBJECTIVE,
            "company_profile": company_profile,
            "legacy_glasswear": {
                "phase": "phase-0",
                "test_type": "iterative-learning-test",
                "inventory_count": 62,
                "anchor_models": ["TAYLOR", "ROBBIE", "VICE", "HUNT", "WATSON", "MAVERICK"],
                "operating_loop": "add_or_fix -> test -> gather_data -> decide -> iterate",
                "source_docs": SOURCE_DOCS,
                "gemini_media_generation": GEMINI_MEDIA_GENERATION_CONTRACT,
                "pii_boundary": (
                    "Gemini receives sanitized business context only; do not send payment "
                    "details, addresses, or private customer data."
                ),
            },
            "runtime_contract": {
                "durable_source_of_truth": "backend",
                "events_are_authoritative": False,
                "engine_owns_durable_state": False,
            },
        },
        "editor_state": {
            "viewport": {"x": 0, "y": 0, "zoom": 1},
            "nodePositions": {
                node["id"]: {
                    "x": 160 if index % 2 == 0 else 520,
                    "y": 120 + index * 180,
                }
                for index, node in enumerate([*nodes, output_node])
            },
        },
    }


def _target_user_state_is_clean(user: User) -> tuple[bool, str]:
    memberships = list(
        OrganizationMembership.objects.select_related("organization")
        .filter(user=user)
        .order_by("created_at")
    )
    if len(memberships) > 1:
        return False, "Target user already has more than one organization membership."

    if memberships and memberships[0].role != "owner":
        return False, "Target user has an existing organization but is not its owner."

    if memberships:
        organization = memberships[0].organization
        if OrganizationMembership.objects.filter(organization=organization).count() > 1:
            return False, "Target user's existing organization has other members."
        if organization.name not in _allowed_existing_org_names(user.email):
            return False, "Target user already has a non-Legacy organization."

    org_ids = [membership.organization_id for membership in memberships]
    visible_graphs = Graph.objects.filter(Q(owner=user) | Q(organization_id__in=org_ids)).distinct()
    unrelated_graphs = [
        graph
        for graph in visible_graphs
        if not _is_legacy_company_graph(graph) and not _is_legacy_support_graph(graph)
    ]
    if unrelated_graphs:
        return False, "Target user already has unrelated company graphs."

    return True, ""


def _is_legacy_company_graph(graph: Graph) -> bool:
    return graph.external_source == EXTERNAL_SOURCE and graph.external_ref == EXTERNAL_REF


def _is_legacy_support_graph(graph: Graph) -> bool:
    """Allow repo-owned Legacy operation graphs created by objective/judge gates."""
    return graph.name.strip().lower().startswith("legacy phase ")


class Command(BaseCommand):
    help = "Seed the Legacy Glasswear Phase 0 clean workspace."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--password", default="")
        parser.add_argument("--json", action="store_true", dest="output_json")

    def handle(self, *args: Any, **options: Any) -> None:
        email = str(options["email"]).strip().lower() or DEFAULT_EMAIL
        password = str(options["password"] or os.environ.get(PASSWORD_ENV, "")).strip()
        output_json = bool(options["output_json"])

        if not password:
            raise CommandError(f"Password is required via --password or {PASSWORD_ENV}.")

        warnings: list[str] = []

        with transaction.atomic():
            user = User.objects.filter(email=email).first()
            created_user = user is None
            if user is None:
                user = User.objects.create_user(email=email, password=password)
                user.is_active = True
                user.save(update_fields=["is_active"])
            else:
                clean, reason = _target_user_state_is_clean(user)
                if not clean:
                    raise CommandError(reason)
                if not user.is_active:
                    user.is_active = True
                    user.save(update_fields=["is_active"])
                    warnings.append("Reactivated existing Legacy user.")
                if not user.check_password(password):
                    user.set_password(password)
                    user.save(update_fields=["password"])
                    warnings.append("Updated existing Legacy user password.")

            user.refresh_from_db()
            memberships = list(OrganizationMembership.objects.filter(user=user))
            if len(memberships) > 1:
                raise CommandError("Target user has more than one organization after creation.")

            if memberships:
                organization = memberships[0].organization
                membership = memberships[0]
            else:
                organization = Organization.objects.create(name=DEFAULT_ORG_NAME)
                membership = OrganizationMembership.objects.create(
                    organization=organization,
                    user=user,
                    role="owner",
                    is_default=True,
                )

            if organization.name != DEFAULT_ORG_NAME:
                organization.name = DEFAULT_ORG_NAME
                organization.save(update_fields=["name", "updated_at"])

            OrganizationMembership.objects.filter(user=user).exclude(pk=membership.pk).delete()
            membership.role = "owner"
            membership.is_default = True
            membership.organization = organization
            membership.save(update_fields=["role", "is_default", "organization", "updated_at"])

            if user.default_organization_id != organization.id:
                user.default_organization = organization
                user.save(update_fields=["default_organization"])

            graph_json = build_legacy_phase0_graph_json()
            graph, created_graph = Graph.objects.update_or_create(
                organization=organization,
                external_source=EXTERNAL_SOURCE,
                external_ref=EXTERNAL_REF,
                defaults={
                    "owner": user,
                    "name": DEFAULT_COMPANY_NAME,
                    "description": COMPANY_OBJECTIVE,
                },
            )
            if created_graph:
                warnings.append("Created Legacy Glasswear company graph.")
            storefront_profile = ensure_storefront_profile(
                company=graph,
                slug=EXTERNAL_SOURCE,
                display_name=DEFAULT_COMPANY_NAME,
                currency="mxn",
                metadata={"source": "legacy_phase_0_seed"},
            )
            MemoryConfiguration.objects.get_or_create(graph=graph)

            latest = graph.versions.order_by("-version").first()
            incoming_checksum = _graph_checksum(graph_json)
            if latest and latest.checksum == incoming_checksum:
                version = latest
                key_already_used = (
                    GraphVersion.objects.filter(
                        graph=graph,
                        external_idempotency_key=EXTERNAL_IDEMPOTENCY_KEY,
                    )
                    .exclude(pk=version.pk)
                    .exists()
                )
                if not version.external_idempotency_key and not key_already_used:
                    version.external_idempotency_key = EXTERNAL_IDEMPOTENCY_KEY
                    version.save(update_fields=["external_idempotency_key"])
            else:
                next_version = (latest.version + 1) if latest else 1
                version = GraphVersion.objects.create(
                    graph=graph,
                    version=next_version,
                    graph_json=graph_json,
                    external_idempotency_key=EXTERNAL_IDEMPOTENCY_KEY if latest is None else "",
                )
                graph.save()
                warnings.append(f"Created Legacy Glasswear graph version {version.version}.")

            membership_count = OrganizationMembership.objects.filter(user=user).count()
            visible_graphs = Graph.objects.filter(Q(owner=user) | Q(organization=organization))
            company_count = (
                visible_graphs.filter(
                    external_source=EXTERNAL_SOURCE,
                    external_ref=EXTERNAL_REF,
                )
                .distinct()
                .count()
            )
            support_graph_count = len(
                [
                    item
                    for item in visible_graphs.distinct()
                    if not _is_legacy_company_graph(item) and _is_legacy_support_graph(item)
                ]
            )
            visible_graph_count = (
                Graph.objects.filter(Q(owner=user) | Q(organization=organization))
                .distinct()
                .count()
            )

            if membership_count != 1:
                raise CommandError("Legacy user does not have exactly one organization membership.")
            if company_count != 1:
                raise CommandError("Legacy user does not have exactly one visible company graph.")

            payload = {
                "user_id": str(user.id),
                "organization_id": str(organization.id),
                "company_id": str(graph.id),
                "storefront_profile_id": str(storefront_profile.id),
                "storefront_slug": storefront_profile.slug,
                "graph_version_id": str(version.id),
                "membership_count": membership_count,
                "company_count": company_count,
                "visible_graph_count": visible_graph_count,
                "support_graph_count": support_graph_count,
                "warnings": warnings,
                "created_user": created_user,
                "created_graph": created_graph,
            }

        if output_json:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded Legacy Glasswear Phase 0 workspace "
                f"(user={email}, organization_id={payload['organization_id']}, "
                f"company_id={payload['company_id']})"
            )
        )
