# Idempotency Matrix

`docs/architecture/runtime-invariants.md` is the controlling runtime contract.
Idempotency records are backend-owned durability records; they do not make
events, Redis, Kafka, the engine, or the frontend authoritative for durable
state.

This matrix is a release checklist for crash-after-apply-before-ack behavior:
after a durable backend mutation succeeds, a retry caused by a lost response,
commit failure, redelivery, or worker crash must not apply the mutation again.

| Boundary | Idempotency key | Duplicate behavior | Required evidence |
| --- | --- | --- | --- |
| Engine callback event | `event_id` / `idempotency_key` | Return duplicate/accepted and do not duplicate run events, node state, task lifecycle, memory, or usage | `backend/tests/reliability/test_callback_crash_after_apply.py` |
| Runtime intent | `intent_id` | Redis redelivery records one `ProcessedRuntimeIntent` and does not repeat checkpoint/state transitions | `backend/tests/integration/adapters/test_runtime_control_plane_invariants.py`, `backend/tests/e2e/test_redis_runtime_transport_failures.py` |
| Human decision submit | `decision_id + submit_id` | Same payload returns already applied and does not call the engine twice; conflicting payload returns 409 | `backend/tests/reliability/test_decision_submit_idempotency.py` |
| Projection event | `event_id + projection_name` | Cursor rewind/replay records one processed projection event and causes no read model drift | `backend/tests/reliability/test_projection_crash_after_apply.py` |
| Memory write | `memory_event_id` | No duplicate fact or summary; retries return the same backend memory observations | `backend/tests/reliability/test_memory_no_duplicate_fact.py`, `backend/tests/reliability/test_memory_write_idempotency.py` |
| Accounting write | `usage/cost_event_id` | No double-counted usage or cost ledger entry | `backend/tests/reliability/test_accounting_no_double_count.py` |
| Frontend command retry | `command_id` / `Idempotency-Key` | No duplicate backend mutation; replay returns additive idempotency metadata | `frontend/__tests__/e2e/command-retry-idempotency.spec.ts` |
| Board/routing mutation | `Idempotency-Key` scoped by whiteboard/action | Same payload returns existing board state with idempotency metadata; conflicting payload returns 409; no duplicate `TaskRoutingRecord` or board event | `backend/tests/unit/services/test_whiteboard_board.py`, `backend/tests/unit/api/test_whiteboard_board_api.py` |
| Kafka consumer receipt | `event_id` / `idempotency_key` scoped by consumer group | Redelivery after receipt/commit loss reuses the receipt or reports duplicate; event payload alone does not mutate authoritative state | `backend/tests/unit/services/test_communication_kafka_consumer.py`, `backend/tests/unit/services/test_whiteboard_board_kafka.py` |
| Connector/tool execution | Stable backend `ToolExecution.idempotency_key` | Succeeded/failed executions reuse the stored sanitized receipt; ambiguous unsafe side effects block automatic redispatch | `backend/tests/unit/services/test_pack_tool_executions_connectors.py`, `backend/tests/unit/services/test_tool_executions.py` |

## Response Contract

Retryable backend mutations preserve the existing success/error envelope and add:

```json
{
  "meta": {
    "idempotency": {
      "status": "applied|already_applied|rejected|retry_required",
      "idempotency_key": "...",
      "resource_type": "...",
      "resource_id": "..."
    }
  }
}
```

When the response `data` is an object, the same metadata is also available as `data.idempotency`. Existing `duplicate` and `already_applied` flags remain compatibility aliases.
