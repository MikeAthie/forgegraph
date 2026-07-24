# Database Domain Audit

This audit answers three questions for ForgeGraph database engineering:

1. What durable data does ForgeGraph need?
2. What database shape exists today?
3. Can the database be refactored safely?

`docs/architecture/runtime-invariants.md` remains the governing contract. Any database refactor must preserve that the backend is the only durable source of truth; the engine, events, Redis, Kafka, WebSockets, and clients are not authoritative state.

## What ForgeGraph needs

ForgeGraph is a company operating system. The database should make these backend-owned product concepts explicit and recoverable:

| Product need | Durable ownership requirement |
| --- | --- |
| Organization / tenancy | Account boundary, memberships, access policies, credentials, billing/accounting scope. |
| Company | User-created business entity with objective, context, installed operating model, memory policy, and operating status. |
| Department / capability / tool | Company structure and assigned capabilities, preferably pack-derived but company-overridable. |
| Operating model pack | Versioned, installable backend-owned configuration with compatibility, namespace, templates, evaluation profiles, policies, tools, and dashboard metadata. |
| Operation | Live or historical company work unit with status, liveness, recovery, input, output, engine dispatch contract, and durable resume state. |
| Task | Concrete work inside an operation, including department/tool/approval linkage, retries, recovery, provenance, and user-facing status. |
| Approval / decision | Human decision records that can pause, unblock, reject, reroute, or approve work. |
| Deliverable / asset | Versioned artifacts that users can read, approve, publish, send, or reuse; outputs must not live only in `Run.output_json`. |
| Whiteboard / command state | Durable company-scoped working state and feedback, with typed cards/classifications where behavior depends on them. |
| Communication / gateway | Threads, messages, attachments, connector config, connector health, schedules, receipts, and safe-send policy. |
| Memory / knowledge | Source-bounded observations, chunks, policies, snapshots, usage, and retrievable provenance. |
| Events / projections | Outbox, receipts, current-state projections, dead letters, and audit logs as read models/observability, not authoritative state. |
| Commerce / inventory / client ops | Generic company operating records that support vertical packs without hard-coding every vertical into core runtime tables. |

The strategic target is not “one table per UI card.” The target is a small set of stable, typed command-side aggregates plus flexible pack-owned JSON where the schema is explicitly versioned and validated.

## What exists today

Static model inventory from `backend/infrastructure/orm/models`:

- 149 Django model classes.
- 97 ORM migrations.
- Model groups by file:
  - `runtime.py`: 22
  - `company_ops.py`: 14
  - `memory.py`: 14
  - `evaluations.py`: 13
  - `graphs.py`: 13
  - `run_records.py`: 12
  - `operating_models.py`: 11
  - `commerce.py`: 10
  - `governance.py`: 9
  - `gateway.py`: 7
  - `decisions_assets.py`: 6
  - `communications.py`: 4
  - `routing.py`: 4
  - `auth.py`: 3
  - `billing.py`: 3
  - `work_whiteboards.py`: 3
  - `credentials.py`: 1

Important current properties:

- The schema already encodes the runtime invariant: `Run`, `RunCheckpoint`, `NodeRun`, `TaskRecord`, `ApprovalTask`, `ProcessedRuntimeIntent`, liveness fields, recovery fields, snapshots, projections, outbox, and dead letters are backend-owned.
- `Graph` is explicitly documented as transitional storage for both workflow definitions and company scopes. This is the largest semantic mismatch with the product ontology.
- `Run` is still the storage object for product “Operation”; `NodeRun` and `TaskRecord` split runtime execution traces from product task projections.
- Operating model packs are a real domain: `OperatingModelPackRelease`, `CompanyOperatingModelInstallation`, namespace claims, service catalog items, engagements, deliverables, config revisions, team roles, tools, policies, and evaluation profiles exist.
- The system has substantial JSON flexibility. Some JSON is appropriate pack/config state; some JSON is carrying product-domain facts that are queried, displayed, or gated and should eventually become typed records.

## JSON-heavy areas to review

These models have the highest JSON concentration and should be classified as either “versioned flexible schema” or “should become typed relational records”:

| Model | JSON fields | Assessment |
| --- | ---: | --- |
| `WorkWhiteboard` | 13 | Too many first-class product contexts are embedded. Keep flexible notes/metadata as JSON, but typed card/context tables should own fields used for routing, approval gates, package readiness, and downstream work. |
| `ServiceCatalogItem` | 7 | Mostly pack/config schema. Acceptable if versioned, validated, and immutable per release. |
| `OperatingBriefRecord` | 7 | Product-facing brief fields may deserve typed child records when they drive approvals, dependencies, or success criteria. |
| `ContextPack` | 7 | Good candidate for versioned “context snapshot” aggregate; keep refs typed where possible. |
| `RoutingPolicy` | 5 | JSON policy rules are acceptable only if validated by schema and released with explicit policy version. |
| `Run` | 4 | `input_json`, dispatch contract, output, and pause state are acceptable runtime payloads; deliverables and approvals should be separately materialized. |
| `CompanyOperatingModelInstallation` | 4 | Acceptable as pack installation config, but company-visible settings should have stable typed fields if queried directly. |
| `ServiceEngagement` | 4 | Intake data can stay JSON; operation and deliverable linkage should stay typed. |
| `GraphTemplate` / `NodeRegistryRelease` | 4 each | Acceptable as advanced-builder/template artifacts. |
| `RunCheckpoint` | 4 | Acceptable; backend-owned durable resume payload. Refactors must not move ownership to engine. |

## Relationship-heavy areas to review

These are not necessarily bad; high FK count often means the model is acting as an integration hub. They need especially clear aggregate ownership and indexes:

- `TaskRoutingRecord`: 12 FKs, 8 indexes.
- `CommunicationAttachment`: 12 FKs, 1 index.
- `PublicationDraft`: 11 FKs, 3 indexes.
- `CommunicationThread`: 10 FKs, 9 indexes.
- `EvidenceLink`: 10 FKs, 6 indexes.
- `PreferenceEvent`, `EvaluationRun`, `ReportRun`: 8 FKs each.

Review question for each: is it a command-side aggregate, an immutable event/evidence record, or a read model? Mixing those roles is the primary source of schema sprawl.

## Refactor recommendation

Yes, ForgeGraph can refactor the database, but it should be done in phases. A broad destructive rename/refactor now would create unnecessary migration risk and could violate runtime invariants. The safe strategy is additive, compatibility-preserving, and product-ontology-driven.

### Phase 0 — Freeze semantics before moving tables

- Add a domain ownership matrix for every model: command aggregate, read model/projection, event/outbox/receipt, config/template, or compatibility/internal.
- Add a migration checklist: owner, product term, invariant impact, backfill path, rollback path, indexes, constraints, and tests.
- Require every new model to declare whether it is authoritative state or a projection/artifact.

### Phase 1 — Product-facing aliases and boundaries

- Keep existing DB table names where renaming would be expensive.
- Introduce clearer service/query boundaries around existing records:
  - `Graph` as company/workflow compatibility storage.
  - `Run` as operation storage.
  - `NodeRun` as runtime trace, not product task.
  - `TaskRecord` / `TaskLifecycleRecord` as product task state.
- Make primary APIs and frontend repositories consume product-language DTOs only.

### Phase 2 — Normalize only stable/gated JSON

Do not normalize every JSON blob. Normalize fields that meet at least one of these criteria:

- Used in filters, joins, dashboards, approvals, readiness gates, or recovery.
- Needs uniqueness/idempotency constraints.
- Needs audit/history at subfield level.
- Feeds downstream departments or client deliverables.
- Must be migrated independently across pack versions.

Likely candidates:

- Whiteboard contexts/cards that gate approvals or downstream deliverables.
- Operating brief success criteria/dependencies/stakeholders when used for readiness gates.
- Service engagement operation/deliverable refs if they are queried as workflow state.
- Communication/gateway connector health and schedules if operational dashboards depend on them.

Keep as JSON:

- Pack manifest/config schemas.
- Versioned graph/template manifests.
- Runtime dispatch payloads and checkpoint snapshots.
- Provider response/request payloads where typed records store the durable summary and status.

### Phase 3 — Explicit company aggregate

Plan, do not rush, the `Graph` semantic split:

- Add an explicit `CompanyProfile` or `CompanyRecord` one-to-one/foreign-key aggregate if product needs exceed what `Graph` should mean.
- Backfill from existing company-scoped `Graph` rows.
- Keep `graphs` table compatibility until all APIs and frontend routes use product-language services.
- Only then consider table renames or deeper graph/workflow separation.

### Phase 4 — Runtime/read-model cleanup

- Preserve backend-owned `Run`, `RunCheckpoint`, `ProcessedRuntimeIntent`, liveness, recovery, and snapshots.
- Document which models are projections: `StateProjection`, `AgentRegistryEntry`, `TaskRecord`, cost aggregates, report projections, etc.
- Ensure projections are rebuildable from authoritative records or explicitly documented as current-state materializations.
- Avoid making Redis/Kafka/WebSocket events required to reconstruct durable state.

## Immediate do-not-do list

- Do not move checkpoint/resume ownership into the engine.
- Do not make frontend whiteboard state authoritative.
- Do not delete compatibility storage just because product terminology moved on.
- Do not normalize pack-owned config before pack schemas stabilize.
- Do not combine this dead-code cleanup with a destructive schema migration.

## Near-term actionable refactor candidates

1. Add a tracked model ownership matrix and require it in PR review for schema changes.
2. Add tests that fail if new product-facing APIs expose raw internal terms (`Graph`, `NodeRun`, raw `output_json`) outside allowed compatibility/advanced routes.
3. Add schema validators for the JSON-heavy pack/config records that are intentionally flexible.
4. Add typed whiteboard card/context records for fields that currently live only in `WorkWhiteboard.*_json` but drive routing, approval, package readiness, or downstream department work.
5. Add a company-profile aggregate around `Graph` before attempting any rename.

## Current conclusion

The database is not hopelessly wrong; it reflects organic growth from workflow engine storage into a company operating system. The main risk is semantic ambiguity, not raw table count. The safest refactor is to make ownership and product semantics explicit first, normalize only JSON that has become durable product state, and leave runtime/checkpoint ownership firmly in the backend.
