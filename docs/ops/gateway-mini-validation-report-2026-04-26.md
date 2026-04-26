# ForgeGraph LLM Gateway Mini Validation

Date: 2026-04-26
Harness: [scripts/stress_runner.py](../../scripts/stress_runner.py)
Artifacts: [logs/stress/gateway-mini-20260426-rerun](../../logs/stress/gateway-mini-20260426-rerun)

## Scope

This mini rerun validated the gateway-enabled path against:

- `endpoint-saturation`
- `engine-concurrency`
- `llm-degradation-timeout`
- `llm-degradation-unavailable`

Each scenario used graph version `f2cde181-3f99-4ea4-a89f-2c096a134533`, concurrency levels `5, 10, 20`, and `10` runs per level.

Before the measured sweep, `engine` and `backend-runtime-intents` were stopped, Redis runtime intent streams were cleared, and both services were recreated so the Redis consumer group and LLM counters started cleanly. An auth preflight run was excluded from these results.

## Result

The gateway preserved the previous safety properties in this mini sweep:

- Total runs: `120`
- Successful runs: `60`
- Failed runs: `60`
- Duplicate node executions: `0`
- Data integrity: `safe` for all scenarios
- Final active runs: `0`
- Final queue pending/processing: `0`
- Final Redis dead letters: `0`
- Final Redis consumer lag: `0`

The 60 failures were expected because the fallback provider is currently configured as `ENGINE_LLM_FALLBACK_MODE=error`; degraded LLM scenarios fail terminally and visibly instead of hanging or corrupting state.

## Scenario Summary

| Scenario | Success / Total | Breakpoint | Avg latency | P95 latency | Max latency | Retries | Integrity |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| endpoint-saturation | 30 / 30 | not observed through 20 | 7054.93 ms | 11580.45 ms | 13057 ms | 2 | safe |
| engine-concurrency | 30 / 30 | not observed through 20 | 7337.10 ms | 12128.60 ms | 12883 ms | 1 | safe |
| llm-degradation-timeout | 0 / 30 | concurrency 5 | 9919.60 ms | 21138.10 ms | 23012 ms | 60 | safe |
| llm-degradation-unavailable | 0 / 30 | concurrency 5 | 3107.10 ms | 3148.85 ms | 3158 ms | 60 | safe |

## Latency Curve

| Scenario | Concurrency | Success | Failed | Avg latency | Max latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| endpoint-saturation | 5 | 10 | 0 | 3722.40 ms | 6180 ms |
| endpoint-saturation | 10 | 10 | 0 | 8881.30 ms | 12021 ms |
| endpoint-saturation | 20 | 10 | 0 | 8561.10 ms | 13057 ms |
| engine-concurrency | 5 | 10 | 0 | 4149.00 ms | 5239 ms |
| engine-concurrency | 10 | 10 | 0 | 7619.80 ms | 10218 ms |
| engine-concurrency | 20 | 10 | 0 | 10242.50 ms | 12883 ms |
| llm-degradation-timeout | 5 | 0 | 10 | 16529.50 ms | 23012 ms |
| llm-degradation-timeout | 10 | 0 | 10 | 3131.00 ms | 3143 ms |
| llm-degradation-timeout | 20 | 0 | 10 | 10098.30 ms | 13097 ms |
| llm-degradation-unavailable | 5 | 0 | 10 | 3063.50 ms | 3085 ms |
| llm-degradation-unavailable | 10 | 0 | 10 | 3130.70 ms | 3158 ms |
| llm-degradation-unavailable | 20 | 0 | 10 | 3127.10 ms | 3145 ms |

## Gateway Metrics

Metric samples were captured from `GET /metrics/llm` during each scenario.

| Scenario | LLM requests | LLM failures | Max queue depth | Fallback attempts | Circuit behavior |
| --- | ---: | ---: | ---: | ---: | --- |
| endpoint-saturation | +62 | +2 | 6 | 0 | stayed closed |
| engine-concurrency | +61 | +1 | 6 | +1 | stayed closed |
| llm-degradation-timeout | 90 | 90 | 6 | 32 | opened, cooled down, reopened, reset closed |
| llm-degradation-unavailable | 90 | 90 | 0 | 20 | opened, reset closed |

Timeout circuit transitions:

```json
[
  {"circuit_open": false, "llm_requests": 123, "llm_failures": 3, "fallback_count": 1},
  {"circuit_open": true, "llm_requests": 20, "llm_failures": 20, "fallback_count": 20},
  {"circuit_open": false, "llm_requests": 80, "llm_failures": 80, "fallback_count": 24},
  {"circuit_open": true, "llm_requests": 86, "llm_failures": 86, "fallback_count": 28},
  {"circuit_open": false, "llm_requests": 0, "llm_failures": 0, "fallback_count": 0}
]
```

The final zeroed sample is the stress runner recreating the engine with chaos disabled after the degraded scenario.

## Metadata Check

Normal prompt execution includes gateway metadata:

```json
{
  "node_id": "prompt_1",
  "provider": "local",
  "fallback_used": false,
  "error_type": "",
  "latency_ms": 724
}
```

Timeout failure metadata includes normalized primary and fallback details:

```json
{
  "node_id": "prompt_1",
  "retry_code": "llm_gateway_fallback_unavailable",
  "provider": "fallback",
  "fallback_used": true,
  "error_type": "unavailable",
  "primary_provider": "local",
  "primary_error_type": "timeout"
}
```

## Conclusion

The gateway path is valid for the next larger stress pass. Normal load through concurrency `20` remained successful with bounded queue depth and no duplicate execution. LLM degradation now produces visible, classified terminal failures with fallback and circuit-breaker metrics instead of silent stalls.

Remaining risk: because fallback is still the placeholder error provider, degraded LLM scenarios validate isolation and observability, not successful provider failover.

Scope note: Gateway v1 covers generation only. Embeddings and transcription adapters remain out of scope for this validation pass.
