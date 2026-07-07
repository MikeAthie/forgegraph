# ForgeGraph Project Architecture

> Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is canonical. If this document conflicts with the invariants, the invariants win.
>
> Scope note: this document intentionally treats the operator UI as an external client and does **not** document the current frontend internals. The frontend may be removed or redesigned independently.

## Source

This map was written from the indexed `codebase-memory` graph for `C:/Users/mathi/projects/forgegraph` plus direct reads of the tracked `origin/main` worktree. At the time of writing the graph contained roughly **37k nodes** and **150k edges** across code symbols, calls, imports, routes, tests, and files.

## One-sentence architecture

ForgeGraph is an AI company operating system whose **Django backend control plane owns all durable truth**, while the **Go engine executes backend-issued work contracts** and reports events/intents back to backend-owned persistence.

## Runtime ownership model

```text
operators / external clients
        |
        | REST, WebSocket, webhooks, gateway callbacks
        v
Django backend control plane  <---->  PostgreSQL / pgvector
        |                              Redis streams / caches
        |                              optional Kafka transports
        |
        | signed gRPC dispatch + backend-owned runtime contracts
        v
Go execution engine
        |
        | runtime intents / signed callbacks / observability events
        v
Django backend control plane
```

The important boundary is not language or process. It is **state authority**:

- The backend owns organizations, companies, graphs, runs, tasks, decisions, memory, approvals, operating-model installations, gateway connections, projections, and recovery state.
- The engine owns active execution only: planning, scheduling, node execution, retries, bounded worker concurrency, provider/tool adapters, and runtime observability.
- Redis, Kafka, WebSockets, callbacks, and event streams are transport or observability artifacts. They are not the source of truth.
- Durable resume and failure recovery must always resolve through backend-owned snapshots, run records, runtime intent outcomes, and liveness policy.

## Repository map, excluding frontend internals

| Path | Role | Notes |
| --- | --- | --- |
| `backend/` | Control plane | Django 6 / DRF APIs, ORM models, migrations, projections, runtime write boundaries, memory, governance, gateway connectors, pack operations, and backend tests. |
| `engine/` | Execution plane | Go gRPC service that executes graph revisions and communicates through backend-owned run repositories, runtime intent publishers, callbacks, memory, tools, and LLM adapters. |
| `operating_model_packs/` | Pack configuration | Product/agency pack definitions that should configure generic backend primitives instead of creating vertical durable ownership. |
| `scripts/ci/` | Guardrails | CI checks for runtime invariants, backend writes, engine ownership, projections, launch claims, and fast/full test lanes. |
| `tools/loadgen/` | Performance harness | Go load-generation client and runner for capacity and stress evidence. |
| `docs/architecture/` | Contracts | State ownership, runtime invariants, execution-plane boundaries, event contracts, projections, and architecture notes. |
| `docs/backend/` | Backend-specific docs | Domain map and backend implementation notes. |
| `docs/ops/` | Operations | Release, rollback, observability, capacity, migration, and incident runbooks. |
| `docs/product/` | Product ontology | Company, department, operation, task, deliverable, approval, and operating-model vocabulary. |

Approximate tracked-source file counts in the docs branch worktree:

| Area | Files |
| --- | ---: |
| `backend/` | 924 |
| `engine/` | 153 |
| `scripts/` | 67 |
| `tools/` | 13 |
| `operating_model_packs/` | 18 |
| `docs/` | 156 |

## Major runtime flows

### 1. Backend-owned run dispatch

1. A client or backend job creates/selects a `GraphVersion` and calls a run API.
2. Backend services prepare engine-ready graph JSON: sentinel edge cleanup, subgraph expansion, memory config, trace context, runtime limits, marketplace/runtime tool manifests, credential references, and tenant scoping.
3. The backend persists a `Run` and related queue/liveness state before execution becomes observable.
4. The backend dispatches a signed execution contract to the engine.
5. The engine executes nodes and reports lifecycle progress back through signed callbacks and/or runtime intents.
6. The backend validates attempt IDs, idempotency keys, state-machine transitions, snapshots, and runtime intent outcomes before mutating durable state.

Key files:

- `backend/application/services/run_preparation.py`
- `backend/application/services/run_state_machine.py`
- `backend/application/services/runtime_write_intents.py`
- `backend/infrastructure/orm/models/runtime.py`
- `backend/infrastructure/orm/models/run_records.py`
- `engine/application/usecase/scheduler.go`
- `engine/adapter/repository/http_run_repository.go`
- `engine/application/port/runtime_intents.go`

### 2. Runtime intent boundary

Runtime intents are the safe replacement for engine-owned durable writes. The engine may publish an intent such as `node_completed`, `store_checkpoint`, `set_run_status`, `pause_run`, or `tool_execution_*`; the backend consumes, validates, idempotently records, and applies it.

This keeps the execution plane useful while preserving the invariant that the backend owns durable state.

### 3. Projections and read models

The backend uses durable domain/runtime records as source data and materializes read models for operational views. Projection logic may consume events, but the authoritative state is still the backend-owned tables and projection checkpoints.

Key files:

- `backend/application/projections/`
- `backend/infrastructure/orm/models/runtime.py`
- `backend/infrastructure/orm/models/governance.py`
- `backend/infrastructure/orm/models/work_whiteboards.py`
- `docs/architecture/read-models-and-projections.md`

### 4. Memory and observations

Memory is split between graph/run memory configuration, durable memory records, vector chunks, observation APIs, and an engine-facing gRPC memory service. The engine can retrieve and save scoped observations through backend services, but durable memory state remains backend-owned.

Key files:

- `backend/adapters/grpc/memory_service.py`
- `backend/application/services/memory_observation_service.py`
- `backend/application/services/vector_search_service.py`
- `backend/infrastructure/orm/models/memory.py`
- `engine/application/port/memory_retriever.go`
- `engine/application/port/memory_store.go`
- `engine/adapter/store/`

### 5. Operating-model packs and company work

Operating-model packs configure generic backend primitives: companies, departments, whiteboards, services, tasks, deliverables, approvals, policies, and evidence. Packs should not introduce special vertical state ownership that bypasses the backend domain model.

Key files:

- `operating_model_packs/`
- `backend/application/services/operating_model_packs.py`
- `backend/infrastructure/orm/models/operating_models.py`
- `backend/infrastructure/orm/models/work_whiteboards.py`
- `backend/infrastructure/orm/models/routing.py`

### 6. Gateway and communications

Gateway connectors normalize inbound/outbound platform traffic, credentials, media artifacts, poll cursors, capabilities, and automation schedules. They should record durable receipts/state in backend models and treat external platform traffic as side-effectful integration I/O.

Key files:

- `backend/application/services/gateway_connectors.py`
- `backend/application/services/gateway_registry.py`
- `backend/infrastructure/orm/models/gateway.py`
- `backend/infrastructure/orm/models/communications.py`
- `backend/adapters/api/gateway/`
- `backend/adapters/api/integrations/`

## Architectural seams from the indexed graph

The graph showed several high-cohesion clusters. Ignoring frontend clusters, the most important backend/engine seams are:

| Seam | Representative graph findings | Architectural interpretation |
| --- | --- | --- |
| Backend API/control-plane cluster | `adapters.api.*`, runs, graphs, whiteboards, operating models, gateway, auth, companies | HTTP-facing command/query boundary. Keep validation and authorization here; delegate business behavior into services. |
| Backend domain/model cluster | ORM models under `infrastructure/orm/models/*` | Durable state registry. This is the only authoritative persistent state surface. |
| Runtime intent / liveness cluster | `runtime_write_intents`, `run_state_machine`, `run_liveness`, snapshots, dead letters | Critical safety boundary for engine/backend interaction and recovery. |
| Engine scheduler cluster | `engine/application/usecase/scheduler.go`, deterministic/runtime-intent tests | Active execution coordinator. Must fail closed on backend write failures. |
| Engine adapter cluster | `adapter/executor`, `adapter/repository`, `adapter/gateway`, `adapter/store` | External integrations for tools, LLMs, backend HTTP, Redis, and memory. |
| Ops/CI guardrail cluster | `scripts/ci/check_*`, launch/readiness scripts | Architecture enforcement and release evidence. Use these when changing runtime boundaries. |

## What to read first

1. [runtime-invariants.md](runtime-invariants.md) — non-negotiable runtime contract.
2. [backend-architecture.md](../backend/backend-architecture.md) — backend control-plane map.
3. [engine-architecture.md](engine-architecture.md) — Go execution-plane map.
4. [state-ownership.md](state-ownership.md) and [state-ownership-contract.md](state-ownership-contract.md) — state authority and mutation boundaries.
5. [runtime-write-intents.md](runtime-write-intents.md) — backend-owned durable write intent model.
6. [read-models-and-projections.md](read-models-and-projections.md) — projection/read-model ownership.
7. [../product/canonical-ontology.md](../product/canonical-ontology.md) — user/product vocabulary.

## Change rules

Before changing backend, engine, runtime docs, CI guardrails, or pack execution behavior:

1. Identify which component would become authoritative for the data being changed.
2. If the answer is not “backend,” redesign the change.
3. If a new event or stream is introduced, classify it as `state` or `observability` and document who applies it.
4. If the engine needs to trigger a durable mutation, express it as a backend-validated intent or callback.
5. Add or update tests in the component that owns the state:
   - backend tests for state, idempotency, liveness, recovery, policy, projections;
   - engine tests for execution planning, scheduling, retry behavior, adapters, and fail-closed semantics;
   - integration tests for signed boundary behavior.
