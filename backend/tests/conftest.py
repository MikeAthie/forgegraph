"""
Pytest configuration and fixtures.
"""

import pytest
from rest_framework.test import APIClient

from infrastructure.orm.models import User


@pytest.fixture
def api_client():
    """Return an API client."""
    return APIClient()


@pytest.fixture
def user(db):
    """Create and return a test user."""
    return User.objects.create_user(
        email="test@example.com",
        password="testpassword123",
    )


@pytest.fixture
def authenticated_client(api_client, user):
    """Return an authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client
