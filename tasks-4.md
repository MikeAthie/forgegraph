# Phase 4 - Observability MVP (Week 8)

**Goal:** "Debug like software".

**Deliverable:** You can see node-by-node execution results (status, output/error, timings) for each workflow run.

**Status:** MVP complete: runs list + trace viewer + editor execution overlay. Live updates: WebSocket delta events with polling fallback (run detail), polling in editor overlay. Go engine execution is still deferred.

> Note: We're still skipping the Go engine for now. Use `seed_phase4_demo`, `seed_run_trace`, and `stream_run_trace` to validate the UI (including live WebSocket deltas) without engine execution.

---

## 1. Backend - Data Model & Persistence

- [x] 1.1 Create `NodeRun` model (Control Plane)
  - [x] Stored fields: `id`, `run`, `node_id`, `node_type`, `status`, `attempt`, `started_at`, `ended_at`, `input_json`, `output_json`, `error_json`
  - [x] Derived timing: `duration_ms` property (computed from timestamps)
- [x] 1.2 Migration for `NodeRun`
  - [x] Table created in `backend/infrastructure/orm/migrations/0001_initial.py`
- [x] 1.3 Update `Run` model (if needed)
  - [x] Status includes `canceled`
  - [x] Has `started_at` / `ended_at` and `duration_ms` property
- [x] 1.4 Data access optimization
  - [x] Indexes for run + node run retrieval
  - [x] API uses `select_related` / `prefetch_related`
- [x] 1.5 Trace persistence integration (control-plane hooks)
  - [x] MVP utilities: `backend/infrastructure/orm/management/commands/seed_phase4_demo.py`, `backend/infrastructure/orm/management/commands/seed_run_trace.py`, `backend/infrastructure/orm/management/commands/stream_run_trace.py`
  - [x] Engine-ready ingestion API: `POST /api/runs/{id}/events` persists + broadcasts delta events
  - [x] Go engine integration deferred (see **Deferred** section)

---

## 2. Backend - Runs API Endpoints

- [x] 2.1 Implement `GET /api/runs/` (RunListView)
  - [x] Filters by `owner == request.user`
  - [x] Includes graph context (`graph_name`, version)
  - [x] Tested (auth required, user isolation, ordering)
- [x] 2.2 Implement `GET /api/runs/{id}` (RunDetailView)
  - [x] Ownership enforced (404 for missing/other user)
  - [x] Includes ordered `node_runs` with timing/output/error
  - [x] Tested (fields + ordering + empty node_runs)
  - [x] Node display names resolved in frontend via `GraphVersion.graph_json`
- [x] 2.3 Implement `POST /api/runs/start` (RunStartView)
  - [x] Request validation (`graph_version_id`, optional `input_json`)
  - [x] Create `Run` record (control-plane DB)
  - [x] Engine call deferred (see **Deferred** section)
  - [x] Return 201 with new `run_id`
- [x] 2.4 Implement `POST /api/runs/{id}/cancel` (RunCancelView)
  - [x] Validate ownership + run state
  - [x] Update `Run` status to `canceled` (control-plane DB)
  - [x] Engine cancel deferred (see **Deferred** section)
- [x] 2.5 (Optional) Keep `POST /api/runs/{id}/resume` stubbed (Phase 6)
  - [x] Returns `501 NOT_IMPLEMENTED`
- [x] 2.6 Update serializers (if needed)
  - [x] `RunDetailWithNodeRunsSerializer` nests `NodeRunSerializer`
  - [x] Includes `duration_ms`
- [x] 2.7 Update Django admin
  - [x] `NodeRun` registered; `RunAdmin` shows NodeRuns inline
- [x] 2.8 Documentation
  - [x] Runs section updated in `backend/API_QUICK_REFERENCE.md`
- [x] 2.9 Backend tests
  - [x] List + detail integration tests
  - [x] Start + cancel integration tests (control-plane behavior)
  - [x] Engine integration tests deferred (see **Deferred** section)

---

## 3. Frontend - Run History Page (Executions List)

- [x] 3.1 Create runs list page (`/runs`)
- [x] 3.2 Display runs in a table/list (graph, status, started, duration)
- [x] 3.3 Visual status indicators (badges/icons)
- [x] 3.4 Click-through to run detail (`/runs/[id]`)
- [x] 3.5 (Optional) Filters (status, graph)
- [x] 3.6 Loading & error states
- [x] 3.7 UX polish (empty state, responsive table)

---

## 4. Frontend - Run Detail (Execution Trace Viewer)

- [x] 4.1 Create run detail page (`/runs/[id]`)
- [x] 4.2 Display run overview (workflow, status, timings, errors)
  - [x] Shows workflow name + version, status badge, started/ended/duration, run id
  - [x] Shows `error_message` when run is failed/canceled
  - [x] Live-updating duration while running
- [x] 4.3 Node-by-node execution list (ordered)
  - [x] Shows node name (from graph JSON), type, status, attempt, duration
- [x] 4.4 Node input/output/error details (expandable, formatted JSON)
- [x] 4.5 Final output summary (surface `Run.output_json`)
- [x] 4.6 Live status updates via polling (stop on terminal status)
- [x] 4.7 Error handling (404/unauthorized, polling failures)
- [x] 4.8 UI/UX polish (sticky detail panel, scroll handling)
- [x] 4.9 (Optional) Re-run capability

---

## 5. Frontend - Graph Editor Execution Integration (Stretch)

- [x] 5.1 Add "Run Workflow" button in editor (`/graphs/[graphId]`)
- [x] 5.2 Show node execution status on the canvas
  - [x] Execution mode: `/graphs/{graphId}?runId={runId}` (linked from run detail via "Open in editor")
- [x] 5.3 Node output panel in editor (results mode)
  - [x] Right-side execution panel shows per-attempt inputs/outputs/errors for the selected node
- [x] 5.4 Provide "Stop/Cancel" control (calls cancel endpoint)
  - [x] Available in execution mode when the run is non-terminal
- [x] 5.5 Post-run reset (restore edit mode / clear transient state)
  - [x] Exit button returns to normal editor view (removes `runId` param)
- [x] 5.6 Testing & UX pass
  - [x] Runs list/detail covered by E2E + backend integration tests; editor execution overlay validated via manual smoke test (see README)

---

## 6. Real-Time Updates - Live Execution Feedback (WebSockets) (Stretch)

- [x] 6.1 Backend: WebSocket setup (Django Channels + auth)
- [x] 6.2 Backend: Event broadcasting (engine/control-plane -> channel layer)
- [x] 6.3 Frontend: WebSocket client (fallback to polling)
- [x] 6.4 UI feedback driven by events (instant node updates, progress)
- [x] 6.5 Testing (manual + resilience)
  - [x] Backend WS integration tests
  - [x] Manual smoke test in Docker (see README "Observability Demo (Phase 4)")

---

## 7. Miscellaneous & Polish

- [x] 7.1 Permissions & security audit (runs + WS)
  - [x] Runs list/detail endpoints are owner-scoped
  - [x] Start/cancel endpoints are owner-scoped
  - [x] WS consumer is owner-scoped
- [x] 7.2 Validate data sizes / large payload handling
  - [x] UI JSON rendering truncates deeply nested / huge payloads (`frontend/lib/json.ts`)
- [x] 7.3 Documentation & README updates
- [x] 7.4 Demo scenarios / seed workflows for observability
  - [x] `seed_phase4_demo` seeds a demo graph + runs; `stream_run_trace` streams deltas over WS
- [x] 7.5 UX review vs n8n/LangChain traces
  - [x] Run list + trace viewer matches the "execution list + per-node details" mental model (polling + WS deltas)
- [x] 7.6 Future hooks (filtering/search, external tracing integrations)
  - [x] See **Deferred** + future notes below

---

## Deferred (Engine Integration)

- [ ] Engine: execute graphs and persist traces (writes `Run` + `NodeRun` during execution)
- [ ] Control plane: call engine over gRPC for `start` / `cancel`
- [ ] End-to-end engine execution tests (runs list/detail driven by real engine traces)

---

## Summary Checklist

| Section | Tasks | Status |
|---------|-------|--------|
| 1. Backend - Data Model & Persistence | 5 | Done |
| 2. Backend - Runs API Endpoints | 9 | Done |
| 3. Frontend - Run History Page | 7 | Done |
| 4. Frontend - Run Detail Viewer | 9 | Done |
| 5. Editor Execution Integration | 6 | Done |
| 6. Real-Time Updates (WebSockets) | 5 | Done |
| 7. Miscellaneous & Polish | 6 | Done |

**Total: ~47 tasks (+ deferred engine integration)**
