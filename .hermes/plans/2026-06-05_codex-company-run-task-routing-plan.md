# Codex Company Run Task Routing Plan

## Goal

When a single Legacy prompt starts a Codex-backed company run, the backend should immediately persist visible department task cards/routing records for the full run, then attach each completed deliverable to its task record. The whiteboard should have enough backend-owned data to display department delegation, handoffs, dependencies, assignment, runtime provider, output deliverables, and ready/blocked/completed state.

This must preserve the runtime invariant from `docs/architecture/runtime-invariants.md`: durable state lives in the backend database. The Codex runtime/engine may execute work and hold ephemeral state, but it must not own durable run state. Events and whiteboard snapshots are transport/read-model artifacts, not authoritative state.

## Current State

- `backend/application/services/codex_session_runtime.py` provides the feature-flagged local Codex session runtime and creates Codex-backed `ServiceDeliverable` records.
- `backend/application/services/legacy_weekend_pipeline.py` and `backend/application/services/department_pipeline.py` orchestrate the Legacy company run stages.
- `backend/scripts/run_legacy_codex_company_run.py` can execute a complete Legacy run.
- A successful run currently completes these 7 department stages:
  - `strategy_research`
  - `brand_content`
  - `crm_lifecycle`
  - `analytics_performance`
  - `channel_execution`
  - `qa_compliance`
  - `client_approval_ops`
- The whiteboard can observe completed stages and deliverables, but it cannot show the delegation/task trail because visible `TaskRoutingRecord` records are not created for the run.

## Proposed Design

### 1. Use Existing Primitives Only

Do not introduce new database models for the weekend slice.

Use:

- `TaskRoutingRecord` as the durable task card/routing record.
- `ProgramStageState.state_json` to cross-link a pipeline stage to its task routing record and current dependency/deliverable summary.
- `ServiceDeliverable.metadata_json` to record the task routing record that produced the deliverable.
- `AssetVersion.provenance_json` to preserve the task/stage/run provenance for generated assets, where asset versions are produced.
- `WorkWhiteboard` metadata/state as a backend-owned read-model snapshot for UI consumption, not as the source of truth.

### 2. Represent Department Task Routing Records

Create one `TaskRoutingRecord` per department stage at company-run bootstrap time. These records are both the visible task cards and the durable routing trail for the initial implementation.

Store explicit values in first-class `TaskRoutingRecord` columns where they already exist. Store the rest in the record's JSON payload/metadata field using a versioned shape such as:

```json
{
  "schema": "company_run_task_routing_v1",
  "company_run_id": "<run id>",
  "whiteboard_id": "<whiteboard id>",
  "program_stage_state_id": "<stage state id>",
  "legacy_stage": "brand_content",
  "department": "brand_content",
  "task_title": "Brand Content",
  "task_kind": "department_delegation",
  "status": "blocked",
  "blocked_state": "blocked",
  "dependency_task_ids": ["<strategy task id>"],
  "handoff_from_task_id": "<strategy task id>",
  "handoff_to_task_ids": ["<crm task id>"],
  "assigned_department": "brand_content",
  "assigned_operator": "legacy_weekend_pipeline",
  "runtime_provider": "codex_session_runtime",
  "output_deliverable_ids": [],
  "created_by_prompt_id": "<prompt/request id if available>"
}
```

Use the actual JSON-bearing field present in `backend/infrastructure/orm/models/routing.py` after implementation inspection. If the model already has fields for status, source/target department, assignee, task type, or payload, prefer those columns and keep the JSON shape as supplemental UI/provenance metadata.

Status vocabulary for the task trail:

- `blocked`: dependencies are incomplete.
- `ready`: dependencies are satisfied and the stage has not started.
- `running`: the pipeline is executing the stage.
- `completed`: the stage produced its deliverable and any asset versions/provenance were attached.
- `failed`: the stage failed; include failure details in metadata.

For the weekend slice, represent handoffs through dependencies and `handoff_from_task_id` / `handoff_to_task_ids` on the department task records. If product later needs separate handoff rows, add additional `TaskRoutingRecord` rows with `task_kind: "department_handoff"` using the same model, still without a new table.

### 3. Bootstrap Records Before Runtime Execution

At the start of a Legacy Codex company run:

1. Resolve the ordered stage plan and department mapping.
2. Open one backend transaction.
3. Create or find the 7 `ProgramStageState` rows for the run.
4. Create one `TaskRoutingRecord` per department stage before invoking Codex.
5. Set `strategy_research` to `ready`; set downstream stages to `blocked` with dependency task IDs.
6. Persist cross-links in each `ProgramStageState.state_json`.
7. Write a compact `WorkWhiteboard` read-model snapshot containing the task IDs and display fields.
8. Commit before calling the Codex runtime.

This guarantees that a whiteboard refresh immediately after prompt submission can show task cards even while execution remains sequential internally.

### 4. Update Records During Stage Execution

When a stage begins:

- Mark its `TaskRoutingRecord` as `running`.
- Update the linked `ProgramStageState.state_json`.
- Refresh the whiteboard task snapshot from backend records.

When a stage completes:

- Attach the produced `ServiceDeliverable.id` to the task record's `output_deliverable_ids`.
- Add `task_routing_record_id`, `program_stage_state_id`, `legacy_stage`, `department`, `company_run_id`, and `runtime_provider` into `ServiceDeliverable.metadata_json`.
- Add the same routing provenance into `AssetVersion.provenance_json` for any produced asset versions.
- Mark the task record and stage state `completed`.
- For each downstream dependent task whose dependencies are complete, mark it `ready`.
- Refresh the whiteboard task snapshot.

When a stage fails:

- Mark the task record `failed`.
- Keep dependent tasks `blocked`.
- Store concise failure metadata in the task record and `ProgramStageState.state_json`.
- Refresh the whiteboard task snapshot.

All status transitions must be committed by backend services. The Codex runtime should only receive enough context to execute and return output; it must not decide durable task state.

### 5. Whiteboard Consumption Later

For this slice, expose enough backend data for the whiteboard without implementing frontend rendering.

Add or refresh a backend-owned whiteboard snapshot shaped like:

```json
{
  "company_run_task_trail": {
    "schema": "company_run_task_trail_v1",
    "task_routing_record_ids": ["<task id>"],
    "tasks": [
      {
        "id": "<task id>",
        "department": "strategy_research",
        "title": "Strategy Research",
        "status": "completed",
        "blocked_state": "completed",
        "dependency_task_ids": [],
        "assigned_department": "strategy_research",
        "assigned_operator": "legacy_weekend_pipeline",
        "runtime_provider": "codex_session_runtime",
        "output_deliverable_ids": ["<deliverable id>"]
      }
    ]
  }
}
```

The authoritative source remains `TaskRoutingRecord` plus linked stage/deliverable rows. The whiteboard snapshot is a denormalized read model so the UI can render cards later without inventing client-side durable state.

Frontend/whiteboard rendering should remain a separate follow-up unless the existing backend whiteboard endpoint requires a minimal serializer change to include this metadata.

## Exact Files Likely To Change

Implementation should first inspect the listed files to confirm exact ORM field names and existing service boundaries.

- `backend/application/services/legacy_weekend_pipeline.py`
  - Add the company-run task bootstrap step before any Codex stage execution.
  - Add status transition calls around each department stage.
  - Ensure the bootstrap is idempotent for resume/retry paths.

- `backend/application/services/department_pipeline.py`
  - Pass the active `TaskRoutingRecord` / task trail context into stage execution.
  - Update linked `ProgramStageState.state_json` as stages move through ready/running/completed/failed.

- `backend/application/services/codex_session_runtime.py`
  - Accept optional task routing context.
  - Include task/stage/run provenance in `ServiceDeliverable.metadata_json`.
  - Include the same provenance in `AssetVersion.provenance_json` where assets are produced.
  - Do not let the runtime own or infer durable task status.

- `backend/scripts/run_legacy_codex_company_run.py`
  - Keep using the backend service path.
  - Optionally print a post-run routing summary for manual verification.
  - Do not create routing records directly in the script unless the script is already the only company-run entrypoint.

- `backend/infrastructure/orm/models/routing.py`
  - No schema change expected.
  - Only update constants/helpers if the model already has local enum/status helpers that need the new status vocabulary.

- `backend/infrastructure/orm/models/operating_models.py`
  - No schema change expected.
  - Confirm `ProgramStageState.state_json` shape and update service serialization only.

- `backend/infrastructure/orm/models/whiteboards.py` or the actual `WorkWhiteboard` model file
  - No schema change expected.
  - Confirm the JSON metadata/state field used for backend-owned whiteboard snapshots.

- `backend/tests/unit/services/test_legacy_weekend_pipeline.py`
  - Add coverage that the 7 task routing records are created before Codex execution.
  - Verify dependency/status transitions and deliverable attachment.

- `backend/tests/unit/services/test_department_pipeline.py`
  - Verify stage state JSON cross-links to routing records and updates status correctly.

- `backend/tests/unit/services/test_codex_session_runtime.py`
  - Verify deliverable metadata/provenance includes task routing context when provided.
  - Verify behavior remains compatible when no task routing context is provided.

Optional, if the helper grows beyond a few functions:

- `backend/application/services/company_run_task_routing.py`
  - Encapsulate bootstrap, status transitions, dependency resolution, and whiteboard snapshot refresh.
- `backend/tests/unit/services/test_company_run_task_routing.py`
  - Focused unit tests for idempotency and task trail state transitions.

## Migration Decision

No migration for the initial implementation.

The requested data can be represented with existing `TaskRoutingRecord` rows and existing JSON fields on stage state, deliverables, asset versions, and whiteboards. A migration should only be considered if `TaskRoutingRecord` lacks any JSON payload/metadata field and cannot associate records with the relevant run/stage/whiteboard using existing columns. Based on the architecture constraint, the preferred fallback is still to use the closest existing JSON-bearing field before adding schema.

## Test Plan

### Unit Tests

- Bootstrap creates exactly 7 `TaskRoutingRecord` rows for a Legacy Codex company run.
- Bootstrap commits records before the first Codex runtime invocation. Use a fake runtime that asserts task records already exist when called.
- Initial statuses are correct:
  - `strategy_research`: `ready`
  - all downstream stages: `blocked`
- Dependency metadata is correct for the ordered Legacy stage chain.
- Stage start marks the task and linked `ProgramStageState.state_json` as `running`.
- Stage completion:
  - marks the task `completed`
  - appends the produced deliverable ID
  - updates `ServiceDeliverable.metadata_json`
  - updates `AssetVersion.provenance_json` where applicable
  - marks the next stage `ready`
- Failure marks the current task `failed` and leaves dependents `blocked`.
- Re-running bootstrap for the same company run is idempotent and does not duplicate task records.
- Existing tests continue to pass when task routing context is absent.

### Integration / Script Verification

Run one complete Legacy Codex company run using `backend/scripts/run_legacy_codex_company_run.py` with the same feature flags/configuration used for the prior successful run.

After completion, verify from the backend database or script summary:

- 7 Codex-backed `ServiceDeliverable` rows exist.
- 7 department `TaskRoutingRecord` rows exist for the run.
- Each task has:
  - department/stage
  - task title
  - status
  - dependencies
  - assigned department/operator/runtime provider
  - output deliverable IDs
  - blocked/ready/completed state
- Each completed task has at least one matching deliverable ID.
- Each deliverable metadata points back to its task routing record.
- Each linked `ProgramStageState.state_json` points to its task routing record.
- `WorkWhiteboard` metadata/state includes the task trail snapshot.
- No durable state is introduced in the Codex runtime/engine or client.

## Rollout Steps

1. Confirm exact field names and existing helper APIs in:
   - `codex_session_runtime.py`
   - `department_pipeline.py`
   - `legacy_weekend_pipeline.py`
   - `routing.py`
   - `operating_models.py`
   - `whiteboards.py`
2. Add a small task-routing helper in the pipeline layer, or a new `company_run_task_routing.py` service if that keeps the orchestration clean.
3. Gate the new behavior behind the existing Codex company-run feature flag, or add a narrowly scoped backend flag such as `legacy_company_run_task_routing`.
4. Implement task bootstrap before Codex execution.
5. Thread task routing context through department execution and deliverable creation.
6. Update task/stage/deliverable/asset/whiteboard metadata on each transition.
7. Add focused unit tests.
8. Run one full Legacy Codex company run and capture the routing summary.
9. Enable the flag in the intended environment.
10. Leave frontend whiteboard task-card rendering as a follow-up unless a serializer change is required for the backend snapshot.

## Risks

- Existing `TaskRoutingRecord` columns may not align exactly with department task semantics. Mitigation: use first-class columns where possible and keep a versioned JSON shape for the rest.
- Duplicate task records can appear on retry/resume if bootstrap is not idempotent. Mitigation: derive a stable key from company run ID and legacy stage, and find-or-create records in one transaction.
- Whiteboard metadata could accidentally become treated as authoritative. Mitigation: always rebuild/refresh it from backend task/stage/deliverable records.
- Status vocabulary may conflict with existing routing statuses. Mitigation: map to existing enum values if present and store display-specific state in JSON.
- Sequential execution may be mistaken for real parallel delegation. Mitigation: records should describe durable delegation/readiness, not imply concurrent execution.
- A failed Codex stage can leave downstream records stale. Mitigation: failure handling must update the current task, dependent blocked state, and whiteboard snapshot in the same backend-owned flow.

## Acceptance Criteria

- Starting a Legacy Codex company run persists the 7 visible department task records before the first Codex runtime call.
- The records use existing ForgeGraph primitives and require no new DB model.
- The task trail includes department, task title, status, dependencies, assigned department/operator/runtime provider, output deliverable IDs, and blocked/ready/completed state.
- Completed `ServiceDeliverable` rows link back to their producing task records through `metadata_json`.
- Produced `AssetVersion` rows include matching task/stage/run provenance where applicable.
- Linked `ProgramStageState.state_json` contains the task routing reference and current task state.
- `WorkWhiteboard` metadata/state contains a backend-owned task trail snapshot suitable for later UI rendering.
- Unit tests cover bootstrap, idempotency, status transitions, deliverable attachment, and no-context compatibility.
- One complete Legacy run verifies 7 completed stages, 7 task records, 7 Codex-backed deliverables, and correct whiteboard task trail data.
- No engine or client component becomes authoritative for durable state.
