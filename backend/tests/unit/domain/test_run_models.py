"""
Unit tests for Run and NodeRun domain models.

Tests model properties, validations, and business logic for Phase 4 observability.
"""

from datetime import timedelta
from typing import cast

import pytest
from django.db import IntegrityError
from django.utils import timezone

from infrastructure.orm.models import Graph, GraphVersion, NodeRun, Run, User

pytestmark = pytest.mark.django_db


class TestRunModel:
    """Tests for Run model properties and validations."""

    def test_run_status_choices_are_valid(self, user):
        """Test that all status choices can be set without errors."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        valid_statuses = ["pending", "running", "paused", "succeeded", "failed", "canceled"]
        for status_value in valid_statuses:
            run = Run.objects.create(owner=user, graph_version=version, status=status_value)
            assert run.status == status_value
            run.delete()

    def test_run_duration_ms_returns_none_when_started_at_is_none(self, user):
        """Test that duration_ms returns None when started_at is None."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="pending", started_at=None
        )

        assert run.duration_ms is None

    def test_run_duration_ms_returns_none_when_ended_at_is_none(self, user):
        """Test that duration_ms returns None when ended_at is None."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="running",
            started_at=timezone.now(),
            ended_at=None,
        )

        assert run.duration_ms is None

    def test_run_duration_ms_calculates_correctly(self, user):
        """Test that duration_ms calculates the correct milliseconds."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        now = timezone.now()
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="succeeded",
            started_at=now,
            ended_at=now + timedelta(milliseconds=1500),
        )

        assert run.duration_ms == 1500

    def test_run_duration_ms_rounds_down_fractional_milliseconds(self, user):
        """Test that duration_ms rounds down fractional milliseconds."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        now = timezone.now()
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="succeeded",
            started_at=now,
            ended_at=now + timedelta(microseconds=1999),
        )

        # 1999 microseconds = 1.999 ms, should round down to 1
        assert run.duration_ms == 1

    def test_run_duration_ms_handles_zero_duration(self, user):
        """Test that duration_ms returns 0 for identical timestamps."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        now = timezone.now()
        run = Run.objects.create(
            owner=user, graph_version=version, status="succeeded", started_at=now, ended_at=now
        )

        assert run.duration_ms == 0

    def test_run_duration_ms_handles_long_duration(self, user):
        """Test that duration_ms correctly handles long durations."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        now = timezone.now()
        # 1 hour = 3,600,000 ms
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="succeeded",
            started_at=now,
            ended_at=now + timedelta(hours=1),
        )

        assert run.duration_ms == 3600000

    def test_run_requires_owner(self, user):
        """Test that a run requires an owner."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        with pytest.raises(IntegrityError):
            Run.objects.create(owner=cast(User, None), graph_version=version, status="pending")

    def test_run_requires_graph_version(self, user):
        """Test that a run requires a graph_version."""
        with pytest.raises(IntegrityError):
            Run.objects.create(
                owner=user,
                graph_version=cast(GraphVersion, None),
                status="pending",
            )

    def test_run_default_values_are_set(self, user):
        """Test that default values are correctly set on creation."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version)

        assert run.status == "pending"
        assert run.input_json == {}
        assert run.output_json is None
        assert run.error_message == ""
        assert run.started_at is None
        assert run.ended_at is None

    def test_run_input_json_stores_complex_data(self, user):
        """Test that input_json can store complex nested data."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        complex_input = {
            "nested": {"key": "value", "array": [1, 2, 3]},
            "number": 42,
            "boolean": True,
            "null": None,
        }
        run = Run.objects.create(owner=user, graph_version=version, input_json=complex_input)

        run.refresh_from_db()
        assert run.input_json == complex_input

    def test_run_output_json_stores_complex_data(self, user):
        """Test that output_json can store complex nested data."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        complex_output = {
            "results": [{"id": 1, "status": "ok"}, {"id": 2, "status": "failed"}],
            "metadata": {"count": 2, "timestamp": "2024-01-01T00:00:00Z"},
        }
        run = Run.objects.create(owner=user, graph_version=version, output_json=complex_output)

        run.refresh_from_db()
        assert run.output_json == complex_output

    def test_run_error_message_stores_long_text(self, user):
        """Test that error_message can store long error messages."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        long_error = "Error: " + ("x" * 5000)
        run = Run.objects.create(owner=user, graph_version=version, error_message=long_error)

        run.refresh_from_db()
        assert run.error_message == long_error

    def test_run_cascade_deletes_with_graph_version(self, user):
        """Test that runs are deleted when their graph_version is deleted."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="pending")

        run_id = run.id
        version.delete()

        assert not Run.objects.filter(id=run_id).exists()

    def test_run_cascade_deletes_with_owner(self, user):
        """Test that runs are deleted when their owner is deleted."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="pending")

        run_id = run.id
        user.delete()

        assert not Run.objects.filter(id=run_id).exists()

    def test_run_indexes_exist(self, user):
        """Test that expected indexes exist on Run model."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        Run.objects.create(owner=user, graph_version=version, status="pending")

        # Check that the indexes are defined in Meta
        assert hasattr(Run, "_meta")
        index_names = [index.name for index in Run._meta.indexes]
        assert "runs_owner_started_idx" in index_names
        assert "runs_owner_status_idx" in index_names


class TestNodeRunModel:
    """Tests for NodeRun model properties and validations."""

    def test_node_run_status_choices_are_valid(self, user):
        """Test that all status choices can be set without errors."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        valid_statuses = ["pending", "running", "succeeded", "failed", "skipped"]
        for status_value in valid_statuses:
            node_run = NodeRun.objects.create(
                run=run, node_id=f"node_{status_value}", node_type="prompt", status=status_value
            )
            assert node_run.status == status_value
            node_run.delete()

    def test_node_run_duration_ms_returns_none_when_started_at_is_none(self, user):
        """Test that duration_ms returns None when started_at is None."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")
        node_run = NodeRun.objects.create(
            run=run, node_id="node_1", node_type="prompt", status="pending", started_at=None
        )

        assert node_run.duration_ms is None

    def test_node_run_duration_ms_returns_none_when_ended_at_is_none(self, user):
        """Test that duration_ms returns None when ended_at is None."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")
        node_run = NodeRun.objects.create(
            run=run,
            node_id="node_1",
            node_type="prompt",
            status="running",
            started_at=timezone.now(),
            ended_at=None,
        )

        assert node_run.duration_ms is None

    def test_node_run_duration_ms_calculates_correctly(self, user):
        """Test that duration_ms calculates the correct milliseconds."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        now = timezone.now()
        node_run = NodeRun.objects.create(
            run=run,
            node_id="node_1",
            node_type="prompt",
            status="succeeded",
            started_at=now,
            ended_at=now + timedelta(milliseconds=250),
        )

        assert node_run.duration_ms == 250

    def test_node_run_duration_ms_handles_zero_duration(self, user):
        """Test that duration_ms returns 0 for identical timestamps."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        now = timezone.now()
        node_run = NodeRun.objects.create(
            run=run,
            node_id="node_1",
            node_type="prompt",
            status="succeeded",
            started_at=now,
            ended_at=now,
        )

        assert node_run.duration_ms == 0

    def test_node_run_duration_ms_handles_microseconds(self, user):
        """Test that duration_ms correctly converts microseconds to milliseconds."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        now = timezone.now()
        # 500 microseconds = 0.5 ms, should round down to 0
        node_run = NodeRun.objects.create(
            run=run,
            node_id="node_1",
            node_type="prompt",
            status="succeeded",
            started_at=now,
            ended_at=now + timedelta(microseconds=500),
        )

        assert node_run.duration_ms == 0

    def test_node_run_requires_run(self, user):
        """Test that a node_run requires a run."""
        with pytest.raises(IntegrityError):
            NodeRun.objects.create(
                run=cast(Run, None),
                node_id="node_1",
                node_type="prompt",
                status="pending",
            )

    def test_node_run_requires_node_id(self, user):
        """Test that a node_run requires a node_id."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        with pytest.raises(IntegrityError):
            NodeRun.objects.create(
                run=run,
                node_id=cast(str, None),
                node_type="prompt",
                status="pending",
            )

    def test_node_run_requires_node_type(self, user):
        """Test that a node_run requires a node_type."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        with pytest.raises(IntegrityError):
            NodeRun.objects.create(
                run=run,
                node_id="node_1",
                node_type=cast(str, None),
                status="pending",
            )

    def test_node_run_default_values_are_set(self, user):
        """Test that default values are correctly set on creation."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")
        node_run = NodeRun.objects.create(run=run, node_id="node_1", node_type="prompt")

        assert node_run.status == "pending"
        assert node_run.attempt == 1
        assert node_run.input_json == {}
        assert node_run.output_json is None
        assert node_run.error_json is None
        assert node_run.started_at is None
        assert node_run.ended_at is None

    def test_node_run_attempt_increments(self, user):
        """Test that multiple attempts can be created for the same node."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        node_run1 = NodeRun.objects.create(run=run, node_id="node_1", node_type="prompt", attempt=1)
        node_run2 = NodeRun.objects.create(run=run, node_id="node_1", node_type="prompt", attempt=2)

        assert node_run1.attempt == 1
        assert node_run2.attempt == 2

    def test_node_run_input_json_stores_complex_data(self, user):
        """Test that input_json can store complex nested data."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        complex_input = {"prompt": "test", "config": {"temp": 0.7, "max_tokens": 100}}
        node_run = NodeRun.objects.create(
            run=run, node_id="node_1", node_type="prompt", input_json=complex_input
        )

        node_run.refresh_from_db()
        assert node_run.input_json == complex_input

    def test_node_run_output_json_stores_complex_data(self, user):
        """Test that output_json can store complex nested data."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        complex_output = {"response": "Hello", "metadata": {"model": "gpt-4", "tokens": 10}}
        node_run = NodeRun.objects.create(
            run=run, node_id="node_1", node_type="prompt", output_json=complex_output
        )

        node_run.refresh_from_db()
        assert node_run.output_json == complex_output

    def test_node_run_error_json_stores_error_details(self, user):
        """Test that error_json can store error details."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        error_details = {
            "code": "TIMEOUT",
            "message": "Node execution timed out after 30s",
            "stack": "...",
        }
        node_run = NodeRun.objects.create(
            run=run, node_id="node_1", node_type="http", error_json=error_details
        )

        node_run.refresh_from_db()
        assert node_run.error_json == error_details

    def test_node_run_cascade_deletes_with_run(self, user):
        """Test that node_runs are deleted when their run is deleted."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")
        node_run = NodeRun.objects.create(run=run, node_id="node_1", node_type="prompt")

        node_run_id = node_run.id
        run.delete()

        assert not NodeRun.objects.filter(id=node_run_id).exists()

    def test_node_run_ordering_by_started_at(self, user):
        """Test that node_runs are ordered by started_at by default."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        now = timezone.now()
        node_run3 = NodeRun.objects.create(
            run=run, node_id="node_3", node_type="prompt", started_at=now + timedelta(seconds=2)
        )
        node_run1 = NodeRun.objects.create(
            run=run, node_id="node_1", node_type="prompt", started_at=now
        )
        node_run2 = NodeRun.objects.create(
            run=run, node_id="node_2", node_type="prompt", started_at=now + timedelta(seconds=1)
        )

        node_runs = list(NodeRun.objects.filter(run=run))
        assert node_runs[0].id == node_run1.id
        assert node_runs[1].id == node_run2.id
        assert node_runs[2].id == node_run3.id

    def test_node_run_indexes_exist(self, user):
        """Test that expected indexes exist on NodeRun model."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")
        NodeRun.objects.create(run=run, node_id="node_1", node_type="prompt")

        # Check that the indexes are defined in Meta
        assert hasattr(NodeRun, "_meta")
        index_names = [index.name for index in NodeRun._meta.indexes]
        assert "node_runs_run_time_idx" in index_names

    def test_node_run_allows_same_node_id_in_different_runs(self, user):
        """Test that the same node_id can exist in different runs."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run1 = Run.objects.create(owner=user, graph_version=version, status="running")
        run2 = Run.objects.create(owner=user, graph_version=version, status="running")

        node_run1 = NodeRun.objects.create(run=run1, node_id="node_1", node_type="prompt")
        node_run2 = NodeRun.objects.create(run=run2, node_id="node_1", node_type="prompt")

        assert node_run1.node_id == node_run2.node_id
        assert node_run1.run != node_run2.run


class TestRunStatusTransitions:
    """Tests for Run status transition logic and state validation."""

    def test_run_can_transition_from_pending_to_running(self, user):
        """Test that a run can transition from pending to running."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="pending")

        run.status = "running"
        run.started_at = timezone.now()
        run.save()

        run.refresh_from_db()
        assert run.status == "running"
        assert run.started_at is not None

    def test_run_can_transition_from_running_to_succeeded(self, user):
        """Test that a run can transition from running to succeeded."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        now = timezone.now()
        run = Run.objects.create(
            owner=user, graph_version=version, status="running", started_at=now
        )

        run.status = "succeeded"
        run.ended_at = timezone.now()
        run.output_json = {"result": "success"}
        run.save()

        run.refresh_from_db()
        assert run.status == "succeeded"
        assert run.ended_at is not None
        assert run.output_json == {"result": "success"}

    def test_run_can_transition_from_running_to_failed(self, user):
        """Test that a run can transition from running to failed."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        now = timezone.now()
        run = Run.objects.create(
            owner=user, graph_version=version, status="running", started_at=now
        )

        run.status = "failed"
        run.ended_at = timezone.now()
        run.error_message = "Node execution failed"
        run.save()

        run.refresh_from_db()
        assert run.status == "failed"
        assert run.ended_at is not None
        assert run.error_message == "Node execution failed"

    def test_run_can_transition_from_running_to_canceled(self, user):
        """Test that a run can transition from running to canceled."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        now = timezone.now()
        run = Run.objects.create(
            owner=user, graph_version=version, status="running", started_at=now
        )

        run.status = "canceled"
        run.ended_at = timezone.now()
        run.error_message = "Canceled by user"
        run.save()

        run.refresh_from_db()
        assert run.status == "canceled"
        assert run.ended_at is not None
        assert run.error_message == "Canceled by user"

    def test_run_can_transition_from_running_to_paused(self, user):
        """Test that a run can transition from running to paused."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        now = timezone.now()
        run = Run.objects.create(
            owner=user, graph_version=version, status="running", started_at=now
        )

        run.status = "paused"
        run.save()

        run.refresh_from_db()
        assert run.status == "paused"

    def test_run_can_transition_from_paused_to_running(self, user):
        """Test that a run can transition from paused to running."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        now = timezone.now()
        run = Run.objects.create(owner=user, graph_version=version, status="paused", started_at=now)

        run.status = "running"
        run.save()

        run.refresh_from_db()
        assert run.status == "running"

    def test_run_can_transition_from_paused_to_resume_requested(self, user):
        """Test that a paused run can move into resume_requested while the engine acks resume."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        now = timezone.now()
        run = Run.objects.create(owner=user, graph_version=version, status="paused", started_at=now)

        run.status = "resume_requested"
        run.save()

        run.refresh_from_db()
        assert run.status == "resume_requested"
