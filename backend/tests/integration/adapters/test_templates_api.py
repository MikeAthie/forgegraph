from uuid import uuid4

from rest_framework import status
from rest_framework.test import APIClient

from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    AuditLog,
    GraphTemplate,
    GraphVersion,
    Run,
    TemplateUsage,
    User,
)


def _create_template(owner: User) -> GraphTemplate:
    return GraphTemplate.objects.create(
        group_id=uuid4(),
        name="Support Assistant",
        description="Template for support triage.",
        category="support",
        tags=["support", "triage"],
        graph_json={"nodes": [], "edges": []},
        sample_input={"ticket": "ABC-123"},
        guide_steps=["Connect credentials", "Run template"],
        version=1,
        changelog="Initial",
        is_latest=True,
        visibility="organization",
        owner_organization=owner.default_organization,
    )


def test_template_versioning_and_tag_discovery(authenticated_client, user):
    template = _create_template(user)

    version_response = authenticated_client.post(
        f"/api/templates/{template.id}/versions",
        {
            "name": "Support Assistant v2",
            "tags": ["support", "triage", "ai"],
            "changelog": "Improved routing prompts.",
        },
        format="json",
    )
    assert version_response.status_code == status.HTTP_201_CREATED
    assert version_response.data["data"]["version"] == 2
    assert "ai" in version_response.data["data"]["tags"]

    list_response = authenticated_client.get("/api/templates/")
    assert list_response.status_code == status.HTTP_200_OK
    assert any("ai" in item["tags"] for item in list_response.data["data"])


def test_template_sharing_is_read_only_for_recipient(authenticated_client, user):
    template = _create_template(user)

    recipient = User.objects.create_user(email="recipient@example.com", password="testpassword123")
    ensure_default_organization(recipient)

    share_response = authenticated_client.post(
        f"/api/templates/{template.id}/shares",
        {"organization_id": str(recipient.default_organization_id)},
        format="json",
    )
    assert share_response.status_code == status.HTTP_200_OK
    assert AuditLog.objects.filter(
        action="template.shared",
        resource_type="graph_template",
        resource_id=str(template.id),
    ).exists()

    recipient_client = APIClient()
    recipient_client.force_authenticate(user=recipient)

    list_response = recipient_client.get("/api/templates/")
    assert list_response.status_code == status.HTTP_200_OK
    assert any(item["id"] == str(template.id) for item in list_response.data["data"])

    mutate_response = recipient_client.post(
        f"/api/templates/{template.id}/versions",
        {"name": "Recipient Mutates Template"},
        format="json",
    )
    assert mutate_response.status_code == status.HTTP_404_NOT_FOUND


def test_template_usage_and_rating_analytics(authenticated_client, user):
    template = _create_template(user)

    clone_response = authenticated_client.post(
        f"/api/templates/{template.id}/clone",
        {"name": "Cloned Support Assistant"},
        format="json",
    )
    assert clone_response.status_code == status.HTTP_201_CREATED
    assert TemplateUsage.objects.filter(template=template, user=user).exists()

    rating_response = authenticated_client.post(
        f"/api/templates/{template.id}/ratings",
        {"rating": 5, "comment": "Great starter flow"},
        format="json",
    )
    assert rating_response.status_code == status.HTTP_200_OK

    cloned_graph_version_id = clone_response.data["data"]["graph_version_id"]
    cloned_version = GraphVersion.objects.get(id=cloned_graph_version_id)
    Run.objects.create(
        owner=user,
        graph_version=cloned_version,
        status="succeeded",
    )

    list_response = authenticated_client.get("/api/templates/")
    assert list_response.status_code == status.HTTP_200_OK

    item = next(item for item in list_response.data["data"] if item["id"] == str(template.id))
    assert item["usage_count"] >= 1
    assert item["rating_count"] >= 1
    assert item["rating_average"] >= 1
    assert item["run_success_rate"] == 1.0
