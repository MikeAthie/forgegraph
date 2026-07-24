from __future__ import annotations

import base64
import json
from io import StringIO
from typing import Any
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command

from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    CommunicationEventReceipt,
    CommunicationMessage,
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

pytestmark = pytest.mark.django_db


def test_run_career_ops_e2e_command_persists_forgegraph_state(user: User) -> None:
    out = StringIO()

    call_command(
        "run_career_ops_e2e",
        user_email=user.email,
        company_name="CareerOps Docker Command Test Co",
        max_jobs=2,
        idempotency_key="careerops-e2e-test",
        stdout=out,
    )

    payload = json.loads(out.getvalue())

    assert payload["status"] == "ok"
    assert payload["processed_count"] == 2
    assert payload["external_side_effects_allowed"] is False
    assert payload["live_send_allowed"] is False
    assert payload["docker_command"].startswith(
        "docker compose exec backend python manage.py run_career_ops_e2e"
    )

    company = Graph.objects.get(id=payload["company_id"])
    assert company.name == "CareerOps Docker Command Test Co"
    base_cv = Asset.objects.get(company=company, source_key="career_ops:cv_source", status="active")
    assert "Cambridge English C2 Proficiency" in json.dumps(base_cv.metadata_json)
    assert "https://github.com/MikeAthie/ForgeGraph" in json.dumps(base_cv.metadata_json)
    assert CompanySignal.objects.filter(company=company, domain_context="career_ops").count() == 2
    assert CompanyOpportunity.objects.filter(company=company).count() == 2
    assert (
        Run.objects.filter(
            organization=company.organization, input_json__career_ops__pipeline="url_intake"
        ).count()
        == 2
    )
    assert TaskRecord.objects.filter(execution__graph_version__graph=company).count() >= 12
    assert DecisionRecord.objects.filter(execution__graph_version__graph=company).count() == 2
    assert StateProjection.objects.filter(company=company).exists()

    deliverable_types = set(
        ServiceDeliverable.objects.filter(company=company).values_list(
            "deliverable_type", flat=True
        )
    )
    assert deliverable_types >= {
        "job_liveness_receipt",
        "job_evaluation_report",
        "tailored_resume_html",
        "ats_resume_text",
        "ats_resume_html",
        "ats_resume_pdf",
        "ats_resume_parseability_report",
        "recruiter_evaluation_report",
        "cover_letter_draft",
        "ats_simulation_report",
        "application_packet",
    }

    for packet in payload["packets"]:
        assert packet["packet_asset_version_id"]
        assert packet["readiness"]["status"] == "blocked"
        assert packet["readiness"]["checks"]["base_cv_present"] == "pass"
        assert packet["readiness"]["checks"]["ats_resume_pdf_present"] == "pass"
        assert packet["readiness"]["checks"]["ats_resume_parseability_passed"] == "pass"
        assert packet["readiness"]["checks"]["exact_version_approval_present"] == "blocked"
        assert packet["external_side_effects_allowed"] is False
        pdf_version = AssetVersion.objects.get(id=packet["ats_resume_pdf_asset_version_id"])
        assert pdf_version.mime_type == "application/pdf"
        assert pdf_version.provenance_json["career_ops"]["external_side_effects_allowed"] is False
        text_version = AssetVersion.objects.get(id=packet["ats_resume_text_asset_version_id"])
        text_content = base64.b64decode(
            text_version.provenance_json["inline_content_base64"]
        ).decode("utf-8")
        assert "Cambridge English C2 Proficiency" in text_content


def test_run_career_ops_e2e_command_can_deliver_whatsapp_handoff(user: User, tmp_path) -> None:
    out = StringIO()
    bridge_posts: list[tuple[str, dict[str, Any]]] = []

    def fake_post(
        url: str,
        *,
        json: dict[str, Any],
        headers: dict[str, Any] | None = None,
        timeout: int = 0,
    ) -> Mock:
        bridge_posts.append((url, json))
        response = Mock()
        response.raise_for_status.return_value = None
        if url.endswith("/send-media"):
            response.json.return_value = {
                "messageId": f"media-{len([u for u, _ in bridge_posts if u.endswith('/send-media')])}"
            }
        else:
            response.json.return_value = {"messageId": "summary-text-1"}
        return response

    health = Mock()
    health.raise_for_status.return_value = None
    health.json.return_value = {"status": "connected"}

    with (
        patch(
            "infrastructure.orm.management.commands.run_career_ops_e2e.requests.get",
            return_value=health,
        ),
        patch(
            "infrastructure.orm.management.commands.run_career_ops_e2e.requests.post",
            side_effect=fake_post,
        ),
    ):
        call_command(
            "run_career_ops_e2e",
            user_email=user.email,
            company_name="CareerOps WhatsApp Test Co",
            max_jobs=2,
            idempotency_key="careerops-e2e-whatsapp-test",
            send_whatsapp=True,
            whatsapp_bridge_url="http://host.docker.internal:3000",
            whatsapp_chat_id="5215539003599@s.whatsapp.net",
            delivery_output_dir=str(tmp_path),
            stdout=out,
        )

    payload = json.loads(out.getvalue())
    delivery = payload["whatsapp_delivery"]
    assert delivery["status"] == "sent"
    assert delivery["cv_count"] == 2
    assert delivery["link_count"] == 2
    assert len(delivery["media_message_ids"]) == 2
    assert delivery["text_message_id"] == "summary-text-1"

    media_posts = [body for url, body in bridge_posts if url.endswith("/send-media")]
    text_posts = [body for url, body in bridge_posts if url.endswith("/send")]
    assert len(media_posts) == 2
    assert len(text_posts) == 1
    assert all(body["mediaType"] == "document" for body in media_posts)
    assert all(body["filePath"].endswith(".pdf") for body in media_posts)
    assert "application links" in text_posts[0]["message"].lower()

    for file_info in delivery["files"]:
        exported = tmp_path / file_info["file_name"]
        assert exported.exists()
        assert exported.read_bytes().startswith(b"%PDF")

    company = Graph.objects.get(id=payload["company_id"])
    message = CommunicationMessage.objects.get(id=delivery["communication_message_id"])
    assert message.company == company
    assert message.attachments.count() >= 4
    assert (
        CommunicationEventReceipt.objects.filter(
            company=company, consumer_group="career_ops_e2e.whatsapp"
        ).count()
        == 3
    )
