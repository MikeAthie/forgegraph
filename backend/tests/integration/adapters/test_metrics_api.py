from django.utils import timezone
from rest_framework import status

from application.services.metrics import (
    record_api_request,
    record_callback_auth_failure,
    record_liveness_reconciliation,
    record_run_completed,
    record_run_started,
    record_stale_attempt_ignored,
)
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    OrganizationMembership,
    Run,
    RunQueueEntry,
)


def test_metrics_summary_returns_run_and_queue_stats(authenticated_client, user):
    graph = Graph.objects.create(owner=user, name="Metrics Graph")
    version = GraphVersion.objects.create(
        graph=graph, version=1, graph_json={"nodes": [], "edges": []}
    )
    pending_run = Run.objects.create(owner=user, graph_version=version, status="pending")
    processing_run = Run.objects.create(owner=user, graph_version=version, status="pending")

    RunQueueEntry.objects.create(
        run=pending_run,
        tenant_id=user.default_organization_id,
        status="pending",
        available_at=timezone.now(),
    )
    RunQueueEntry.objects.create(
        run=processing_run,
        tenant_id=user.default_organization_id,
        status="processing",
        available_at=timezone.now(),
        attempts=1,
    )

    record_run_started()
    record_run_completed("succeeded", 1200)
    record_run_completed("failed", 3000)
    record_liveness_reconciliation("engine_stalled")
    record_stale_attempt_ignored("engine_callback")
    record_callback_auth_failure("invalid_signature")
    record_api_request(status_code=200, duration_ms=120)
    record_api_request(status_code=503, duration_ms=240)

    response = authenticated_client.get("/api/metrics/summary")
    assert response.status_code == status.HTTP_200_OK
    payload = response.data["data"]
    assert payload["runs"]["started_total"] >= 1
    assert payload["runs"]["completed_total"] >= 2
    assert payload["runs"]["failed_total"] >= 1
    assert payload["runs"]["liveness_reconciled_total"] >= 1
    assert payload["runs"]["liveness_reconciled_by_reason"]["engine_stalled"] >= 1
    assert payload["runs"]["stale_attempt_ignored_total"] >= 1
    assert payload["runs"]["stale_attempt_ignored_by_source"]["engine_callback"] >= 1
    assert "failure_rate" in payload["runs"]
    assert "active_total" in payload["runs"]
    assert payload["queue"]["pending"] >= 1
    assert payload["queue"]["processing"] >= 1
    assert payload["queue"]["total_depth"] >= 2
    assert "oldest_pending_age_seconds" in payload["queue"]
    assert "by_tenant" in payload["queue"]
    assert "websocket" in payload
    assert payload["api"]["requests_total"] >= 2
    assert payload["api"]["server_errors_total"] >= 1
    assert payload["api"]["callback_auth_failures_total"] >= 1
    assert payload["api"]["callback_auth_failures_by_reason"]["invalid_signature"] >= 1
    assert "guardrails" in payload
    assert "generated_at" in payload


def test_metrics_summary_requires_admin_role(api_client, user):
    membership = OrganizationMembership.objects.get(
        organization=user.default_organization,
        user=user,
    )
    membership.role = "viewer"
    membership.save(update_fields=["role"])

    api_client.force_authenticate(user=user)
    response = api_client.get("/api/metrics/summary")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["error"]["code"] == "FORBIDDEN"
