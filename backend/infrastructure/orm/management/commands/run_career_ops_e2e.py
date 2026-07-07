"""Run a ForgeGraph-owned CareerOps end-to-end dry run.

This command is intentionally self-contained so it can be executed inside the
Docker backend container as a reproducible CareerOps smoke/E2E path. It creates
or reuses a CareerOps company, persists a canonical base CV asset, ingests a
bounded set of postings, materializes the backend-owned URL pipeline, writes
versioned packet artifacts, runs readiness gates, and emits JSON evidence.
"""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from django.utils import timezone

from django.core.management.base import BaseCommand, CommandParser

from application.services.career_ops_daily_discovery import run_career_ops_daily_discovery
from application.services.career_ops_quality_gates import check_career_ops_packet_readiness
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    CommunicationAttachment,
    CommunicationEventReceipt,
    CommunicationMessage,
    CommunicationThread,
    CompanyOpportunity,
    CompanySignal,
    DecisionRecord,
    Graph,
    Run,
    ServiceDeliverable,
    StateProjection,
    TaskRecord,
    User,
)

DEFAULT_USER_EMAIL = "careerops.operator@forgegraph.local"
DEFAULT_COMPANY_NAME = "CareerOps ForgeGraph Company"
DEFAULT_IDEMPOTENCY_KEY = "careerops-e2e-docker-command"


DEFAULT_POSTINGS: tuple[dict[str, Any], ...] = (
    {
        "title": "Backend Developer (Python)",
        "company": "360Dialog",
        "url": "https://dynamitejobs.com/company/360dialog/remote-job/backend-developer-python-remote",
        "location": "Fully remote worldwide; applicants from anywhere welcome",
        "provider": "forgegraph_careerops_fixture",
        "salary": "$45.9k-$114.6k/year / €40k-€100k/year",
        "description": (
            "Messaging Platform backend role powering partner/client APIs, WhatsApp channel lifecycle, "
            "billing, integrations, and service-to-service communication. Requires deep Python, async APIs, "
            "PostgreSQL, queues, workers, AWS, observability, correctness, maintainability, and production ownership."
        ),
    },
    {
        "title": "Backend Engineer",
        "company": "Clera",
        "url": "https://jobs.ashbyhq.com/clera/a4153576-c26a-459e-9a18-ecf447b1df1f/application",
        "location": "Remote, LATAM-based with US Pacific timezone overlap",
        "provider": "forgegraph_careerops_fixture",
        "salary": "$70k-$100k USD/year + equity",
        "description": (
            "Early backend engineer role building AI voice and browser agents in production. Own core backend "
            "services, APIs, EHR and insurance portal integrations, reliability, observability, queues, event-driven "
            "architecture, Python or TypeScript/Node, relational databases, AWS/GCP, and founder collaboration."
        ),
    },
    {
        "title": "Senior Backend Engineer (Python, FastAPI, AWS)",
        "company": "Hire5 / Tricura Insurance Group",
        "url": "https://talents.vaia.com/companies/hire5/senior-backend-engineer-python-fastapi-aws-remote-latam-104960058/",
        "location": "Remote, LatAm / North & South American time zones; 9am-6pm EST",
        "provider": "forgegraph_careerops_fixture",
        "salary": "$90k-$120k USD/year estimated",
        "description": (
            "Senior backend role for a healthcare insurance platform using Python, FastAPI, Pydantic, AWS, Terraform, "
            "Airflow, REST APIs, monitoring, logging, third-party integrations, rate limiting, data transformation, "
            "tests, architecture, peer review, autonomy, and possible AI/ML integrations."
        ),
    },
    {
        "title": "Senior Software Engineer (Colombia)",
        "company": "Connectly",
        "url": "https://jobs.ashbyhq.com/connectly/87ca9897-e249-434e-bc87-4e206958a6dd/application",
        "location": "Remote/LATAM (Col); confirm Mexico eligibility before final submission",
        "provider": "forgegraph_careerops_fixture",
        "salary": "Competitive compensation with equity; amount not listed",
        "description": (
            "Conversational commerce startup building WhatsApp-centered AI engagement for Latin American retailers. "
            "Design, build, and launch production-grade conversational AI solutions using Python, AWS, Kafka, Postgres, "
            "DynamoDB, React, TypeScript, prompt design, LLM integration, product sense, and customer-facing execution."
        ),
    },
    {
        "title": "Fractional Senior Full Stack Engineer (Stabilization / AI-Generated Code)",
        "company": "Bullpen Talent",
        "url": "https://jobs.ashbyhq.com/bullpen-talent/834a1f6e-995e-4832-bcbf-d25da23fc8f0/application",
        "location": "Remote LATAM & Eastern Europe; fractional contract 10-40 hrs/week",
        "provider": "forgegraph_careerops_fixture",
        "salary": "Hourly/fractional; amount not listed",
        "description": (
            "Role stabilizes AI-generated and founder-built early-stage products with fragile codebases. Work includes "
            "reviewing codebases, identifying bugs and technical risks, refactoring, maintainability, auth/payments/backend "
            "gaps, lightweight QA/testing, Python FastAPI/Django, Node.js/TypeScript, React/Next.js, Firebase/Supabase, APIs, "
            "and modern web architectures."
        ),
    },
)


BASE_CV_METADATA: dict[str, Any] = {
    "name": "Miguel Athie",
    "title": "Backend-leaning Software Engineer",
    "email": "miguel.athien@gmail.com",
    "phone": "+52 55 3900 3599",
    "location": "Mexico City, MX | Mexico / Spain",
    "github": "https://github.com/MikeAthie",
    "professional_summary": (
        "Backend-leaning Software Engineer with strong end-to-end ownership building production APIs, data systems, "
        "AI-native workflows, and async service architectures. Experienced with Python, FastAPI, PostgreSQL, Redis, "
        "workers, JavaScript/TypeScript, and Go-based backend services."
    ),
    "summary": "Backend engineer building Python APIs, data systems, and AI workflow systems.",
    "proof_points": [
        "Built production APIs and service boundaries with Python, FastAPI, Django, PostgreSQL, Redis, and workers.",
        "Built async and event-driven pipelines for data-heavy workflows and operational automation.",
        "Integrated AI-powered features, RAG workflows, and agentic workflows into source-bounded product systems.",
        "Delivered product-facing software from discovery and architecture through implementation, testing, and launch.",
        "Meta Back-End Developer Professional Certificate.",
        "IBM RAG and Agentic AI Professional Certificate.",
        "Cambridge English C2 Proficiency certificate.",
    ],
    "skills": [
        {"category": "Backend / APIs", "items": ["Python", "FastAPI", "Django", "Go", "REST APIs", "service architecture"]},
        {"category": "Data & async systems", "items": ["PostgreSQL", "Redis", "Redis Streams", "Celery", "workers", "event-driven pipelines"]},
        {"category": "AI engineering", "items": ["RAG", "LangGraph", "agentic workflows", "LLM integration", "grounded outputs"]},
        {"category": "Frontend / product", "items": ["React", "Next.js", "TypeScript", "dashboards", "internal tools"]},
        {"category": "Reliability", "items": ["Prometheus", "observability", "retries", "dry-run workflows", "testing", "debugging"]},
    ],
    "experience": [
        {
            "organization": "Grey Cross Developments",
            "role": "Product Engineer",
            "period": "Jul 2022 - Present",
            "bullets": [
                "Owned backend products end to end, from discovery and architecture through implementation and deployment.",
                "Designed APIs and service boundaries with maintainable interfaces and production-minded iteration.",
                "Built async and event-driven pipelines using PostgreSQL, Redis, workers, and structured data flows.",
            ],
        },
        {
            "organization": "Vittahouse",
            "role": "Automation & Data Consultant",
            "period": "Oct 2019 - Nov 2025",
            "bullets": [
                "Automated accounting and audit workflows, reducing manual effort and improving recurring operational consistency.",
                "Built discrepancy-detection and normalization workflows to surface data issues earlier.",
            ],
        },
    ],
    "projects": [
        {
            "name": "ForgeGraph",
            "subtitle": "AI-native backend platform for agentic workflows (Go + Django)",
            "period": "2026 - Present",
            "url": "https://github.com/MikeAthie/ForgeGraph",
            "bullets": [
                "Built backend services for structured project knowledge, memory, summaries, operational workflows, retries, dry-run execution, and admin-facing endpoints.",
                "Added reliability features including Prometheus counters, retry mechanisms, structured service boundaries, and tests around critical workflows.",
            ],
        },
        {
            "name": "Lex Toolkit",
            "subtitle": "AI agents for legal workflows (Next.js + FastAPI)",
            "period": "Nov 2025 - Present",
            "url": "https://github.com/MikeAthie/Lex-Toolkit",
            "bullets": [
                "Built a full-stack application with Next.js and FastAPI for professional law-practice workflows.",
                "Developed AI agent use cases for law practice operations with product-quality delivery and clear API contracts.",
            ],
        },
    ],
    "education": [
        {
            "institution": "Instituto Tecnologico Autonomo de Mexico (ITAM)",
            "degree": "BSc in Law",
            "graduation_year": "2017",
        }
    ],
    "certifications": [
        "Meta Back-End Developer Professional Certificate",
        "IBM RAG and Agentic AI Professional Certificate",
        "Cambridge English C2 Proficiency certificate",
    ],
    "constraints": {
        "supported_languages": ["English", "Spanish"],
        "unsupported_required_languages": ["German", "Mandarin", "Chinese"],
        "preferred_stack": ["Python", "JavaScript", "TypeScript", "Go"],
        "excluded_primary_stacks": ["Java", "Kotlin", "Scala", "Spring"],
        "location_priority": "US-based remote hiring LatAm, then Mexico/LatAm, then Spain/EU",
    },
    "career_ops": {
        "deliverable_type": "cv_source",
        "summary": "Backend engineer building Python APIs, data systems, and AI workflow systems.",
        "proof_points": [
            "Built production APIs using Python, FastAPI, PostgreSQL, Redis, workers, and service boundaries.",
            "Delivered RAG and agentic workflow prototypes with source-bounded outputs and observability.",
            "Holds Meta Back-End Developer Professional Certificate, IBM RAG and Agentic AI Professional Certificate, and Cambridge English C2 Proficiency certificate.",
        ],
    },
}


class Command(BaseCommand):
    help = "Run ForgeGraph-owned CareerOps E2E dry run inside the backend/Docker runtime."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--user-email", default=DEFAULT_USER_EMAIL)
        parser.add_argument("--company-name", default=DEFAULT_COMPANY_NAME)
        parser.add_argument("--max-jobs", type=int, default=5)
        parser.add_argument("--idempotency-key", default=DEFAULT_IDEMPOTENCY_KEY)
        parser.add_argument(
            "--postings-json",
            default="",
            help="Optional container-visible JSON file with posting records. Defaults to the built-in five-job fixture.",
        )
        parser.add_argument("--json", action="store_true", dest="json_output")
        parser.add_argument(
            "--send-whatsapp",
            action="store_true",
            help="Send the 5 CV PDFs and 5 application links through the configured WhatsApp bridge.",
        )
        parser.add_argument("--whatsapp-bridge-url", default="http://host.docker.internal:3000")
        parser.add_argument(
            "--whatsapp-chat-id",
            default=os.environ.get("CAREER_OPS_WHATSAPP_CHAT_ID", os.environ.get("WHATSAPP_CHAT_ID", "")),
            help="WhatsApp chatId accepted by the local bridge, e.g. 52155...@s.whatsapp.net.",
        )
        parser.add_argument(
            "--delivery-output-dir",
            default="/app/.hermes/career_ops_e2e_delivery",
            help="Container-visible directory for exported CV PDFs. Use FORGEGRAPH_HOST_BACKEND_PATH for host path translation.",
        )

    def handle(self, *args: object, **options: object) -> None:
        actor = _ensure_user(str(options["user_email"]))
        company = _ensure_company(actor=actor, name=str(options["company_name"]))
        base_cv = _ensure_base_cv(company=company)
        postings = _load_postings(str(options.get("postings_json") or ""))
        max_jobs = max(1, min(int(options.get("max_jobs") or 5), 10))
        postings = postings[:max_jobs]
        idempotency_key = str(options["idempotency_key"])

        discovery = run_career_ops_daily_discovery(
            company=company,
            actor=actor,
            postings=postings,
            idempotency_key=idempotency_key,
            max_new_options=max_jobs,
            max_evaluations=max_jobs,
        )

        packets: list[dict[str, Any]] = []
        live_send_allowed = False
        for run_info in discovery.get("runs", []):
            packet_version_id = run_info.get("packet_asset_version_id")
            readiness_payload: dict[str, Any] | None = None
            asset_versions: dict[str, str | None] = {}
            if packet_version_id:
                packet_version = AssetVersion.objects.get(id=packet_version_id)
                readiness = check_career_ops_packet_readiness(company=company, packet_version=packet_version)
                readiness_payload = {
                    "status": readiness.status,
                    "checks": readiness.checks,
                    "blockers": readiness.blockers,
                    "live_send_allowed": readiness.live_send_allowed,
                }
                live_send_allowed = live_send_allowed or readiness.live_send_allowed
                asset_versions = _asset_versions_for_packet(company=company, packet_version=packet_version)
            packets.append(
                {
                    "run_id": run_info.get("run_id"),
                    "opportunity_id": run_info.get("opportunity_id"),
                    "decision_id": run_info.get("decision_id"),
                    "packet_asset_version_id": packet_version_id,
                    **asset_versions,
                    "readiness": readiness_payload,
                    "blocked_reasons": run_info.get("blocked_reasons", []),
                    "external_side_effects_allowed": False,
                }
            )

        whatsapp_delivery: dict[str, Any] | None = None
        if bool(options.get("send_whatsapp")):
            whatsapp_delivery = _send_whatsapp_delivery(
                company=company,
                actor=actor,
                packets=packets,
                bridge_url=str(options["whatsapp_bridge_url"]),
                chat_id=str(options.get("whatsapp_chat_id") or ""),
                output_dir=str(options.get("delivery_output_dir") or "/app/.hermes/career_ops_e2e_delivery"),
                idempotency_key=idempotency_key,
            )

        payload = {
            "status": discovery.get("status", "ok"),
            "company_id": str(company.id),
            "company_name": company.name,
            "user_id": str(actor.id),
            "user_email": actor.email,
            "base_cv_asset_id": str(base_cv.id),
            "processed_count": discovery.get("processed_count", len(packets)),
            "projection_id": discovery.get("projection_id"),
            "packets": packets,
            "counts": _counts(company=company),
            "blocked_reasons": discovery.get("blocked_reasons", []),
            "external_side_effects_allowed": False,
            "live_send_allowed": bool(live_send_allowed),
            "docker_command": _docker_command(max_jobs=max_jobs, company_name=company.name, user_email=actor.email),
            "whatsapp_delivery": whatsapp_delivery,
        }
        self.stdout.write(json.dumps(payload, sort_keys=True))


def _ensure_user(email: str) -> User:
    normalized = (email or DEFAULT_USER_EMAIL).strip().lower()
    user = User.objects.filter(email=normalized).first()
    if user is None:
        user = User.objects.create_user(email=normalized, password="careerops-local-dev-only")
    ensure_default_organization(user)
    return user


def _ensure_company(*, actor: User, name: str) -> Graph:
    ensure_default_organization(actor)
    if actor.default_organization is None:
        raise ValueError("CareerOps E2E requires an organization-scoped actor.")
    company = Graph.objects.filter(owner=actor, organization=actor.default_organization, name=name).first()
    if company is None:
        company = Graph.objects.create(owner=actor, organization=actor.default_organization, name=name)
    return company


def _ensure_base_cv(*, company: Graph) -> Asset:
    if company.organization is None:
        raise ValueError("CareerOps E2E requires an organization-scoped company.")
    asset, _ = Asset.objects.get_or_create(
        organization=company.organization,
        company=company,
        source_key="career_ops:cv_source",
        defaults={
            "title": "Miguel Athie canonical CareerOps CV source",
            "asset_type": "document",
            "status": "active",
            "created_by_type": "system",
            "metadata_json": BASE_CV_METADATA,
        },
    )
    asset.title = "Miguel Athie canonical CareerOps CV source"
    asset.asset_type = "document"
    asset.status = "active"
    asset.metadata_json = BASE_CV_METADATA
    asset.save(update_fields=["title", "asset_type", "status", "metadata_json", "updated_at"])
    return asset


def _load_postings(path: str) -> list[dict[str, Any]]:
    if not path:
        return [dict(posting) for posting in DEFAULT_POSTINGS]
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("postings"), list):
        records = data["postings"]
    elif isinstance(data, list):
        records = data
    else:
        raise ValueError("--postings-json must contain a list or an object with a postings list.")
    return [dict(record) for record in records if isinstance(record, dict)]


def _asset_versions_for_packet(*, company: Graph, packet_version: AssetVersion) -> dict[str, str | None]:
    opportunity_id = _packet_opportunity_id(packet_version)
    mapping = {
        "tailored_resume_html": "tailored_resume_asset_version_id",
        "ats_resume_text": "ats_resume_text_asset_version_id",
        "ats_resume_html": "ats_resume_html_asset_version_id",
        "ats_resume_pdf": "ats_resume_pdf_asset_version_id",
        "ats_resume_parseability_report": "ats_resume_parseability_report_asset_version_id",
        "recruiter_evaluation_report": "recruiter_evaluation_asset_version_id",
        "cover_letter_draft": "cover_letter_asset_version_id",
        "ats_simulation_report": "ats_simulation_asset_version_id",
    }
    result: dict[str, str | None] = {value: None for value in mapping.values()}
    if not opportunity_id:
        return result
    for deliverable in ServiceDeliverable.objects.filter(
        company=company,
        metadata_json__career_ops__opportunity_id=opportunity_id,
        deliverable_type__in=mapping.keys(),
    ):
        career_ops = deliverable.metadata_json.get("career_ops", {}) if isinstance(deliverable.metadata_json, dict) else {}
        version_id = career_ops.get("asset_version_id") if isinstance(career_ops, dict) else None
        if version_id:
            result[mapping[deliverable.deliverable_type]] = str(version_id)
    return result


def _packet_opportunity_id(packet_version: AssetVersion) -> str | None:
    provenance = packet_version.provenance_json or {}
    career_ops = provenance.get("career_ops", {}) if isinstance(provenance, dict) else {}
    if not isinstance(career_ops, dict):
        return None
    opportunity = career_ops.get("opportunity", {})
    if isinstance(opportunity, dict) and opportunity.get("id"):
        return str(opportunity["id"])
    return None


def _counts(*, company: Graph) -> dict[str, int]:
    return {
        "runs": Run.objects.filter(organization=company.organization, input_json__career_ops__dry_run=True).count(),
        "signals": CompanySignal.objects.filter(company=company, domain_context="career_ops").count(),
        "opportunities": CompanyOpportunity.objects.filter(company=company).count(),
        "tasks": TaskRecord.objects.filter(execution__graph_version__graph=company).count(),
        "decisions": DecisionRecord.objects.filter(execution__graph_version__graph=company).count(),
        "deliverables": ServiceDeliverable.objects.filter(company=company).count(),
        "state_projections": StateProjection.objects.filter(company=company).count(),
    }


def _docker_command(*, max_jobs: int, company_name: str, user_email: str) -> str:
    return (
        "docker compose exec backend python manage.py run_career_ops_e2e "
        f"--max-jobs {max_jobs} "
        f"--company-name {json.dumps(company_name)} "
        f"--user-email {json.dumps(user_email)} "
        f"--idempotency-key {json.dumps(DEFAULT_IDEMPOTENCY_KEY)}"
    )



def _send_whatsapp_delivery(
    *,
    company: Graph,
    actor: User,
    packets: list[dict[str, Any]],
    bridge_url: str,
    chat_id: str,
    output_dir: str,
    idempotency_key: str,
) -> dict[str, Any]:
    chat_id = chat_id.strip()
    if not chat_id:
        raise ValueError("--send-whatsapp requires --whatsapp-chat-id or CAREER_OPS_WHATSAPP_CHAT_ID.")
    bridge_url = bridge_url.rstrip("/")
    headers = _bridge_request_headers(bridge_url)
    health_response = requests.get(f"{bridge_url}/health", headers=headers, timeout=15)
    health_response.raise_for_status()
    health_payload = health_response.json()
    if health_payload.get("status") not in {"connected", "ready", "authenticated"}:
        raise ValueError(f"WhatsApp bridge is not connected: {health_payload}")

    exported = _export_cv_pdfs_for_delivery(packets=packets, output_dir=output_dir, bridge_url=bridge_url)
    if len(exported) != len(packets):
        raise ValueError(f"Expected {len(packets)} exported CV PDFs, got {len(exported)}.")

    thread, _ = CommunicationThread.objects.get_or_create(
        organization=company.organization,
        company=company,
        source_key=f"career_ops:e2e:{company.id}:whatsapp:{idempotency_key}",
        defaults={
            "created_by_user": actor,
            "title": "CareerOps WhatsApp E2E Delivery",
            "thread_type": "deliverable",
            "visibility_mode": "operator",
            "status": "waiting_on_operator",
        },
    )
    link_lines = [f"{idx}. {item['company']} — {item['role_title']}: {item['job_url']}" for idx, item in enumerate(exported, start=1)]
    summary_text = "CareerOps E2E ran inside ForgeGraph. CV PDFs are attached above; application links:\n" + "\n".join(link_lines)
    message, _ = CommunicationMessage.objects.get_or_create(
        thread=thread,
        idempotency_key=f"career_ops:e2e:{company.id}:whatsapp:{idempotency_key}:summary",
        defaults={
            "organization": company.organization,
            "company": company,
            "sender_kind": "company",
            "sender_company": company,
            "message_kind": "handoff",
            "body": summary_text,
            "body_format": "plain",
            "visibility": "operator",
        },
    )
    message.organization = company.organization
    message.company = company
    message.sender_kind = "company"
    message.sender_company = company
    message.message_kind = "handoff"
    message.body = summary_text
    message.body_format = "plain"
    message.visibility = "operator"

    media_message_ids: list[str] = []
    sent_files: list[dict[str, Any]] = []
    # Preflight every host-visible file path before sending anything.
    missing_paths = [item["host_file_path"] for item in exported if not Path(item["container_file_path"]).exists()]
    if missing_paths:
        raise FileNotFoundError(f"Exported CV file missing before send: {missing_paths}")

    for idx, item in enumerate(exported, start=1):
        media_payload = {
            "chatId": chat_id,
            "filePath": item["host_file_path"],
            "mediaType": "document",
            "caption": f"CareerOps CV {idx}/5 — {item['company']} — {item['role_title']}\n{item['job_url']}",
            "fileName": item["file_name"],
        }
        media_response = requests.post(f"{bridge_url}/send-media", json=media_payload, headers=headers, timeout=120)
        media_response.raise_for_status()
        media_message_id = _message_id(media_response.json())
        media_message_ids.append(media_message_id)
        sent_files.append({**item, "media_message_id": media_message_id})
        pdf_version = AssetVersion.objects.get(id=item["asset_version_id"])
        CommunicationAttachment.objects.get_or_create(message=message, artifact=pdf_version.asset)
        CommunicationAttachment.objects.get_or_create(message=message, artifact_revision=pdf_version)
        if pdf_version.asset.origin_deliverable_id:
            CommunicationAttachment.objects.get_or_create(
                message=message,
                service_deliverable_id=pdf_version.asset.origin_deliverable_id,
            )
        _persist_whatsapp_receipt(
            company=company,
            event_id=media_message_id,
            idempotency_key=f"career_ops:e2e:{company.id}:whatsapp:{idempotency_key}:media:{idx}:{media_message_id}",
            event_type="career_ops.cv_pdf.delivered",
            payload={"chat_id": chat_id, **item, "media_message_id": media_message_id},
        )

    text_response = requests.post(
        f"{bridge_url}/send",
        json={"chatId": chat_id, "message": summary_text},
        headers=headers,
        timeout=30,
    )
    text_response.raise_for_status()
    text_message_id = _message_id(text_response.json())
    message.metadata_json = {
        **(message.metadata_json or {}),
        "career_ops": {
            "delivery_type": "whatsapp_e2e",
            "chat_id": chat_id,
            "bridge_url": bridge_url,
            "text_message_id": text_message_id,
            "media_message_ids": media_message_ids,
            "cv_count": len(sent_files),
            "link_count": len(link_lines),
            "external_side_effects_allowed": True,
        },
    }
    message.save()
    _persist_whatsapp_receipt(
        company=company,
        event_id=text_message_id,
        idempotency_key=f"career_ops:e2e:{company.id}:whatsapp:{idempotency_key}:summary:{text_message_id}",
        event_type="career_ops.links_summary.delivered",
        payload={"chat_id": chat_id, "text_message_id": text_message_id, "links": link_lines},
    )
    return {
        "status": "sent",
        "bridge_status": health_payload.get("status"),
        "chat_id": chat_id,
        "text_message_id": text_message_id,
        "media_message_ids": media_message_ids,
        "cv_count": len(sent_files),
        "link_count": len(link_lines),
        "files": sent_files,
        "communication_thread_id": str(thread.id),
        "communication_message_id": str(message.id),
    }


def _export_cv_pdfs_for_delivery(
    *, packets: list[dict[str, Any]], output_dir: str, bridge_url: str
) -> list[dict[str, Any]]:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    exported: list[dict[str, Any]] = []
    for packet in packets:
        version_id = packet.get("ats_resume_pdf_asset_version_id")
        if not version_id:
            continue
        version = AssetVersion.objects.get(id=version_id)
        provenance = version.provenance_json or {}
        encoded = provenance.get("inline_content_base64")
        if not encoded:
            raise ValueError(f"ATS resume PDF AssetVersion {version.id} has no inline_content_base64.")
        pdf_bytes = base64.b64decode(str(encoded))
        career_ops = version.asset.metadata_json.get("career_ops", {}) if isinstance(version.asset.metadata_json, dict) else {}
        opportunity_id = str(career_ops.get("opportunity_id") or packet.get("opportunity_id") or "")
        opportunity = CompanyOpportunity.objects.filter(id=opportunity_id).first()
        opp_meta = opportunity.metadata_json.get("career_ops", {}) if opportunity and isinstance(opportunity.metadata_json, dict) else {}
        company_name = str(opp_meta.get("employer_name") or (opportunity.company_name if opportunity else "Company"))
        role_title = str(opp_meta.get("role_title") or (opportunity.title if opportunity else "Role"))
        job_url = str(opp_meta.get("job_url") or "")
        file_name = f"Miguel-Athie-{_slugify(company_name)}-{_slugify(role_title)}-CV.pdf"
        container_file_path = target_dir / file_name
        container_file_path.write_bytes(pdf_bytes)
        exported.append(
            {
                "asset_version_id": str(version.id),
                "asset_id": str(version.asset_id),
                "opportunity_id": opportunity_id,
                "company": company_name,
                "role_title": role_title,
                "job_url": job_url,
                "file_name": file_name,
                "container_file_path": str(container_file_path),
                "host_file_path": _bridge_visible_file_path(bridge_url, str(container_file_path)),
                "size_bytes": len(pdf_bytes),
            }
        )
    return exported


def _persist_whatsapp_receipt(
    *, company: Graph, event_id: str, idempotency_key: str, event_type: str, payload: dict[str, Any]
) -> CommunicationEventReceipt:
    receipt, _ = CommunicationEventReceipt.objects.get_or_create(
        consumer_group="career_ops_e2e.whatsapp",
        idempotency_key=idempotency_key,
        defaults={
            "event_id": event_id,
            "topic": "whatsapp.local_bridge",
            "organization": company.organization,
            "company": company,
            "event_type": event_type,
            "schema_version": "1.0",
            "aggregate_type": "graph",
            "aggregate_id": str(company.id),
            "status": "handled",
            "handled_at": timezone.now(),
            "payload_json": payload,
        },
    )
    return receipt


def _bridge_request_headers(bridge_url: str) -> dict[str, str]:
    parsed = urlparse(bridge_url)
    if parsed.hostname == "host.docker.internal":
        port = f":{parsed.port}" if parsed.port else ""
        return {"Host": f"127.0.0.1{port}"}
    return {}


def _bridge_visible_file_path(bridge_url: str, package_path: str) -> str:
    parsed = urlparse(bridge_url)
    if parsed.hostname != "host.docker.internal":
        return package_path
    host_backend_path = os.environ.get("FORGEGRAPH_HOST_BACKEND_PATH", "").strip()
    if not host_backend_path:
        return package_path
    normalized = package_path.replace("\\", "/")
    if normalized == "/app":
        return host_backend_path
    if normalized.startswith("/app/"):
        relative = normalized[len("/app/") :]
        clean_host_backend_path = host_backend_path.rstrip("/\\")
        return f"{clean_host_backend_path}/{relative}"
    return package_path


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug[:80] or "careerops"


def _message_id(payload: dict[str, Any]) -> str:
    return str(payload.get("messageId") or payload.get("id") or payload.get("message_id") or "")
