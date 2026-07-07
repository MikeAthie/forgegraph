# Backend Architecture

> Runtime precedence: [../architecture/runtime-invariants.md](../architecture/runtime-invariants.md) is canonical. If this document conflicts with the invariants, the invariants win.
>
> Scope note: this document documents the Django backend/control plane only. It intentionally does not document current frontend internals.

## Role

The backend is ForgeGraph's **control plane** and the only durable source of truth. It owns:

- tenancy, organizations, users, memberships, access policy, billing and audit scope;
- company operating data, packs, departments, services, whiteboards, tasks, approvals, deliverables, and evidence;
- graph definitions and immutable graph versions;
- run records, node records, runtime intents, snapshots, liveness, recovery, dead letters, and tool execution records;
- memory observations, memory chunks, usage accounting, and vector search records;
- gateway/communication connector state;
- projection/read-model materialization and replay checkpoints.

The backend may delegate active execution to the Go engine, but it must never delegate durable state ownership.

## Layer map

```text
backend/
  adapters/
    api/         REST API, serializers, auth, webhooks, readiness, and control-plane callbacks
    grpc/        memory gRPC service used by the engine
    ws/          WebSocket consumers and broadcast helpers
    embedding/   embedding provider adapters
  application/
    services/    business/application services and runtime safety boundaries
    projections/ read-model projection handlers
    dto/         response/application DTOs
  domain/        domain events, entities, value objects, and manager-level contracts
  infrastructure/
    orm/         Django models, migrations, managers, management commands
    grpc/        generated engine protobuf bindings
  config/        Django settings, URL root, ASGI/WSGI, celery config
  tests/         unit, integration, e2e, reliability, and API tests
```

## HTTP/API boundary

The root Django URL file exposes health/readiness and mounts `adapters.api.urls` under both `/api/` and `/api/v1/` for compatibility:

- `backend/config/urls.py`
- `backend/adapters/api/urls.py`

The API router currently includes these domain surfaces:

| API area | Mounted path(s) | Ownership |
| --- | --- | --- |
| Auth/session | `auth/`, `ws-ticket` | Login, registration, token refresh, WebSocket ticketing. |
| Organizations | `orgs`, `orgs/`, `orgs/current`, `orgs/me` | Tenant/account boundary and membership context. |
| Companies/portfolio | `companies/`, portfolio top-level routes | Company workspace and cross-company views. |
| Operating models/services | operating-model, company blueprint, service engagement routes | Pack installation, company operating-model configuration, service catalog, deliverables. |
| Whiteboards/communications | top-level whiteboard and communication routes | Generic workboard, thread, message, receipt and collaboration surfaces. |
| Runs/engine | `runs`, `runs/`, `engine/`, `executions/`, `approvals/` | Backend-owned run creation, engine callbacks, runtime events, approval handoff. |
| Graphs/templates/marketplace | `graphs/`, `graph-versions`, `templates/`, `marketplace/`, `runtime-tools/` | Workflow graph definitions, versions, prompt/templates, runtime tool contracts. |
| Memory/analytics/accounting | `memory/`, `analytics/`, `accounting/`, `metrics/` | Memory, usage, observability, and cost/accounting read models. |
| Gateway/integrations | `gateway/`, `integrations/`, `credentials/` | External platforms, connector credentials, webhooks, capabilities. |
| Governance/ops | `audit-logs/`, `policies/`, `retention/`, `operator/`, `ops/`, `scim/`, `billing/` | Compliance, policy, release/ops, SCIM, billing. |
| Commerce/product operations | `inventory/`, `commerce/`, `storefront/`, `company-ops/`, `learning/` | Inventory, storefront, product operation, learning and outcome loops. |

API modules should stay thin: validate/authorize/serialize at the edge and put durable business behavior in `application/services` or model managers.

## Application service seams

The indexed graph shows that the backend service layer is where most cross-domain orchestration lives. High-signal service seams include:

| Service area | Representative files | Purpose |
| --- | --- | --- |
| Run preparation and dispatch | `application/services/run_preparation.py`, `run_queue.py`, `engine_client.py` | Convert backend graph/version state into an engine execution contract. |
| Runtime safety | `runtime_write_intents.py`, `run_state_machine.py`, `run_liveness.py`, `run_snapshots.py`, `run_locking.py` | Validate state transitions, process engine intents, manage snapshots/liveness/recovery. |
| Task lifecycle | `task_lifecycle.py`, `company_run_task_routing.py`, `routing.py` | Keep tasks, whiteboards, routing records, and operation snapshots aligned. |
| Projections | `application/projections/*`, projection management commands | Build read models from backend-owned events/state and track replay cursors. |
| Memory | `memory_observation_service.py`, `vector_search_service.py`, `embedding_service.py`, `memory_gc.py` | Durable observations, vector chunks, retrieval, dedupe, retention and usage. |
| Operating-model packs | `operating_model_packs.py`, `company_operating_models.py`, pack management commands | Load pack config and map it to generic backend primitives. |
| Gateway/connectors | `gateway_connectors.py`, `gateway_registry.py`, `communication_kafka.py` | External messaging/platform integration, capabilities, receipts and polling cursors. |
| Governance/evidence | `company_learning.py`, `operator_actions.py`, `policy_*`, `agency_*`, `deliverable_*` | Evidence, quality gates, outcomes, policy, reports, deliverables. |
| Commerce/company ops | `commerce.py`, `company_ops.py`, inventory/services | Product-operation and storefront primitives. |

## Durable model registry

`backend/infrastructure/orm/models/__init__.py` exports the compatibility registry. The concrete model files are intentionally grouped by domain:

| Model file | Important durable entities |
| --- | --- |
| `auth.py` | `User`, `Organization`, `OrganizationMembership` |
| `graphs.py` | `Graph`, `GraphVersion`, graph templates, prompt templates, memory config/session, node registry/package installs |
| `runtime.py` | `Run`, `RunQueueEntry`, `RunEvent`, runtime intents/outcomes, processed-event idempotency, domain events/outbox, projections, tool executions |
| `run_records.py` | `RunCheckpoint`, `NodeRun`, `NodeRunCache`, `ApprovalTask`, agent/task records, retry/dead-letter/task lifecycle records, judges |
| `memory.py` | `MemoryEntry`, `MemoryObservation`, `MemoryUsage`, `LLMUsage`, `LLMBudget`, quotas, audit/operator logs, service metrics, policies, SSO/SCIM |
| `operating_models.py` | Pack releases/installations, namespace claims, company access/assignment, service catalog, engagements, deliverables, programs/stages |
| `work_whiteboards.py` | Request classification, work whiteboards, product operations |
| `routing.py` | Department registry/membership, routing policies, task routing records |
| `communications.py` | Threads, messages, attachments, event receipts |
| `gateway.py` | Gateway connections, conversations, inbound receipts, poll cursors, capabilities, media artifacts, automation schedules |
| `company_ops.py` | Signals, objectives, opportunities, publication/procurement drafts, inventory events, assets, evidence, preferences/outcomes/policies/escalations |
| `commerce.py` | Inventory products/reservations/stock/order shells, storefront profile, payments, Stripe events, fulfillment |
| `decisions_assets.py` | Decisions, operating briefs, interactions, assets/versions, media generation jobs |
| `governance.py` | Assertions, dependencies, state projections, reviews, metric snapshots, report runs, validation/rework records |
| `evaluations.py` | Evaluations, findings, scorecards, policy packs, taxonomies, company team roles/assignments, capacity/portfolio/cost records |
| `credentials.py` | API keys and credential metadata |
| `domain_signals.py` | Domain signal helpers and hooks |
| `billing.py` | Billing plans/subscriptions and related records |

Design rule: new durable state should be placed in the model file for its domain, not appended reactively to whichever file is currently convenient. If no domain fits, update the domain map first.

## Runtime write path

Backend-owned runtime mutation centers on `application/services/runtime_write_intents.py` and `application/services/run_state_machine.py`.

Supported runtime intents currently include:

- `pause_run`
- `ack_run_resumed`
- `node_completed`
- `store_checkpoint`
- `set_run_status`
- `task_lifecycle_transition`
- `record_retry_operation`
- `tool_execution_started`
- `tool_execution_succeeded`
- `tool_execution_failed`
- `tool_execution_ambiguous`
- `upsert_node_run`

The service validates UUIDs, timestamps, attempt IDs, supported intent types, idempotency, stale attempt behavior, dead letters, snapshot compensation, and state-machine transitions before any durable write is committed.

## Engine callback/control-plane boundary

The backend exposes signed callback/control-plane APIs under the API adapters. The engine must not mutate database state directly. It can:

- request current run/graph state through signed backend HTTP repositories;
- emit signed lifecycle callbacks;
- publish runtime intents;
- retrieve/save scoped memory through backend services;
- receive explicit backend snapshots/resume contexts.

The backend must:

- reject stale attempt IDs;
- dedupe callback/runtime-intent IDs;
- fail closed on malformed state mutations;
- preserve backend-owned run liveness and recovery policy;
- materialize observability separately from authoritative state.

## Memory architecture

Memory has three backend-facing surfaces:

1. **Configuration** through graph memory settings and sessions (`graphs.py`).
2. **Durable records** through `MemoryEntry`, `MemoryObservation`, chunks, usage and policies (`memory.py`).
3. **Engine-facing gRPC** through `adapters/grpc/memory_service.py`, which bridges engine requests to backend services.

The engine-facing gRPC service is an adapter. The durable observation/search semantics live in `application/services/memory_observation_service.py` and `vector_search_service.py`.

## Operating-model and company architecture

ForgeGraph product work should use generic primitives:

- `Company` / organization-scoped access;
- departments and routing policies;
- work whiteboards and product operations;
- service catalog, engagements, deliverables, programs, stage states;
- tasks, approvals, decisions, evidence, reviews;
- gateway/communication records for client/platform I/O.

Pack-specific code should live in pack config, pack tools, management commands, or generic service orchestration. It should not create one-off vertical database ownership unless the product domain genuinely needs a durable core concept.

## Tests and guardrails

Backend changes should use the most specific test lane that covers the changed ownership boundary:

| Change area | Tests / scripts |
| --- | --- |
| Runtime ownership | `tests/integration/adapters/test_runtime_control_plane_invariants.py`, `tests/unit/services/test_runtime_write_intents.py`, `scripts/ci/check_backend_runtime_writes.py` |
| Run state/liveness | `tests/unit/services/test_run_state_machine.py`, `test_run_liveness.py`, `test_snapshot_recovery_drills.py` |
| Projections | `tests/unit/projections/*`, `tests/integration/test_*projection*`, `scripts/ci/check_projection_guardrails.py` |
| API adapters | `tests/unit/api/*`, `tests/integration/adapters/*` |
| Memory | `tests/integration/adapters/test_memory_grpc_service.py`, `tests/unit/services/test_memory_*`, `test_vector_search_service.py` |
| Gateway/connectors | `tests/unit/services/test_gateway_platform_services.py`, connector-specific tests |
| Pack/company work | whiteboard, service engagement, operating-model pack, department routing, and company ops tests |

## Backend change checklist

- Does this create or mutate durable state? If yes, the path must be backend-owned.
- Is the state authoritative or just a read model/projection? Name it accordingly.
- Does a new event mutate state? If yes, the backend must validate and apply it.
- Does the engine need the value? Pass it as an execution contract, signed callback, or runtime intent; do not make the engine infer durable state.
- Does the model belong to an existing domain file? If not, update the domain map first.
- Does the change need idempotency, stale-attempt rejection, or replay behavior? Add tests before relying on it.
