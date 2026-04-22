from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.services.run_queue import RunQueueSettings, enqueue_run
from infrastructure.orm.management.commands import process_run_queue
from infrastructure.orm.management.commands.process_run_queue import Command
from infrastructure.orm.models import Graph, GraphVersion, Run


class _RecordingEngineClient:
    def __init__(self) -> None:
        self.start_calls: list[dict[str, object]] = []

    def __enter__(self) -> _RecordingEngineClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def start_run(self, **kwargs):
        self.start_calls.append(kwargs)


@pytest.mark.django_db
def test_process_run_queue_uses_persisted_dispatch_graph_without_repreparing(monkeypatch, user):
    graph = Graph.objects.create(owner=user, name="Queued Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={
            "nodes": [{"id": "source", "type": "transform", "name": "Source"}],
            "edges": [],
        },
    )
    persisted_graph = {
        "nodes": [{"id": "agent_1", "type": "agent", "name": "Agent"}],
        "edges": [],
        "metadata": {
            "tool_resolution": {
                "manifest_version": 2,
                "manifest_checksum": "pinned-checksum",
            }
        },
    }
    run = Run.objects.create(
        owner=user,
        graph_version=version,
        status="pending",
        input_json={"hello": "queue"},
        dispatch_graph_json=persisted_graph,
    )
    entry = enqueue_run(run, tenant_id=str(user.default_organization_id))

    engine_client = _RecordingEngineClient()

    def _unexpected_prepare_graph_for_engine(*args, **kwargs):
        raise AssertionError(
            "prepare_graph_for_engine should not be called when dispatch_graph_json is pinned"
        )

    monkeypatch.setattr(
        process_run_queue,
        "prepare_graph_for_engine",
        _unexpected_prepare_graph_for_engine,
    )
    monkeypatch.setattr(process_run_queue, "validate_prompt_credentials", lambda graph, owner: [])
    monkeypatch.setattr(
        process_run_queue, "resolve_engine_callback_url", lambda run_id: "http://callback"
    )
    monkeypatch.setattr(
        process_run_queue,
        "select_engine_target",
        lambda run_id: SimpleNamespace(host="localhost", port=50051, engine_id="engine-1"),
    )
    monkeypatch.setattr(
        process_run_queue, "get_engine_client", lambda *args, **kwargs: engine_client
    )
    monkeypatch.setattr(process_run_queue, "broadcast_run_updated", lambda run: None)
    monkeypatch.setattr(process_run_queue, "record_run_started", lambda: None)

    queue_settings = RunQueueSettings(
        max_per_tenant=1,
        lock_timeout_seconds=300,
        retry_delay_seconds=30,
    )

    Command()._process_entry(entry, queue_settings)

    run.refresh_from_db()
    entry.refresh_from_db()

    assert run.status == "running"
    assert entry.status == "completed"
    assert len(engine_client.start_calls) == 1
    assert engine_client.start_calls[0]["graph_json"] == persisted_graph
