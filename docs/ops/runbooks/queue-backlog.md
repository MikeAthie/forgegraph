# Queue Backlog

1. Check `/api/metrics/summary` for `queue.backlog`, `queue.oldest_pending_age_seconds`, and `queue.stalled_runs`.
2. Confirm at least one `process_run_queue` worker is running and emitting the run queue worker heartbeat.
3. Inspect engine readiness and backend stale-run reconciliation.
4. Confirm workers are not crash-looping and callbacks are being accepted.
5. If `RUN_QUEUE_ENABLED=true` and starts return `queue_warning=run_queue_worker_unavailable`, start or roll back the queue worker before accepting more traffic.
6. If backlog follows a release, halt rollout and consider rollback.
