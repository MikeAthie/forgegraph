from datetime import UTC, datetime, timedelta

import pytest

from application.services.retention import DataRetentionService
from infrastructure.orm.models import (
    ApprovalTask,
    AuditLog,
    Graph,
    GraphVersion,
    NodeRun,
    Run,
    RunCheckpoint,
    RunEvent,
    TenantRetentionPolicy,
)

pytestmark = pytest.mark.django_db


def _create_run_with_logs(user, ended_at: datetime) -> Run:
    graph = Graph.objects.create(owner=user, name="Retention Graph")
    version = GraphVersion.objects.create(
        graph=graph, version=1, graph_json={"nodes": [], "edges": []}
    )
    run = Run.objects.create(
        owner=user,
        graph_version=version,
        status="succeeded",
        started_at=ended_at - timedelta(minutes=3),
        ended_at=ended_at,
    )
    RunEvent.objects.create(run=run, event_type="start", payload={})
    NodeRun.objects.create(
        run=run,
        node_id="node-1",
        node_type="prompt",
        status="succeeded",
    )
    RunCheckpoint.objects.create(
        run=run,
        node_id="node-1",
        step_index=1,
        state_json={},
        completed_nodes=["node-1"],
        skipped_nodes=[],
        graph_json={"nodes": [], "edges": []},
    )
    ApprovalTask.objects.create(run=run, node_id="node-1", payload={})
    return run


def test_run_log_retention_deletes_logs(user):
    ended_at = datetime.now(UTC) - timedelta(days=45)
    run = _create_run_with_logs(user, ended_at)

    policy = TenantRetentionPolicy.objects.create(
        tenant_id=user.default_organization_id,
        run_logs_retention_days=30,
    )

    service = DataRetentionService(batch_size=10)
    result = service.cleanup_tenant(str(user.default_organization_id), policy, dry_run=False)

    assert result["run_events_deleted"] == 1
    assert result["node_runs_deleted"] == 1
    assert result["run_checkpoints_deleted"] == 1
    assert result["approval_tasks_deleted"] == 1
    assert Run.objects.filter(id=run.id).exists()


def test_audit_retention_dry_run_preserves_rows(user):
    policy = TenantRetentionPolicy.objects.create(
        tenant_id=user.default_organization_id,
        audit_logs_retention_days=30,
    )
    log = AuditLog.objects.create(
        tenant_id=user.default_organization_id,
        actor=user,
        action="retention_policy_updated",
        resource_type="tenant_retention_policy",
        resource_id="policy-1",
        metadata={},
    )
    AuditLog.objects.filter(id=log.id).update(created_at=datetime.now(UTC) - timedelta(days=60))

    service = DataRetentionService(batch_size=10)
    result = service.cleanup_tenant(str(user.default_organization_id), policy, dry_run=True)

    assert result["audit_logs_deleted"] == 1
    assert AuditLog.objects.filter(id=log.id).exists()
