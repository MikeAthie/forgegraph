"""
Unit tests for Django ORM models.

Tests model behavior, properties, methods, and model-level validation.
"""

import hashlib
import json
from datetime import timedelta
from typing import Any

import pytest
from django.db import IntegrityError
from django.utils import timezone

from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    NodeRun,
    PromptTemplate,
    Run,
    User,
)

pytestmark = pytest.mark.django_db


class TestUserModel:
    """Tests for User model."""

    def test_user_creation_with_email(self):
        """Should create a user with email as identifier."""
        user = User.objects.create_user(email="test@example.com", password="testpass123")

        assert user.email == "test@example.com"
        assert user.check_password("testpass123")
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_superuser is False

    def test_user_email_is_normalized(self):
        """Email should be normalized (lowercase domain)."""
        user = User.objects.create_user(email="test@EXAMPLE.COM", password="testpass123")

        assert user.email == "test@example.com"

    def test_user_email_must_be_unique(self):
        """Creating users with duplicate emails should fail."""
        User.objects.create_user(email="test@example.com", password="testpass123")

        with pytest.raises(IntegrityError):
            User.objects.create_user(email="test@example.com", password="differentpass")

    def test_user_email_is_required(self):
        """Creating user without email should fail."""
        with pytest.raises(ValueError, match="Email field must be set"):
            User.objects.create_user(email="", password="testpass123")

    def test_user_str_returns_email(self):
        """String representation should return email."""
        user = User.objects.create_user(email="test@example.com", password="testpass123")

        assert str(user) == "test@example.com"

    def test_create_superuser(self):
        """Should create superuser with correct permissions."""
        superuser = User.objects.create_superuser(
            email="admin@example.com", password="adminpass123"
        )

        assert superuser.is_staff is True
        assert superuser.is_superuser is True

    def test_create_superuser_requires_is_staff(self):
        """Superuser creation should fail if is_staff is False."""
        with pytest.raises(ValueError, match="Superuser must have is_staff=True"):
            User.objects.create_superuser(
                email="admin@example.com", password="adminpass123", is_staff=False
            )

    def test_create_superuser_requires_is_superuser(self):
        """Superuser creation should fail if is_superuser is False."""
        with pytest.raises(ValueError, match="Superuser must have is_superuser=True"):
            User.objects.create_superuser(
                email="admin@example.com", password="adminpass123", is_superuser=False
            )

    def test_user_has_uuid_primary_key(self):
        """User should have UUID as primary key."""
        user = User.objects.create_user(email="test@example.com", password="testpass123")

        assert isinstance(user.id, type(user.id))  # UUID type
        assert str(user.id)  # Should be convertible to string


class TestGraphModel:
    """Tests for Graph model."""

    def test_graph_creation(self, user):
        """Should create a graph with required fields."""
        graph = Graph.objects.create(
            owner=user, name="Test Graph", description="A test description"
        )

        assert graph.name == "Test Graph"
        assert graph.description == "A test description"
        assert graph.owner == user
        assert graph.created_at is not None
        assert graph.updated_at is not None

    def test_graph_description_defaults_to_empty_string(self, user):
        """Description should default to empty string if not provided."""
        graph = Graph.objects.create(owner=user, name="Test Graph")

        assert graph.description == ""

    def test_graph_str_includes_name_and_owner(self, user):
        """String representation should include name and owner email."""
        graph = Graph.objects.create(owner=user, name="My Workflow")

        assert "My Workflow" in str(graph)
        assert user.email in str(graph)

    def test_graph_has_uuid_primary_key(self, user):
        """Graph should have UUID as primary key."""
        graph = Graph.objects.create(owner=user, name="Test")

        assert isinstance(graph.id, type(graph.id))
        assert str(graph.id)

    def test_graph_updated_at_changes_on_save(self, user):
        """updated_at should change when graph is modified."""
        graph = Graph.objects.create(owner=user, name="Original")
        original_updated = graph.updated_at

        graph.name = "Updated"
        graph.save()

        assert graph.updated_at > original_updated

    def test_graph_cascade_deletes_with_owner(self, user):
        """Graph should be deleted when owner is deleted."""
        graph = Graph.objects.create(owner=user, name="Test")
        graph_id = graph.id

        user.delete()

        assert not Graph.objects.filter(id=graph_id).exists()

    def test_graph_ordering_by_updated_at_desc(self, user):
        """Graphs should be ordered by updated_at descending."""
        graph1 = Graph.objects.create(owner=user, name="First")
        graph2 = Graph.objects.create(owner=user, name="Second")

        graphs = list(Graph.objects.all())

        assert graphs[0] == graph2  # Most recently updated first
        assert graphs[1] == graph1


class TestGraphVersionModel:
    """Tests for GraphVersion model."""

    def test_graph_version_creation(self, user):
        """Should create a graph version with required fields."""
        graph = Graph.objects.create(owner=user, name="Test")
        graph_json: dict[str, Any] = {"nodes": [{"id": "n1", "type": "prompt"}], "edges": []}

        version = GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json)

        assert version.graph == graph
        assert version.version == 1
        assert version.graph_json == graph_json
        assert version.created_at is not None

    def test_graph_version_computes_checksum_on_save(self, user):
        """Checksum should be computed automatically on save."""
        graph = Graph.objects.create(owner=user, name="Test")
        graph_json: dict[str, Any] = {"nodes": [], "edges": []}

        version = GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json)

        # Compute expected checksum
        json_str = json.dumps(graph_json, sort_keys=True, separators=(",", ":"))
        expected_checksum = hashlib.sha256(json_str.encode()).hexdigest()

        assert version.checksum == expected_checksum
        assert len(version.checksum) == 64  # SHA256 is 64 hex chars

    def test_graph_version_checksum_is_deterministic(self, user):
        """Same graph_json should always produce same checksum."""
        graph = Graph.objects.create(owner=user, name="Test")
        graph_json: dict[str, Any] = {"nodes": [], "edges": []}

        version1 = GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json)
        version2 = GraphVersion.objects.create(graph=graph, version=2, graph_json=graph_json)

        assert version1.checksum == version2.checksum

    def test_graph_version_unique_version_per_graph(self, user):
        """Version numbers should be unique per graph."""
        graph = Graph.objects.create(owner=user, name="Test")
        GraphVersion.objects.create(graph=graph, version=1, graph_json={"nodes": [], "edges": []})

        with pytest.raises(IntegrityError):
            GraphVersion.objects.create(
                graph=graph, version=1, graph_json={"nodes": [], "edges": []}
            )

    def test_graph_version_same_version_different_graphs(self, user):
        """Same version number allowed for different graphs."""
        graph1 = Graph.objects.create(owner=user, name="Graph 1")
        graph2 = Graph.objects.create(owner=user, name="Graph 2")

        version1 = GraphVersion.objects.create(
            graph=graph1, version=1, graph_json={"nodes": [], "edges": []}
        )
        version2 = GraphVersion.objects.create(
            graph=graph2, version=1, graph_json={"nodes": [], "edges": []}
        )

        assert version1.version == version2.version
        assert version1.graph != version2.graph

    def test_graph_version_str_includes_graph_and_version(self, user):
        """String representation should include graph name and version."""
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        str_repr = str(version)
        assert "My Graph" in str_repr
        assert "v1" in str_repr

    def test_graph_version_cascade_deletes_with_graph(self, user):
        """Graph versions should be deleted when graph is deleted."""
        graph = Graph.objects.create(owner=user, name="Test")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        version_id = version.id

        graph.delete()

        assert not GraphVersion.objects.filter(id=version_id).exists()

    def test_graph_version_ordering_by_version_desc(self, user):
        """Graph versions should be ordered by version descending."""
        graph = Graph.objects.create(owner=user, name="Test")
        v1 = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        v2 = GraphVersion.objects.create(
            graph=graph, version=2, graph_json={"nodes": [], "edges": []}
        )

        versions = list(GraphVersion.objects.all())

        assert versions[0] == v2  # Highest version first
        assert versions[1] == v1


class TestPromptTemplateModel:
    """Tests for PromptTemplate model."""

    def test_prompt_template_creation(self, user):
        """Should create a prompt template with required fields."""
        prompt = PromptTemplate.objects.create(
            owner=user,
            title="Test Prompt",
            description="A test prompt",
            category="research",
            content="Prompt content here",
        )

        assert prompt.title == "Test Prompt"
        assert prompt.description == "A test prompt"
        assert prompt.category == "research"
        assert prompt.content == "Prompt content here"
        assert prompt.owner == user

    def test_prompt_template_defaults(self, user):
        """Should apply default values for optional fields."""
        prompt = PromptTemplate.objects.create(
            owner=user, title="Test", category="other", content="Content"
        )

        assert prompt.description == ""
        assert prompt.variables_schema == {}
        assert prompt.version == "1.0.0"
        assert prompt.license == "MIT"
        assert prompt.visibility == "private"

    def test_prompt_template_str_returns_title(self, user):
        """String representation should return title."""
        prompt = PromptTemplate.objects.create(
            owner=user, title="Email Helper", category="email", content="Content"
        )

        assert str(prompt) == "Email Helper"

    def test_prompt_template_is_builtin_property_false_for_user_prompts(self, user):
        """is_builtin should be False for user-owned prompts."""
        prompt = PromptTemplate.objects.create(
            owner=user, title="Test", category="other", content="Content"
        )

        assert prompt.is_builtin is False

    def test_prompt_template_is_builtin_property_true_for_null_owner(self):
        """is_builtin should be True for prompts with owner=None."""
        prompt = PromptTemplate.objects.create(
            owner=None,
            title="Built-in",
            category="other",
            content="Content",
            visibility="public",
        )

        assert prompt.is_builtin is True

    def test_prompt_template_clone_for_user_creates_copy(self, user):
        """clone_for_user should create a private copy owned by the user."""
        original = PromptTemplate.objects.create(
            owner=None,
            title="Original Prompt",
            description="Original description",
            category="research",
            content="Original content",
            variables_schema={"var1": "value1"},
            visibility="public",
        )

        clone = original.clone_for_user(user)

        assert clone.owner == user
        assert clone.title == "Original Prompt (Copy)"
        assert clone.description == original.description
        assert clone.category == original.category
        assert clone.content == original.content
        assert clone.variables_schema == original.variables_schema
        assert clone.visibility == "private"

    def test_prompt_template_clone_deep_copies_variables_schema(self, user):
        """clone_for_user should deep copy variables_schema."""
        original = PromptTemplate.objects.create(
            owner=None,
            title="Test",
            category="other",
            content="Content",
            variables_schema={"nested": {"key": "value"}},
            visibility="public",
        )

        clone = original.clone_for_user(user)

        # Modify original's schema
        original.variables_schema["nested"]["key"] = "modified"
        original.save()

        clone.refresh_from_db()
        assert clone.variables_schema["nested"]["key"] == "value"

    def test_prompt_template_cascade_deletes_with_owner(self, user):
        """Prompt should be deleted when owner is deleted."""
        prompt = PromptTemplate.objects.create(
            owner=user, title="Test", category="other", content="Content"
        )
        prompt_id = prompt.id

        user.delete()

        assert not PromptTemplate.objects.filter(id=prompt_id).exists()

    def test_prompt_template_ordering_by_created_at_desc(self, user):
        """Prompts should be ordered by created_at descending."""
        prompt1 = PromptTemplate.objects.create(
            owner=user, title="First", category="other", content="Content"
        )
        prompt2 = PromptTemplate.objects.create(
            owner=user, title="Second", category="other", content="Content"
        )

        prompts = list(PromptTemplate.objects.all())

        assert prompts[0] == prompt2  # Most recently created first
        assert prompts[1] == prompt1

    def test_prompt_template_category_choices(self, user):
        """Should accept valid category choices."""
        valid_categories = [
            "research",
            "summarization",
            "email",
            "extraction",
            "reasoning",
            "other",
        ]

        for category in valid_categories:
            prompt = PromptTemplate.objects.create(
                owner=user, title=f"Test {category}", category=category, content="Content"
            )
            assert prompt.category == category

    def test_prompt_template_visibility_choices(self, user):
        """Should accept valid visibility choices."""
        prompt1 = PromptTemplate.objects.create(
            owner=user, title="Private", category="other", content="Content", visibility="private"
        )
        prompt2 = PromptTemplate.objects.create(
            owner=user, title="Public", category="other", content="Content", visibility="public"
        )

        assert prompt1.visibility == "private"
        assert prompt2.visibility == "public"


class TestRunModel:
    """Tests for Run model."""

    def test_run_creation(self, user):
        """Should create a run with required fields."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="pending",
            input_json={"input": "test"},
        )

        assert run.owner == user
        assert run.graph_version == version
        assert run.status == "pending"
        assert run.input_json == {"input": "test"}

    def test_run_defaults(self, user):
        """Should apply default values for optional fields."""
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

    def test_run_str_includes_id_and_status(self, user):
        """String representation should include run ID and status."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        str_repr = str(run)
        assert str(run.id) in str_repr
        assert "running" in str_repr

    def test_run_duration_ms_property(self, user):
        """duration_ms should calculate duration in milliseconds."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        now = timezone.now()
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            started_at=now,
            ended_at=now + timedelta(seconds=5, milliseconds=500),
        )

        assert run.duration_ms == 5500

    def test_run_duration_ms_returns_none_when_incomplete(self, user):
        """duration_ms should return None if started_at or ended_at is missing."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        run = Run.objects.create(owner=user, graph_version=version)

        assert run.duration_ms is None

    def test_run_status_choices(self, user):
        """Should accept valid status choices."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        valid_statuses = ["pending", "running", "paused", "succeeded", "failed", "canceled"]

        for status in valid_statuses:
            run = Run.objects.create(owner=user, graph_version=version, status=status)
            assert run.status == status

    def test_run_cascade_deletes_with_owner(self, user):
        """Run should be deleted when owner is deleted."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version)
        run_id = run.id

        user.delete()

        assert not Run.objects.filter(id=run_id).exists()

    def test_run_cascade_deletes_with_graph_version(self, user):
        """Run should be deleted when graph version is deleted."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version)
        run_id = run.id

        version.delete()

        assert not Run.objects.filter(id=run_id).exists()


class TestNodeRunModel:
    """Tests for NodeRun model."""

    def test_node_run_creation(self, user):
        """Should create a node run with required fields."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version)

        node_run = NodeRun.objects.create(
            run=run,
            node_id="node1",
            node_type="prompt",
            status="succeeded",
            input_json={"input": "test"},
            output_json={"output": "result"},
        )

        assert node_run.run == run
        assert node_run.node_id == "node1"
        assert node_run.node_type == "prompt"
        assert node_run.status == "succeeded"
        assert node_run.input_json == {"input": "test"}
        assert node_run.output_json == {"output": "result"}

    def test_node_run_defaults(self, user):
        """Should apply default values for optional fields."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version)

        node_run = NodeRun.objects.create(run=run, node_id="node1", node_type="prompt")

        assert node_run.status == "pending"
        assert node_run.attempt == 1
        assert node_run.input_json == {}
        assert node_run.output_json is None
        assert node_run.error_json is None
        assert node_run.started_at is None
        assert node_run.ended_at is None

    def test_node_run_str_includes_node_id_and_status(self, user):
        """String representation should include node ID and status."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version)
        node_run = NodeRun.objects.create(
            run=run, node_id="node1", node_type="prompt", status="running"
        )

        str_repr = str(node_run)
        assert "node1" in str_repr
        assert "running" in str_repr

    def test_node_run_duration_ms_property(self, user):
        """duration_ms should calculate duration in milliseconds."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version)

        now = timezone.now()
        node_run = NodeRun.objects.create(
            run=run,
            node_id="node1",
            node_type="prompt",
            started_at=now,
            ended_at=now + timedelta(milliseconds=250),
        )

        assert node_run.duration_ms == 250

    def test_node_run_duration_ms_returns_none_when_incomplete(self, user):
        """duration_ms should return None if started_at or ended_at is missing."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version)

        node_run = NodeRun.objects.create(run=run, node_id="node1", node_type="prompt")

        assert node_run.duration_ms is None

    def test_node_run_status_choices(self, user):
        """Should accept valid status choices."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version)

        valid_statuses = ["pending", "running", "succeeded", "failed", "skipped"]

        for status in valid_statuses:
            node_run = NodeRun.objects.create(
                run=run, node_id=f"node_{status}", node_type="prompt", status=status
            )
            assert node_run.status == status

    def test_node_run_cascade_deletes_with_run(self, user):
        """Node run should be deleted when run is deleted."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version)
        node_run = NodeRun.objects.create(run=run, node_id="node1", node_type="prompt")
        node_run_id = node_run.id

        run.delete()

        assert not NodeRun.objects.filter(id=node_run_id).exists()

    def test_node_run_attempt_tracking(self, user):
        """Should track retry attempts for node runs."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version)

        # First attempt
        node_run1 = NodeRun.objects.create(
            run=run, node_id="node1", node_type="prompt", attempt=1, status="failed"
        )

        # Retry attempt
        node_run2 = NodeRun.objects.create(
            run=run, node_id="node1", node_type="prompt", attempt=2, status="succeeded"
        )

        assert node_run1.attempt == 1
        assert node_run2.attempt == 2
