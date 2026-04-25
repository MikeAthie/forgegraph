"""
Integration tests for Graph APIs.

Tests all Graph and GraphVersion endpoints following REST best practices.
"""

from typing import Any

import pytest
from rest_framework import status

from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    MemoryConfiguration,
    OrganizationMembership,
)

pytestmark = pytest.mark.django_db


class TestGraphListCreate:
    """Tests for GET /api/graphs/ and POST /api/graphs/"""

    def test_list_graphs_requires_authentication(self, api_client):
        """Unauthenticated requests should be rejected."""
        response = api_client.get("/api/graphs/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_graphs_returns_user_graphs_only(self, authenticated_client, user):
        """Should return only graphs owned by the authenticated user."""
        # Create graphs for the user
        graph1 = Graph.objects.create(owner=user, name="My Graph 1", description="First graph")
        graph2 = Graph.objects.create(owner=user, name="My Graph 2", description="Second graph")

        # Create graph for another user
        from infrastructure.orm.models import User

        other_user = User.objects.create_user(email="other@example.com", password="password123")
        Graph.objects.create(owner=other_user, name="Other User Graph", description="Not visible")

        response = authenticated_client.get("/api/graphs/")

        assert response.status_code == status.HTTP_200_OK
        assert "data" in response.data
        assert "meta" in response.data
        assert len(response.data["data"]) == 2

        # Verify graph data
        graph_ids = {g["id"] for g in response.data["data"]}
        assert str(graph1.id) in graph_ids
        assert str(graph2.id) in graph_ids

    def test_list_graphs_includes_version_count(self, authenticated_client, user):
        """Each graph should include version_count and latest_version."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        GraphVersion.objects.create(graph=graph, version=1, graph_json={"nodes": [], "edges": []})
        GraphVersion.objects.create(graph=graph, version=2, graph_json={"nodes": [], "edges": []})

        response = authenticated_client.get("/api/graphs/")

        assert response.status_code == status.HTTP_200_OK
        graph_data = response.data["data"][0]
        assert graph_data["version_count"] == 2
        assert graph_data["latest_version"] == 2

    def test_create_graph_requires_authentication(self, api_client):
        """Unauthenticated requests should be rejected."""
        response = api_client.post("/api/graphs/", {"name": "Test Graph"}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_graph_success(self, authenticated_client, user):
        """Should create a new graph and return it."""
        data = {"name": "New Workflow", "description": "A test workflow"}

        response = authenticated_client.post("/api/graphs/", data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert "data" in response.data
        assert response.data["data"]["name"] == "New Workflow"
        assert response.data["data"]["description"] == "A test workflow"
        assert response.data["data"]["version_count"] == 0
        assert response.data["data"]["latest_version"] is None

        # Verify it was created in database
        assert Graph.objects.filter(name="New Workflow", owner=user).exists()

    def test_create_graph_name_is_required(self, authenticated_client):
        """Creating a graph without name should fail."""
        response = authenticated_client.post(
            "/api/graphs/", {"description": "Missing name"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "details" in response.data["error"]

    def test_create_graph_description_is_optional(self, authenticated_client, user):
        """Should allow creating a graph without description."""
        response = authenticated_client.post(
            "/api/graphs/", {"name": "No Description"}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["description"] == ""


class TestGraphDetail:
    """Tests for GET/PATCH/DELETE /api/graphs/{id}/"""

    def test_get_graph_requires_authentication(self, api_client, user):
        """Unauthenticated requests should be rejected."""
        graph = Graph.objects.create(owner=user, name="Test")
        response = api_client.get(f"/api/graphs/{graph.id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_graph_returns_details_with_versions(self, authenticated_client, user):
        """Should return graph with all versions."""
        graph = Graph.objects.create(owner=user, name="Test Graph")
        GraphVersion.objects.create(graph=graph, version=1, graph_json={"nodes": [], "edges": []})
        GraphVersion.objects.create(graph=graph, version=2, graph_json={"nodes": [], "edges": []})

        response = authenticated_client.get(f"/api/graphs/{graph.id}")

        assert response.status_code == status.HTTP_200_OK
        assert "data" in response.data
        assert response.data["data"]["name"] == "Test Graph"
        assert len(response.data["data"]["versions"]) == 2
        assert response.data["data"]["versions"][0]["version"] == 2  # Latest first
        assert response.data["data"]["versions"][1]["version"] == 1

    def test_get_graph_not_found(self, authenticated_client):
        """Should return 404 for non-existent graph."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = authenticated_client.get(f"/api/graphs/{fake_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.data
        assert response.data["error"]["code"] == "NOT_FOUND"

    def test_get_graph_denies_access_to_other_users_graphs(self, api_client, user):
        """User should not be able to access another user's graph."""
        from infrastructure.orm.models import User

        other_user = User.objects.create_user(email="other@example.com", password="password123")
        graph = Graph.objects.create(owner=other_user, name="Private Graph")

        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/graphs/{graph.id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_graph_name_and_description(self, authenticated_client, user):
        """Should update graph metadata."""
        graph = Graph.objects.create(owner=user, name="Old Name", description="Old Description")

        data = {"name": "New Name", "description": "New Description"}
        response = authenticated_client.patch(f"/api/graphs/{graph.id}", data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["name"] == "New Name"
        assert response.data["data"]["description"] == "New Description"

        graph.refresh_from_db()
        assert graph.name == "New Name"
        assert graph.description == "New Description"

    def test_update_graph_partial_update(self, authenticated_client, user):
        """Should allow updating only name or only description."""
        graph = Graph.objects.create(
            owner=user, name="Original", description="Original Description"
        )

        response = authenticated_client.patch(
            f"/api/graphs/{graph.id}", {"name": "Updated Name"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["name"] == "Updated Name"
        assert response.data["data"]["description"] == "Original Description"

    def test_delete_graph_success(self, authenticated_client, user):
        """Should delete graph and all versions."""
        graph = Graph.objects.create(owner=user, name="To Delete")
        GraphVersion.objects.create(graph=graph, version=1, graph_json={"nodes": [], "edges": []})

        response = authenticated_client.delete(f"/api/graphs/{graph.id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Graph.objects.filter(id=graph.id).exists()
        assert not GraphVersion.objects.filter(graph_id=graph.id).exists()

    def test_delete_graph_not_found(self, authenticated_client):
        """Should return 404 when deleting non-existent graph."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = authenticated_client.delete(f"/api/graphs/{fake_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestGraphVersionListCreate:
    """Tests for GET/POST /api/graphs/{id}/versions/"""

    def test_list_versions_requires_authentication(self, api_client, user):
        """Unauthenticated requests should be rejected."""
        graph = Graph.objects.create(owner=user, name="Test")
        response = api_client.get(f"/api/graphs/{graph.id}/versions")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_versions_returns_all_versions(self, authenticated_client, user):
        """Should return all versions for a graph."""
        graph = Graph.objects.create(owner=user, name="Test")
        GraphVersion.objects.create(graph=graph, version=1, graph_json={"nodes": [], "edges": []})
        GraphVersion.objects.create(graph=graph, version=2, graph_json={"nodes": [], "edges": []})

        response = authenticated_client.get(f"/api/graphs/{graph.id}/versions")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) == 2
        assert response.data["data"][0]["version"] == 2  # Latest first

    def test_create_version_auto_increments(self, authenticated_client, user):
        """Version numbers should auto-increment."""
        graph = Graph.objects.create(owner=user, name="Test")
        GraphVersion.objects.create(graph=graph, version=1, graph_json={"nodes": [], "edges": []})

        graph_json = {"nodes": [{"id": "n1", "type": "prompt", "name": "Test"}], "edges": []}
        response = authenticated_client.post(
            f"/api/graphs/{graph.id}/versions", {"graph_json": graph_json}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["version"] == 2

    def test_create_version_via_top_level_endpoint(self, authenticated_client, user):
        """Top-level graph version create should accept graph_id in the payload."""
        graph = Graph.objects.create(owner=user, name="Top Level Test")
        graph_json = {"nodes": [{"id": "n1", "type": "prompt", "name": "Test"}], "edges": []}

        response = authenticated_client.post(
            "/api/graph-versions",
            {"graph_id": str(graph.id), "graph_json": graph_json},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["graph_id"] == str(graph.id)
        assert response.data["data"]["graph_json"] == graph_json

    def test_create_version_validates_graph_json(self, authenticated_client, user):
        """Should validate graph_json structure."""
        graph = Graph.objects.create(owner=user, name="Test")

        # Missing required fields
        invalid_json: dict[str, Any] = {"nodes": []}  # Missing edges
        response = authenticated_client.post(
            f"/api/graphs/{graph.id}/versions",
            {"graph_json": invalid_json},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data

    def test_create_version_validates_node_structure(self, authenticated_client, user):
        """Should validate node structure."""
        graph = Graph.objects.create(owner=user, name="Test")

        invalid_json: dict[str, Any] = {
            "nodes": [{"type": "prompt"}],  # Missing id and name
            "edges": [],
        }
        response = authenticated_client.post(
            f"/api/graphs/{graph.id}/versions",
            {"graph_json": invalid_json},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "GRAPH_VALIDATION_ERROR"

    def test_create_version_computes_checksum(self, authenticated_client, user):
        """Should compute and store checksum."""
        graph = Graph.objects.create(owner=user, name="Test")
        graph_json: dict[str, Any] = {"nodes": [], "edges": []}

        response = authenticated_client.post(
            f"/api/graphs/{graph.id}/versions", {"graph_json": graph_json}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert "checksum" in response.data["data"]
        assert len(response.data["data"]["checksum"]) == 64  # SHA256

    def test_create_version_accepts_agent_node_type(self, authenticated_client, user):
        """Graph version creation should accept the agent node type."""
        graph = Graph.objects.create(owner=user, name="Agent Graph")
        graph_json: dict[str, Any] = {
            "nodes": [
                {"id": "agent-1", "type": "agent", "name": "Agent", "config": {}},
                {"id": "output-1", "type": "output", "name": "Output", "config": {}},
            ],
            "edges": [
                {"id": "e1", "from": "agent-1", "to": "output-1"},
            ],
        }

        response = authenticated_client.post(
            f"/api/graphs/{graph.id}/versions", {"graph_json": graph_json}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["graph_json"]["nodes"][0]["type"] == "agent"

    def test_create_version_preserves_edge_labels_and_node_policies(
        self, authenticated_client, user
    ):
        graph = Graph.objects.create(owner=user, name="Test")

        graph_json = {
            "nodes": [
                {
                    "id": "prompt1",
                    "type": "prompt",
                    "name": "Prompt",
                    "config": {"prompt_id": "p1"},
                    "retry_policy": {
                        "max_attempts": 4,
                        "backoff_ms": 250,
                        "backoff_strategy": "fixed",
                    },
                    "timeout_ms": 1500,
                },
                {
                    "id": "branch1",
                    "type": "branch",
                    "name": "Branch",
                    "config": {"condition": "vars.ok == true"},
                },
                {"id": "out_true", "type": "output", "name": "True out", "config": {}},
                {"id": "out_false", "type": "output", "name": "False out", "config": {}},
            ],
            "edges": [
                {"id": "e1", "from": "prompt1", "to": "branch1"},
                {"id": "e2", "from": "branch1", "to": "out_true", "label": "true"},
                {"id": "e3", "from": "branch1", "to": "out_false", "label": "false"},
            ],
        }

        create_response = authenticated_client.post(
            f"/api/graphs/{graph.id}/versions", {"graph_json": graph_json}, format="json"
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        version_id = create_response.data["data"]["id"]

        detail_response = authenticated_client.get(f"/api/graphs/{graph.id}/versions/{version_id}")
        assert detail_response.status_code == status.HTTP_200_OK
        assert detail_response.data["data"]["graph_json"] == graph_json

    def test_create_version_preserves_documented_contract_fields(self, authenticated_client, user):
        """The API should persist optional P0 graph contract fields unchanged."""
        graph = Graph.objects.create(owner=user, name="Contract Graph")
        graph_json = {
            "nodes": [
                {"id": "prompt1", "type": "prompt", "name": "Prompt", "config": {}},
                {"id": "output1", "type": "output", "name": "Output", "config": {}},
            ],
            "edges": [{"id": "e1", "from": "prompt1", "to": "output1"}],
            "metadata": {"allow_cycles": False, "source": "contract-test"},
            "editor_state": {"viewport": {"x": 10, "y": 20, "zoom": 1.25}},
            "graph_id": "graph-contract-1",
            "version_id": "version-contract-1",
        }

        create_response = authenticated_client.post(
            f"/api/graphs/{graph.id}/versions", {"graph_json": graph_json}, format="json"
        )

        assert create_response.status_code == status.HTTP_201_CREATED
        version_id = create_response.data["data"]["id"]

        detail_response = authenticated_client.get(f"/api/graphs/{graph.id}/versions/{version_id}")
        assert detail_response.status_code == status.HTTP_200_OK
        assert detail_response.data["data"]["graph_json"] == graph_json


class TestGraphVersionDetail:
    """Tests for GET /api/graphs/{id}/versions/{version_id}"""

    def test_get_version_returns_full_graph_json(self, authenticated_client, user):
        """Should return version with complete graph_json."""
        graph = Graph.objects.create(owner=user, name="Test")
        graph_json = {
            "nodes": [{"id": "n1", "type": "prompt", "name": "Test Node"}],
            "edges": [],
        }
        version = GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json)

        response = authenticated_client.get(f"/api/graphs/{graph.id}/versions/{version.id}")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["graph_json"] == graph_json
        assert response.data["data"]["version"] == 1

    def test_get_version_not_found(self, authenticated_client, user):
        """Should return 404 for non-existent version."""
        graph = Graph.objects.create(owner=user, name="Test")
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = authenticated_client.get(f"/api/graphs/{graph.id}/versions/{fake_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestGraphVersionLatest:
    """Tests for GET /api/graphs/{id}/versions/latest"""

    def test_get_latest_version_returns_highest_version(self, authenticated_client, user):
        """Should return the version with the highest version number."""
        graph = Graph.objects.create(owner=user, name="Test")
        GraphVersion.objects.create(graph=graph, version=1, graph_json={"nodes": [], "edges": []})
        GraphVersion.objects.create(graph=graph, version=2, graph_json={"nodes": [], "edges": []})

        response = authenticated_client.get(f"/api/graphs/{graph.id}/versions/latest")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["version"] == 2

    def test_get_latest_version_no_versions(self, authenticated_client, user):
        """Should return 404 if graph has no versions."""
        graph = Graph.objects.create(owner=user, name="Test")

        response = authenticated_client.get(f"/api/graphs/{graph.id}/versions/latest")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"]["code"] == "NOT_FOUND"


class TestExternalWorkflowCreate:
    """Tests for POST /api/graphs/external-workflows"""

    def test_external_workflow_requires_authentication(self, api_client):
        payload = {
            "name": "External Workflow",
            "graph_json": {"nodes": [], "edges": []},
        }
        response = api_client.post("/api/graphs/external-workflows", payload, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_external_workflow_creates_graph_and_version(self, authenticated_client, user):
        payload = {
            "name": "QA Workflow",
            "description": "Created externally",
            "external_source": "qa",
            "external_ref": "qa-workflow-001",
            "graph_json": {
                "nodes": [
                    {"id": "prompt1", "type": "prompt", "name": "Prompt 1", "config": {}},
                    {"id": "output1", "type": "output", "name": "Done", "config": {}},
                ],
                "edges": [
                    {"id": "e1", "from": "START", "to": "prompt1"},
                    {"id": "e2", "from": "prompt1", "to": "output1"},
                ],
            },
        }

        response = authenticated_client.post(
            "/api/graphs/external-workflows",
            payload,
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["graph_name"] == "QA Workflow"
        assert response.data["data"]["graph_description"] == "Created externally"
        assert response.data["data"]["graph_version"] == 1
        assert response.data["data"]["external_source"] == "qa"
        assert response.data["data"]["external_ref"] == "qa-workflow-001"
        assert response.data["data"]["created_graph"] is True
        assert response.data["data"]["created_version"] is True
        assert response.data["data"]["idempotent_replay"] is False
        assert isinstance(response.data["data"]["warnings"], list)

        graph = Graph.objects.get(id=response.data["data"]["graph_id"])
        version = GraphVersion.objects.get(id=response.data["data"]["graph_version_id"])

        assert graph.owner_id == user.id
        assert graph.external_source == "qa"
        assert graph.external_ref == "qa-workflow-001"
        assert version.graph_id == graph.id
        assert version.version == 1
        assert version.graph_json == payload["graph_json"]
        assert MemoryConfiguration.objects.filter(graph=graph).exists()

    def test_external_ref_reuses_graph_and_creates_new_version(self, authenticated_client):
        payload_v1 = {
            "name": "QA Workflow",
            "external_source": "qa",
            "external_ref": "qa-workflow-002",
            "graph_json": {
                "nodes": [
                    {"id": "prompt1", "type": "prompt", "name": "Prompt 1", "config": {}},
                    {"id": "output1", "type": "output", "name": "Done", "config": {}},
                ],
                "edges": [
                    {"id": "e1", "from": "START", "to": "prompt1"},
                    {"id": "e2", "from": "prompt1", "to": "output1"},
                ],
            },
        }
        first = authenticated_client.post(
            "/api/graphs/external-workflows", payload_v1, format="json"
        )
        assert first.status_code == status.HTTP_201_CREATED
        graph_id = first.data["data"]["graph_id"]

        payload_v2 = {
            **payload_v1,
            "graph_json": {
                "nodes": [
                    {"id": "prompt1", "type": "prompt", "name": "Prompt 1", "config": {}},
                    {"id": "transform1", "type": "transform", "name": "T", "config": {}},
                    {"id": "output1", "type": "output", "name": "Done", "config": {}},
                ],
                "edges": [
                    {"id": "e1", "from": "START", "to": "prompt1"},
                    {"id": "e2", "from": "prompt1", "to": "transform1"},
                    {"id": "e3", "from": "transform1", "to": "output1"},
                ],
            },
        }
        second = authenticated_client.post(
            "/api/graphs/external-workflows",
            payload_v2,
            format="json",
        )

        assert second.status_code == status.HTTP_201_CREATED
        assert second.data["data"]["graph_id"] == graph_id
        assert second.data["data"]["graph_version"] == 2
        assert second.data["data"]["created_graph"] is False
        assert second.data["data"]["created_version"] is True

    def test_external_ref_same_graph_json_reuses_latest_version(self, authenticated_client):
        payload = {
            "name": "Stable Workflow",
            "external_source": "qa",
            "external_ref": "qa-workflow-003",
            "graph_json": {
                "nodes": [
                    {"id": "prompt1", "type": "prompt", "name": "Prompt 1", "config": {}},
                    {"id": "output1", "type": "output", "name": "Done", "config": {}},
                ],
                "edges": [
                    {"id": "e1", "from": "START", "to": "prompt1"},
                    {"id": "e2", "from": "prompt1", "to": "output1"},
                ],
            },
        }
        first = authenticated_client.post("/api/graphs/external-workflows", payload, format="json")
        second = authenticated_client.post("/api/graphs/external-workflows", payload, format="json")

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_200_OK
        assert second.data["data"]["graph_id"] == first.data["data"]["graph_id"]
        assert second.data["data"]["graph_version_id"] == first.data["data"]["graph_version_id"]
        assert second.data["data"]["created_graph"] is False
        assert second.data["data"]["created_version"] is False
        assert second.data["data"]["idempotent_replay"] is False

    def test_external_workflow_idempotency_key_replays_result(self, authenticated_client):
        payload = {
            "name": "Idempotent Workflow",
            "external_source": "qa",
            "external_ref": "qa-workflow-004",
            "idempotency_key": "qa-workflow-004:v1",
            "graph_json": {
                "nodes": [
                    {"id": "prompt1", "type": "prompt", "name": "Prompt 1", "config": {}},
                    {"id": "output1", "type": "output", "name": "Done", "config": {}},
                ],
                "edges": [
                    {"id": "e1", "from": "START", "to": "prompt1"},
                    {"id": "e2", "from": "prompt1", "to": "output1"},
                ],
            },
        }
        first = authenticated_client.post("/api/graphs/external-workflows", payload, format="json")

        payload_changed = {
            **payload,
            "name": "Changed Name That Should Be Ignored",
            "graph_json": {
                "nodes": [
                    {"id": "different", "type": "prompt", "name": "Different", "config": {}},
                    {"id": "output1", "type": "output", "name": "Done", "config": {}},
                ],
                "edges": [
                    {"id": "e1", "from": "START", "to": "different"},
                    {"id": "e2", "from": "different", "to": "output1"},
                ],
            },
        }
        second = authenticated_client.post(
            "/api/graphs/external-workflows",
            payload_changed,
            format="json",
        )

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_200_OK
        assert second.data["data"]["graph_id"] == first.data["data"]["graph_id"]
        assert second.data["data"]["graph_version_id"] == first.data["data"]["graph_version_id"]
        assert second.data["data"]["idempotent_replay"] is True
        assert second.data["data"]["created_graph"] is False
        assert second.data["data"]["created_version"] is False
        assert GraphVersion.objects.filter(graph_id=first.data["data"]["graph_id"]).count() == 1

    def test_external_workflow_accepts_idempotency_header(self, authenticated_client):
        payload = {
            "name": "Header Idempotency Workflow",
            "external_source": "qa",
            "external_ref": "qa-workflow-005",
            "graph_json": {
                "nodes": [
                    {"id": "prompt1", "type": "prompt", "name": "Prompt 1", "config": {}},
                    {"id": "output1", "type": "output", "name": "Done", "config": {}},
                ],
                "edges": [
                    {"id": "e1", "from": "START", "to": "prompt1"},
                    {"id": "e2", "from": "prompt1", "to": "output1"},
                ],
            },
        }
        headers = {"HTTP_IDEMPOTENCY_KEY": "qa-workflow-005:v1"}

        first = authenticated_client.post(
            "/api/graphs/external-workflows",
            payload,
            format="json",
            **headers,
        )
        second = authenticated_client.post(
            "/api/graphs/external-workflows",
            payload,
            format="json",
            **headers,
        )

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_200_OK
        assert second.data["data"]["idempotency_key"] == "qa-workflow-005:v1"
        assert second.data["data"]["idempotent_replay"] is True

    def test_external_workflow_requires_member_role(self, authenticated_client, user):
        OrganizationMembership.objects.filter(
            organization_id=user.default_organization_id,
            user=user,
        ).update(role="viewer")
        payload = {
            "name": "Forbidden Workflow",
            "graph_json": {"nodes": [], "edges": []},
        }

        response = authenticated_client.post(
            "/api/graphs/external-workflows",
            payload,
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["error"]["code"] == "FORBIDDEN"

    def test_external_workflow_validates_graph_json_shape(self, authenticated_client):
        payload = {
            "name": "Invalid Workflow",
            "graph_json": {"nodes": []},
        }

        response = authenticated_client.post(
            "/api/graphs/external-workflows",
            payload,
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

    def test_external_workflow_can_require_entry_exit(self, authenticated_client):
        payload = {
            "name": "Strict Workflow",
            "require_entry_exit": True,
            "graph_json": {
                "nodes": [{"id": "prompt1", "type": "prompt", "name": "Prompt 1", "config": {}}],
                "edges": [{"id": "e1", "from": "START", "to": "prompt1"}],
            },
        }

        response = authenticated_client.post(
            "/api/graphs/external-workflows",
            payload,
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "GRAPH_VALIDATION_ERROR"
        error_types = [item["type"] for item in response.data["error"]["details"]]
        assert "no_output_node" in error_types


class TestGraphAPIResponseFormat:
    """Tests for standardized API response format."""

    def test_success_response_has_data_and_meta(self, authenticated_client, user):
        """All success responses should have data and meta fields."""
        Graph.objects.create(owner=user, name="Test")

        response = authenticated_client.get("/api/graphs/")

        assert response.status_code == status.HTTP_200_OK
        assert "data" in response.data
        assert "meta" in response.data
        assert "requestId" in response.data["meta"]
        assert "timestamp" in response.data["meta"]

    def test_error_response_has_error_and_meta(self, authenticated_client):
        """All error responses should have error and meta fields."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = authenticated_client.get(f"/api/graphs/{fake_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.data
        assert "meta" in response.data
        assert "code" in response.data["error"]
        assert "message" in response.data["error"]
        assert "requestId" in response.data["meta"]
        assert "timestamp" in response.data["meta"]

    def test_validation_error_includes_details(self, authenticated_client):
        """Validation errors should include field-level details."""
        response = authenticated_client.post(
            "/api/graphs/", {"description": "No name"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "details" in response.data["error"]
        assert isinstance(response.data["error"]["details"], list)


class TestGraphValidateEndpoint:
    """Tests for POST /api/graphs/validate"""

    def test_validate_requires_authentication(self, api_client):
        """Unauthenticated requests should be rejected."""
        response = api_client.post("/api/graphs/validate", {}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_validate_requires_graph_json(self, authenticated_client):
        """Should return error if graph_json is missing."""
        response = authenticated_client.post("/api/graphs/validate", {}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

    def test_validate_valid_graph(self, authenticated_client):
        """Should return valid=true for a valid graph."""
        valid_graph = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "First", "config": {}},
                {"id": "node2", "type": "output", "name": "End", "config": {}},
            ],
            "edges": [
                {"id": "e1", "from": "START", "to": "node1"},
                {"id": "e2", "from": "node1", "to": "node2"},
            ],
        }

        response = authenticated_client.post(
            "/api/graphs/validate",
            {"graph_json": valid_graph},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["valid"] is True
        assert len(response.data["data"]["errors"]) == 0

    def test_validate_missing_start_node(self, authenticated_client):
        """Should return error for missing start edge."""
        graph = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "First", "config": {}},
                {"id": "node2", "type": "output", "name": "End", "config": {}},
            ],
            "edges": [
                {"id": "e1", "from": "node1", "to": "node2"},
            ],
        }

        response = authenticated_client.post(
            "/api/graphs/validate",
            {"graph_json": graph},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["valid"] is False
        error_types = [e["type"] for e in response.data["data"]["errors"]]
        assert "no_start_node" in error_types

    def test_validate_missing_output_node(self, authenticated_client):
        """Should return error for missing output node."""
        graph = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "First", "config": {}},
            ],
            "edges": [
                {"id": "e1", "from": "START", "to": "node1"},
            ],
        }

        response = authenticated_client.post(
            "/api/graphs/validate",
            {"graph_json": graph},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["valid"] is False
        error_types = [e["type"] for e in response.data["data"]["errors"]]
        assert "no_output_node" in error_types

    def test_validate_disconnected_node_warning(self, authenticated_client):
        """Should return warning for disconnected nodes."""
        graph = {
            "nodes": [
                {"id": "node1", "type": "prompt", "name": "First", "config": {}},
                {"id": "node2", "type": "output", "name": "End", "config": {}},
                {"id": "orphan", "type": "transform", "name": "Orphan", "config": {}},
            ],
            "edges": [
                {"id": "e1", "from": "START", "to": "node1"},
                {"id": "e2", "from": "node1", "to": "node2"},
            ],
        }

        response = authenticated_client.post(
            "/api/graphs/validate",
            {"graph_json": graph},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        # Graph is still valid (warnings don't make it invalid)
        assert response.data["data"]["valid"] is True
        warning_types = [w["type"] for w in response.data["data"]["warnings"]]
        assert "disconnected_node" in warning_types

    def test_validate_strict_agent_config_error(self, authenticated_client):
        """Strict validation should reject malformed agent config."""
        graph = {
            "nodes": [
                {
                    "id": "agent-1",
                    "type": "agent",
                    "name": "Agent",
                    "config": {"model": "gpt-4.1-mini"},
                },
                {"id": "output-1", "type": "output", "name": "End", "config": {}},
            ],
            "edges": [
                {"id": "e1", "from": "START", "to": "agent-1"},
                {"id": "e2", "from": "agent-1", "to": "output-1"},
            ],
        }

        response = authenticated_client.post(
            "/api/graphs/validate",
            {"graph_json": graph, "strict": True},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["valid"] is False
        config_errors = [
            error
            for error in response.data["data"]["errors"]
            if error.get("type") == "invalid_node_config"
        ]
        assert len(config_errors) == 1
        assert config_errors[0]["field"] == "tools"

    def test_validate_strict_agent_config_success(self, authenticated_client):
        """Strict validation should accept a valid agent config."""
        graph = {
            "nodes": [
                {
                    "id": "agent-1",
                    "type": "agent",
                    "name": "Agent",
                    "config": {
                        "model": "gpt-4.1-mini",
                        "tools": ["lookup_customer", "send_email"],
                        "max_steps": 5,
                        "max_tool_calls": 3,
                        "approval_required_tools": ["send_email"],
                    },
                },
                {"id": "output-1", "type": "output", "name": "End", "config": {}},
            ],
            "edges": [
                {"id": "e1", "from": "START", "to": "agent-1"},
                {"id": "e2", "from": "agent-1", "to": "output-1"},
            ],
        }

        response = authenticated_client.post(
            "/api/graphs/validate",
            {"graph_json": graph, "strict": True},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["valid"] is True
        assert response.data["data"]["errors"] == []
