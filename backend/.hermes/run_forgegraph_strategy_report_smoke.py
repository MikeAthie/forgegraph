from __future__ import annotations

import json
import os
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402
from django.utils import timezone  # noqa: E402

django.setup()

from application.services.company_archive import ArchiveService  # noqa: E402
from application.services.strategy_report_builder import generate_strategy_report  # noqa: E402
from infrastructure.orm.models import ApprovalTask, Graph, GraphVersion, MemoryObservation, Run, User  # noqa: E402

RUN_ID = datetime.now(UTC).strftime("forgegraph_strategy_report_%Y%m%d_%H%M%S")
OUT_DIR = Path(".hermes") / "forgegraph_strategy_report_smoke" / RUN_ID
OUT_DIR.mkdir(parents=True, exist_ok=True)

user = User.objects.select_related("default_organization").filter(email="legacy.glasswear.test@example.com").first()
if user is None or user.default_organization_id is None:
    user = User.objects.select_related("default_organization").filter(default_organization__isnull=False).order_by("date_joined").first()
if user is None or user.default_organization is None:
    raise SystemExit("No ForgeGraph user with an organization is available.")
organization = user.default_organization

company = Graph.objects.create(
    owner=user,
    organization=organization,
    name="Atlas Growth Agency OS",
    description="ForgeGraph-owned agency operating system for productized campaign delivery.",
    external_source="forgegraph-strategy-report-smoke",
    external_ref=RUN_ID,
)
version = GraphVersion.objects.create(
    graph=company,
    version=1,
    graph_json={
        "nodes": [],
        "edges": [],
        "metadata": {
            "company_profile": {
                "companyName": "Atlas Growth Agency OS",
                "companyType": "Productized digital marketing agency",
                "objective": "Design, validate, package, and hand off client campaign strategy with approval gates.",
                "client_context": {
                    "name": "Legacy",
                    "industry": "Premium eyewear and optical retail",
                    "market": "Mexico City",
                    "tier": "VIP / premium local launch",
                    "goal": "Approval-gated Optical Noir weekend launch",
                },
            }
        },
    },
)

operation = Run.objects.create(
    owner=user,
    organization=organization,
    graph_version=version,
    status="succeeded",
    started_at=timezone.now(),
    ended_at=timezone.now(),
    input_json={
        "operation_name": "Legacy Optical Noir Strategy Handoff",
        "operation_brief": "a polished client-facing strategy report for the Legacy Optical Noir weekend social launch",
    },
    output_json={
        "positioning": "Position Legacy Optical Noir as quiet-status eyewear for Mexico City buyers who want a precise, editorial look without loud luxury signaling.",
        "target_audience": [
            "Style-aware professionals in Roma Norte, Condesa, Juarez, and Polanco who buy fewer but better accessories.",
            "Existing optical customers who respond to curated drops, appointment guidance, and WhatsApp concierge support.",
            "Gift buyers looking for a premium but practical weekend purchase with fast human assistance.",
        ],
        "approach": "Use a weekend approval-gated social launch: lead with product photography, send prospects into WhatsApp consultation, and measure saves, replies, profile visits, and appointment intent before scaling media spend.",
        "constraints": [
            "No live publishing claim until channel receipts exist.",
            "No text, logos, people, or fake brand marks inside campaign images.",
            "Spanish-first copy must stay concrete, premium, and low-hype.",
            "Client approval is required before production launch or paid amplification.",
        ],
        "execution_plan": (
            "Approve the Optical Noir direction and select final hero assets; publish the weekend social set only after approval and channel receipts; "
            "route high-intent replies into WhatsApp concierge for availability, fit guidance, and holds; run a 48-hour response window; "
            "then use the Monday readout to choose the best-performing angle for retargeting. Handoff assets: strategy report, approval checklist, campaign asset set, WhatsApp response scripts, and measurement plan."
        ),
        "risks": [
            "Overly polished luxury language could feel generic; keep copy specific to the product and CDMX buying context.",
            "Launching without channel receipts would weaken provenance; keep production blocked until approval is recorded.",
            "Image quality must remain production-grade; placeholder/spec-rendered assets should trigger a hold rather than client-ready status.",
        ],
        "recommendations": [
            "Approve the Optical Noir visual direction if the product-photo assets match the premium/noir standard.",
            "Use WhatsApp as the primary conversion path for the weekend rather than pushing immediate checkout.",
            "Keep the first launch small, measured, and approval-gated; scale only after saves/replies/appointments validate demand.",
            "Use the approved production image path as the primary media route and keep secondary providers as redundancy once their quotas and credits are healthy.",
        ],
        "decision_traces": [
            {
                "decision": "Make Optical Noir a product-photo-led weekend launch instead of a broad discount campaign.",
                "alternatives": ["discount-led urgency", "generic lifestyle content", "paid-first reach campaign"],
                "constraints": ["premium positioning", "no unsupported live publishing claim", "approval before production"],
                "departments": ["Strategy", "Brand Content", "QA Compliance", "Channel Execution"],
                "rationale": "Product photography and concierge response preserve premium trust while still creating measurable weekend demand.",
                "rejected": ["discount-led urgency", "unapproved live-publishing claim"],
            },
            {
                "decision": "Use WhatsApp consultation as the conversion path before paid scale.",
                "alternatives": ["direct checkout push", "influencer-first launch"],
                "constraints": ["limited launch proof", "need for human fit guidance", "approval-gated operations"],
                "departments": ["CRM", "Channel Execution", "Analytics"],
                "rationale": "Human guidance is more credible for premium optical products and gives the team cleaner intent signals.",
                "rejected": ["checkout-first message without consultation"],
            },
        ],
        "iteration_deltas": [
            {
                "what_changed": "the shift from placeholder readiness to production-photo readiness",
                "why_changed": "Placeholder renderings did not meet the client-ready standard for premium optical retail.",
                "trigger": "visual QA comparison against approved product-photography direction",
                "department": "QA Compliance",
            },
            {
                "what_changed": "The report framing now emphasizes client decisions, launch controls, and next actions.",
                "why_changed": "The handoff needs to read like an approval document, not a raw department note.",
                "trigger": "handoff quality review",
                "department": "Client Approval Ops",
            },
        ],
        "memory_attributions": [
            {
                "memory_title": "Client-ready quality standard",
                "changed_reasoning": "Approved deliverables must separate client-facing handoff from backend provenance and must clearly block placeholder media.",
            }
        ],
    },
)

ApprovalTask.objects.create(
    run=operation,
    node_id="approval_legacy_optical_noir_strategy",
    assignee=user,
    status="rejected",
    payload={"prompt_message": "Approve the first handoff if media and report are client-ready."},
    result={
        "approved": False,
        "what_changed_after_rejection": "Held client-ready status until media used real raster generation and the report used a polished client handoff format.",
        "improved_before_reapproval": "The handoff now distinguishes strategy approval, production launch approval, and channel receipt requirements.",
    },
    resolved_at=timezone.now(),
)
MemoryObservation.objects.create(
    tenant_id=organization.id,
    graph_id=company.id,
    run_id=operation.id,
    type="case",
    title="Legacy Optical Noir quality learning",
    content="Client-ready campaign work needs production-grade media, polished handoff format, provenance in manifests, and explicit approval gates before launch.",
    scope="run",
    topic_key=f"legacy-optical-noir-quality-{RUN_ID}",
)

artifacts = {}
for fmt in ("html", "pdf", "md"):
    artifact = generate_strategy_report(str(company.id), str(operation.id), audience="client", format=fmt)
    output_path = OUT_DIR / artifact.filename
    if isinstance(artifact.content, bytes):
        output_path.write_bytes(artifact.content)
    else:
        output_path.write_text(artifact.content, encoding="utf-8")
    artifacts[fmt] = {
        "filename": artifact.filename,
        "path": str(output_path),
        "content_type": artifact.content_type,
        "bytes": output_path.stat().st_size,
        "traceability_sections": sorted(artifact.traceability.keys()),
    }

client_zip = OUT_DIR / "Legacy_Optical_Noir_Strategy_Report_FORGEGRAPH.zip"
with zipfile.ZipFile(client_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for fmt in ("html", "pdf"):
        zf.write(artifacts[fmt]["path"], artifacts[fmt]["filename"])
    zf.writestr(
        "traceability_manifest.json",
        json.dumps(
            {
                "run_id": RUN_ID,
                "company_id": str(company.id),
                "operation_id": str(operation.id),
                "source": "ForgeGraph strategy_report_builder.generate_strategy_report",
                "formats": {fmt: artifacts[fmt] for fmt in ("html", "pdf")},
            },
            indent=2,
            sort_keys=True,
        ),
    )

archive = ArchiveService()
asset = archive.create_asset(
    company=company,
    title="Legacy Optical Noir Strategy Report Bundle",
    asset_type="strategy_report_bundle",
    source_key=f"forgegraph-strategy-report-smoke:{RUN_ID}:bundle",
    created_by_type="system",
    created_by_id=user.id,
    metadata={"source": "strategy_report_builder", "client_facing": True, "no_markdown_in_client_zip": True},
)
version_obj = archive.create_asset_version(
    asset=asset,
    content_uri=str(client_zip),
    content=client_zip.read_bytes(),
    mime_type="application/zip",
    provenance={
        "source": "ForgeGraph strategy_report_builder.generate_strategy_report",
        "run_id": RUN_ID,
        "operation_id": str(operation.id),
        "company_id": str(company.id),
        "included_formats": ["html", "pdf", "traceability_manifest.json"],
        "internal_markdown_path": artifacts["md"]["path"],
    },
)

html_text = Path(artifacts["html"]["path"]).read_text(encoding="utf-8")
md_text = Path(artifacts["md"]["path"]).read_text(encoding="utf-8")
bad_tokens = [
    token
    for token in [
        "Internal lineage",
        "Intended use",
        "Excluded client formats",
        "downstream HTML/PDF packaging",
        "codex_media_spec",
        "media_generation_job",
        "GraphVersion",
        "NodeRun",
    ]
    if token.lower() in html_text.lower() or token.lower() in md_text.lower()
]

manifest = {
    "run_id": RUN_ID,
    "company_id": str(company.id),
    "operation_id": str(operation.id),
    "asset_id": str(asset.id),
    "asset_version_id": str(version_obj.id),
    "out_dir": str(OUT_DIR),
    "client_zip": str(client_zip),
    "client_zip_bytes": client_zip.stat().st_size,
    "artifacts": artifacts,
    "quality_checks": {
        "html_bytes": artifacts["html"]["bytes"],
        "pdf_bytes": artifacts["pdf"]["bytes"],
        "pdf_starts_with_pdf_header": Path(artifacts["pdf"]["path"]).read_bytes().startswith(b"%PDF-1.4"),
        "client_zip_has_markdown": any(name.lower().endswith((".md", ".markdown")) for name in zipfile.ZipFile(client_zip).namelist()),
        "bad_visible_tokens": bad_tokens,
    },
}
manifest_path = OUT_DIR / "run_manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
print(json.dumps(manifest, indent=2, sort_keys=True))
