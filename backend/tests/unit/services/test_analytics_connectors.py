from __future__ import annotations

import pytest


def test_analytics_connector_contract_is_pending_until_generic_connector_exists() -> None:
    pytest.skip(
        "Generic analytics/performance connector is not implemented. Enable metric-source safety contract tests when it exists."
    )
