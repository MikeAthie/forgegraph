# ForgeGraph Stress Report

Date: 2026-04-25
Harness: [scripts/stress_runner.py](/c:/Users/mathi/projects/forgegraph/scripts/stress_runner.py)
Artifacts: [logs/stress/full](/c:/Users/mathi/projects/forgegraph/logs/stress/full)

## Scope

This run exercised eight scenarios against the local Docker stack:

- `endpoint-saturation`
- `engine-concurrency`
- `redis-saturation`
- `llm-degradation-delay`
- `llm-degradation-timeout`
- `llm-degradation-unavailable`
- `failure-injection-engine-stop`
- `failure-injection-redis-stop`

Each scenario used the same graph version (`f2cde181-3f99-4ea4-a89f-2c096a134533`), concurrency levels `5, 10, 20, 50`, and `50` runs per level.

## Executive Summary

ForgeGraph does not show silent data corruption in this sweep. No duplicate node execution was observed across `1,600` runs. The dominant failure mode is graceful degradation into rate limiting or LLM timeouts at `concurrency 50`, with one sharper breakpoint: stopping the engine mid-run causes failures as early as `concurrency 5`.

The backend itself became operationally unhealthy after prolonged stress. Before the successful Redis-stop rerun, `POST /api/auth/login` hung for `60` seconds and the backend health check repeatedly exceeded its `5` second timeout. A `docker compose restart backend backend-runtime-intents` restored service immediately, so recovery is possible but not automatic under sustained load.

## Aggregate Metrics

- Scenarios: `8`
- Total runs: `1600`
- Successful runs: `1494`
- Failed runs: `106`
- Timeouts: `49`
- Retries observed: `133`
- Duplicate node executions: `0`
- Worst-case latency: `360811 ms`
- Error mix: `rate_limit=52`, `timeout=49`, `internal=5`

## Breakpoints

| Scenario | Breaking point | First failure | Behavior | Integrity | Success / Total |
| --- | --- | --- | --- | --- | --- |
| endpoint-saturation | concurrency 50 | rate_limit | degrades | safe | 178 / 200 |
| engine-concurrency | concurrency 50 | timeout | stalls | safe | 196 / 200 |
| redis-saturation | concurrency 50 | rate_limit | stalls | safe | 177 / 200 |
| llm-degradation-delay | concurrency 50 | timeout | stalls | safe | 190 / 200 |
| llm-degradation-timeout | concurrency 50 | rate_limit | stalls | safe | 183 / 200 |
| llm-degradation-unavailable | concurrency 50 | timeout | stalls | safe | 193 / 200 |
| failure-injection-engine-stop | concurrency 5 | internal | recovers | safe | 184 / 200 |
| failure-injection-redis-stop | concurrency 50 | timeout | recovers | safe | 193 / 200 |

## System Findings

### Backend

- Backend saturation is predictable at `concurrency 50`. The first hard failures are API-side rate limits, not corrupted runs.
- The stronger backend failure showed up after accumulated stress: on `2026-04-25`, `POST /api/auth/login` timed out after `60` seconds and the container health check exceeded its `5` second timeout repeatedly.
- Recovery required a manual restart of `backend` and `backend-runtime-intents`. After restart, auth returned `200` immediately and the Redis-stop scenario completed.

Sample evidence:

```text
TimeoutError
timed out
```

```text
Health check exceeded timeout (5s)
```

### Engine

- Under normal concurrency pressure, the engine starts breaking at `concurrency 50`.
- The first engine failures are LLM-facing timeouts during `prompt_2`, not ordering corruption or duplicate execution.
- Stopping the engine mid-run is the sharpest failure point in the suite. Failures started at `concurrency 5`, and the worst run took `360811 ms` before timing out waiting for a terminal state.

Sample evidence:

```json
{"run_id":"3d7a567c-6b6d-4776-8977-8d7e3be17d61","concurrency":50,"error_type":"timeout","error":"node prompt_2 (prompt): LLM call failed: failed reading stream: context deadline exceeded"}
```

```json
{"run_id":"247245d6-9521-41c6-9f40-a729a5f84f5c","concurrency":5,"error_type":"internal","error":"timed out waiting for terminal status"}
```

### Redis And Runtime Transport

- Redis pressure does not immediately corrupt run state, but it does contribute to stalls and timeout-heavy behavior at `concurrency 50`.
- The transport consumer logs showed real lag and backlog during the run, for example `stream_length=33128`, `lag=9`, `backlog=9`, `dead_letter_count=7`.
- The backend metrics API did not surface this. Scenario summaries still reported all `runtime_transport` counters as zero before and after load. That means the current API view is not trustworthy for Redis bottleneck analysis because the counters live in the separate consumer process.

Sample evidence:

```text
Runtime intent consumer lag: stream_length=33128 pending=0 lag=9 backlog=9 consumer_idle_ms=67076411 dead_letter_count=7
```

### LLM Degradation

- Slow, timing out, or unavailable LLM behavior produces stalls rather than immediate hard failure.
- All three LLM degradation scenarios first broke at `concurrency 50`.
- The common symptom is a `context deadline exceeded` error in `prompt_2`.
- `llm-degradation-unavailable` had the highest average latency in this group at `20297.54 ms`.

## Data Integrity

- No duplicate node execution was observed in any scenario.
- No scenario produced evidence of silent state corruption from the harness perspective.
- Recovery after service failure was possible for both engine stop and Redis stop.
- Confidence is weaker than it should be for Redis transport state because the backend metrics summary is blind to the live consumer counters.

## Important Test Conditions

- The system was not clean at the start of the sweep. `queue.processing` was already `374`, `runs.active_total` was already above `440`, and the transport layer already had `dead_letter_count=7`.
- These results are therefore valid as stressed-system measurements, not clean-room capacity numbers.
- The local model originally configured by the graph was unavailable. The test graph was updated to use `docker.io/ai/llama3.1:latest` before the final scenario sweep.

## Artifacts

- Scenario summaries:
  - [endpoint-saturation](/c:/Users/mathi/projects/forgegraph/logs/stress/full/endpoint-saturation/summary.json)
  - [engine-concurrency](/c:/Users/mathi/projects/forgegraph/logs/stress/full/engine-concurrency/summary.json)
  - [redis-saturation](/c:/Users/mathi/projects/forgegraph/logs/stress/full/redis-saturation/summary.json)
  - [llm-degradation-delay](/c:/Users/mathi/projects/forgegraph/logs/stress/full/llm-degradation-delay/summary.json)
  - [llm-degradation-timeout](/c:/Users/mathi/projects/forgegraph/logs/stress/full/llm-degradation-timeout/summary.json)
  - [llm-degradation-unavailable](/c:/Users/mathi/projects/forgegraph/logs/stress/full/llm-degradation-unavailable/summary.json)
  - [failure-injection-engine-stop](/c:/Users/mathi/projects/forgegraph/logs/stress/full/failure-injection-engine-stop/summary.json)
  - [failure-injection-redis-stop](/c:/Users/mathi/projects/forgegraph/logs/stress/full/failure-injection-redis-stop/summary.json)
- Per-run logs:
  - [runs.jsonl](/c:/Users/mathi/projects/forgegraph/logs/stress/full/endpoint-saturation/runs.jsonl)
  - [runs.jsonl](/c:/Users/mathi/projects/forgegraph/logs/stress/full/engine-concurrency/runs.jsonl)
  - [runs.jsonl](/c:/Users/mathi/projects/forgegraph/logs/stress/full/redis-saturation/runs.jsonl)
  - [runs.jsonl](/c:/Users/mathi/projects/forgegraph/logs/stress/full/llm-degradation-delay/runs.jsonl)
  - [runs.jsonl](/c:/Users/mathi/projects/forgegraph/logs/stress/full/llm-degradation-timeout/runs.jsonl)
  - [runs.jsonl](/c:/Users/mathi/projects/forgegraph/logs/stress/full/llm-degradation-unavailable/runs.jsonl)
  - [runs.jsonl](/c:/Users/mathi/projects/forgegraph/logs/stress/full/failure-injection-engine-stop/runs.jsonl)
  - [runs.jsonl](/c:/Users/mathi/projects/forgegraph/logs/stress/full/failure-injection-redis-stop/runs.jsonl)

## Bottom Line

- Backend breaks first as controlled rate limiting at `concurrency 50`, then later as an operational stall requiring restart after sustained stress.
- Engine breaks first on LLM deadline handling at `concurrency 50`, and much earlier when the engine process is killed mid-run.
- Redis acts more like a stall amplifier than a single-point crash trigger in this sweep, but transport observability is incomplete because the API metrics are blind to the live consumer process.
- The system degrades or recovers predictably more often than it corrupts state, but backend self-recovery and Redis transport visibility are still weak points.
