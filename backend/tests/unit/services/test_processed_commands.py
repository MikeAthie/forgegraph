from __future__ import annotations

from types import SimpleNamespace

import pytest
from rest_framework.response import Response

from application.services.processed_commands import (
    IdempotencyConflict,
    build_idempotency_context,
    record_processed_command,
    replay_processed_command,
)
from infrastructure.orm.models import Organization, ProcessedCommand


@pytest.mark.django_db
def test_processed_command_replays_already_applied_response() -> None:
    organization = Organization.objects.create(name="Idempotency Org")
    request = SimpleNamespace(headers={"Idempotency-Key": "cancel-run-1"})
    context = build_idempotency_context(
        request=request,
        organization=organization,
        action="runs.cancel:run-1",
        request_payload={"reason": "operator retry"},
    )
    response = Response(
        {
            "data": {"id": "run-1", "status": "canceled"},
            "meta": {"requestId": "original", "timestamp": "2026-05-03T00:00:00Z"},
        },
        status=200,
    )

    record_processed_command(
        context=context,
        response=response,
        resource_type="run",
        resource_id="run-1",
    )

    replayed = replay_processed_command(context)

    assert replayed is not None
    assert replayed.status_code == 200
    assert replayed.data["data"]["status"] == "canceled"
    assert replayed.data["data"]["already_applied"] is True
    assert replayed.data["meta"]["already_applied"] is True
    assert ProcessedCommand.objects.count() == 1


@pytest.mark.django_db
def test_processed_command_rejects_key_reuse_with_different_body() -> None:
    organization = Organization.objects.create(name="Idempotency Conflict Org")
    request = SimpleNamespace(headers={"Idempotency-Key": "resume-1"})
    original = build_idempotency_context(
        request=request,
        organization=organization,
        action="runs.resume:run-1",
        request_payload={"approved": True},
    )
    record_processed_command(
        context=original,
        response=Response({"data": {"resumed": True}, "meta": {}}, status=200),
        resource_type="run",
        resource_id="run-1",
    )
    conflicting = build_idempotency_context(
        request=request,
        organization=organization,
        action="runs.resume:run-1",
        request_payload={"approved": False},
    )

    with pytest.raises(IdempotencyConflict):
        replay_processed_command(conflicting)
