from __future__ import annotations

import pytest


def test_landing_connector_contract_is_pending_until_generic_connector_exists() -> None:
    pytest.skip(
        "Generic landing/CMS connector is not implemented. Enable draft/publish safety contract tests when it exists."
    )
