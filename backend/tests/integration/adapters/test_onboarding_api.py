"""
Integration tests for onboarding APIs.
"""

import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestOnboardingMilestones:
    def test_list_milestones(self, authenticated_client):
        response = authenticated_client.get("/api/onboarding/milestones")
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert len(data) >= 3
        keys = {item["key"] for item in data}
        assert "select_template" in keys
        assert "attach_credential" in keys
        assert "run_template" in keys
        assert "company_first_run_explained" in keys

    def test_complete_milestone(self, authenticated_client):
        response = authenticated_client.post(
            "/api/onboarding/milestones",
            {"milestone": "select_template", "metadata": {"template_id": "abc"}},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["milestone"] == "select_template"

        follow_up = authenticated_client.get("/api/onboarding/milestones")
        assert follow_up.status_code == status.HTTP_200_OK
        completed = {item["key"]: item["completed"] for item in follow_up.data["data"]}
        assert completed["select_template"] is True
