from __future__ import annotations

import pytest
from django.utils import timezone

from application.services.memory_observation_service import MemoryObservationService
from application.services.strategy_report_builder import (
    ReportTraceabilityError,
    generate_strategy_report,
)
from infrastructure.orm.models import (
    ApprovalTask,
    Graph,
    GraphVersion,
    MemoryObservation,
    Run,
)

pytestmark = pytest.mark.django_db


def _create_completed_legacy_operation(user) -> tuple[Graph, Run]:
    organization = user.default_organization
    assert organization is not None
    graph = Graph.objects.create(
        owner=user,
        organization=organization,
        name="Atlas Growth Agency OS",
        description="Operate an AI digital marketing agency.",
    )
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={
            "nodes": [],
            "edges": [],
            "metadata": {
                "company_profile": {
                    "companyName": "Atlas Growth Agency OS",
                    "companyType": "Digital Marketing Agency",
                    "objective": "Design, validate, launch, and improve client campaigns.",
                    "client_context": {
                        "name": "Legacy",
                        "industry": "Luxury eyewear",
                        "market": "Mexico City",
                        "tier": "VIP",
                        "goal": "Launch a luxury glasses brand in Mexico City",
                    },
                }
            },
        },
    )
    run = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=version,
        status="succeeded",
        started_at=timezone.now(),
        ended_at=timezone.now(),
        input_json={
            "operation_name": "Campaign Architecture Follow-up",
            "operation_brief": "Improve the Legacy launch strategy after pressure tests.",
        },
        output_json={
            "positioning": "Position Legacy as quiet-status luxury eyewear for Mexico City.",
            "target_audience": [
                "Polanco private-client buyers",
                "Roma Norte design-led professionals",
            ],
            "approach": "Use appointment proof before broad reach.",
            "constraints": ["MXN 1.4M cap", "three launch channels", "VIP tone"],
            "execution_plan": {
                "channels": [
                    "private appointments",
                    "stylist and concierge partnerships",
                    "small Meta retargeting test",
                ],
                "rollout_phases": [
                    "brief and compliance cleanup",
                    "private fitting demand capture",
                    "guarded paid test",
                ],
                "timeline": "Six-week pilot before scale.",
            },
            "risks": [
                "Demand capture may be slower than a paid-first plan.",
                "Limited channels reduce fast reach.",
            ],
            "recommendations": [
                "Approve the three-channel VIP pilot.",
                "Hold broad creator scale until appointment conversion is proven.",
            ],
            "decision_traces": [
                {
                    "decision": "Make appointment proof the launch core.",
                    "alternatives": ["paid-first reach", "organic-only editorial"],
                    "constraints": ["MXN 1.4M cap", "brand perception risk"],
                    "departments": ["Strategy", "Finance", "Performance Marketing"],
                    "rationale": "VIP buyers need proof of taste and service before reach.",
                    "rejected": ["MXN 2.4M paid-heavy launch"],
                }
            ],
            "iteration_deltas": [
                {
                    "what_changed": "Paid retargeting moved to a secondary test.",
                    "why_changed": "Brand perception beat short-term lead volume.",
                    "trigger": "conflicting performance and brand signals",
                    "department": "Strategy",
                }
            ],
            "memory_attributions": [
                {
                    "memory_title": "Luxury retail appointment benchmark",
                    "changed_reasoning": "Relevant memory shifted the plan toward appointments.",
                }
            ],
        },
    )
    ApprovalTask.objects.create(
        run=run,
        node_id="approval_strategy",
        assignee=user,
        status="rejected",
        payload={"prompt_message": "Approve the campaign claims."},
        result={
            "approved": False,
            "what_changed_after_rejection": "Removed health-adjacent language.",
            "improved_before_reapproval": "Preserved legal clarity and VIP client trust.",
        },
        resolved_at=timezone.now(),
    )
    MemoryObservation.objects.create(
        tenant_id=organization.id,
        graph_id=graph.id,
        run_id=run.id,
        type="case",
        title="Legacy appointment learning",
        content="Appointments protected brand perception while paid demand was tested.",
        scope="run",
        topic_key="legacy-appointment-proof",
    )
    return graph, run


def test_generate_strategy_report_builds_client_markdown_from_traceable_state(user) -> None:
    company, operation = _create_completed_legacy_operation(user)

    artifact = generate_strategy_report(str(company.id), str(operation.id))

    assert artifact.format == "md"
    assert artifact.content_type.startswith("text/markdown")
    assert isinstance(artifact.content, str)
    assert "# Client Strategy Report: Legacy" in artifact.content
    assert "**Strategy:** Campaign Architecture Follow-up" in artifact.content
    assert "Make appointment proof the launch core" in artifact.content
    assert "MXN 1.4M cap" in artifact.content
    assert "Requirements shaping the choice" in artifact.content
    assert "prior experience shifted the plan toward appointments" in artifact.content
    assert "Approve the three-channel VIP pilot" in artifact.content
    assert "**Operation:**" not in artifact.content
    assert "Constraints applied" not in artifact.content
    assert "Memory" not in artifact.content
    assert "memory" not in artifact.content
    assert "operation" not in artifact.content.lower()
    assert "constraint" not in artifact.content.lower()
    assert "iteration" not in artifact.content.lower()
    assert "graph" not in artifact.content.lower()
    assert "node" not in artifact.content.lower()
    assert set(artifact.traceability) >= {
        "executive_summary",
        "strategy_narrative",
        "key_decisions",
        "iteration_story",
        "insights",
        "execution_plan",
        "risks_tradeoffs",
        "recommendations",
    }


def test_generate_strategy_report_reuses_prior_run_memory_for_follow_up(user) -> None:
    company, prior_operation = _create_completed_legacy_operation(user)
    organization = user.default_organization
    assert organization is not None
    service = MemoryObservationService()
    prior_memory = service.create_observation(
        tenant_id=organization.id,
        graph_id=company.id,
        run_id=prior_operation.id,
        type="case",
        title="Legacy rejected WhatsApp claim",
        content=(
            "Prior approved learning: keep appointment proof central, avoid unverified "
            "WhatsApp exclusivity claims, and stay within configured email/social sandbox "
            "connectors unless additional connectors are approved."
        ),
        scope="graph",
        topic_key="legacy-follow-up-approval-learning",
    )

    context = service.get_context(
        tenant_id=organization.id,
        graph_id=company.id,
        query="Legacy follow-up WhatsApp appointment proof",
        limit=5,
    )

    assert prior_memory.id in {memory.id for memory in context.observations}

    follow_up = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=prior_operation.graph_version,
        status="succeeded",
        started_at=timezone.now(),
        ended_at=timezone.now(),
        input_json={
            "operation_name": "Campaign Architecture Follow-up",
            "operation_brief": "Improve the second Legacy campaign using approved learnings.",
        },
        output_json={
            "positioning": "Keep Legacy as appointment-led quiet luxury eyewear.",
            "target_audience": ["VIP eyewear buyers in Mexico City"],
            "approach": "Reuse appointment proof and configured email/social sandbox channels.",
            "constraints": [
                "Do not use unverified WhatsApp exclusivity claims",
                "Use configured email/social sandbox connectors only",
            ],
            "execution_plan": {
                "channels": ["email", "social retargeting", "appointment concierge follow-up"],
                "timeline": "Four-week follow-up campaign before channel expansion.",
            },
            "risks": ["Unsupported connector claims would weaken client trust."],
            "recommendations": [
                "Approve the follow-up only after the connector list is confirmed.",
                "Keep appointment proof in the lead message.",
            ],
            "decision_traces": [
                {
                    "decision": "Keep the follow-up appointment-led.",
                    "alternatives": ["WhatsApp exclusivity claim", "paid-first broad reach"],
                    "constraints": [
                        "Use configured connectors only",
                        "Preserve approved appointment proof",
                    ],
                    "departments": ["Strategy", "Compliance", "Performance Marketing"],
                    "rationale": "The prior approved learning reduced compliance risk.",
                    "rejected": ["unverified WhatsApp exclusivity claim"],
                }
            ],
            "iteration_deltas": [
                {
                    "what_changed": "Follow-up messaging kept appointment proof and removed the exclusivity claim.",
                    "why_changed": "Prior approved learning showed the claim was not safe to repeat.",
                    "trigger": "second-run memory review",
                    "department": "Compliance",
                }
            ],
            "memory_attributions": [
                {
                    "memory_title": prior_memory.title,
                    "changed_reasoning": (
                        "Prior approved learning kept appointment proof central and avoided "
                        "the rejected WhatsApp exclusivity claim."
                    ),
                }
            ],
        },
    )

    artifact = generate_strategy_report(str(company.id), str(follow_up.id))
    content = artifact.content.lower()

    assert "prior experience" in content
    assert "appointment proof" in content
    assert "unverified whatsapp exclusivity claim" in content
    assert str(prior_memory.id) in {
        source["id"]
        for sources in artifact.traceability.values()
        for source in sources
        if source["kind"] == "memory"
    }
    assert "memory" not in content


def test_generate_strategy_report_supports_html_and_pdf_formats(user) -> None:
    company, operation = _create_completed_legacy_operation(user)

    html_artifact = generate_strategy_report(str(company.id), str(operation.id), format="html")
    pdf_artifact = generate_strategy_report(str(company.id), str(operation.id), format="pdf")

    assert isinstance(html_artifact.content, str)
    assert "<h1>Client Strategy Report: Legacy</h1>" in html_artifact.content
    assert html_artifact.content_type.startswith("text/html")
    assert isinstance(pdf_artifact.content, bytes)
    assert pdf_artifact.content.startswith(b"%PDF-1.4")
    assert pdf_artifact.content_type == "application/pdf"


def test_generate_strategy_report_fails_when_sections_are_not_traceable(user) -> None:
    organization = user.default_organization
    assert organization is not None
    graph = Graph.objects.create(
        owner=user, organization=organization, name="Atlas Growth Agency OS"
    )
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {"company_profile": {}}},
    )
    run = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=version,
        status="succeeded",
        started_at=timezone.now(),
        ended_at=timezone.now(),
        input_json={"operation_brief": "Launch Legacy."},
        output_json={"deliverable": "A thin final note without traceable decisions."},
    )

    with pytest.raises(ReportTraceabilityError):
        generate_strategy_report(str(graph.id), str(run.id))


def test_generate_strategy_report_requires_completed_operation(user) -> None:
    organization = user.default_organization
    assert organization is not None
    graph = Graph.objects.create(
        owner=user, organization=organization, name="Atlas Growth Agency OS"
    )
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    run = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=version,
        status="running",
        started_at=timezone.now(),
        input_json={"operation_brief": "Launch Legacy."},
    )

    with pytest.raises(ReportTraceabilityError, match="completed operation"):
        generate_strategy_report(str(graph.id), str(run.id))
