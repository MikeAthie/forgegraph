from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from application.services.codex_session_runtime import build_codex_deliverable_for_stage
from application.services.company_run_task_routing import refresh_whiteboard_task_snapshot
from application.services.department_pipeline import (
    complete_stage,
    create_pipeline_for_engagement,
    stage_state_for_engagement,
    start_stage,
)
from application.services.legacy_weekend_pipeline import (
    DEFAULT_COMPANY_EXTERNAL_REF,
    DEFAULT_TEMPLATE_ID,
    PACK_ID,
    _ensure_catalog,
    _ensure_company,
    _ensure_engagement,
    _ensure_pack,
    _ensure_whiteboard,
    _user_organization,
)
from infrastructure.orm.models import (
    AssetVersion,
    DepartmentRegistry,
    Organization,
    ServiceDeliverable,
    TaskRoutingRecord,
    User,
)
from scripts.prepare_legacy_handoff_email import prepare_legacy_handoff

STAGES = [
    {
        "stage_id": "strategy_research",
        "deliverable_type": "codex_strategy_brief",
        "title": "Legacy Codex Strategy Brief",
        "prompt": "Create the strategy/research brief for Legacy. Include audience, positioning, proof points, campaign thesis, constraints, and downstream handoff requirements.",
    },
    {
        "stage_id": "brand_content",
        "deliverable_type": "codex_brand_content_pack",
        "title": "Legacy Codex Brand Content Pack",
        "prompt": "Create the brand/content pack for Legacy. Include Spanish-first message house, caption options, hooks, CTA rules, visual direction, and handoff to channel execution.",
    },
    {
        "stage_id": "crm_lifecycle",
        "deliverable_type": "codex_crm_response_scripts",
        "title": "Legacy Codex CRM / WhatsApp Scripts",
        "prompt": "Create CRM/DM/WhatsApp response scripts for Legacy. Cover availability, styling help, price sensitivity, shipping, appointment/try-on, objections, and follow-up cadence.",
    },
    {
        "stage_id": "analytics_performance",
        "deliverable_type": "codex_measurement_plan",
        "title": "Legacy Codex Measurement Plan",
        "prompt": "Create the analytics/performance measurement plan for a weekend social launch. Include manual tracking sheet columns, KPIs, thresholds, daily readout, and optimization decisions.",
    },
    {
        "stage_id": "channel_execution",
        "deliverable_type": "codex_channel_execution_calendar",
        "title": "Legacy Codex Channel Execution Calendar",
        "prompt": "Create a 10-day Instagram/channel execution calendar for Legacy. Include post sequence, format, caption angle, asset needs, owner, due date, CTA, and routing tasks.",
    },
    {
        "stage_id": "qa_compliance",
        "deliverable_type": "codex_qa_report",
        "title": "Legacy Codex Launch QA Report",
        "prompt": "Create a QA/compliance report for the Legacy launch package. Check brand consistency, Spanish copy quality, asset readiness, privacy constraints, missing connectors, launch blockers, and approve/hold decision.",
    },
    {
        "stage_id": "client_approval_ops",
        "deliverable_type": "codex_client_approval_packet",
        "title": "Legacy Codex Client Approval Packet",
        "prompt": "Create the client approval packet for Mike/Legacy. Summarize what is ready, decisions required, approval checklist, launch instructions, blocked production actions, and next steps.",
    },
]

DEPARTMENTS = {
    "strategy_research": "Strategy & Research",
    "brand_content": "Brand & Content",
    "channel_execution": "Channel Execution",
    "crm_lifecycle": "CRM & Lifecycle",
    "analytics_performance": "Analytics & Performance",
    "qa_compliance": "QA & Compliance",
    "client_approval_ops": "Client Approval Ops",
}

LEGACY_INFO = """
Client: Legacy, a Spanish-first luxury eyewear / glasswear / sunglasses brand in Mexico City.
Anchor product/campaign: Optical Noir; restrained luxury, nighttime CDMX energy, confident but not hypey.
Goal: fast agency-style weekend social launch with concrete deliverables, not just setup records.
Audience: style-conscious CDMX buyers who want premium eyewear, giftable accessories, and an elevated boutique feel.
Constraints: no fake live publishing; production connector gaps must be explicit. Do not expose exact inventory counts, costs, margins, supplier details, tokens, or raw credentials. Deliver in client-ready markdown.
Required outputs by the end of the run: strategy, brand/copy pack, CRM response scripts, measurement plan, channel calendar/routing tasks, QA report, and client approval packet.
""".strip()


def _ensure_departments(organization: Organization) -> None:
    for slug, name in DEPARTMENTS.items():
        department, _ = DepartmentRegistry.objects.get_or_create(
            organization=organization,
            slug=slug,
            defaults={"name": name, "department_type": "atlas_agency"},
        )
        department.name = name
        department.department_type = "atlas_agency"
        department.active = True
        department.service_tags_json = ["atlas", "digital_marketing_pro", "codex_session"]
        metadata = dict(department.metadata_json or {})
        metadata.update({"source": "legacy_codex_company_run", "operating_model_pack_id": PACK_ID})
        department.metadata_json = metadata
        department.save()


def run(email: str = "admin@forgegraph.local") -> dict[str, Any]:
    settings.ENABLE_CODEX_SESSION_RUNTIME = True
    settings.CODEX_SESSION_COMMAND = r"C:\Users\mathi\AppData\Roaming\npm\codex.cmd"
    codex_workdir = Path(settings.BASE_DIR).parent / ".hermes" / "codex_session_workdir"
    codex_workdir.mkdir(parents=True, exist_ok=True)
    if not (codex_workdir / ".git").exists():
        import subprocess

        subprocess.run(
            ["git", "init"], cwd=codex_workdir, check=True, capture_output=True, text=True
        )
    settings.CODEX_SESSION_WORKDIR = str(codex_workdir)
    settings.CODEX_SESSION_TIMEOUT_SECONDS = 360

    user = User.objects.filter(email=email).first() or User.objects.order_by("date_joined").first()
    if user is None:
        raise RuntimeError("No user found for Legacy Codex company run.")
    organization = _user_organization(user)
    _ensure_departments(organization)
    company = _ensure_company(
        user=user,
        organization=organization,
        company_name="Legacy",
        external_ref=DEFAULT_COMPANY_EXTERNAL_REF,
    )
    pack_status, installation = _ensure_pack(company=company, user=user)
    manifest = {
        "client": "Legacy",
        "source": "codex_session_company_run.v1",
        "started_at": timezone.now().isoformat(),
        "posts": [],
    }
    root = Path(settings.BASE_DIR).parent / ".hermes" / "legacy_codex_run"
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    catalog = _ensure_catalog(organization=organization, user=user, manifest=manifest)
    engagement = _ensure_engagement(
        user=user,
        organization=organization,
        company=company,
        catalog=catalog,
        root=root,
        manifest=manifest,
    )
    whiteboard = _ensure_whiteboard(
        user=user,
        organization=organization,
        company=company,
        engagement=engagement,
        root=root,
        manifest=manifest,
    )
    program = create_pipeline_for_engagement(
        engagement,
        template_id=DEFAULT_TEMPLATE_ID,
        created_by=user,
        run_context={
            "source": "legacy_codex_company_run",
            "runtime_provider": "codex_session_runtime",
        },
    )

    deliverables = []
    for item in STAGES:
        stage = stage_state_for_engagement(engagement, item["stage_id"])
        start_stage(stage, actor=user)
        prompt = f"{LEGACY_INFO}\n\nStage request: {item['prompt']}\n\nReturn a complete deliverable with headings, bullet points, tables where useful, and explicit handoff notes to the next department."
        deliverable = build_codex_deliverable_for_stage(
            engagement=engagement,
            stage_state=stage,
            user=user,
            deliverable_type=item["deliverable_type"],
            title=item["title"],
            prompt=prompt,
        )
        complete_stage(
            stage,
            outputs=[
                {
                    "kind": "codex_session_deliverable",
                    "type": "service_deliverable",
                    "id": str(deliverable.id),
                }
            ],
            actor=user,
        )
        deliverable.refresh_from_db()
        deliverables.append(deliverable)

    engagement.customer_status = "review_ready"
    engagement.status = "in_progress"
    engagement.metadata_json = {
        **dict(engagement.metadata_json or {}),
        "codex_session_company_run": True,
        "codex_session_started_from_single_prompt": True,
        "codex_session_completed_at": timezone.now().isoformat(),
    }
    engagement.save(update_fields=["customer_status", "status", "metadata_json", "updated_at"])
    whiteboard.status = whiteboard.STATUS_IN_APPROVAL
    whiteboard.work_status = whiteboard.WORK_STATUS_REVIEW
    whiteboard.save(update_fields=["status", "work_status", "updated_at"])
    refresh_whiteboard_task_snapshot(whiteboard, program)
    handoff = prepare_legacy_handoff(
        engagement=engagement,
        program=program,
        requested_by=user,
    )

    evidence = {
        "run_completed_at": timezone.now().isoformat(),
        "organization": {"id": str(organization.id), "name": organization.name},
        "company": {"id": str(company.id), "name": company.name},
        "pack": {
            "pack_id": PACK_ID,
            "status": pack_status,
            "installation_id": str(installation.id) if installation else None,
        },
        "engagement": {
            "id": str(engagement.id),
            "status": engagement.status,
            "customer_status": engagement.customer_status,
        },
        "whiteboard": {
            "id": str(whiteboard.id),
            "status": whiteboard.status,
            "work_status": whiteboard.work_status,
        },
        "program": {
            "id": str(program.id),
            "status": program.status,
            "current_stage_id": program.current_stage_id,
        },
        "stage_statuses": list(
            program.stage_states.order_by("sequence").values("stage_id", "status", "completed_at")
        ),
        "deliverables": [
            {
                "id": str(d.id),
                "type": d.deliverable_type,
                "title": d.title,
                "department": d.department.slug if d.department else None,
                "artifact_id": str(d.artifact_id) if d.artifact_id else None,
                "summary": d.summary,
            }
            for d in deliverables
        ],
        "deliverable_count": ServiceDeliverable.objects.filter(
            engagement=engagement, metadata_json__source="codex_session_runtime"
        ).count(),
        "asset_version_count": AssetVersion.objects.filter(
            asset__company=company, provenance_json__source="codex_session_runtime"
        ).count(),
        "routing_task_count": TaskRoutingRecord.objects.filter(
            service_engagement=engagement
        ).count(),
        "handoff": handoff,
    }
    output_path = root / f"evidence_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    evidence["evidence_path"] = str(output_path)
    return evidence


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
