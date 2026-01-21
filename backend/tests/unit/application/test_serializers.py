"""
Unit tests for API serializers.

Tests serializer validation, field transformations, and error messages.
"""

from adapters.api.auth.serializers import LoginSerializer, RegisterSerializer
from adapters.api.graphs.serializers import (
    GraphCreateSerializer,
    GraphUpdateSerializer,
    GraphVersionCreateSerializer,
)
from adapters.api.prompts.serializers import (
    PromptCreateSerializer,
    PromptPublishSerializer,
    PromptUpdateSerializer,
)


class TestRegisterSerializer:
    """Tests for RegisterSerializer."""

    def test_valid_registration_data(self):
        """Should validate correct registration data."""
        data = {"email": "test@example.com", "password": "testpassword123"}
        serializer = RegisterSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["email"] == "test@example.com"

    def test_email_is_required(self):
        """Should require email field."""
        data = {"password": "testpassword123"}
        serializer = RegisterSerializer(data=data)

        assert not serializer.is_valid()
        assert "email" in serializer.errors

    def test_password_is_required(self):
        """Should require password field."""
        data = {"email": "test@example.com"}
        serializer = RegisterSerializer(data=data)

        assert not serializer.is_valid()
        assert "password" in serializer.errors

    def test_invalid_email_format(self):
        """Should reject invalid email formats."""
        data = {"email": "not-an-email", "password": "testpassword123"}
        serializer = RegisterSerializer(data=data)

        assert not serializer.is_valid()
        assert "email" in serializer.errors


class TestLoginSerializer:
    """Tests for LoginSerializer."""

    def test_valid_login_data(self):
        """Should validate correct login data."""
        data = {"email": "test@example.com", "password": "testpassword123"}
        serializer = LoginSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["email"] == "test@example.com"

    def test_email_is_required(self):
        """Should require email field."""
        data = {"password": "testpassword123"}
        serializer = LoginSerializer(data=data)

        assert not serializer.is_valid()
        assert "email" in serializer.errors

    def test_password_is_required(self):
        """Should require password field."""
        data = {"email": "test@example.com"}
        serializer = LoginSerializer(data=data)

        assert not serializer.is_valid()
        assert "password" in serializer.errors


class TestGraphCreateSerializer:
    """Tests for GraphCreateSerializer."""

    def test_valid_graph_creation_data(self):
        """Should validate correct graph creation data."""
        data = {"name": "My Workflow", "description": "A test workflow"}
        serializer = GraphCreateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["name"] == "My Workflow"
        assert serializer.validated_data["description"] == "A test workflow"

    def test_name_is_required(self):
        """Should require name field."""
        data = {"description": "Missing name"}
        serializer = GraphCreateSerializer(data=data)

        assert not serializer.is_valid()
        assert "name" in serializer.errors

    def test_description_is_optional(self):
        """Should allow omitting description."""
        data = {"name": "My Workflow"}
        serializer = GraphCreateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["description"] == ""

    def test_description_can_be_empty_string(self):
        """Should allow empty string for description."""
        data = {"name": "My Workflow", "description": ""}
        serializer = GraphCreateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["description"] == ""

    def test_name_max_length_validation(self):
        """Should enforce max length for name."""
        data = {"name": "x" * 256, "description": "Test"}
        serializer = GraphCreateSerializer(data=data)

        assert not serializer.is_valid()
        assert "name" in serializer.errors


class TestGraphUpdateSerializer:
    """Tests for GraphUpdateSerializer."""

    def test_valid_graph_update_data(self):
        """Should validate correct graph update data."""
        data = {"name": "Updated Name", "description": "Updated description"}
        serializer = GraphUpdateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["name"] == "Updated Name"

    def test_all_fields_are_optional(self):
        """Should allow partial updates with no required fields."""
        data = {}
        serializer = GraphUpdateSerializer(data=data)

        assert serializer.is_valid()

    def test_name_only_update(self):
        """Should allow updating only name."""
        data = {"name": "New Name"}
        serializer = GraphUpdateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["name"] == "New Name"
        assert "description" not in serializer.validated_data

    def test_description_only_update(self):
        """Should allow updating only description."""
        data = {"description": "New description"}
        serializer = GraphUpdateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["description"] == "New description"
        assert "name" not in serializer.validated_data

    def test_description_can_be_empty_string(self):
        """Should allow clearing description with empty string."""
        data = {"description": ""}
        serializer = GraphUpdateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["description"] == ""


class TestGraphVersionCreateSerializer:
    """Tests for GraphVersionCreateSerializer."""

    def test_valid_graph_version_data(self):
        """Should validate correct graph version data."""
        data = {
            "graph_json": {
                "nodes": [{"id": "n1", "type": "prompt", "name": "Test"}],
                "edges": [],
            }
        }
        serializer = GraphVersionCreateSerializer(data=data)

        assert serializer.is_valid()
        assert "nodes" in serializer.validated_data["graph_json"]
        assert "edges" in serializer.validated_data["graph_json"]

    def test_graph_json_is_required(self):
        """Should require graph_json field."""
        data = {}
        serializer = GraphVersionCreateSerializer(data=data)

        assert not serializer.is_valid()
        assert "graph_json" in serializer.errors

    def test_graph_json_must_be_object(self):
        """Should reject non-object graph_json."""
        data = {"graph_json": []}
        serializer = GraphVersionCreateSerializer(data=data)

        assert not serializer.is_valid()
        assert "graph_json" in serializer.errors

    def test_graph_json_must_contain_nodes(self):
        """Should require 'nodes' in graph_json."""
        data = {"graph_json": {"edges": []}}
        serializer = GraphVersionCreateSerializer(data=data)

        assert not serializer.is_valid()
        assert "graph_json" in serializer.errors

    def test_graph_json_must_contain_edges(self):
        """Should require 'edges' in graph_json."""
        data = {"graph_json": {"nodes": []}}
        serializer = GraphVersionCreateSerializer(data=data)

        assert not serializer.is_valid()
        assert "graph_json" in serializer.errors

    def test_nodes_must_be_array(self):
        """Should require nodes to be an array."""
        data = {"graph_json": {"nodes": {}, "edges": []}}
        serializer = GraphVersionCreateSerializer(data=data)

        assert not serializer.is_valid()
        assert "graph_json" in serializer.errors

    def test_edges_must_be_array(self):
        """Should require edges to be an array."""
        data = {"graph_json": {"nodes": [], "edges": {}}}
        serializer = GraphVersionCreateSerializer(data=data)

        assert not serializer.is_valid()
        assert "graph_json" in serializer.errors

    def test_empty_nodes_and_edges_are_valid(self):
        """Should allow empty nodes and edges arrays."""
        data = {"graph_json": {"nodes": [], "edges": []}}
        serializer = GraphVersionCreateSerializer(data=data)

        assert serializer.is_valid()

    def test_graph_json_with_complex_structure(self):
        """Should validate complex graph_json structures."""
        data = {
            "graph_json": {
                "nodes": [
                    {"id": "n1", "type": "prompt", "name": "Start", "config": {}},
                    {"id": "n2", "type": "http", "name": "API Call", "config": {}},
                ],
                "edges": [{"source": "n1", "target": "n2"}],
            }
        }
        serializer = GraphVersionCreateSerializer(data=data)

        assert serializer.is_valid()


class TestPromptCreateSerializer:
    """Tests for PromptCreateSerializer."""

    def test_valid_prompt_creation_data(self):
        """Should validate correct prompt creation data."""
        data = {
            "title": "Test Prompt",
            "description": "A test prompt",
            "category": "research",
            "content": "Prompt content here",
            "variables_schema": {"var1": {"type": "string"}},
        }
        serializer = PromptCreateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["title"] == "Test Prompt"
        assert serializer.validated_data["category"] == "research"

    def test_required_fields(self):
        """Should require title, category, and content."""
        data = {}
        serializer = PromptCreateSerializer(data=data)

        assert not serializer.is_valid()
        assert "title" in serializer.errors
        assert "category" in serializer.errors
        assert "content" in serializer.errors

    def test_description_is_optional(self):
        """Should allow omitting description."""
        data = {"title": "Test", "category": "research", "content": "Content"}
        serializer = PromptCreateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["description"] == ""

    def test_variables_schema_is_optional(self):
        """Should allow omitting variables_schema."""
        data = {"title": "Test", "category": "research", "content": "Content"}
        serializer = PromptCreateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["variables_schema"] == {}

    def test_valid_category_choices(self):
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
            data = {"title": "Test", "category": category, "content": "Content"}
            serializer = PromptCreateSerializer(data=data)

            assert serializer.is_valid(), f"Category {category} should be valid"
            assert serializer.validated_data["category"] == category

    def test_invalid_category_choice(self):
        """Should reject invalid category choices."""
        data = {"title": "Test", "category": "invalid_category", "content": "Content"}
        serializer = PromptCreateSerializer(data=data)

        assert not serializer.is_valid()
        assert "category" in serializer.errors

    def test_title_max_length_validation(self):
        """Should enforce max length for title."""
        data = {
            "title": "x" * 256,
            "category": "research",
            "content": "Content",
        }
        serializer = PromptCreateSerializer(data=data)

        assert not serializer.is_valid()
        assert "title" in serializer.errors

    def test_variables_schema_accepts_json_object(self):
        """Should accept JSON objects for variables_schema."""
        data = {
            "title": "Test",
            "category": "research",
            "content": "Content",
            "variables_schema": {"nested": {"key": "value"}},
        }
        serializer = PromptCreateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["variables_schema"]["nested"]["key"] == "value"


class TestPromptUpdateSerializer:
    """Tests for PromptUpdateSerializer."""

    def test_valid_prompt_update_data(self):
        """Should validate correct prompt update data."""
        data = {
            "title": "Updated Title",
            "description": "Updated description",
            "content": "Updated content",
        }
        serializer = PromptUpdateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["title"] == "Updated Title"

    def test_all_fields_are_optional(self):
        """Should allow partial updates with no required fields."""
        data = {}
        serializer = PromptUpdateSerializer(data=data)

        assert serializer.is_valid()

    def test_title_only_update(self):
        """Should allow updating only title."""
        data = {"title": "New Title"}
        serializer = PromptUpdateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["title"] == "New Title"

    def test_content_only_update(self):
        """Should allow updating only content."""
        data = {"content": "New content"}
        serializer = PromptUpdateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["content"] == "New content"

    def test_variables_schema_update(self):
        """Should allow updating variables_schema."""
        data = {"variables_schema": {"new_var": {"type": "number"}}}
        serializer = PromptUpdateSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["variables_schema"]["new_var"]["type"] == "number"


class TestPromptPublishSerializer:
    """Tests for PromptPublishSerializer."""

    def test_valid_publish_data(self):
        """Should validate correct publish data."""
        data = {"license": "Apache-2.0"}
        serializer = PromptPublishSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["license"] == "Apache-2.0"

    def test_license_is_optional(self):
        """Should allow omitting license (defaults to MIT)."""
        data = {}
        serializer = PromptPublishSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["license"] == "MIT"

    def test_empty_data_uses_default_license(self):
        """Should use default MIT license when no data provided."""
        serializer = PromptPublishSerializer(data={})

        assert serializer.is_valid()
        assert serializer.validated_data["license"] == "MIT"

    def test_license_max_length_validation(self):
        """Should enforce max length for license."""
        data = {"license": "x" * 65}
        serializer = PromptPublishSerializer(data=data)

        assert not serializer.is_valid()
        assert "license" in serializer.errors
