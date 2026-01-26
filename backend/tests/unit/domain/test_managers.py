"""
Unit tests for custom model managers and querysets.

Tests custom manager methods and queryset filters.
"""

import pytest
from datetime import timedelta

from django.utils import timezone

from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    PromptTemplate,
    User,
)

pytestmark = pytest.mark.django_db


class TestGraphManager:
    """Tests for Graph custom manager."""

    def test_for_user_filters_by_owner(self, user):
        """for_user should return only graphs owned by the user."""
        other_user = User.objects.create_user(email="other@example.com", password="testpass123")

        # Create graphs for both users
        user_graph1 = Graph.objects.create(owner=user, name="User Graph 1")
        user_graph2 = Graph.objects.create(owner=user, name="User Graph 2")
        Graph.objects.create(owner=other_user, name="Other User Graph")

        # Query graphs for user
        user_graphs = Graph.objects.for_user(user)

        assert user_graphs.count() == 2
        assert user_graph1 in user_graphs
        assert user_graph2 in user_graphs

    def test_for_user_returns_empty_for_user_without_graphs(self):
        """for_user should return empty queryset if user has no graphs."""
        user = User.objects.create_user(email="test@example.com", password="testpass123")

        user_graphs = Graph.objects.for_user(user)

        assert user_graphs.count() == 0

    def test_for_user_is_chainable(self, user):
        """for_user should be chainable with other queryset methods."""
        Graph.objects.create(owner=user, name="Alpha")
        Graph.objects.create(owner=user, name="Beta")

        # Chain with filter
        filtered = Graph.objects.for_user(user).filter(name="Alpha")

        assert filtered.count() == 1
        assert filtered.first().name == "Alpha"

    def test_for_user_preserves_ordering(self, user):
        """for_user should preserve default ordering by updated_at."""
        graph1 = Graph.objects.create(owner=user, name="First")
        graph2 = Graph.objects.create(owner=user, name="Second")

        # Ensure deterministic ordering across DBs with coarse timestamp precision.
        now = timezone.now()
        Graph.objects.filter(id=graph1.id).update(updated_at=now)
        Graph.objects.filter(id=graph2.id).update(updated_at=now + timedelta(seconds=1))

        graphs = list(Graph.objects.for_user(user))

        # Should be ordered by updated_at descending (most recent first)
        assert graphs[0] == graph2
        assert graphs[1] == graph1


class TestGraphVersionManager:
    """Tests for GraphVersion custom manager."""

    def test_latest_for_graph_returns_highest_version(self, user):
        """latest_for_graph should return the version with highest version number."""
        graph = Graph.objects.create(owner=user, name="Test Graph")

        GraphVersion.objects.create(graph=graph, version=1, graph_json={"nodes": [], "edges": []})
        GraphVersion.objects.create(graph=graph, version=2, graph_json={"nodes": [], "edges": []})
        v3 = GraphVersion.objects.create(
            graph=graph, version=3, graph_json={"nodes": [], "edges": []}
        )

        latest = GraphVersion.objects.latest_for_graph(graph.id)

        assert latest == v3
        assert latest.version == 3

    def test_latest_for_graph_returns_none_when_no_versions(self, user):
        """latest_for_graph should return None if graph has no versions."""
        graph = Graph.objects.create(owner=user, name="Test Graph")

        latest = GraphVersion.objects.latest_for_graph(graph.id)

        assert latest is None

    def test_latest_for_graph_with_non_sequential_versions(self, user):
        """latest_for_graph should work with non-sequential version numbers."""
        graph = Graph.objects.create(owner=user, name="Test Graph")

        GraphVersion.objects.create(graph=graph, version=1, graph_json={"nodes": [], "edges": []})
        v5 = GraphVersion.objects.create(
            graph=graph, version=5, graph_json={"nodes": [], "edges": []}
        )
        GraphVersion.objects.create(graph=graph, version=3, graph_json={"nodes": [], "edges": []})

        latest = GraphVersion.objects.latest_for_graph(graph.id)

        assert latest == v5
        assert latest.version == 5

    def test_latest_for_graph_only_considers_specified_graph(self, user):
        """latest_for_graph should only consider versions for the specified graph."""
        graph1 = Graph.objects.create(owner=user, name="Graph 1")
        graph2 = Graph.objects.create(owner=user, name="Graph 2")

        v1_g1 = GraphVersion.objects.create(
            graph=graph1, version=1, graph_json={"nodes": [], "edges": []}
        )
        GraphVersion.objects.create(graph=graph2, version=10, graph_json={"nodes": [], "edges": []})

        latest_g1 = GraphVersion.objects.latest_for_graph(graph1.id)

        assert latest_g1 == v1_g1
        assert latest_g1.version == 1


class TestPromptTemplateManager:
    """Tests for PromptTemplate custom manager."""

    def test_public_filters_public_visibility(self, user):
        """public should return only prompts with public visibility."""
        # Create prompts with different visibilities
        private_prompt = PromptTemplate.objects.create(
            owner=user,
            title="Private Prompt",
            category="research",
            content="Content",
            visibility="private",
        )
        public_prompt = PromptTemplate.objects.create(
            owner=user,
            title="Public Prompt",
            category="research",
            content="Content",
            visibility="public",
        )

        public_prompts = PromptTemplate.objects.public()

        assert private_prompt not in public_prompts
        assert public_prompt in public_prompts
        assert not public_prompts.filter(visibility="private").exists()

    def test_public_includes_builtin_prompts(self):
        """public should include built-in prompts (owner=None)."""
        builtin = PromptTemplate.objects.create(
            owner=None,
            title="Built-in Prompt",
            category="research",
            content="Content",
            visibility="public",
        )

        public_prompts = PromptTemplate.objects.public()

        assert builtin in public_prompts

    def test_public_is_chainable(self, user):
        """public should be chainable with other queryset methods."""
        PromptTemplate.objects.create(
            owner=user,
            title="Public Research",
            category="research",
            content="Content",
            visibility="public",
        )
        PromptTemplate.objects.create(
            owner=user,
            title="Public Email",
            category="email",
            content="Content",
            visibility="public",
        )

        # Chain with filter
        research_prompts = PromptTemplate.objects.public().filter(
            category="research", title="Public Research"
        )

        assert research_prompts.count() == 1
        assert research_prompts.first().title == "Public Research"

    def test_for_user_includes_owned_prompts(self, user):
        """for_user should include prompts owned by the user."""
        private_prompt = PromptTemplate.objects.create(
            owner=user,
            title="My Private Prompt",
            category="research",
            content="Content",
            visibility="private",
        )

        user_prompts = PromptTemplate.objects.for_user(user)

        assert private_prompt in user_prompts

    def test_for_user_includes_public_prompts(self, user):
        """for_user should include all public prompts."""
        other_user = User.objects.create_user(email="other@example.com", password="testpass123")

        public_prompt = PromptTemplate.objects.create(
            owner=other_user,
            title="Public Prompt",
            category="research",
            content="Content",
            visibility="public",
        )

        user_prompts = PromptTemplate.objects.for_user(user)

        assert public_prompt in user_prompts

    def test_for_user_includes_builtin_prompts(self, user):
        """for_user should include built-in prompts (owner=None)."""
        builtin = PromptTemplate.objects.create(
            owner=None,
            title="Built-in Prompt",
            category="research",
            content="Content",
            visibility="public",
        )

        user_prompts = PromptTemplate.objects.for_user(user)

        assert builtin in user_prompts

    def test_for_user_excludes_other_users_private_prompts(self, user):
        """for_user should not include private prompts from other users."""
        other_user = User.objects.create_user(email="other@example.com", password="testpass123")

        private_prompt = PromptTemplate.objects.create(
            owner=other_user,
            title="Other's Private",
            category="research",
            content="Content",
            visibility="private",
        )

        user_prompts = PromptTemplate.objects.for_user(user)

        assert private_prompt not in user_prompts

    def test_for_user_complete_visibility_logic(self, user):
        """for_user should correctly implement complete visibility logic."""
        other_user = User.objects.create_user(email="other@example.com", password="testpass123")

        # User's private prompt - VISIBLE
        user_private = PromptTemplate.objects.create(
            owner=user,
            title="My Private",
            category="research",
            content="Content",
            visibility="private",
        )

        # User's public prompt - VISIBLE
        user_public = PromptTemplate.objects.create(
            owner=user,
            title="My Public",
            category="research",
            content="Content",
            visibility="public",
        )

        # Other's public prompt - VISIBLE
        other_public = PromptTemplate.objects.create(
            owner=other_user,
            title="Other's Public",
            category="research",
            content="Content",
            visibility="public",
        )

        # Other's private prompt - NOT VISIBLE
        other_private = PromptTemplate.objects.create(
            owner=other_user,
            title="Other's Private",
            category="research",
            content="Content",
            visibility="private",
        )

        # Built-in prompt - VISIBLE
        builtin = PromptTemplate.objects.create(
            owner=None,
            title="Built-in",
            category="research",
            content="Content",
            visibility="public",
        )

        user_prompts = PromptTemplate.objects.for_user(user)
        prompt_ids = set(user_prompts.values_list("id", flat=True))

        assert user_private.id in prompt_ids
        assert user_public.id in prompt_ids
        assert other_public.id in prompt_ids
        assert builtin.id in prompt_ids
        assert other_private.id not in prompt_ids

    def test_for_user_is_chainable(self, user):
        """for_user should be chainable with other queryset methods."""
        PromptTemplate.objects.create(
            owner=user,
            title="Research Prompt",
            category="research",
            content="Content",
        )
        PromptTemplate.objects.create(
            owner=user,
            title="Email Prompt",
            category="email",
            content="Content",
        )

        # Chain with filter
        research_prompts = PromptTemplate.objects.for_user(user).filter(
            category="research", title="Research Prompt"
        )

        assert research_prompts.count() == 1
        assert research_prompts.first().title == "Research Prompt"


class TestPromptTemplateCloneMethod:
    """Tests for PromptTemplate.clone_for_user method."""

    def test_clone_for_user_creates_new_instance(self, user):
        """clone_for_user should create a new database instance."""
        original = PromptTemplate.objects.create(
            owner=None,
            title="Original",
            category="research",
            content="Content",
            visibility="public",
        )
        original_count = PromptTemplate.objects.count()

        clone = original.clone_for_user(user)

        assert PromptTemplate.objects.count() == original_count + 1
        assert clone.id != original.id

    def test_clone_for_user_sets_correct_owner(self, user):
        """clone_for_user should set the new user as owner."""
        original = PromptTemplate.objects.create(
            owner=None,
            title="Original",
            category="research",
            content="Content",
            visibility="public",
        )

        clone = original.clone_for_user(user)

        assert clone.owner == user

    def test_clone_for_user_sets_private_visibility(self, user):
        """clone_for_user should always set visibility to private."""
        original = PromptTemplate.objects.create(
            owner=None,
            title="Original",
            category="research",
            content="Content",
            visibility="public",
        )

        clone = original.clone_for_user(user)

        assert clone.visibility == "private"

    def test_clone_for_user_appends_copy_to_title(self, user):
        """clone_for_user should append ' (Copy)' to the title."""
        original = PromptTemplate.objects.create(
            owner=None,
            title="Original Prompt",
            category="research",
            content="Content",
            visibility="public",
        )

        clone = original.clone_for_user(user)

        assert clone.title == "Original Prompt (Copy)"

    def test_clone_for_user_copies_all_relevant_fields(self, user):
        """clone_for_user should copy description, category, content, etc."""
        original = PromptTemplate.objects.create(
            owner=None,
            title="Original",
            description="Original description",
            category="research",
            content="Original content",
            variables_schema={"var": "value"},
            version="1.0.0",
            license="MIT",
            visibility="public",
        )

        clone = original.clone_for_user(user)

        assert clone.description == original.description
        assert clone.category == original.category
        assert clone.content == original.content
        assert clone.version == original.version
        assert clone.license == original.license

    def test_clone_for_user_deep_copies_variables_schema(self, user):
        """clone_for_user should deep copy variables_schema to prevent mutations."""
        original = PromptTemplate.objects.create(
            owner=None,
            title="Original",
            category="research",
            content="Content",
            variables_schema={"nested": {"key": "value"}},
            visibility="public",
        )

        clone = original.clone_for_user(user)

        # Modify original's schema
        original.variables_schema["nested"]["key"] = "modified"
        original.save()

        # Clone's schema should remain unchanged
        clone.refresh_from_db()
        assert clone.variables_schema["nested"]["key"] == "value"

    def test_clone_for_user_independent_timestamps(self, user):
        """clone should have its own created_at and updated_at."""
        original = PromptTemplate.objects.create(
            owner=None,
            title="Original",
            category="research",
            content="Content",
            visibility="public",
        )

        clone = original.clone_for_user(user)

        # Clone's timestamps should be equal to or later than original
        assert clone.created_at >= original.created_at
        # They should have their own timestamp records
        assert clone.created_at is not None
        assert clone.updated_at is not None
