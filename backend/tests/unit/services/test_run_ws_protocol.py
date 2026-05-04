from __future__ import annotations

from application.services.run_ws_protocol import (
    build_ws_public_message,
    normalize_ws_public_message,
)


def test_public_ws_message_preserves_state_feed_fields() -> None:
    message = build_ws_public_message(
        "run_completed",
        run_id="run-1",
        trace_id="trace-1",
        event_id="evt-1",
        tenant_id="tenant-1",
        state_version=12,
        requires_refetch=True,
        payload={"status": "succeeded"},
        timestamp="2026-05-03T00:00:00+00:00",
    )

    normalized = normalize_ws_public_message(message)

    assert normalized is not None
    assert normalized["type"] == "run_completed"
    assert normalized["tenant_id"] == "tenant-1"
    assert normalized["state_version"] == 12
    assert normalized["requires_refetch"] is True


def test_legacy_node_stream_chunk_normalizes_to_public_replay_message() -> None:
    normalized = normalize_ws_public_message(
        {
            "type": "node_stream.chunk",
            "run_id": "run-1",
            "event_id": "evt-stream-1",
            "state_version": 3,
            "tenant_id": "tenant-1",
            "level": "verbose",
            "node_stream": {
                "node_id": "prompt_1",
                "chunk": "hello",
                "chunk_index": 1,
            },
        }
    )

    assert normalized is not None
    assert normalized["type"] == "node_stream_chunk"
    assert normalized["event_id"] == "evt-stream-1"
    assert normalized["state_version"] == 3
    assert normalized["tenant_id"] == "tenant-1"
    assert normalized["level"] == "verbose"
    assert normalized["payload"]["chunk"] == "hello"
