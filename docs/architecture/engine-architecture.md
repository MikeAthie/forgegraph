# Engine Architecture

> Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is canonical. If this document conflicts with the invariants, the invariants win.
>
> Scope note: this document documents the Go engine/execution plane only. It intentionally does not document current frontend internals.

## Role

The Go engine is ForgeGraph's **execution plane**. It runs backend-issued graph execution contracts, schedules nodes, invokes adapters, emits runtime observations, and returns results to the backend.

It does **not** own durable runtime state. In production-like modes, durable writes must flow back through backend-owned APIs, callbacks, or runtime intents.

## Package map

```text
engine/
  main.go                         configuration, dependency wiring, gRPC server, metrics server
  engine.proto                    gRPC contract between backend and engine
  application/
    port/                         interfaces for repositories, memory, executors, events, runtime intents
    usecase/                      scheduler, deterministic execution harness, snapshots, summarization worker
  domain/
    entity/                       Graph, Run, NodeRun, State, Policy, MessageBuffer, MemoryConfig
    service/                      graph validation, schema validation, execution planning, conditions, token counting
    value/                        node/run value objects
  adapter/
    executor/                     node executors: prompt, tool, transform, merge, subgraph, memory/observation, output
    gateway/                      LLM clients, event emitters, credential resolution, runtime intent publishers
    repository/                   backend HTTP run repository and test/local memory repository
    store/                        memory stores and Redis health/tiered store adapters
    summarizer/                   LLM summarization and JSON extraction
    tool/                         built-in and manifest-backed tool registry
    metrics/                      Prometheus metrics adapters
  infrastructure/
    logger/ metrics/ tracing/     cross-cutting instrumentation
```

Approximate non-test Go package file counts from the docs branch worktree:

| Package | Files | Purpose |
| --- | ---: | --- |
| `adapter/executor` | 23 | Node execution adapters and executor-specific helpers. |
| `adapter/gateway` | 14 | Provider clients, callback/event emitters, backend/runtime-intent transport. |
| `application/port` | 9 | Interfaces that isolate scheduler/use cases from concrete adapters. |
| `domain/entity` | 7 | Runtime graph/run/state/domain entities. |
| `adapter/store` | 5 | Memory/Redis/tiered store adapters. |
| `application/usecase` | 5 | Scheduler, snapshots, hooks, summarization worker. |
| `domain/service` | 5 | Validation, planning, conditions and token counting. |
| root package | 4 | gRPC service startup, config, protobuf bindings. |

## Startup and wiring

`engine/main.go` loads environment configuration, validates runtime state mode, wires adapters, and starts:

- a gRPC server for backend dispatch;
- a metrics HTTP server;
- optional Redis-backed runtime intent publishing;
- optional backend HTTP run repository;
- provider/gateway clients;
- memory and summarization adapters;
- scheduler/use-case dependencies.

Important config groups:

| Config group | Examples | Ownership meaning |
| --- | --- | --- |
| gRPC/metrics | `GRPC_PORT`, `METRICS_PORT`, TLS cert settings | Engine serving and observability. |
| backend callback/control plane | `ENGINE_CALLBACK_URL`, `CONTROL_PLANE_URL`, `ENGINE_CALLBACK_SECRET` | Signed boundary back to backend-owned state. |
| run state mode | `ENGINE_RUN_STATE_MODE`, `ENGINE_ALLOW_IN_MEMORY_MODE` | Production should use backend/control-plane mode, not engine-owned memory. |
| runtime intents | `ENGINE_RUNTIME_WRITE_MODE`, `ENGINE_RUNTIME_INTENT_STREAM`, retry/outcome settings | Durable write request path back to the backend. |
| Redis/cache | Redis host/pool/timeouts/sentinel settings | Transport/cache, not authoritative state. |
| memory gRPC | `MEMORY_GRPC_HOST`, `MEMORY_GRPC_PORT` | Engine-facing memory retrieval/save adapter. |
| tools/providers | `TOOL_MANIFEST_DIR`, runtime mode/provider settings | Execution-time tool/LLM configuration. |

## Execution flow

```text
Backend creates durable Run + dispatch graph
        |
        | gRPC StartRun / ResumeRun contract
        v
engine main.go service boundary
        |
        v
application/usecase Scheduler
        |
        +--> domain/service execution planner and validators
        +--> adapter/executor node executors
        +--> adapter/gateway LLM/tool/provider calls
        +--> adapter/store memory/cache calls
        |
        +--> adapter/repository HTTP run repository
        |       (reads backend state, emits durable write intents)
        |
        +--> runtime intent publisher / signed event emitter
                |
                v
        Backend validates, persists, broadcasts, recovers
```

The scheduler should fail closed when backend-owned writes fail. Tests in `engine/application/usecase/runtime_intents_test.go` and related deterministic tests cover this boundary.

## Application ports

The `application/port` package is the architectural seam between engine use cases and adapters:

| Port | Purpose |
| --- | --- |
| `RunRepository` | Read current run state and request backend-owned run/node/cache/checkpoint/pause mutations. Production implementation is HTTP/control-plane-backed. |
| `GraphRepository` | Load graph definitions if needed; current dispatch usually includes graph JSON in the gRPC request. |
| `RuntimeIntentPublisher` | Publish durable write requests for backend validation/application. |
| `NodeExecutor` | Execute a single node implementation. |
| `EventEmitter` | Emit lifecycle/observability events back to backend. |
| `MemoryRetriever` / `MemoryStore` | Retrieve and write scoped memory through backend-compatible adapters. |
| `Summarizer` | Summarize execution context through provider adapters. |
| `RetryRecorder` | Record retry-operation metadata through backend-owned state paths. |
| `RunContext` | Carry runtime contract identifiers such as tenant, run, attempt and trace IDs. |

Keep new execution behavior behind these ports so tests can prove scheduling semantics without binding the use case layer to a concrete provider or storage client.

## Backend HTTP repository

`engine/adapter/repository/http_run_repository.go` is the concrete bridge from engine execution to backend-owned state. It:

- signs control-plane HTTP requests;
- reads backend run state and snapshots;
- maps backend not-found/conflict errors to engine domain errors;
- publishes runtime intents for run status, checkpoints, node runs, tool execution lifecycle and pause/resume operations;
- blocks direct pause/checkpoint writes when runtime intents are enabled.

This adapter is allowed to *request* durable mutations. The backend remains the authority that accepts, rejects, dedupes, or applies them.

## Runtime intents

`engine/application/port/runtime_intents.go` defines `RuntimeIntentEnvelope`:

- `intent_id`
- `intent_type`
- `run_id`
- `attempt_id`
- `timestamp`
- `payload`
- optional `trace_id`

Engine code should prefer stable deterministic IDs where retry/idempotency matters. The backend then enforces stale attempt rejection, idempotency and state-machine validity.

## Scheduler responsibilities

`engine/application/usecase/scheduler.go` is the high-complexity center of the engine. It is responsible for:

- hydrating the graph/run execution context from the backend request;
- validating runtime budgets and graph structure;
- deriving executable node order;
- coordinating worker concurrency;
- executing node adapters;
- handling pause/resume and human-gate semantics;
- publishing runtime intents and observability events;
- retrying safe work while blocking unsafe automatic retries;
- preserving trace/context propagation;
- failing closed when backend write boundaries reject/timeout.

The scheduler may hold ephemeral execution state for the active invocation. It must not become the durable run database.

## Executors and adapters

The `adapter/executor` package maps graph node types to concrete execution behavior:

- prompt/model execution;
- tool execution with result limits and runtime tool policy;
- transform/merge/output nodes;
- subgraph execution;
- memory retrieval/save/context/search/timeline nodes;
- retry and policy helpers.

The `adapter/gateway` package holds external model/provider and backend boundary clients:

- OpenAI/Anthropic/Gemini/local/fallback/chaos clients;
- marketplace manifest client;
- credential resolver;
- signed HTTP event emitter;
- Redis and backend-ack runtime intent publishers.

The `adapter/store` package handles memory/cache backing stores. Treat Redis/tiered store contents as cache/transport unless a backend model explicitly persists the authoritative record.

## Domain services

Domain services are engine-local execution helpers:

- graph validation and schema checks;
- execution planning;
- condition evaluation;
- token counting.

They should stay deterministic and side-effect-light. Anything that changes durable state belongs at the backend boundary.

## Testing and guardrails

Engine changes should usually run:

```bash
cd engine
go test ./...
```

Use narrower test files when changing a boundary:

| Change area | Tests / guardrails |
| --- | --- |
| Runtime ownership | `architecture_enforcement_test.go`, `statelessness_guard_test.go`, `scripts/ci/check_engine_ownership.sh` |
| Scheduler behavior | `application/usecase/scheduler*_test.go`, `runtime_intents_test.go`, `runtime_intent_transport_failures_test.go` |
| Backend repository | `adapter/repository/http_run_repository_test.go` |
| Executors | `adapter/executor/*_test.go` |
| LLM/provider gateway | `adapter/gateway/*_test.go` |
| Memory/store | `adapter/store/*_test.go`, observation executor tests |
| Metrics/logging | `adapter/metrics/*`, `infrastructure/logger/*` tests |

## Engine change checklist

- Does the change add durable state to the engine? If yes, redesign it.
- Does the engine need to trigger a durable mutation? Express it as a runtime intent or signed backend callback.
- Does the change depend on Redis, Kafka, local files or memory for correctness after restart? If yes, it violates the durable-state invariant unless the backend can reconstruct it.
- Does a retry risk duplicate side effects? Require stable IDs and backend idempotency.
- Does a pause/resume path require engine-local process state? Move the resume context to backend-owned snapshots.
- Does the adapter touch credentials or provider secrets? Keep them in environment/backend credential resolution; do not log or persist secrets.
