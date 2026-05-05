from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory, force_authenticate

from adapters.api.system_state.views import SystemStateOverviewView

pytestmark = pytest.mark.django_db


def test_overview_is_read_only(user) -> None:
    request = APIRequestFactory().get("/api/system-state/overview/")
    force_authenticate(request, user=user)

    with CaptureQueriesContext(connection) as queries:
        response = SystemStateOverviewView.as_view()(request)

    assert response.status_code == 200
    assert [
        query["sql"]
        for query in queries
        if query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ] == []
