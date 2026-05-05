from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from application.workers.process_os_projection_events import process_pending_projection_events
from infrastructure.orm.models import (
    CostAggregate,
    CostLedgerEntry,
    Graph,
    GraphVersion,
    LLMUsage,
    Run,
)

pytestmark = pytest.mark.django_db


def test_accounting_projection_does_not_double_count_usage(user) -> None:
    organization = user.default_organization
    assert organization is not None
    graph = Graph.objects.create(
        owner=user, organization=organization, name="Accounting Projection"
    )
    version = GraphVersion.objects.create(
        graph=graph, version=1, graph_json={"nodes": [], "edges": []}
    )
    run = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=version,
        status="succeeded",
        started_at=timezone.now(),
        ended_at=timezone.now(),
    )
    LLMUsage.objects.create(
        tenant_id=organization.id,
        run=run,
        node_id="prompt_1",
        provider="openai",
        model="gpt-4.1-mini",
        prompt_tokens=240,
        completion_tokens=60,
        total_tokens=300,
        cost_usd=Decimal("1.500000"),
    )

    process_pending_projection_events(organization_id=organization.id)
    process_pending_projection_events(organization_id=organization.id)

    assert CostLedgerEntry.objects.filter(organization=organization).count() == 1
    assert CostAggregate.objects.filter(organization=organization).count() == 2
    assert CostLedgerEntry.objects.get(organization=organization).total_cost_usd == Decimal(
        "1.500000"
    )
    assert list(
        CostAggregate.objects.filter(organization=organization).values_list(
            "total_cost_usd",
            flat=True,
        )
    ) == [Decimal("1.500000"), Decimal("1.500000")]
