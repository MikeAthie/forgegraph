from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    MemoryChunk,
    MemoryObservation,
    MemoryUsage,
    NodeRun,
    Run,
)

pytestmark = pytest.mark.django_db


def _create_run(user):
    graph = Graph.objects.create(owner=user, name="Memory Analytics Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    return Run.objects.create(
        owner=user,
        graph_version=version,
        status="succeeded",
        started_at=timezone.now(),
        ended_at=timezone.now(),
    )


def test_memory_usage_includes_curated_memory_stats(authenticated_client, user):
    run = _create_run(user)
    MemoryUsage.objects.create(
        tenant_id=user.default_organization_id,
        usage_date=timezone.now().date(),
        summarization_prompt_tokens=80,
        summarization_completion_tokens=20,
        summarization_total_tokens=100,
        summarization_cost_usd=1.5,
    )
    chunk = MemoryChunk.objects.create(
        tenant_id=user.default_organization_id,
        agent_id=None,
        run_id=run.id,
        session_id=None,
        content="Indexed observation chunk",
        chunk_type="observation",
        metadata={"source": "test"},
        embedding=[0.0] * 1536,
        embedding_model="text-embedding-3-small",
        source_timestamp=timezone.now(),
    )
    MemoryObservation.objects.create(
        tenant_id=user.default_organization_id,
        graph_id=run.graph_version.graph_id,
        run_id=run.id,
        session_id=run.thread_id,
        type="fact",
        title="Indexed preference",
        content="Customer prefers async follow-up.",
        scope="graph",
        topic_key="pref",
        memory_chunk=chunk,
        last_seen_at=timezone.now(),
    )
    MemoryObservation.objects.create(
        tenant_id=user.default_organization_id,
        graph_id=run.graph_version.graph_id,
        run_id=run.id,
        session_id=run.thread_id,
        type="fact",
        title="Pending observation",
        content="Customer also prefers concise recaps.",
        scope="graph",
        topic_key="pref-2",
        last_seen_at=timezone.now(),
    )
    NodeRun.objects.create(
        run=run,
        node_id="obs-context",
        node_type="observation_context",
        status="succeeded",
        started_at=timezone.now() - timedelta(minutes=2),
        ended_at=timezone.now() - timedelta(minutes=1),
    )

    response = authenticated_client.get("/api/analytics/memory/usage", {"period": "30d"})

    assert response.status_code == status.HTTP_200_OK
    payload = response.data["data"]
    assert payload["curated_memory"]["observations_total"] == 2
    assert payload["curated_memory"]["indexed_observations_total"] == 1
    assert payload["curated_memory"]["pending_index_total"] == 1
    assert payload["curated_memory"]["retrieval_runs_in_period"] == 1
    assert payload["retention"]["observations_retention_mode"] == "manual"
    assert "manual cleanup" in payload["retention"]["summary"]


def test_memory_export_returns_report_dataset(authenticated_client, user):
    run = _create_run(user)
    MemoryUsage.objects.create(
        tenant_id=user.default_organization_id,
        usage_date=timezone.now().date(),
        summarization_prompt_tokens=10,
        summarization_completion_tokens=5,
        summarization_total_tokens=15,
        summarization_cost_usd=0.25,
    )
    MemoryObservation.objects.create(
        tenant_id=user.default_organization_id,
        graph_id=run.graph_version.graph_id,
        run_id=run.id,
        session_id=run.thread_id,
        type="fact",
        title="Support style",
        content="Use direct and minimal responses.",
        scope="graph",
        topic_key="support-style",
        last_seen_at=timezone.now(),
    )

    json_response = authenticated_client.get(
        "/api/analytics/memory/export",
        {"dataset": "report", "export_format": "json", "period": "30d"},
    )
    assert json_response.status_code == status.HTTP_200_OK
    payload = json_response.data["data"]
    assert payload["dataset"] == "report"
    assert payload["usage"]["curated_memory"]["observations_total"] == 1
    assert "indexing" in payload["performance"]

    csv_response = authenticated_client.get(
        "/api/analytics/memory/export",
        {"dataset": "report", "export_format": "csv", "period": "30d"},
    )
    assert csv_response.status_code == status.HTTP_200_OK
    assert csv_response["Content-Type"].startswith("text/csv")
    body = csv_response.content.decode()
    assert "observations_total" in body
    assert "pending_index_total" in body


def test_memory_export_supports_date_range_and_staff_tenant_scope(authenticated_client, user):
    user.is_staff = True
    user.save(update_fields=["is_staff"])

    other_user = type(user).objects.create_user(
        email="other-memory-tenant@example.com",
        password="testpassword123",
    )
    ensure_default_organization(other_user)
    other_run = _create_run(other_user)
    MemoryUsage.objects.create(
        tenant_id=other_user.default_organization_id,
        usage_date=timezone.now().date(),
        summarization_prompt_tokens=20,
        summarization_completion_tokens=10,
        summarization_total_tokens=30,
        summarization_cost_usd=0.5,
    )
    MemoryObservation.objects.create(
        tenant_id=other_user.default_organization_id,
        graph_id=other_run.graph_version.graph_id,
        run_id=other_run.id,
        session_id=other_run.thread_id,
        type="fact",
        title="Scoped observation",
        content="Only visible for the selected tenant.",
        scope="graph",
        topic_key="scoped-observation",
        last_seen_at=timezone.now(),
    )

    response = authenticated_client.get(
        "/api/analytics/memory/export",
        {
            "dataset": "report",
            "export_format": "json",
            "tenant_id": other_user.default_organization_id,
            "start_date": timezone.now().date().isoformat(),
            "end_date": timezone.now().date().isoformat(),
        },
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.data["data"]
    assert payload["usage"]["curated_memory"]["observations_total"] == 1
    assert payload["usage"]["totals"]["summarization_total_tokens"] == 30


def test_memory_usage_rejects_cross_tenant_scope_for_non_staff(authenticated_client, user):
    response = authenticated_client.get(
        "/api/analytics/memory/usage",
        {"tenant_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
