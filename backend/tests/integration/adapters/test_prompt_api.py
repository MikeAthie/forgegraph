"""
Integration tests for Prompt APIs.

Tests all PromptTemplate endpoints following REST best practices.
"""

import pytest
from rest_framework import status

from infrastructure.orm.models import PromptTemplate, User

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_builtin_prompts():
    """Remove built-in prompts seeded by migrations to ensure clean test state."""
    PromptTemplate.objects.filter(owner__isnull=True).delete()
    yield


class TestPromptListCreate:
    """Tests for GET /api/prompts/ and POST /api/prompts/"""

    def test_list_prompts_requires_authentication(self, api_client):
        """Unauthenticated requests should be rejected."""
        response = api_client.get("/api/prompts/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_prompts_returns_user_and_public_prompts(self, authenticated_client, user):
        """Should return user's private prompts and all public prompts."""
        # Create user's private prompt
        PromptTemplate.objects.create(
            owner=user,
            title="My Private Prompt",
            category="research",
            content="Private content",
            visibility="private",
        )

        # Create public prompt by another user
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        PromptTemplate.objects.create(
            owner=other_user,
            title="Public Prompt",
            category="summarization",
            content="Public content",
            visibility="public",
        )

        # Create private prompt by another user (should not be visible)
        PromptTemplate.objects.create(
            owner=other_user,
            title="Other Private",
            category="email",
            content="Not visible",
            visibility="private",
        )

        # Create built-in prompt (owner=None)
        PromptTemplate.objects.create(
            owner=None,
            title="Built-in Prompt",
            category="extraction",
            content="Built-in content",
            visibility="public",
        )

        response = authenticated_client.get("/api/prompts/")

        assert response.status_code == status.HTTP_200_OK
        assert "data" in response.data
        assert len(response.data["data"]) == 3  # user, public, builtin

        prompt_titles = {p["title"] for p in response.data["data"]}
        assert "My Private Prompt" in prompt_titles
        assert "Public Prompt" in prompt_titles
        assert "Built-in Prompt" in prompt_titles
        assert "Other Private" not in prompt_titles

    def test_list_prompts_filter_by_category(self, authenticated_client, user):
        """Should filter prompts by category."""
        PromptTemplate.objects.create(
            owner=user, title="Research", category="research", content="Content"
        )
        PromptTemplate.objects.create(
            owner=user, title="Summary", category="summarization", content="Content"
        )

        response = authenticated_client.get("/api/prompts/?category=research")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) == 1
        assert response.data["data"][0]["category"] == "research"

    def test_list_prompts_filter_by_ownership(self, authenticated_client, user):
        """Should filter by ownership (mine, builtin, all)."""
        PromptTemplate.objects.create(
            owner=user, title="Mine", category="research", content="Content"
        )
        PromptTemplate.objects.create(
            owner=None,
            title="Built-in",
            category="research",
            content="Content",
            visibility="public",
        )

        # Filter for "mine"
        response = authenticated_client.get("/api/prompts/?ownership=mine")
        assert len(response.data["data"]) == 1
        assert response.data["data"][0]["title"] == "Mine"

        # Filter for "builtin"
        response = authenticated_client.get("/api/prompts/?ownership=builtin")
        assert len(response.data["data"]) == 1
        assert response.data["data"][0]["is_builtin"] is True

    def test_list_prompts_search_by_title_or_description(self, authenticated_client, user):
        """Should search in title and description."""
        PromptTemplate.objects.create(
            owner=user,
            title="Email Draft Helper",
            description="Helps with emails",
            category="email",
            content="Content",
        )
        PromptTemplate.objects.create(
            owner=user,
            title="Research Assistant",
            description="For research tasks",
            category="research",
            content="Content",
        )

        response = authenticated_client.get("/api/prompts/?search=email")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) == 1
        assert "Email" in response.data["data"][0]["title"]

    def test_create_prompt_requires_authentication(self, api_client):
        """Unauthenticated requests should be rejected."""
        data = {"title": "Test", "category": "other", "content": "Content"}
        response = api_client.post("/api/prompts/", data, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_prompt_success(self, authenticated_client, user):
        """Should create a new prompt."""
        data = {
            "title": "New Prompt",
            "description": "A test prompt",
            "category": "research",
            "content": "This is the prompt content",
            "variables_schema": {"user_input": {"type": "string"}},
        }

        response = authenticated_client.post("/api/prompts/", data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert "data" in response.data
        assert response.data["data"]["title"] == "New Prompt"
        assert response.data["data"]["visibility"] == "private"
        assert response.data["data"]["is_builtin"] is False

        # Verify it was created in database
        assert PromptTemplate.objects.filter(title="New Prompt", owner=user).exists()

    def test_create_prompt_required_fields(self, authenticated_client):
        """Should require title, category, and content."""
        response = authenticated_client.post(
            "/api/prompts/", {"description": "Missing fields"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "details" in response.data["error"]

    def test_create_prompt_invalid_category(self, authenticated_client):
        """Should reject invalid categories."""
        data = {"title": "Test", "category": "invalid_category", "content": "Content"}
        response = authenticated_client.post("/api/prompts/", data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

    def test_create_prompt_default_visibility_is_private(self, authenticated_client, user):
        """New prompts should be private by default."""
        data = {"title": "Test", "category": "other", "content": "Content"}
        response = authenticated_client.post("/api/prompts/", data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["visibility"] == "private"

        prompt = PromptTemplate.objects.get(title="Test")
        assert prompt.visibility == "private"


class TestPromptDetail:
    """Tests for GET/PATCH/DELETE /api/prompts/{id}/"""

    def test_get_prompt_requires_authentication(self, api_client, user):
        """Unauthenticated requests should be rejected."""
        prompt = PromptTemplate.objects.create(
            owner=user, title="Test", category="other", content="Content"
        )
        response = api_client.get(f"/api/prompts/{prompt.id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_prompt_returns_details(self, authenticated_client, user):
        """Should return prompt with all fields."""
        prompt = PromptTemplate.objects.create(
            owner=user,
            title="Test Prompt",
            description="Test description",
            category="research",
            content="Prompt content",
            variables_schema={"var": {"type": "string"}},
            version="1.0.0",
            license="MIT",
            visibility="private",
        )

        response = authenticated_client.get(f"/api/prompts/{prompt.id}")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["title"] == "Test Prompt"
        assert response.data["data"]["content"] == "Prompt content"
        assert response.data["data"]["variables_schema"] == {"var": {"type": "string"}}
        assert response.data["data"]["version"] == "1.0.0"

    def test_get_prompt_not_found(self, authenticated_client):
        """Should return 404 for non-existent prompt."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = authenticated_client.get(f"/api/prompts/{fake_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"]["code"] == "NOT_FOUND"

    def test_get_public_prompt_from_other_user(self, api_client, user):
        """Should allow accessing public prompts from other users."""
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        prompt = PromptTemplate.objects.create(
            owner=other_user,
            title="Public Prompt",
            category="other",
            content="Content",
            visibility="public",
        )

        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/prompts/{prompt.id}")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["title"] == "Public Prompt"

    def test_get_private_prompt_from_other_user_denied(self, api_client, user):
        """Should deny access to private prompts from other users."""
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        prompt = PromptTemplate.objects.create(
            owner=other_user,
            title="Private Prompt",
            category="other",
            content="Content",
            visibility="private",
        )

        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/prompts/{prompt.id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_prompt_success(self, authenticated_client, user):
        """Should update prompt fields."""
        prompt = PromptTemplate.objects.create(
            owner=user,
            title="Original",
            description="Original description",
            category="research",
            content="Original content",
        )

        data = {
            "title": "Updated",
            "description": "Updated description",
            "content": "Updated content",
        }
        response = authenticated_client.patch(f"/api/prompts/{prompt.id}", data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["title"] == "Updated"
        assert response.data["data"]["description"] == "Updated description"
        assert response.data["data"]["content"] == "Updated content"

        prompt.refresh_from_db()
        assert prompt.title == "Updated"

    def test_update_prompt_partial_update(self, authenticated_client, user):
        """Should allow partial updates."""
        prompt = PromptTemplate.objects.create(
            owner=user,
            title="Original",
            description="Original",
            category="research",
            content="Original",
        )

        response = authenticated_client.patch(
            f"/api/prompts/{prompt.id}", {"title": "Only Title Updated"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["title"] == "Only Title Updated"
        assert response.data["data"]["description"] == "Original"

    def test_update_prompt_only_owner_can_update(self, api_client, user):
        """Only the owner should be able to update a prompt."""
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        prompt = PromptTemplate.objects.create(
            owner=other_user,
            title="Other's Prompt",
            category="other",
            content="Content",
        )

        api_client.force_authenticate(user=user)
        response = api_client.patch(f"/api/prompts/{prompt.id}", {"title": "Hacked"}, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_prompt_success(self, authenticated_client, user):
        """Should delete prompt."""
        prompt = PromptTemplate.objects.create(
            owner=user, title="To Delete", category="other", content="Content"
        )

        response = authenticated_client.delete(f"/api/prompts/{prompt.id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not PromptTemplate.objects.filter(id=prompt.id).exists()

    def test_delete_prompt_only_owner_can_delete(self, api_client, user):
        """Only the owner should be able to delete a prompt."""
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        prompt = PromptTemplate.objects.create(
            owner=other_user, title="Other's Prompt", category="other", content="Content"
        )

        api_client.force_authenticate(user=user)
        response = api_client.delete(f"/api/prompts/{prompt.id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert PromptTemplate.objects.filter(id=prompt.id).exists()


class TestPromptClone:
    """Tests for POST /api/prompts/{id}/clone"""

    def test_clone_prompt_requires_authentication(self, api_client, user):
        """Unauthenticated requests should be rejected."""
        prompt = PromptTemplate.objects.create(
            owner=user, title="Test", category="other", content="Content"
        )
        response = api_client.post(f"/api/prompts/{prompt.id}/clone")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_clone_own_prompt(self, authenticated_client, user):
        """Should allow cloning own prompt."""
        original = PromptTemplate.objects.create(
            owner=user,
            title="Original Prompt",
            description="Original",
            category="research",
            content="Content",
            variables_schema={"var": "value"},
        )

        response = authenticated_client.post(f"/api/prompts/{original.id}/clone")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["title"] == "Original Prompt (Copy)"
        assert response.data["data"]["content"] == "Content"
        assert response.data["data"]["visibility"] == "private"
        assert str(response.data["data"]["owner_id"]) == str(user.id)

        # Verify clone was created
        assert PromptTemplate.objects.filter(owner=user).count() == 2

    def test_clone_public_prompt_from_other_user(self, api_client, user):
        """Should allow cloning public prompts from other users."""
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        original = PromptTemplate.objects.create(
            owner=other_user,
            title="Public Prompt",
            category="research",
            content="Content",
            visibility="public",
        )

        api_client.force_authenticate(user=user)
        response = api_client.post(f"/api/prompts/{original.id}/clone")

        assert response.status_code == status.HTTP_201_CREATED
        assert str(response.data["data"]["owner_id"]) == str(user.id)

    def test_clone_private_prompt_from_other_user_denied(self, api_client, user):
        """Should deny cloning private prompts from other users."""
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        original = PromptTemplate.objects.create(
            owner=other_user,
            title="Private Prompt",
            category="research",
            content="Content",
            visibility="private",
        )

        api_client.force_authenticate(user=user)
        response = api_client.post(f"/api/prompts/{original.id}/clone")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_clone_builtin_prompt(self, authenticated_client, user):
        """Should allow cloning built-in prompts."""
        builtin = PromptTemplate.objects.create(
            owner=None,
            title="Built-in Prompt",
            category="research",
            content="Content",
            visibility="public",
        )

        response = authenticated_client.post(f"/api/prompts/{builtin.id}/clone")

        assert response.status_code == status.HTTP_201_CREATED
        assert str(response.data["data"]["owner_id"]) == str(user.id)
        assert response.data["data"]["visibility"] == "private"


class TestPromptPublish:
    """Tests for POST /api/prompts/{id}/publish"""

    def test_publish_prompt_requires_authentication(self, api_client, user):
        """Unauthenticated requests should be rejected."""
        prompt = PromptTemplate.objects.create(
            owner=user, title="Test", category="other", content="Content"
        )
        response = api_client.post(f"/api/prompts/{prompt.id}/publish")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_publish_prompt_success(self, authenticated_client, user):
        """Should make prompt public."""
        prompt = PromptTemplate.objects.create(
            owner=user,
            title="To Publish",
            category="research",
            content="Content",
            visibility="private",
        )

        data = {"license": "Apache-2.0"}
        response = authenticated_client.post(
            f"/api/prompts/{prompt.id}/publish", data, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["visibility"] == "public"
        assert response.data["data"]["license"] == "Apache-2.0"

        prompt.refresh_from_db()
        assert prompt.visibility == "public"
        assert prompt.license == "Apache-2.0"

    def test_publish_prompt_default_license(self, authenticated_client, user):
        """Should use MIT license by default."""
        prompt = PromptTemplate.objects.create(
            owner=user, title="Test", category="other", content="Content"
        )

        response = authenticated_client.post(f"/api/prompts/{prompt.id}/publish", {}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["license"] == "MIT"

    def test_publish_prompt_only_owner_can_publish(self, api_client, user):
        """Only the owner should be able to publish a prompt."""
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        prompt = PromptTemplate.objects.create(
            owner=other_user, title="Other's Prompt", category="other", content="Content"
        )

        api_client.force_authenticate(user=user)
        response = api_client.post(f"/api/prompts/{prompt.id}/publish")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestPromptAPIResponseFormat:
    """Tests for standardized API response format."""

    def test_success_response_has_data_and_meta(self, authenticated_client, user):
        """All success responses should have data and meta fields."""
        PromptTemplate.objects.create(owner=user, title="Test", category="other", content="Content")

        response = authenticated_client.get("/api/prompts/")

        assert response.status_code == status.HTTP_200_OK
        assert "data" in response.data
        assert "meta" in response.data
        assert "requestId" in response.data["meta"]
        assert "timestamp" in response.data["meta"]

    def test_error_response_has_error_and_meta(self, authenticated_client):
        """All error responses should have error and meta fields."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = authenticated_client.get(f"/api/prompts/{fake_id}")

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
            "/api/prompts/", {"description": "Missing required fields"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "details" in response.data["error"]
        assert isinstance(response.data["error"]["details"], list)
