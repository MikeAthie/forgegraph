from __future__ import annotations

import pytest

from application.services.os_projections import sync_task_records_for_organization

pytestmark = pytest.mark.django_db


def test_legacy_projection_sweep_is_disabled_by_default(user) -> None:
    organization = user.default_organization
    assert organization is not None

    with pytest.raises(RuntimeError, match="Legacy OS projection sweep disabled"):
        sync_task_records_for_organization(organization)
