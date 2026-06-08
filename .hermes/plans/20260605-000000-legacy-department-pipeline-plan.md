# Legacy Department Pipeline Plan

Status: plan only  
Scope: ForgeGraph/Atlas changes so Legacy marketing-agency deliverables are produced through department-stage workflow, not labeled after generation.  
Non-goal: implement app code in this change.

## Runtime Invariant Guard

All implementation work must preserve the repo runtime invariant:

- The backend remains the only durable source of truth for deliverables, assets, approvals, department stage state, routing decisions, snapshots, recovery, and resume state.
- The engine may execute generation and hold ephemeral execution context, but it must not own durable department state.
- Events remain transport and observability artifacts. They may announce state transitions, but they must not be the source of record.
- Clients and whiteboard UI render backend-owned state and submit user intent. They must not become authoritative for durable route, stage, or approval state.

Before editing runtime code, docs, or tests, the implementer must re-open `docs/architecture/runtime-invariants.md` and verify the planned change does not make the engine, event stream, or client durable-state-authoritative.

## Current State

Known from the Legacy batch context:

- Hermes generated a first Legacy batch directly, including strategy docs, social calendar, copy pack, 6 PNG social posts, 1 MP4 reel, `ServiceDeliverables`, `Assets`, and `TaskRoutingRecords`.
- The department assignment happened after the generation work had already been completed.
- Current routing is therefore mostly metadata/post-hoc labeling instead of a workflow that constrains how work is produced.
- The output exists as agency-like artifacts, but the production path does not yet prove department accountability, stage handoff, revision ownership, or QA/approval flow.
- The likely durable entities already exist or are adjacent to existing entities: `ServiceDeliverable`, `Asset`, `TaskRoutingRecord`, project/client/account records, and whiteboard nodes/events.
- Atlas whiteboard likely visualizes work and routing, but department-stage state needs to become backend-owned workflow state rather than inferred UI grouping.

Implication: the MVP should not throw away the existing deliverable model. It should add an explicit durable department pipeline model around deliverables and route generation through that model.

## Target Department Responsibilities

### 1. Strategy & Research

Owns:

- Client brief normalization for Legacy.
- Audience, positioning, competitor, offer, seasonal, and channel research.
- Campaign objective definition.
- Deliverable brief creation for each requested artifact.
- Success metrics and constraints that downstream departments must honor.

Produces:

- `strategy_brief`
- `audience_insights`
- `campaign_plan`
- `deliverable_briefs`
- `measurement_plan`

Handoff requirements:

- Every downstream deliverable references a Strategy-owned brief ID.
- Channel-specific work cannot start until Strategy marks its brief approved for production or explicitly marked as weekend-MVP provisional.

### 2. Brand & Content

Owns:

- Legacy brand voice and tone.
- Visual direction for glasswear/sunglasses.
- Copy pack, captions, hooks, hashtags, and creative concepts.
- Content rules for Spanish/English, CDMX context, product language, claims, and brand consistency.

Produces:

- `brand_voice_rules`
- `creative_concepts`
- `copy_pack`
- `visual_direction`
- `asset_prompts`

Handoff requirements:

- Every generated visual or video asset must reference a Brand & Content concept/copy source.
- Brand & Content can request Strategy clarification without making the engine authoritative for the revision state.

### 3. Channel Execution

Owns:

- Production of channel-specific assets.
- Social post PNGs, reel MP4, format variants, captions per channel, and posting schedule packaging.
- Channel specs such as Instagram square/reel dimensions, file naming, aspect ratios, and export metadata.

Produces:

- `instagram_post_assets`
- `instagram_reel_asset`
- `social_calendar`
- `channel_publish_package`

Handoff requirements:

- Channel Execution consumes approved/provisional Brand & Content assets and copy.
- It emits durable `Asset` and `ServiceDeliverable` records through backend services only.

### 4. CRM & Lifecycle

Owns:

- Lifecycle use of the same campaign: email/SMS/WhatsApp ideas, lead capture offers, segmentation, abandoned cart or product-interest nurture, and customer journey.
- Ensures campaign deliverables can be reused beyond social media.

Produces:

- `crm_segment_plan`
- `email_or_whatsapp_copy`
- `lifecycle_calendar`
- `retention_followups`

Handoff requirements:

- CRM deliverables reference Strategy audience and Brand copy.
- CRM may be optional for weekend MVP but must exist as a visible stage with skipped/deferred status, not silently absent.

### 5. Analytics & Performance

Owns:

- KPI definitions, UTMs, measurement plan, reporting shell, experiment hypotheses, and post-launch readout structure.
- Performance review loops for the next batch.

Produces:

- `kpi_plan`
- `utm_plan`
- `experiment_plan`
- `reporting_template`

Handoff requirements:

- Analytics receives all channel publish packages.
- Analytics state is backend-owned and can create follow-up tasks, but events alone are not durable evidence of analysis completion.

### 6. QA & Compliance

Owns:

- Brand QA, format QA, spelling, claims, accessibility checks where applicable, export validation, and platform spec checks.
- Verifies deliverables are client-safe before approval routing.

Produces:

- `qa_report`
- `issue_list`
- `compliance_status`
- `asset_validation_results`

Handoff requirements:

- Approval Ops cannot request final client approval until QA & Compliance has passed or explicitly waived each blocker in durable backend state.

### 7. Client/Approval Ops

Owns:

- Client review package, approval state, revision requests, final acceptance, and delivery summary.
- Tracks what Mike/client approved, rejected, or requested to revise.

Produces:

- `client_review_package`
- `approval_record`
- `revision_request`
- `final_delivery_summary`

Handoff requirements:

- Final delivery is only complete when Approval Ops records a backend-owned approval or an explicit internal MVP acceptance.

## Target Workflow

The Legacy deliverable pipeline should be modeled as department-stage routing:

1. Create a Legacy project/campaign run.
2. Backend creates ordered department stages for the run.
3. Strategy & Research produces briefs and measurement constraints.
4. Brand & Content transforms briefs into copy, concepts, and asset prompts.
5. Channel Execution generates/export assets and channel packages.
6. CRM & Lifecycle creates lifecycle extensions or records a durable deferred/skipped status for the weekend MVP.
7. Analytics & Performance attaches tracking/reporting artifacts.
8. QA & Compliance validates all deliverables and assets.
9. Client/Approval Ops packages work and records approval/revision state.

Each stage has:

- durable status: `pending`, `ready`, `in_progress`, `blocked`, `needs_revision`, `completed`, `skipped`
- owner department
- input artifact references
- output artifact references
- blocking issues
- revision links
- started/completed timestamps
- backend-generated audit trail

Events may mirror stage changes to the whiteboard, but the backend stage record is authoritative.

## Data Model Changes

Add or extend backend-owned entities:

### `Department`

Likely fields:

- `id`
- `slug`
- `displayName`
- `description`
- `responsibilitySummary`
- `defaultOrder`
- `isActive`

Seed departments:

- `strategy_research`
- `brand_content`
- `channel_execution`
- `crm_lifecycle`
- `analytics_performance`
- `qa_compliance`
- `client_approval_ops`

### `DepartmentPipelineTemplate`

Represents reusable pipeline definitions for service types.

Likely fields:

- `id`
- `slug`
- `name`
- `clientType` or `serviceType`
- `departmentOrder`
- `requiredStageSlugs`
- `optionalStageSlugs`
- `createdAt`
- `updatedAt`

Legacy default: `legacy_marketing_weekend_mvp`.

### `DepartmentStage`

Durable stage instance for a project/campaign/service run.

Likely fields:

- `id`
- `projectId` or `clientId`
- `serviceRunId` or `campaignRunId`
- `departmentId`
- `pipelineTemplateId`
- `sequence`
- `status`
- `title`
- `inputArtifactIds`
- `outputArtifactIds`
- `blockingIssueIds`
- `revisionOfStageId`
- `startedAt`
- `completedAt`
- `skippedReason`
- `createdAt`
- `updatedAt`

### `ArtifactLineage`

If no equivalent exists, add lineage between briefs, copy, assets, deliverables, QA reports, and approval packages.

Likely fields:

- `id`
- `sourceArtifactType`
- `sourceArtifactId`
- `targetArtifactType`
- `targetArtifactId`
- `relationship`
- `createdByDepartmentStageId`
- `createdAt`

### Extend `ServiceDeliverable`

Add or verify fields:

- `departmentStageId`
- `owningDepartmentId`
- `sourceBriefId`
- `status`
- `qaStatus`
- `approvalStatus`
- `lineageRootId`

### Extend `Asset`

Add or verify fields:

- `departmentStageId`
- `owningDepartmentId`
- `sourceDeliverableId`
- `sourceConceptId`
- `channel`
- `format`
- `variant`
- `qaStatus`
- `approvalStatus`

### Extend `TaskRoutingRecord`

Convert from post-hoc label to durable routing/action record.

Add or verify fields:

- `departmentStageId`
- `fromDepartmentId`
- `toDepartmentId`
- `routingReason`
- `requiredInputs`
- `expectedOutputs`
- `status`
- `decidedBy`
- `createdAt`
- `resolvedAt`

Do not make `TaskRoutingRecord` the only source of stage truth. It should explain routing decisions; `DepartmentStage` should own durable stage status.

## API Changes

Backend APIs should support department-stage orchestration:

- `GET /departments` returns seeded department list and responsibilities.
- `GET /projects/:projectId/department-pipeline` returns pipeline template, stage instances, statuses, artifact references, and blockers.
- `POST /projects/:projectId/department-pipeline` creates a pipeline from a template.
- `POST /department-stages/:stageId/start` transitions stage to `in_progress`.
- `POST /department-stages/:stageId/complete` records output artifact IDs and completes the stage.
- `POST /department-stages/:stageId/block` records blockers.
- `POST /department-stages/:stageId/request-revision` creates a durable revision request.
- `POST /department-stages/:stageId/skip` records durable skip/defer state for optional weekend MVP stages.
- `POST /legacy/campaign-runs` or existing project-run endpoint accepts Legacy campaign goals and creates the department pipeline.
- `POST /legacy/campaign-runs/:runId/generate-weekend-mvp` starts orchestration through stages, if a Legacy-specific route is acceptable for the MVP.

API contract principles:

- Responses return backend-owned state snapshots.
- Event streams may broadcast changes but clients must refetch or reconcile from backend state.
- Mutations validate allowed transitions server-side.
- The engine receives immutable stage input payloads and returns proposed outputs; backend services persist accepted outputs and stage transitions.

## Service/Orchestration Changes

Add or modify backend services so the pipeline is authoritative:

- Department registry/seeding service.
- Pipeline template service.
- Stage transition service with explicit transition validation.
- Artifact lineage service.
- Legacy campaign pipeline factory.
- Department execution orchestrator that calls existing generation services stage-by-stage.
- QA gate service.
- Approval package service.

Engine integration should change from:

`generate assets -> create deliverables/assets -> attach department labels`

to:

`create backend pipeline -> execute Strategy stage -> persist Strategy outputs -> route to Brand stage -> persist Brand outputs -> route to Channel stage -> persist channel outputs -> continue through CRM/Analytics/QA/Approval`

The engine should never decide final durable stage status by itself. It can return execution results such as generated text, image paths, video paths, candidate QA findings, or suggested routing. Backend services validate and persist.

## Whiteboard UX And State Changes

Atlas whiteboard should become a department workflow board for campaign runs.

### Board Structure

- Horizontal lanes or columns for the seven departments.
- Cards/nodes for department stages, deliverables, assets, QA issues, and approval package.
- Edges show artifact lineage and handoffs.
- Stage status badges render backend-owned statuses.
- Blockers and revision requests appear as first-class nodes or badges.

### State Rules

- Whiteboard state is a projection of backend pipeline state.
- Drag/drop or manual reroute sends an intent mutation to backend.
- The client optimistically displays pending changes only as transient UI state and reconciles from backend response.
- Board snapshots are backend-owned. The UI must not persist independent authoritative snapshots.
- Events update the board for responsiveness, but refresh/recovery must be possible from backend `GET /projects/:projectId/department-pipeline`.

### UX Requirements

- Department cards show: responsibility, inputs, outputs, status, blockers, owner.
- Selecting a stage opens an inspector with input artifacts, generated outputs, lineage, and allowed actions.
- Legacy weekend MVP board defaults CRM & Lifecycle to `skipped` or `deferred` only if backend records the skip reason.
- QA & Compliance must visibly gate Client/Approval Ops.
- Approval Ops view packages all final deliverables with approval/revision actions.

## Legacy-Specific Weekend MVP

Goal: prove the pipeline by generating a smaller Legacy batch through departments end-to-end.

### MVP Input

Legacy brand context from `C:/Users/mathi/projects/legacy/front`:

- CDMX glasswear/sunglasses brand.
- Existing site/product tone and visual references.
- Weekend campaign objective, assumed: produce a client-reviewable organic social package plus approval record.

Implementation should read Legacy repo content during generation, but copied durable facts should be persisted in ForgeGraph backend as Strategy outputs. The Legacy frontend repo must not become ForgeGraph's durable state store.

### MVP Output

Required through pipeline:

- Strategy & Research:
  - one concise campaign strategy brief
  - one audience/positioning note
  - one measurement plan
- Brand & Content:
  - one copy pack
  - six post concepts
  - one reel concept/script
  - asset generation prompts
- Channel Execution:
  - six PNG Instagram posts
  - one MP4 reel
  - one social calendar
  - channel publish package metadata
- CRM & Lifecycle:
  - weekend MVP may create one lifecycle extension note, or record a backend-owned `skipped` status with reason: `not_required_for_weekend_social_mvp`
- Analytics & Performance:
  - KPI/UTM/reporting template
- QA & Compliance:
  - QA report for text, format, brand consistency, file existence, and channel dimensions
- Client/Approval Ops:
  - client review package
  - approval/revision record

### MVP Constraints

- Reuse existing generation/export capability where possible.
- Preserve existing `ServiceDeliverable`, `Asset`, and `TaskRoutingRecord` records, but create them from department stages.
- Include deterministic fixture mode for tests so PNG/MP4 existence and metadata can be validated without flaky creative generation.
- Do not require full CRM automation before the weekend MVP can demonstrate the department pipeline.

## Validation And Tests

### Unit Tests

- Department seed list contains exactly the seven required departments.
- Pipeline template creates stages in the required order.
- Stage transition validation rejects invalid jumps, such as Approval before QA pass.
- `TaskRoutingRecord` cannot complete a stage without backend stage transition.
- `ServiceDeliverable` and `Asset` require `departmentStageId` for new Legacy pipeline outputs.
- Artifact lineage links Strategy outputs to Brand outputs and Brand outputs to Channel assets.

### Service Tests

- Creating a Legacy campaign run creates all seven stages.
- Running the weekend MVP completes Strategy, Brand, Channel, Analytics, QA, and Approval stages.
- CRM stage is either completed with lifecycle output or skipped with durable reason.
- QA failure blocks Approval Ops.
- Revision request moves the correct upstream stage to `needs_revision`.
- Recovery from persisted backend state resumes at the first incomplete required stage.

### API Tests

- `GET /departments` returns department responsibilities.
- `GET /projects/:projectId/department-pipeline` reconstructs board state from backend records.
- Stage mutation endpoints enforce authorization and allowed transitions.
- Event stream messages are consistent with persisted backend state but are not needed to reconstruct state.

### UI Tests

- Whiteboard renders seven department lanes.
- Stage cards show backend statuses and output counts.
- QA gate prevents approval action when QA is blocked.
- Manual reroute sends backend mutation and reconciles board state.
- Reloading the board reconstructs all stages from backend snapshot.

### Legacy E2E Test

- Given Legacy fixture inputs, run `legacy_marketing_weekend_mvp`.
- Verify durable records:
  - seven `DepartmentStage` records
  - generated Strategy, Brand, Channel, Analytics, QA, Approval deliverables
  - six PNG `Asset` records
  - one MP4 `Asset` record
  - lineage from brief -> concepts/copy -> channel assets -> QA -> approval package
  - `TaskRoutingRecord` entries for each handoff
- Verify files exist and metadata matches expected dimensions/formats.
- Verify final approval package can be opened from the whiteboard.

## Acceptance Criteria

- Mike can list the seven departments in Atlas and see clear responsibilities for each.
- Starting a Legacy campaign creates a department pipeline before generation begins.
- Legacy deliverables are generated stage-by-stage through the pipeline.
- Every new Legacy `ServiceDeliverable` and `Asset` has an owning department stage.
- `TaskRoutingRecord` records handoffs and routing decisions, not post-hoc labeling.
- The whiteboard shows department lanes, stage status, lineage, blockers, and approval gate.
- Reloading or recovering the board uses backend state only.
- QA & Compliance can block Client/Approval Ops.
- CRM & Lifecycle is explicit in the pipeline, even if skipped/deferred for weekend MVP.
- The weekend MVP produces a client-reviewable package: strategy brief, copy pack, social calendar, 6 PNG posts, 1 MP4 reel, QA report, analytics template, and approval record.
- Automated tests prove stage order, durable state ownership, routing, lineage, QA gating, and backend-state recovery.

## Risks And Mitigations

- Risk: Existing code treats events or engine state as effective source of truth.
  - Mitigation: add backend stage records first; events only mirror committed transitions.

- Risk: Department pipeline becomes a UI-only board.
  - Mitigation: require all whiteboard reload/recovery paths to use backend pipeline snapshot.

- Risk: Post-hoc labels remain for old deliverables and confuse MVP validation.
  - Mitigation: separate legacy/imported records from new pipeline-created records with a `createdViaDepartmentPipeline` flag or equivalent migration marker.

- Risk: Full CRM automation delays the weekend MVP.
  - Mitigation: allow durable skipped/deferred CRM stage with explicit reason while preserving the lane and workflow semantics.

- Risk: Media generation is flaky or slow in tests.
  - Mitigation: add deterministic fixture mode that creates known-good test assets and validates orchestration separately from creative generation quality.

- Risk: QA gate blocks demo progress due unresolved automated checks.
  - Mitigation: support explicit backend-owned QA waiver with reason and actor, but make it visible in the approval package.

- Risk: File/model names differ from this plan.
  - Mitigation: start implementation with `rg "ServiceDeliverable|TaskRoutingRecord|Asset|Hermes|Atlas|whiteboard|department|routing"` and update exact file targets before editing.

## Exact Likely Files To Inspect Or Change

The sandbox could not be read while this plan was authored, so these are exact likely targets to verify with `rg` before implementation. Do not edit runtime code until `docs/architecture/runtime-invariants.md` has been read in the implementation turn.

### Required Architecture/Docs

- `docs/architecture/runtime-invariants.md`
- `docs/architecture/department-pipeline.md` or new equivalent
- `.hermes/plans/20260605-000000-legacy-department-pipeline-plan.md`

### Backend Models And Migrations

- `backend/**/models/*deliverable*`
- `backend/**/models/*asset*`
- `backend/**/models/*routing*`
- `backend/**/models/*project*`
- `backend/**/models/*task*`
- `backend/**/migrations/*`
- `server/**/models/*deliverable*`
- `server/**/models/*asset*`
- `server/**/models/*routing*`
- `apps/**/api/**/models*`
- `packages/**/database/**`
- `packages/**/db/**`
- `prisma/schema.prisma`
- `drizzle.config.*`
- `src/**/entities/*deliverable*`
- `src/**/entities/*asset*`
- `src/**/entities/*routing*`

### Backend Services

- `backend/**/services/*deliverable*`
- `backend/**/services/*asset*`
- `backend/**/services/*routing*`
- `backend/**/services/*department*`
- `backend/**/services/*pipeline*`
- `backend/**/services/*hermes*`
- `backend/**/services/*legacy*`
- `server/**/services/*deliverable*`
- `server/**/services/*asset*`
- `server/**/services/*routing*`
- `server/**/services/*department*`
- `server/**/services/*pipeline*`
- `packages/**/services/**`
- `src/**/services/**`
- `src/**/application/**`
- `src/**/domain/**`

### API Routes/Controllers

- `backend/**/routes/**`
- `backend/**/controllers/**`
- `server/**/routes/**`
- `server/**/controllers/**`
- `apps/**/api/**`
- `app/api/**`
- `src/**/routes/**`
- `src/**/controllers/**`
- `src/**/api/**`

Search terms:

- `ServiceDeliverable`
- `ServiceDeliverables`
- `TaskRoutingRecord`
- `TaskRoutingRecords`
- `Asset`
- `Assets`
- `department`
- `routing`
- `whiteboard`
- `Hermes`
- `Atlas`
- `Legacy`

### Engine/Hermes Generation

- `hermes/**`
- `.hermes/**`
- `engine/**`
- `workers/**`
- `packages/**/engine/**`
- `packages/**/hermes/**`
- `src/**/engine/**`
- `src/**/hermes/**`
- `src/**/workers/**`
- `scripts/**/legacy*`
- `scripts/**/generate*`
- `scripts/**/hermes*`

Expected changes:

- replace direct Legacy generation entry point with department-stage orchestrated run
- add stage-specific execution adapters
- ensure generated outputs are persisted by backend services

### Atlas Whiteboard UI

- `apps/**/atlas/**`
- `apps/**/web/**/atlas/**`
- `apps/**/web/**/whiteboard/**`
- `app/**/atlas/**`
- `app/**/whiteboard/**`
- `components/**/whiteboard/**`
- `components/**/atlas/**`
- `src/**/components/**/whiteboard/**`
- `src/**/components/**/atlas/**`
- `src/**/features/**/whiteboard/**`
- `src/**/features/**/atlas/**`
- `src/**/stores/**`
- `src/**/state/**`

Expected changes:

- department lane view
- stage inspector
- backend snapshot fetch
- event reconciliation
- QA approval gate UI

### Shared Types

- `packages/**/types/**`
- `packages/**/contracts/**`
- `src/**/types/**`
- `src/**/schemas/**`
- `shared/**`
- `common/**`

Expected changes:

- `Department`
- `DepartmentPipelineTemplate`
- `DepartmentStage`
- stage status enum
- artifact lineage contract
- department pipeline API response schema

### Tests

- `backend/**/tests/**`
- `server/**/tests/**`
- `apps/**/__tests__/**`
- `apps/**/tests/**`
- `tests/**`
- `e2e/**`
- `playwright/**`
- `cypress/**`
- `src/**/__tests__/**`
- `src/**/*.test.*`
- `src/**/*.spec.*`

Expected additions:

- stage transition tests
- pipeline creation tests
- Legacy weekend MVP service test
- whiteboard rendering/reload tests
- QA gate tests
- event-vs-backend recovery tests

## Implementation Sequence

1. Re-read `docs/architecture/runtime-invariants.md`.
2. Use `rg` to locate existing deliverable, asset, routing, Hermes, Atlas, and whiteboard code.
3. Document exact existing flow for the first Legacy batch.
4. Add department registry and pipeline model behind backend services.
5. Add migrations/seeds for seven departments and Legacy weekend MVP template.
6. Add stage transition service with validation.
7. Add/extend API contracts for departments and pipeline snapshot/mutations.
8. Change Legacy generation to create pipeline first and execute stage-by-stage.
9. Ensure all generated deliverables/assets reference department stage and lineage.
10. Add QA gate and approval package service.
11. Update Atlas whiteboard to render backend pipeline snapshot as department lanes.
12. Add tests in the order: model/service, API, UI, Legacy E2E.
13. Run the Legacy weekend MVP fixture and compare against acceptance criteria.

