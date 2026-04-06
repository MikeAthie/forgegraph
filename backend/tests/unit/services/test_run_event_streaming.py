from __future__ import annotations

from uuid import uuid4

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from application.services.run_event_streaming import (
    EVENT_LEVEL_IMPORTANT,
    EVENT_LEVEL_VERBOSE,
    STREAM_SUMMARY_EVENT_TYPE,
    add_event_level,
    flush_stream_summary,
    message_allowed_for_level,
    update_stream_summary,
)

pytestmark = pytest.mark.django_db

LOC_MEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "run-event-streaming-tests",
    }
}


@override_settings(CACHES=LOC_MEM_CACHE)
def test_message_allowed_for_level_filters_verbose_messages_by_default() -> None:
    verbose_message = add_event_level(
        {
            "type": "node_stream.chunk",
            "run_id": str(uuid4()),
            "node_stream": {"chunk": "hello"},
        }
    )
    important_message = add_event_level(
        {
            "type": STREAM_SUMMARY_EVENT_TYPE,
            "run_id": str(uuid4()),
            "node_stream": {"chunk_count": 5},
        },
        level=EVENT_LEVEL_IMPORTANT,
    )

    assert verbose_message["level"] == EVENT_LEVEL_VERBOSE
    assert message_allowed_for_level(verbose_message, "important") is False
    assert message_allowed_for_level(verbose_message, "verbose") is True
    assert message_allowed_for_level(important_message, "important") is True


@override_settings(
    CACHES=LOC_MEM_CACHE,
    RUN_EVENT_STREAM_SUMMARY_MIN_CHUNKS=3,
    RUN_EVENT_STREAM_SUMMARY_INTERVAL_MS=60000,
    RUN_EVENT_STREAM_SUMMARY_PREVIEW_CHARS=32,
)
def test_stream_summary_batches_chunks_and_flushes_final_payload() -> None:
    cache.clear()
    run_id = str(uuid4())
    base_payload = {
        "node_id": "agent_1",
        "node_type": "agent",
        "attempt": 1,
    }

    assert (
        update_stream_summary(
            run_id=run_id,
            payload={**base_payload, "chunk": "Hel", "chunk_index": 1},
            event_time=timezone.now(),
        )
        is None
    )
    assert (
        update_stream_summary(
            run_id=run_id,
            payload={**base_payload, "chunk": "lo ", "chunk_index": 2},
            event_time=timezone.now(),
        )
        is None
    )

    summary = update_stream_summary(
        run_id=run_id,
        payload={**base_payload, "chunk": "world", "chunk_index": 3},
        event_time=timezone.now(),
    )

    assert summary is not None
    assert summary["chunk_count"] == 3
    assert summary["new_chunks"] == 3
    assert summary["text_preview"] == "Hello world"
    assert summary["final"] is False

    assert (
        update_stream_summary(
            run_id=run_id,
            payload={**base_payload, "chunk": "!", "chunk_index": 4},
            event_time=timezone.now(),
        )
        is None
    )

    final_summary = flush_stream_summary(
        run_id=run_id,
        node_id="agent_1",
        attempt=1,
        final_reason="node_completed",
    )

    assert final_summary is not None
    assert final_summary["chunk_count"] == 4
    assert final_summary["new_chunks"] == 1
    assert final_summary["final"] is True
    assert final_summary["final_reason"] == "node_completed"
