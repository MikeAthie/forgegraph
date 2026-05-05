# Idempotency Matrix

`docs/architecture/runtime-invariants.md` is the controlling runtime contract. Idempotency records are backend-owned durability records; they do not make events, the engine, or the frontend authoritative for durable state.

| Boundary | Idempotency key | Duplicate behavior | Crash-after-apply test |
| --- | --- | --- | --- |
| Engine callback event | `event_id` / `idempotency_key` | Return duplicate accepted and do not apply the callback twice | Required: `backend/tests/reliability/test_callback_crash_after_apply.py` |
| Runtime intent | `intent_id` | No duplicate state transition | Required: `backend/tests/e2e/test_redis_runtime_transport_failures.py` |
| Human decision submit | `decision_id + submit_id` | Return already applied for the same payload; reject conflicting duplicate payloads | Required: `backend/tests/reliability/test_decision_submit_idempotency.py` |
| Projection event | `event_id + projection_name` | No read model drift | Required: `backend/tests/reliability/test_projection_crash_after_apply.py` |
| Memory write | `memory_event_id` | No duplicate fact or summary; duplicate retries return the same backend memory observations | Required: `backend/tests/reliability/test_memory_no_duplicate_fact.py` |
| Accounting write | `usage/cost_event_id` | No double-counted usage or cost ledger entry | Required: `backend/tests/reliability/test_accounting_no_double_count.py` |
| Frontend command retry | `command_id` / `Idempotency-Key` | No duplicate backend mutation; replay returns additive idempotency metadata | Required: `frontend/__tests__/e2e/command-retry-idempotency.spec.ts` |

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
