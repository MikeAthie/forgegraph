from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from django.utils import timezone
from rest_framework.test import APIClient

from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import MemoryObservation, User


def _create_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "fact",
        "title": "Preferred Contact",
        "content": "Customer prefers email follow-up.",
        "scope": "graph",
        "graph_id": str(uuid4()),
        "session_id": str(uuid4()),
    }
    payload.update(overrides)
    return payload


def test_create_and_get_memory_observation(authenticated_client: APIClient, user: User):
    response = authenticated_client.post(
        "/api/memory/observations",
        data=_create_payload(),
        format="json",
    )

    assert response.status_code == 201
    created = response.json()["data"]
    assert created["type"] == "fact"
    assert created["scope"] == "graph"
    assert created["tenant_id"] == str(user.default_organization_id)

    detail_response = authenticated_client.get(f"/api/memory/observations/{created['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["id"] == created["id"]
    assert detail_response.json()["data"]["content"] == "Customer prefers email follow-up."


def test_search_timeline_and_context_return_matching_observations(
    authenticated_client: APIClient,
    user: User,
):
    first = MemoryObservation.objects.create(
        tenant_id=user.default_organization_id,
        graph_id=uuid4(),
        session_id=uuid4(),
        type="fact",
        title="Support Preference",
        content="Customer likes concise summaries.",
        scope="graph",
        topic_key="support-preference",
        tool_name="crm_lookup",
        last_seen_at=timezone.now() - timedelta(minutes=5),
    )
    second = MemoryObservation.objects.create(
        tenant_id=user.default_organization_id,
        graph_id=uuid4(),
        session_id=uuid4(),
        type="fact",
        title="Billing Preference",
        content="Customer wants invoices as PDFs.",
        scope="graph",
        topic_key="billing-preference",
        tool_name="billing_lookup",
        last_seen_at=timezone.now(),
    )

    search_response = authenticated_client.get(
        "/api/memory/observations/search",
        data={"query": "invoice", "limit": "5"},
    )
    assert search_response.status_code == 200
    search_results = search_response.json()["data"]
    assert [item["id"] for item in search_results] == [str(second.id)]

    timeline_response = authenticated_client.get(
        "/api/memory/observations/timeline",
        data={"scope": "graph", "limit": "5"},
    )
    assert timeline_response.status_code == 200
    timeline_results = timeline_response.json()["data"]
    assert [item["id"] for item in timeline_results[:2]] == [str(second.id), str(first.id)]

    context_response = authenticated_client.get(
        "/api/memory/observations/context",
        data={"query": "summary", "limit": "3"},
    )
    assert context_response.status_code == 200
    context_data = context_response.json()["data"]
    assert context_data["degraded"] is True
    assert context_data["strategies"] == ["fts", "timeline"]
    assert [item["id"] for item in context_data["observations"]] == [str(first.id)]


def test_update_and_delete_memory_observation(authenticated_client: APIClient, user: User):
    observation = MemoryObservation.objects.create(
        tenant_id=user.default_organization_id,
        graph_id=uuid4(),
        session_id=uuid4(),
        type="fact",
        title="Original Title",
        content="Original content.",
        scope="graph",
        topic_key="original-title",
    )

    update_response = authenticated_client.patch(
        f"/api/memory/observations/{observation.id}",
        data={"title": "Updated Title", "content": "Updated content."},
        format="json",
    )
    assert update_response.status_code == 200
    updated = update_response.json()["data"]
    assert updated["title"] == "Updated Title"
    assert updated["content"] == "Updated content."
    assert updated["revision_count"] == 2

    delete_response = authenticated_client.delete(f"/api/memory/observations/{observation.id}")
    assert delete_response.status_code == 204

    missing_detail = authenticated_client.get(f"/api/memory/observations/{observation.id}")
    assert missing_detail.status_code == 404

    deleted_detail = authenticated_client.get(
        f"/api/memory/observations/{observation.id}",
        data={"include_deleted": "true"},
    )
    assert deleted_detail.status_code == 200
    assert deleted_detail.json()["data"]["is_deleted"] is True


def test_memory_observation_endpoints_are_tenant_scoped(api_client: APIClient, user: User):
    other_user = User.objects.create_user(
        email="other@example.com",
        password="testpassword123",
    )
    ensure_default_organization(other_user)

    observation = MemoryObservation.objects.create(
        tenant_id=other_user.default_organization_id,
        graph_id=uuid4(),
        session_id=uuid4(),
        type="fact",
        title="Other Tenant",
        content="Should not be visible.",
        scope="graph",
        topic_key="other-tenant",
    )

    api_client.force_authenticate(user=user)

    detail_response = api_client.get(f"/api/memory/observations/{observation.id}")
    assert detail_response.status_code == 404

    search_response = api_client.get("/api/memory/observations/search", data={"query": "visible"})
    assert search_response.status_code == 200
    assert search_response.json()["data"] == []


def test_memory_observation_permissions_match_role_contract(api_client: APIClient, user: User):
    viewer = User.objects.create_user(email="viewer@example.com", password="testpassword123")
    organization = user.default_organization
    assert organization is not None
    viewer.default_organization = organization
    viewer.save(update_fields=["default_organization"])
    viewer.organization_memberships.create(
        organization=organization,
        role="viewer",
        is_default=True,
    )

    observation = MemoryObservation.objects.create(
        tenant_id=organization.id,
        graph_id=uuid4(),
        session_id=uuid4(),
        type="fact",
        title="Tenant Note",
        content="Visible to authenticated tenant users.",
        scope="graph",
        topic_key="tenant-note",
    )

    api_client.force_authenticate(user=viewer)

    detail_response = api_client.get(f"/api/memory/observations/{observation.id}")
    assert detail_response.status_code == 200

    delete_response = api_client.delete(f"/api/memory/observations/{observation.id}")
    assert delete_response.status_code == 403
