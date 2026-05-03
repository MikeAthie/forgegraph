from django.core.cache import cache
from django.test import override_settings

from application.services.websocket_subscribers import (
    WS_SUBSCRIBERS_CACHE_KEY,
    can_accept_run_websocket_subscriber,
    get_websocket_subscriber_snapshot,
    register_run_websocket_subscriber,
    unregister_run_websocket_subscriber,
    update_run_websocket_subscriber_activity,
)

LOC_MEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "ws-subscriber-service-tests",
    }
}


@override_settings(
    CACHES=LOC_MEM_CACHE,
    RUN_WS_MAX_CONNECTIONS_PER_ORG=2,
    RUN_WS_MAX_CONNECTIONS_PER_USER=1,
)
def test_websocket_subscriber_limits_are_visible_and_enforced() -> None:
    cache.delete(WS_SUBSCRIBERS_CACHE_KEY)

    accepted, details = can_accept_run_websocket_subscriber(
        organization_id="org-a",
        user_id="user-a",
    )
    assert accepted is True
    assert details["limits"] == {"per_org": 2, "per_user": 1}

    register_run_websocket_subscriber(
        connection_id="conn-a",
        run_id="run-a",
        organization_id="org-a",
        user_id="user-a",
        event_level="default",
        event_types=["run_completed", "decision_required"],
        last_seen_event_id="evt-1",
    )

    accepted, details = can_accept_run_websocket_subscriber(
        organization_id="org-a",
        user_id="user-a",
    )
    assert accepted is False
    assert details["code"] == "user_connection_limit"

    register_run_websocket_subscriber(
        connection_id="conn-b",
        run_id="run-b",
        organization_id="org-a",
        user_id="user-b",
        event_level="minimal",
    )

    accepted, details = can_accept_run_websocket_subscriber(
        organization_id="org-a",
        user_id="user-c",
    )
    assert accepted is False
    assert details["code"] == "org_connection_limit"

    accepted, details = can_accept_run_websocket_subscriber(
        organization_id="org-b",
        user_id="user-c",
    )
    assert accepted is True
    assert details["counts"] == {"organization": 0, "user": 0}


@override_settings(CACHES=LOC_MEM_CACHE)
def test_websocket_subscriber_snapshot_tracks_fanout_and_slow_clients() -> None:
    cache.delete(WS_SUBSCRIBERS_CACHE_KEY)
    register_run_websocket_subscriber(
        connection_id="conn-a",
        run_id="run-a",
        organization_id="org-a",
        user_id="user-a",
        event_level="default",
    )

    update_run_websocket_subscriber_activity(
        connection_id="conn-a",
        event_id="evt-2",
        event_type="run_completed",
        sent=True,
    )
    update_run_websocket_subscriber_activity(
        connection_id="conn-a",
        event_type="node_stream_chunk",
        filtered=True,
    )
    update_run_websocket_subscriber_activity(
        connection_id="conn-a",
        event_type="run_updated",
        dropped=True,
        slow_disconnect=True,
        slow_disconnect_reason="send_timeout",
    )

    snapshot = get_websocket_subscriber_snapshot()
    assert snapshot["active_connections"] == 1
    assert snapshot["fanout"] == {
        "messages_sent": 1,
        "messages_dropped": 1,
        "messages_filtered": 1,
        "slow_disconnects": 1,
    }
    assert snapshot["by_org"][0]["messages_sent"] == 1
    assert snapshot["by_org"][0]["messages_dropped"] == 1
    assert snapshot["by_org"][0]["messages_filtered"] == 1
    assert snapshot["by_org"][0]["slow_disconnects"] == 1
    assert snapshot["connections"][0]["last_seen_event_id"] == "evt-2"

    unregister_run_websocket_subscriber(connection_id="conn-a")
    assert get_websocket_subscriber_snapshot()["active_connections"] == 0
