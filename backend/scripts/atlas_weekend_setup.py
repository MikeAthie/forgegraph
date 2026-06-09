from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from django.db import transaction
from django.utils import timezone

from application.services.operating_model_packs import install_pack_for_company
from application.services.tenancy import set_default_organization
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    CompanyOperatingModelInstallation,
    DepartmentMembership,
    DepartmentRegistry,
    Graph,
    GraphVersion,
    Organization,
    OrganizationMembership,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    User,
    WorkWhiteboard,
)

EMAIL = "hermes.operator+atlas@forgegraph.local"
ORG_NAME = "Intuition Labs"
COMPANY_NAME = "Atlas Mkt"
PACK_ID = "digital_marketing_pro.v1"
SOURCE = "atlas-weekend-setup.v1"

DEPARTMENTS = [
    (
        "strategy_research",
        "Strategy & Research",
        ["atlas", "digital_marketing_pro", "strategy", "research"],
    ),
    (
        "brand_content",
        "Brand & Content",
        ["atlas", "digital_marketing_pro", "brand", "content", "creative"],
    ),
    (
        "channel_execution",
        "Channel Execution",
        ["atlas", "digital_marketing_pro", "channels", "launch", "connectors"],
    ),
    (
        "crm_lifecycle",
        "CRM & Lifecycle",
        ["atlas", "digital_marketing_pro", "crm", "lifecycle", "consent"],
    ),
    (
        "analytics_performance",
        "Analytics & Performance",
        ["atlas", "digital_marketing_pro", "analytics", "performance", "measurement"],
    ),
    (
        "qa_compliance",
        "QA & Compliance",
        ["atlas", "digital_marketing_pro", "qa", "compliance", "risk"],
    ),
    (
        "client_approval_ops",
        "Client/Approval Ops",
        ["atlas", "digital_marketing_pro", "client", "approval", "ops"],
    ),
]

DELIVERABLES = [
    {
        "type": "client_brief",
        "title": "Weekend Client Brief",
        "department": "strategy_research",
        "summary": "A client-ready brief for selling a weekend Atlas marketing sprint.",
        "sections": [
            "Objective: turn a prospect's messy growth request into a governed ForgeGraph service engagement.",
            "Audience: owner-led B2B service teams that need messaging, launch readiness, and measurable follow-up quickly.",
            "Inputs still needed: target customer, offer/pricing, proof points, channels already available, approval contact.",
            "Weekend outcome: an approval-ready package that can be shown to a client before production connector execution.",
        ],
    },
    {
        "type": "scope_of_work",
        "title": "Atlas Weekend Sprint Scope of Work",
        "department": "client_approval_ops",
        "summary": "A sellable SOW for a fixed weekend launch-prep sprint.",
        "sections": [
            "Package: Weekend Launch Readiness Sprint.",
            "Included: strategy brief, message house, launch checklist, connector gap report, measurement plan, approval packet, and campaign launch package.",
            "Not included: live media spend, unapproved production publishing, credential collection outside ForgeGraph governance, or unsupported connector workarounds.",
            "Acceptance: client can approve the strategy/content/measurement package or request one revision round.",
        ],
    },
    {
        "type": "strategy_brief",
        "title": "Weekend Strategy Brief",
        "department": "strategy_research",
        "summary": "Positioning and channel thesis for the Atlas weekend sprint.",
        "sections": [
            "Thesis: sell an operator-grade marketing sprint focused on clarity, launch readiness, and evidence-backed next actions.",
            "Primary promise: Atlas converts intake into client-visible deliverables and approval gates inside ForgeGraph.",
            "Channel rationale: use LinkedIn/email/landing-page copy first because they can be reviewed without live connector credentials.",
            "Risk: do not imply production execution until credentials, approvals, and channel policies are confirmed.",
        ],
    },
    {
        "type": "message_house",
        "title": "Atlas Message House",
        "department": "brand_content",
        "summary": "Core claims, proof points, objections, and CTAs for selling Atlas marketing services.",
        "sections": [
            "Core message: Atlas is a ForgeGraph-operated marketing service that produces governed, client-ready deliverables fast.",
            "Proof points: company-scoped work graph, department routing, approval lifecycle, deliverable history, and connector honesty.",
            "Objections: 'Can it execute?' Answer: Atlas separates approved plans from production execution and exposes connector gaps clearly.",
            "CTA: Book a Weekend Launch Readiness Sprint.",
        ],
    },
    {
        "type": "channel_copy_pack",
        "title": "Weekend Channel Copy Pack",
        "department": "brand_content",
        "summary": "Draft LinkedIn/email/landing copy for the first Atlas sales motion.",
        "sections": [
            "LinkedIn post: 'Most marketing ops fail before launch because approvals, claims, and measurement are scattered. Atlas keeps them inside a ForgeGraph company workspace.'",
            "Outbound email subject: 'A weekend launch-readiness sprint for your next campaign'.",
            "Landing hero: 'Turn a rough marketing request into an approval-ready launch package by Monday.'",
            "CTA language: 'Start with a brief, see the deliverables, approve the next sprint.'",
        ],
    },
    {
        "type": "launch_readiness_checklist",
        "title": "Weekend Launch Readiness Checklist",
        "department": "channel_execution",
        "summary": "Ready/blocked checklist for client-safe campaign launch preparation.",
        "sections": [
            "Ready: strategy, messaging, draft copy, measurement assumptions, approval packet.",
            "Needs client input: target account list, brand voice examples, offer constraints, required disclaimers.",
            "Blocked for production: live credentials, ad account permissions, sending domains, tracking pixels, and final approval.",
            "Decision: proceed with sandbox/planning package now; hold production execution until connector and approval gates pass.",
        ],
    },
    {
        "type": "connector_gap_report",
        "title": "Connector Gap Report",
        "department": "client_approval_ops",
        "summary": "Honest production-readiness disclosure for missing credentials/connectors.",
        "sections": [
            "Email connector: needed before live sends; planning copy can proceed now.",
            "Social connector: needed before scheduled publishing; draft posts can proceed now.",
            "Analytics connector: needed before measured performance reporting; measurement plan can proceed now.",
            "Impact: connector gaps do not block sales deliverables, but they do block claims of live execution.",
        ],
    },
    {
        "type": "measurement_plan",
        "title": "Weekend Measurement Plan",
        "department": "analytics_performance",
        "summary": "KPI and evidence plan for turning the sprint into a measurable service.",
        "sections": [
            "Primary KPI: qualified replies or booked discovery calls from approved launch assets.",
            "Secondary KPIs: landing-page conversion, email reply rate, social engagement, approval cycle time.",
            "Baseline requirement: capture current traffic/reply/booked-call numbers before live execution.",
            "Reporting cadence: first readout 7 days after production launch; optimization roadmap after enough signal exists.",
        ],
    },
    {
        "type": "approval_packet",
        "title": "Client Approval Packet",
        "department": "client_approval_ops",
        "summary": "Exact approval request for the weekend sprint package.",
        "sections": [
            "Approve: strategy brief, message house, channel copy drafts, launch checklist, connector gap report, measurement plan.",
            "Approve with edits: provide line comments and one consolidated revision request.",
            "Reject: identify which claim, channel, or audience assumption is unsafe or off-brand.",
            "Decision needed by Sunday evening to package final materials for Monday follow-up.",
        ],
    },
    {
        "type": "campaign_launch_package",
        "title": "Weekend Campaign Launch Package",
        "department": "channel_execution",
        "summary": "Unified handoff package combining strategy, copy, readiness, approval, and measurement.",
        "sections": [
            "Package contents: brief, SOW, strategy, message house, copy pack, checklist, connector gap report, measurement plan, approval packet.",
            "Client-safe framing: this is an approval-ready launch package, not a claim of live deployment.",
            "Production next step: collect credentials/permissions and execute approved channel tasks through ForgeGraph.",
            "Weekend success definition: Atlas has durable deliverables that can be used to sell the first marketing services sprint.",
        ],
    },
]


def graph_json(
    departments: dict[str, DepartmentRegistry], deliverables: list[ServiceDeliverable]
) -> dict[str, Any]:
    nodes = []
    edges = []
    for idx, (slug, label, _tags) in enumerate(DEPARTMENTS):
        nodes.append(
            {
                "id": f"dept_{slug}",
                "type": "agent",
                "name": label,
                "config": {
                    "department_slug": slug,
                    "department_id": str(departments[slug].id),
                    "role": "atlas_agency_department",
                },
                "position": {"x": 100 + idx * 180, "y": 120},
            }
        )
    nodes.append(
        {
            "id": "approval_gate_weekend_package",
            "type": "human_gate",
            "name": "Weekend Package Approval Gate",
            "config": {"approval_scope": "weekend_launch_readiness_sprint"},
            "position": {"x": 760, "y": 360},
        }
    )
    nodes.append(
        {
            "id": "final_weekend_deliverable_package",
            "type": "output",
            "name": "Final Weekend Campaign Launch Package",
            "config": {"deliverable_ids": [str(item.id) for item in deliverables]},
            "position": {"x": 980, "y": 360},
        }
    )
    for slug, _label, _tags in DEPARTMENTS:
        edges.append({"id": f"edge_start_{slug}", "from": "START", "to": f"dept_{slug}"})
        edges.append(
            {
                "id": f"edge_{slug}_approval",
                "from": f"dept_{slug}",
                "to": "approval_gate_weekend_package",
            }
        )
    edges.append(
        {
            "id": "edge_approval_output",
            "from": "approval_gate_weekend_package",
            "to": "final_weekend_deliverable_package",
        }
    )
    edges.append(
        {"id": "edge_output_end", "from": "final_weekend_deliverable_package", "to": "END"}
    )
    return {
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "company_profile": {
                "name": COMPANY_NAME,
                "departments": [
                    {"id": str(departments[slug].id), "slug": slug, "name": label}
                    for slug, label, _tags in DEPARTMENTS
                ],
            },
            "atlas": {
                "pack_id": PACK_ID,
                "service_motion": "weekend_launch_readiness_sprint",
                "deliverable_count": len(deliverables),
                "source": SOURCE,
            },
        },
    }


def markdown_for(item: dict[str, Any], company: Graph, engagement: ServiceEngagement) -> str:
    body = [
        f"# {item['title']}",
        "",
        f"**Company:** {company.name}",
        "**Service:** Weekend Launch Readiness Sprint",
        f"**Engagement ID:** {engagement.id}",
        f"**Deliverable type:** `{item['type']}`",
        "",
        f"## Summary\n{item['summary']}",
        "",
        "## Client-ready content",
    ]
    body.extend(f"- {section}" for section in item["sections"])
    body.extend(
        [
            "",
            "## Evidence / caveats",
            "- Produced inside ForgeGraph as part of the Atlas Mkt company workspace.",
            "- Connector limitations are represented explicitly rather than hidden or treated as blockers to planning deliverables.",
            "- Production launch claims require final client approval and live connector readiness.",
        ]
    )
    return "\n".join(body) + "\n"


@transaction.atomic
def run() -> dict[str, Any]:  # noqa: C901
    password = os.environ.get("ATLAS_OPERATOR_PASSWORD") or User.objects.make_random_password(
        length=32
    )
    user, user_created = User.objects.get_or_create(email=EMAIL, defaults={})
    user.set_password(password)
    user.save(update_fields=["password"])

    org, org_created = Organization.objects.get_or_create(name=ORG_NAME)
    membership, _ = OrganizationMembership.objects.get_or_create(
        organization=org,
        user=user,
        defaults={"role": "owner", "is_default": True},
    )
    if membership.role != "owner" or not membership.is_default:
        membership.role = "owner"
        membership.is_default = True
        membership.save(update_fields=["role", "is_default", "updated_at"])
    set_default_organization(user, org.id)
    user.refresh_from_db()

    company, company_created = Graph.objects.get_or_create(
        organization=org,
        external_source="atlas",
        external_ref="atlas-mkt",
        defaults={
            "owner": user,
            "name": COMPANY_NAME,
            "description": "ForgeGraph-native Atlas marketing company used to sell and deliver governed marketing services.",
        },
    )
    changed = False
    if company.name != COMPANY_NAME:
        company.name = COMPANY_NAME
        changed = True
    if company.owner_id != user.id:
        company.owner = user
        changed = True
    if changed:
        company.save()

    departments: dict[str, DepartmentRegistry] = {}
    for slug, label, tags in DEPARTMENTS:
        dept, _ = DepartmentRegistry.objects.get_or_create(
            organization=org,
            slug=slug,
            defaults={"name": label},
        )
        dept.name = label
        dept.department_type = "agency_department"
        dept.service_tags_json = tags
        dept.active = True
        meta = dict(dept.metadata_json or {})
        meta.update(
            {
                "subject_id": slug,
                "operating_model_pack_id": PACK_ID,
                "company_id": str(company.id),
                "source": SOURCE,
            }
        )
        dept.metadata_json = meta
        dept.save()
        DepartmentMembership.objects.get_or_create(
            organization=org,
            department=dept,
            user=user,
            defaults={"role": "lead", "status": "active", "created_by": user},
        )
        departments[slug] = dept

    pack_status = "installed"
    try:
        installation = install_pack_for_company(
            company=company, user=user, pack_id=PACK_ID, role="primary"
        )
    except Exception as exc:  # keep setup moving; surface exact error in evidence
        installation = CompanyOperatingModelInstallation.objects.filter(
            company=company, pack_id=PACK_ID
        ).first()
        pack_status = f"install_error:{exc.__class__.__name__}:{exc}"

    catalog, _ = ServiceCatalogItem.objects.get_or_create(
        organization=org,
        slug="atlas-weekend-launch-readiness-sprint",
        defaults={
            "title": "Atlas Weekend Launch Readiness Sprint",
            "description": "Fixed-scope ForgeGraph-native marketing service package that turns intake into approval-ready deliverables by the end of the weekend.",
            "status": "active",
            "visibility": "organization",
            "audience": "B2B service teams",
            "created_by": user,
        },
    )
    catalog.title = "Atlas Weekend Launch Readiness Sprint"
    catalog.description = "Fixed-scope ForgeGraph-native marketing service package that turns intake into approval-ready deliverables by the end of the weekend."
    catalog.status = "active"
    catalog.visibility = "organization"
    catalog.audience = "B2B service teams"
    catalog.required_pack_ids_json = [PACK_ID]
    catalog.deliverables_schema_json = [
        {"type": item["type"], "title": item["title"], "department": item["department"]}
        for item in DELIVERABLES
    ]
    catalog.pricing_metadata_json = {
        "package": "weekend_sprint",
        "positioning": "fixed scope, approval-ready by Monday",
        "currency": "USD",
    }
    catalog.metadata_json = {"source": SOURCE, "forgegraph_native": True}
    catalog.save()

    engagement, _ = ServiceEngagement.objects.get_or_create(
        company=company,
        source_key="atlas-weekend-launch-readiness-sprint:v1",
        defaults={
            "organization": org,
            "catalog_item": catalog,
            "status": "in_progress",
            "customer_status": "working",
            "requested_by": user,
            "assigned_operator": user,
            "started_at": timezone.now(),
        },
    )
    engagement.organization = org
    engagement.catalog_item = catalog
    engagement.status = "in_progress"
    engagement.customer_status = "review_ready"
    engagement.public_summary = "Atlas Mkt weekend sprint producing client-ready marketing service deliverables inside ForgeGraph."
    engagement.internal_notes = "Created by Hermes operator for weekend deliverable push. Connector gaps are explicit deliverables, not blockers."
    engagement.intake_data_json = {
        "service_offer": "Weekend Launch Readiness Sprint",
        "deadline": "end_of_weekend",
        "sales_goal": "Have durable client-ready deliverables to sell Atlas marketing services.",
    }
    engagement.required_pack_ids_json = [PACK_ID]
    engagement.metadata_json = {
        "source": SOURCE,
        "forgegraph_native": True,
        "company_lives_inside_forgegraph": True,
    }
    engagement.assigned_operator = user
    engagement.requested_by = user
    if not engagement.started_at:
        engagement.started_at = timezone.now()
    engagement.save()

    whiteboard, _ = WorkWhiteboard.objects.get_or_create(
        organization=org,
        company=company,
        idempotency_key="atlas-weekend-launch-readiness-sprint:whiteboard:v1",
        defaults={"created_by": user},
    )
    whiteboard.service_engagement = engagement
    whiteboard.status = WorkWhiteboard.STATUS_IN_APPROVAL
    whiteboard.work_status = WorkWhiteboard.WORK_STATUS_REVIEW
    whiteboard.request_type = "atlas_marketing_service"
    whiteboard.project_name = "Atlas Weekend Launch Readiness Sprint"
    whiteboard.client_name = "Atlas prospective clients"
    whiteboard.request_summary = "Create a ForgeGraph-native Atlas marketing company workspace with client-ready weekend sprint deliverables."
    whiteboard.objective = "Produce enough client-facing deliverables by the end of the weekend to sell Atlas marketing services."
    whiteboard.timeline = "By end of weekend"
    whiteboard.constraints_json = {
        "connector_policy": "Represent missing connectors honestly; do not block deliverable planning."
    }
    whiteboard.stakeholder_context_json = {"operator": EMAIL, "approver": "Mike"}
    whiteboard.delivery_context_json = {
        "package": "weekend_launch_readiness_sprint",
        "client_visible": True,
    }
    whiteboard.metadata_json = {
        "source": SOURCE,
        "agent_owned": True,
        "service_engagement_id": str(engagement.id),
    }
    whiteboard.completion_score = 0.82
    whiteboard.save()

    deliverables: list[ServiceDeliverable] = []
    now = timezone.now()
    for order, item in enumerate(DELIVERABLES, start=1):
        dept = departments[item["department"]]
        asset_key = f"atlas-weekend:{engagement.id}:{item['type']}"
        content = markdown_for(item, company, engagement)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        asset, _ = Asset.objects.get_or_create(
            company=company,
            source_key=asset_key,
            defaults={
                "organization": org,
                "title": item["title"],
                "asset_type": "deliverable",
                "created_by_type": "agent",
                "created_by_id": user.id,
            },
        )
        asset.organization = org
        asset.title = item["title"]
        asset.asset_type = "deliverable"
        asset.status = "active"
        asset.metadata_json = {
            "source": SOURCE,
            "deliverable_type": item["type"],
            "department_slug": item["department"],
            "inline_markdown": content,
        }
        asset.save()
        if not AssetVersion.objects.filter(asset=asset, content_hash=digest).exists():
            latest_num = (
                AssetVersion.objects.filter(asset=asset)
                .order_by("-version_number")
                .values_list("version_number", flat=True)
                .first()
                or 0
            )
            AssetVersion.objects.create(
                asset=asset,
                version_number=latest_num + 1,
                content_uri=f"inline://atlas-weekend/{asset.id}/v{latest_num + 1}.md",
                content_hash=digest,
                mime_type="text/markdown",
                size_bytes=len(content.encode("utf-8")),
                provenance_json={
                    "source": SOURCE,
                    "generated_by": EMAIL,
                    "content_inline_in_asset_metadata": True,
                },
            )
        deliverable, _ = ServiceDeliverable.objects.get_or_create(
            engagement=engagement,
            deliverable_type=item["type"],
            defaults={"organization": org, "company": company, "created_by": user},
        )
        deliverable.organization = org
        deliverable.company = company
        deliverable.title = item["title"]
        deliverable.status = "ready"
        deliverable.visibility = "customer"
        deliverable.department = dept
        deliverable.artifact = asset
        deliverable.summary = item["summary"]
        deliverable.metadata_json = {
            "source": SOURCE,
            "order": order,
            "weekend_target": True,
            "acceptance_criteria": [
                "Client-visible summary is present.",
                "Department owner is mapped to an Atlas department.",
                "Connector limitations are explicit where relevant.",
                "Artifact has a versioned markdown payload.",
            ],
            "target_delivery_window": "end_of_weekend",
        }
        deliverable.delivered_at = (
            now if item["type"] in {"approval_packet", "campaign_launch_package"} else None
        )
        deliverable.save()
        asset.origin_deliverable_id = deliverable.id
        asset.save(update_fields=["origin_deliverable_id", "updated_at"])
        deliverables.append(deliverable)

    model = graph_json(departments, deliverables)
    latest = GraphVersion.objects.filter(graph=company).order_by("-version").first()
    should_create_version = latest is None or latest.graph_json != model
    if should_create_version:
        version = GraphVersion.objects.create(
            graph=company, version=(latest.version + 1 if latest else 1), graph_json=model
        )
    else:
        version = latest

    return {
        "user": {"id": str(user.id), "email": user.email, "created": user_created},
        "organization": {"id": str(org.id), "name": org.name, "created": org_created},
        "company": {"id": str(company.id), "name": company.name, "created": company_created},
        "pack": {
            "pack_id": PACK_ID,
            "status": pack_status,
            "installation_id": str(installation.id) if installation else None,
        },
        "departments": [
            {"id": str(departments[slug].id), "slug": slug, "name": departments[slug].name}
            for slug, _label, _tags in DEPARTMENTS
        ],
        "operating_model_version": {
            "id": str(version.id),
            "version": version.version,
            "created_or_updated": should_create_version,
        },
        "service_catalog": {"id": str(catalog.id), "slug": catalog.slug, "title": catalog.title},
        "service_engagement": {
            "id": str(engagement.id),
            "status": engagement.status,
            "customer_status": engagement.customer_status,
        },
        "whiteboard": {
            "id": str(whiteboard.id),
            "status": whiteboard.status,
            "work_status": whiteboard.work_status,
        },
        "deliverables": [
            {
                "id": str(item.id),
                "title": item.title,
                "type": item.deliverable_type,
                "status": item.status,
                "department": item.department.slug if item.department else None,
                "artifact_id": str(item.artifact_id) if item.artifact_id else None,
                "latest_asset_version_id": str(
                    item.artifact.versions.order_by("-version_number").first().id
                )
                if item.artifact and item.artifact.versions.exists()
                else None,
            }
            for item in deliverables
        ],
    }


payload = run()
print(json.dumps(payload, sort_keys=True, indent=2))
