# WebSocket Replay Failure

Inspect `StateFeedEvent` retention, subscriber cursors, replay-window misses,
tenant visibility checks, and full-resync responses. If replay cannot be proven
tenant-safe, force `full_resync_required` and verify the client refetches
backend-owned state.
