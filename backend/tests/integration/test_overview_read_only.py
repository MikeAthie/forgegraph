from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory, force_authenticate

from adapters.api.system_state.views import SystemStateOverviewView

pytestmark = pytest.mark.django_db


def test_overview_get_does_not_write(user) -> None:
    factory = APIRequestFactory()
    request = factory.get("/api/system-state/overview/")
    force_authenticate(request, user=user)
    view = SystemStateOverviewView.as_view()

    with CaptureQueriesContext(connection) as queries:
        response = view(request)

    assert response.status_code == 200
    write_queries = [
        query["sql"]
        for query in queries
        if query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]
    assert write_queries == []


def test_overview_exposes_company_os_sections_from_backend_state(user) -> None:
    factory = APIRequestFactory()
    request = factory.get("/api/system-state/overview/")
    force_authenticate(request, user=user)
    response = SystemStateOverviewView.as_view()(request)

    assert response.status_code == 200
    overview = response.data["data"]
    for section_name in [
        "running",
        "blocked",
        "decisions",
        "costs",
        "failures",
        "memory",
        "projection",
    ]:
        section = overview[section_name]
        assert section["source"].startswith("backend_")
        assert section["computed_at"]
        assert section["last_updated_at"]
        assert isinstance(section["freshness_ms"], int)
        assert section["status"] in {"fresh", "stale", "rebuilding", "degraded"}
        assert isinstance(section["stale"], bool)
        assert isinstance(section["degraded"], bool)

    assert "runtime_intent_lag_seconds" in overview["failures"]
    assert "lag_seconds" in overview["projection"]
    assert "summary" in overview
    assert "active_agents" in overview
    assert "active_tasks" in overview
    assert "pending_decisions" in overview
    assert "accounting" in overview
    assert "operations" in overview
