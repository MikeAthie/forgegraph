# ForgeGraph Clean Capacity Stress Report

Date: 2026-04-25 local time
Completed: 2026-04-26T00:39:50Z
Harness: [scripts/stress_runner.py](../../scripts/stress_runner.py)
Artifacts: [logs/stress/clean-20260425-full-v2](../../logs/stress/clean-20260425-full-v2)

## Scope

This run repeated the same eight-scenario suite against a clean runtime baseline:

- `endpoint-saturation`
- `engine-concurrency`
- `redis-saturation`
- `llm-degradation-delay`
- `llm-degradation-timeout`
- `llm-degradation-unavailable`
- `failure-injection-engine-stop`
- `failure-injection-redis-stop`

Each scenario used graph version `f2cde181-3f99-4ea4-a89f-2c096a134533`, concurrency levels `5, 10, 20, 50`, and `50` runs per level.

## Clean Reset

The reset deliberately avoided deleting backend-owned durable run state.

- Stopped `engine` and `backend-runtime-intents` before cleanup.
- Normalized stale `run_queue` rows whose runs were already backend-owned terminal or paused states: `174` processing rows for failed runs were marked failed, and `200` processing rows for succeeded/canceled/paused runs were marked completed.
- Deleted only Redis transport artifacts: `forgegraph:runtime:intents` and `forgegraph:runtime:intents:dead`.
- Preserved `forgegraph:snapshot:*` keys because snapshots are backend-owned recovery state.
- Recreated `engine`, `backend`, and `backend-runtime-intents` to reset process-local metrics.

Clean baseline before the valid run:

```json
{
  "health": "ok",
  "queue_pending": 0,
  "queue_processing": 0,
  "redis_stream_length": 0,
  "redis_dead_letter_count": 0,
  "runtime_transport_source": "redis"
}
```

Note: historical paused fixture runs remained in PostgreSQL. Queue depth and Redis transport were clean; the database was not flushed because the backend is the durable source of truth.

## Harness Note

An earlier clean run at `logs/stress/clean-20260425-full` is excluded because the access token expired mid-suite and later scenarios returned `401 Given token not valid`. The harness now re-authenticates once on `401`, and `clean-20260425-full-v2` is the valid capacity run.

## Aggregate Metrics

- Total runs: `1600`
- Successful runs: `1067`
- Failed runs: `533`
- Duplicate node executions: `0`
- Retries observed: `1788`
- Timeout failures: `455`
- Internal failures: `76`
- Rate-limit failures: `2`
- Worst observed terminal latency: `70868 ms`

## Capacity Summary

| Scenario | Safe concurrency | First failure point | Dominant failure | Behavior | Recovery time |
| --- | ---: | --- | --- | --- | --- |
| endpoint-saturation | 5 | concurrency 10 | LLM backpressure queue timeout | stalls | n/a |
| engine-concurrency | 5 | concurrency 10 | LLM backpressure queue timeout | stalls | n/a |
| redis-saturation | 5 | concurrency 10 | LLM backpressure queue timeout | stalls | n/a |
| llm-degradation-delay | 5 | concurrency 10 | LLM backpressure queue timeout | stalls | n/a |
| llm-degradation-timeout | 5 | concurrency 10 | LLM backpressure queue timeout | stalls | n/a |
| llm-degradation-unavailable | 5 | concurrency 10 | LLM backpressure queue timeout | stalls | n/a |
| failure-injection-engine-stop | none under injected stop | concurrency 5 | engine stalled recovery | recovers | `70868 ms` max terminal latency |
| failure-injection-redis-stop | 10 | concurrency 20 | LLM backpressure queue timeout | recovers | `43254 ms` max terminal latency |

Safe concurrency means all `50` runs at that level completed successfully with no duplicate node execution.

## Latency Curve

| Scenario | Concurrency | Success / Total | Avg ms | P95 ms | Max ms | Max Redis backlog |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| endpoint-saturation | 5 | 50 / 50 | 21084.08 | 30788.25 | 44342 | 5 |
| endpoint-saturation | 10 | 42 / 50 | 34345.38 | 51982.05 | 57862 | 20 |
| endpoint-saturation | 20 | 21 / 50 | 30847.44 | 50761.20 | 53798 | 4 |
| endpoint-saturation | 50 | 9 / 50 | 23871.96 | 43203.30 | 46472 | 19 |
| engine-concurrency | 5 | 50 / 50 | 21955.24 | 33050.55 | 38773 | 9 |
| engine-concurrency | 10 | 40 / 50 | 33225.72 | 52556.10 | 54227 | 10 |
| engine-concurrency | 20 | 21 / 50 | 28927.52 | 44965.15 | 66634 | 7 |
| engine-concurrency | 50 | 8 / 50 | 22666.60 | 37067.35 | 37534 | 28 |
| redis-saturation | 5 | 50 / 50 | 20734.98 | 26091.90 | 44433 | 9 |
| redis-saturation | 10 | 44 / 50 | 33631.54 | 55148.60 | 59955 | 5 |
| redis-saturation | 20 | 27 / 50 | 29733.62 | 49370.40 | 62949 | 7 |
| redis-saturation | 50 | 12 / 50 | 23763.90 | 41460.65 | 43353 | 21 |
| llm-degradation-delay | 5 | 50 / 50 | 17095.60 | 28964.95 | 34935 | 9 |
| llm-degradation-delay | 10 | 43 / 50 | 31098.82 | 46044.85 | 53702 | 9 |
| llm-degradation-delay | 20 | 21 / 50 | 31163.44 | 54108.10 | 62456 | 10 |
| llm-degradation-delay | 50 | 10 / 50 | 24183.92 | 42970.30 | 47923 | 11 |
| llm-degradation-timeout | 5 | 50 / 50 | 19568.26 | 29819.65 | 32665 | 8 |
| llm-degradation-timeout | 10 | 40 / 50 | 31320.16 | 44663.85 | 64576 | 10 |
| llm-degradation-timeout | 20 | 22 / 50 | 31006.04 | 51645.60 | 55416 | 9 |
| llm-degradation-timeout | 50 | 10 / 50 | 24265.70 | 42517.25 | 47320 | 22 |
| llm-degradation-unavailable | 5 | 50 / 50 | 19060.48 | 24413.90 | 32858 | 10 |
| llm-degradation-unavailable | 10 | 43 / 50 | 34234.20 | 50752.80 | 68684 | 2 |
| llm-degradation-unavailable | 20 | 23 / 50 | 31495.36 | 50177.30 | 53937 | 6 |
| llm-degradation-unavailable | 50 | 11 / 50 | 24384.02 | 42501.95 | 45812 | 24 |
| failure-injection-engine-stop | 5 | 45 / 50 | 17034.50 | 70859.00 | 70868 | 13 |
| failure-injection-engine-stop | 10 | 50 / 50 | 16014.10 | 27168.70 | 33754 | 9 |
| failure-injection-engine-stop | 20 | 38 / 50 | 24699.76 | 33412.30 | 43841 | 8 |
| failure-injection-engine-stop | 50 | 24 / 50 | 26527.22 | 41850.15 | 50980 | 9 |
| failure-injection-redis-stop | 5 | 50 / 50 | 7980.40 | 17384.75 | 18999 | 4 |
| failure-injection-redis-stop | 10 | 50 / 50 | 15775.44 | 24634.65 | 43254 | 5 |
| failure-injection-redis-stop | 20 | 41 / 50 | 25371.00 | 37524.25 | 42731 | 8 |
| failure-injection-redis-stop | 50 | 22 / 50 | 23621.80 | 39079.65 | 41664 | 28 |

## Failure Points

The dominant clean-run bottleneck is now the bounded LLM backpressure layer, not Redis or backend corruption. At concurrency `10+`, the common failure is:

```text
llm backpressure queue timeout: timed out waiting for llm capacity
```

At concurrency `50`, some runs fail faster with:

```text
llm backpressure queue full: llm queue full
```

This is expected graceful degradation: latency is bounded by queue/request timeouts and the system does not create duplicate node executions.

Engine-stop recovery is faster than the original stressed run. The previous worst case was `360811 ms`; this clean run marked stalled engine-kill victims with `recovery_state=stalled_failed` and `recovery_reason=engine_stalled` in about `70868 ms`.

Redis-stop recovered cleanly. Redis backlog was visible through the metrics API, peaked at `28` in per-run snapshots, and returned to `0` after the scenario. Dead letters stayed at `0`.

## Final Health

After the suite:

```json
{
  "health": "ok",
  "watchdog_healthy": true,
  "queue_pending": 0,
  "queue_processing": 0,
  "runtime_transport_source": "redis",
  "redis_stream_length": 20651,
  "redis_pending": 0,
  "redis_lag": 0,
  "redis_backlog": 0,
  "redis_dead_letter_count": 0
}
```

All core services were healthy after the run. `backend-runtime-intents` had one container restart during the failure-injection phase; `backend`, `engine`, and `redis` had restart count `0`.

## Bottom Line

- Clean safe concurrency for normal and LLM-degraded execution is `5`.
- The first real capacity break is `concurrency 10`, driven by bounded local LLM capacity.
- Redis is observable and drains back to zero backlog; it was not the primary bottleneck in this clean run.
- Engine-kill recovery is predictable and much faster than before, but injected engine stop still causes some runs to fail closed rather than resume.
- No silent corruption and no duplicate node execution were observed.

## Remaining Risks

- The local model plus `ENGINE_LLM_MAX_CONCURRENCY=4` makes LLM capacity the limiting factor. Raising safe concurrency requires tuning LLM concurrency, queue size, and timeout values against the actual model throughput.
- Engine failure recovery currently fails closed for runs with `recovery_policy=fail`; automatic resume behavior depends on run recovery policy and checkpoint availability.
- Historical paused fixture runs still exist in PostgreSQL and appear in some aggregate run metrics. They did not affect queue depth or Redis transport measurements.
