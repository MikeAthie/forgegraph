"""
End-to-end tests for complete user flows.

Tests realistic scenarios that span multiple API endpoints and features,
simulating how real users would interact with the application.
"""

import pytest
from django.conf import settings
from rest_framework import status

pytestmark = pytest.mark.django_db

STRONG_PASSWORD = "ForgeGraphTest!12345"


class TestCompleteAuthFlow:
    """Test complete authentication flow from registration to logout."""

    def test_user_registration_login_profile_logout_flow(self, api_client):
        """
        Complete flow: Register → Login → Access Profile → Logout → Verify logged out
        """
        # Step 1: Register a new user
        register_response = api_client.post(
            "/api/auth/register",
            {"email": "newuser@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        assert register_response.status_code == status.HTTP_201_CREATED
        assert register_response.data["email"] == "newuser@example.com"

        # Step 2: Login with registered credentials
        login_response = api_client.post(
            "/api/auth/login",
            {"email": "newuser@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        assert login_response.status_code == status.HTTP_200_OK
        access_token = login_response.data["access"]
        assert access_token

        # Step 3: Access profile using JWT
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        profile_response = api_client.get("/api/auth/me")
        assert profile_response.status_code == status.HTTP_200_OK
        assert profile_response.data["email"] == "newuser@example.com"

        # Step 4: Logout
        logout_response = api_client.post("/api/auth/logout", {}, format="json")
        assert logout_response.status_code == status.HTTP_204_NO_CONTENT

        # Step 5: Verify refresh token is blacklisted
        refresh_cookie = login_response.cookies.get(settings.AUTH_REFRESH_COOKIE)
        api_client.cookies[settings.AUTH_REFRESH_COOKIE] = refresh_cookie.value
        refresh_response = api_client.post("/api/auth/refresh", {}, format="json")
        assert refresh_response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
        ]

    def test_token_refresh_flow(self, api_client, user):
        """
        Token refresh flow: Login → Use token → Refresh → Use new token
        """
        # Step 1: Login
        login_response = api_client.post(
            "/api/auth/login",
            {"email": user.email, "password": "testpassword123"},
            format="json",
        )
        old_access = login_response.data["access"]

        # Step 2: Use token successfully
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
        profile_response = api_client.get("/api/auth/me")
        assert profile_response.status_code == status.HTTP_200_OK

        # Step 3: Refresh token
        refresh_response = api_client.post("/api/auth/refresh", {}, format="json")
        assert refresh_response.status_code == status.HTTP_200_OK
        new_access = refresh_response.data["access"]
        assert new_access != old_access

        # Step 4: Use new token successfully
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_access}")
        profile_response2 = api_client.get("/api/auth/me")
        assert profile_response2.status_code == status.HTTP_200_OK


class TestGraphWorkflowFlow:
    """Test complete graph workflow from creation to deletion."""

    def test_create_graph_add_versions_view_delete_flow(self, authenticated_client, user):
        """
        Complete graph workflow: Create → Add Version → View → Update → Delete
        """
        # Step 1: Create a new graph
        create_response = authenticated_client.post(
            "/api/graphs/",
            {"name": "My Workflow", "description": "Test workflow"},
            format="json",
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        graph_id = create_response.data["data"]["id"]

        # Step 2: Add first version
        version1_response = authenticated_client.post(
            f"/api/graphs/{graph_id}/versions",
            {"graph_json": {"nodes": [], "edges": []}},
            format="json",
        )
        assert version1_response.status_code == status.HTTP_201_CREATED
        assert version1_response.data["data"]["version"] == 1

        # Step 3: Add second version
        version2_response = authenticated_client.post(
            f"/api/graphs/{graph_id}/versions",
            {
                "graph_json": {
                    "nodes": [{"id": "n1", "type": "prompt", "name": "Start"}],
                    "edges": [],
                }
            },
            format="json",
        )
        assert version2_response.status_code == status.HTTP_201_CREATED
        assert version2_response.data["data"]["version"] == 2

        # Step 4: View graph with all versions
        detail_response = authenticated_client.get(f"/api/graphs/{graph_id}")
        assert detail_response.status_code == status.HTTP_200_OK
        assert len(detail_response.data["data"]["versions"]) == 2

        # Step 5: Get latest version
        latest_response = authenticated_client.get(f"/api/graphs/{graph_id}/versions/latest")
        assert latest_response.status_code == status.HTTP_200_OK
        assert latest_response.data["data"]["version"] == 2

        # Step 6: Update graph metadata
        update_response = authenticated_client.patch(
            f"/api/graphs/{graph_id}",
            {"name": "Updated Workflow"},
            format="json",
        )
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.data["data"]["name"] == "Updated Workflow"

        # Step 7: List all graphs (should include updated graph)
        list_response = authenticated_client.get("/api/graphs/")
        assert list_response.status_code == status.HTTP_200_OK
        assert any(g["id"] == graph_id for g in list_response.data["data"])

        # Step 8: Delete graph
        delete_response = authenticated_client.delete(f"/api/graphs/{graph_id}")
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT

        # Step 9: Verify deletion
        verify_response = authenticated_client.get(f"/api/graphs/{graph_id}")
        assert verify_response.status_code == status.HTTP_404_NOT_FOUND

    def test_multi_user_graph_isolation_flow(self, api_client):
        """
        Test that graphs are properly isolated between users.
        """
        # Create two users
        api_client.post(
            "/api/auth/register",
            {"email": "user1@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        api_client.post(
            "/api/auth/register",
            {"email": "user2@example.com", "password": STRONG_PASSWORD},
            format="json",
        )

        # Login as user1
        login1 = api_client.post(
            "/api/auth/login",
            {"email": "user1@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        token1 = login1.data["access"]

        # User1 creates a graph
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token1}")
        graph_response = api_client.post(
            "/api/graphs/",
            {"name": "User1's Graph"},
            format="json",
        )
        graph_id = graph_response.data["data"]["id"]

        # Login as user2
        login2 = api_client.post(
            "/api/auth/login",
            {"email": "user2@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        token2 = login2.data["access"]

        # User2 should not see user1's graph
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token2}")
        list_response = api_client.get("/api/graphs/")
        assert not any(g["id"] == graph_id for g in list_response.data["data"])

        # User2 should not be able to access user1's graph
        detail_response = api_client.get(f"/api/graphs/{graph_id}")
        assert detail_response.status_code == status.HTTP_404_NOT_FOUND


class TestPromptLibraryFlow:
    """Test complete prompt library workflow."""

    def test_create_prompt_publish_clone_flow(self, api_client):
        """
        Complete prompt flow: Create → Publish → Clone by another user
        """
        # Register and login as user1
        api_client.post(
            "/api/auth/register",
            {"email": "author@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        login1 = api_client.post(
            "/api/auth/login",
            {"email": "author@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        token1 = login1.data["access"]

        # User1 creates a private prompt
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token1}")
        create_response = api_client.post(
            "/api/prompts/",
            {
                "title": "Research Helper",
                "description": "Helps with research",
                "category": "research",
                "content": "You are a research assistant...",
            },
            format="json",
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        prompt_id = create_response.data["data"]["id"]
        assert create_response.data["data"]["visibility"] == "private"

        # User1 publishes the prompt
        publish_response = api_client.post(
            f"/api/prompts/{prompt_id}/publish",
            {"license": "MIT"},
            format="json",
        )
        assert publish_response.status_code == status.HTTP_200_OK
        assert publish_response.data["data"]["visibility"] == "public"

        # Register and login as user2
        api_client.post(
            "/api/auth/register",
            {"email": "cloner@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        login2 = api_client.post(
            "/api/auth/login",
            {"email": "cloner@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        token2 = login2.data["access"]

        # User2 can see the published prompt
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token2}")
        list_response = api_client.get("/api/prompts/")
        assert any(p["id"] == prompt_id for p in list_response.data["data"])

        # User2 clones the prompt
        clone_response = api_client.post(f"/api/prompts/{prompt_id}/clone")
        assert clone_response.status_code == status.HTTP_201_CREATED
        clone_id = clone_response.data["data"]["id"]
        assert clone_id != prompt_id
        assert clone_response.data["data"]["title"] == "Research Helper (Copy)"
        assert clone_response.data["data"]["visibility"] == "private"

        # User2 can modify their clone
        update_response = api_client.patch(
            f"/api/prompts/{clone_id}",
            {"title": "My Research Helper"},
            format="json",
        )
        assert update_response.status_code == status.HTTP_200_OK

        # Original prompt remains unchanged
        original_response = api_client.get(f"/api/prompts/{prompt_id}")
        assert original_response.data["data"]["title"] == "Research Helper"

    def test_prompt_filtering_and_search_flow(self, authenticated_client, user):
        """
        Test prompt library filtering and search functionality.
        """
        # Create prompts in different categories
        authenticated_client.post(
            "/api/prompts/",
            {
                "title": "Email Writer",
                "description": "Helps write emails",
                "category": "email",
                "content": "Write an email...",
            },
            format="json",
        )
        authenticated_client.post(
            "/api/prompts/",
            {
                "title": "Research Assistant",
                "description": "Helps with research",
                "category": "research",
                "content": "Research...",
            },
            format="json",
        )
        authenticated_client.post(
            "/api/prompts/",
            {
                "title": "Summary Generator",
                "description": "Creates summaries",
                "category": "summarization",
                "content": "Summarize...",
            },
            format="json",
        )

        # Filter by category
        research_response = authenticated_client.get("/api/prompts/?category=research")
        assert all(p["category"] == "research" for p in research_response.data["data"])
        assert any(p["title"] == "Research Assistant" for p in research_response.data["data"])

        # Search by title
        search_response = authenticated_client.get("/api/prompts/?search=Email%20Writer")
        assert any(p["title"] == "Email Writer" for p in search_response.data["data"])

        # Filter by ownership (mine)
        mine_response = authenticated_client.get("/api/prompts/?ownership=mine")
        assert len(mine_response.data["data"]) == 3


class TestCompleteWorkflowScenario:
    """Test a realistic end-to-end workflow scenario."""

    def test_complete_workflow_creation_and_execution_scenario(self, api_client):
        """
        Realistic scenario: User creates account, builds workflow, adds prompts, prepares for execution.
        """
        # Step 1: Register
        register = api_client.post(
            "/api/auth/register",
            {"email": "workflow@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        assert register.status_code == status.HTTP_201_CREATED

        # Step 2: Login
        login = api_client.post(
            "/api/auth/login",
            {"email": "workflow@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        token = login.data["access"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # Step 3: Create prompt templates
        prompt1 = api_client.post(
            "/api/prompts/",
            {
                "title": "Data Extractor",
                "category": "extraction",
                "content": "Extract key information from: {input_text}",
            },
            format="json",
        )
        prompt1_id = prompt1.data["data"]["id"]

        prompt2 = api_client.post(
            "/api/prompts/",
            {
                "title": "Summarizer",
                "category": "summarization",
                "content": "Summarize: {extracted_data}",
            },
            format="json",
        )
        prompt2_id = prompt2.data["data"]["id"]

        # Step 4: Create a workflow graph
        graph = api_client.post(
            "/api/graphs/",
            {
                "name": "Extract and Summarize",
                "description": "Extracts data and creates summary",
            },
            format="json",
        )
        graph_id = graph.data["data"]["id"]

        # Step 5: Create graph version with nodes referencing prompts
        version = api_client.post(
            f"/api/graphs/{graph_id}/versions",
            {
                "graph_json": {
                    "nodes": [
                        {
                            "id": "extract",
                            "type": "prompt",
                            "name": "Extract Data",
                            "config": {"promptId": prompt1_id},
                        },
                        {
                            "id": "summarize",
                            "type": "prompt",
                            "name": "Create Summary",
                            "config": {"promptId": prompt2_id},
                        },
                        {
                            "id": "output",
                            "type": "output",
                            "name": "Final Output",
                        },
                    ],
                    "edges": [
                        {"id": "e1", "from": "extract", "to": "summarize"},
                        {"id": "e2", "from": "summarize", "to": "output"},
                    ],
                }
            },
            format="json",
        )
        assert version.status_code == status.HTTP_201_CREATED

        # Step 6: Verify workflow is ready
        detail = api_client.get(f"/api/graphs/{graph_id}")
        assert detail.status_code == status.HTTP_200_OK
        assert len(detail.data["data"]["versions"]) == 1
        assert detail.data["data"]["versions"][0]["version"] == 1

        # Step 7: List all resources
        graphs_list = api_client.get("/api/graphs/")
        prompts_list = api_client.get("/api/prompts/")
        assert len(graphs_list.data["data"]) == 1

        prompt_ids = {p["id"] for p in prompts_list.data["data"]}
        assert prompt1_id in prompt_ids
        assert prompt2_id in prompt_ids


class TestErrorHandlingFlows:
    """Test error handling in complete flows."""

    def test_invalid_credentials_cannot_access_resources(self, api_client, user):
        """
        Verify that invalid/missing credentials prevent access to protected resources.
        """
        # Try to access protected endpoints without authentication
        responses = [
            api_client.get("/api/graphs/"),
            api_client.get("/api/prompts/"),
            api_client.get("/api/auth/me"),
        ]

        for response in responses:
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_graph_json_prevents_version_creation(self, authenticated_client, user):
        """
        Verify that invalid graph JSON is rejected at version creation.
        """
        # Create graph
        graph = authenticated_client.post("/api/graphs/", {"name": "Test"}, format="json")
        graph_id = graph.data["data"]["id"]

        # Try to create version with invalid JSON
        invalid_responses = [
            authenticated_client.post(
                f"/api/graphs/{graph_id}/versions",
                {"graph_json": {"nodes": []}},  # Missing edges
                format="json",
            ),
            authenticated_client.post(
                f"/api/graphs/{graph_id}/versions",
                {"graph_json": {"edges": []}},  # Missing nodes
                format="json",
            ),
            authenticated_client.post(
                f"/api/graphs/{graph_id}/versions",
                {"graph_json": []},  # Not an object
                format="json",
            ),
        ]

        for response in invalid_responses:
            assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_deleted_resources_cannot_be_accessed(self, authenticated_client, user):
        """
        Verify that deleted resources return 404.
        """
        # Create and delete a graph
        graph = authenticated_client.post("/api/graphs/", {"name": "To Delete"}, format="json")
        graph_id = graph.data["data"]["id"]

        authenticated_client.delete(f"/api/graphs/{graph_id}")

        # Attempt to access deleted resource
        responses = [
            authenticated_client.get(f"/api/graphs/{graph_id}"),
            authenticated_client.patch(f"/api/graphs/{graph_id}", {"name": "New"}, format="json"),
            authenticated_client.delete(f"/api/graphs/{graph_id}"),
        ]

        for response in responses:
            assert response.status_code == status.HTTP_404_NOT_FOUND
