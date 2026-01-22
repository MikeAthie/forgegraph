# ForgeGraph — Project Spec (MVP Blueprint)

Version: 0.1
Status: Draft (MVP)
Owner: GreyX
Last updated: 2026-01-13

## 1. One-liner

A visual, high-performance workflow engine for AI agents and automation, built for production.

## 2. Core promise

Design agent workflows visually. Run them reliably at scale. Debug them like software.

## 2.1 Design Principles

ForgeGraph uses a **schema-driven, LangGraph-style runtime** with an **n8n-inspired UX**:

- **Agnostic execution primitives** - A small, stable set of node types that can express most workflows
- **Schema-first reliability** - Outputs can be validated and structured (e.g., JSON Schema / Pydantic-like validation) to reduce hallucinations
- **N8n-like UX, LangGraph-like semantics** - Easy graph building with real runtime logic (start nodes, conditional edges, merging, final output)
- **State-driven execution** - Nodes read from and write to a shared run state

## 3. Target users

Primary:
- Developers
- AI engineers
- Tech-savvy operators
- Indie hackers building internal automation

Secondary:
- Small teams needing reliable internal AI workflows
- Dev tooling evaluators (portfolio / hiring managers)

## 4. Non-goals (MVP)

Not in MVP:
- Multi-tenant enterprise features (SSO/SAML, SCIM)
- Marketplace monetization
- Team permissions beyond basic ownership
- External "public prompt scraping"
- Full plugin SDK or sandboxed arbitrary code execution
- Full LangChain compatibility layer
- Full "Temporal-level" durability (we implement a lighter version)

## 5. MVP feature scope

### 5.1 Visual Graph Builder (Frontend)
- Drag nodes onto canvas
- Connect nodes with edges
- Select node to edit configuration in a side panel
- Save graph as JSON (GraphVersion) via control plane API
- Load and edit previously saved graphs
- Basic graph validation (client-side)
  - cannot have orphaned required inputs (best-effort)
  - prevent obvious cycles unless explicitly supported later

### 5.2 Execution Engine (Go)
- Load Graph JSON
- Build execution plan:
  - Validate graph structure (DAG for MVP)
  - Build adjacency + indegree tracking
- Execute nodes with:
  - Concurrency (parallel branches)
  - Retries (per-node policy)
  - Timeouts (per-node policy)
- Collect:
  - Node outputs
  - Logs
  - Timings (start/end/duration)
  - State snapshots (key-value "state")

### 5.3 Node types (initial)
Minimum set of agnostic execution primitives:

| Node | Description |
|------|-------------|
| **Prompt** | Calls LLM with structured instructions, can target an output schema, writes validated output to state |
| **Tool (HTTP)** | Generic tool executor (HTTP as baseline), UX uses "service pills" as presets, writes response to state |
| **Transform** | Deterministic state transforms (mapping, formatting, extraction), writes derived values to state |
| **Branch** | Evaluates conditions → routes execution to exactly one path (true/false edges) |
| **Merge** | Waits for multiple inputs → continues downstream (synchronization barrier) |
| **Human Gate** | Pauses run → resumes on approval/input |
| **Output** | Collects + validates final result → ends run |

**State keys:**
- `node.<id>.output` - Node execution output
- `vars.<name>` - Computed variables from transform nodes
- `input.<name>` - Run input values

### 5.4 Prompt Library
- Ship with 10+ original prompts
- Categories:
  - research
  - summarization
  - email drafting
  - extraction
  - reasoning
- UI:
  - browse → view → clone → customize

### 5.5 User prompt upload and publish
- Users can create and store their own prompt templates
- Private by default
- Optional publish:
  - title
  - description
  - license
  - version
- No scraping, no copying

### 5.6 Run history and "debug like software"
- Run list per user
- Run detail view:
  - node timeline/status
  - per-node input/output preview
  - errors and retry attempts
  - timings
- Live run updates:
  - MVP can poll
  - v1 uses SSE or WebSockets

## 6. Architecture overview

### 6.1 Services
Monorepo services:

1) frontend (NextJS)
- Graph builder UI
- Prompt library UI
- Run viewer UI
- Talks to control plane via REST

2) control-plane (Django + DRF)
- Auth + users
- Graph CRUD + versioning
- Prompt CRUD + publishing
- Run summary APIs
- Human gate actions (approve/resume)
- Talks to engine via gRPC

3) engine (Go)
- gRPC API
- Workflow scheduler + executors
- Trace emitter + persistence
- Calls external services (LLM, HTTP APIs)

4) postgres (DB)
- Shared persistent store for control plane + engine
- Stores graphs, prompts, runs, traces

5) redis (optional MVP)
- Reserved for:
  - event bus
  - queue
  - pubsub for live trace

### 6.2 Why Django + Go split
- Django provides fast shipping for product surface:
  - auth, admin, CRUD reliability
- Go provides high-performance runtime:
  - concurrency, scheduling, timeouts, predictable behavior

### 6.3 Communication
- Frontend <-> Control Plane: REST + JSON
- Control Plane <-> Engine: gRPC
- Engine -> Control Plane/UI updates:
  - MVP: writes to DB; UI polls
  - v1: gRPC stream to control plane + SSE to frontend
  - optional: Redis Streams/NATS for event bus

## 7. Data model (Control Plane)

### 7.1 User
- id (uuid)
- email
- password_hash (if not external auth)
- created_at

### 7.2 Graph
- id (uuid)
- owner_id (user uuid)
- name
- description
- created_at
- updated_at

### 7.3 GraphVersion
- id (uuid)
- graph_id
- version (int)
- graph_json (jsonb)
- created_at
- checksum (string) optional

### 7.4 PromptTemplate
- id (uuid)
- owner_id nullable (null = built-in prompt)
- title
- description
- category
- content (text)
- variables_schema (jsonb) optional
- version (string)
- license (string)
- visibility (private/public)
- created_at
- updated_at

### 7.5 Run
- id (uuid)
- owner_id
- graph_version_id
- status (RUNNING/PAUSED/SUCCEEDED/FAILED/CANCELED)
- started_at
- ended_at
- input_json (jsonb)
- output_json (jsonb) optional
- error_message optional

### 7.6 NodeRun
- id (uuid)
- run_id
- node_id (string)
- node_type (string)
- status
- attempt (int)
- started_at
- ended_at
- duration_ms
- input_json (jsonb)
- output_json (jsonb)
- error_json (jsonb)

### 7.7 TraceEvent (optional table; can be embedded in NodeRun for MVP)
- id (uuid)
- run_id
- ts
- type (NODE_STARTED/NODE_OUTPUT/etc)
- node_id
- payload_json

## 8. Graph JSON contract (MVP)

### 8.1 Top-level
- graph_id
- version_id
- nodes: []
- edges: []
- metadata: {name, description}

### 8.2 Node schema
Each node:
- id (string)
- type (enum: prompt, http, transform, branch, merge, human_gate, output)
- name (string)
- config (object) - type-specific configuration
- retry_policy (object) optional
- timeout_ms (int) optional

### 8.3 Edge schema
Each edge:
- id (string)
- from (node_id)
- to (node_id)
- label (string) optional - used for branch routing ("true"/"false")

**Edge semantics:**
- Edges define execution dependencies and data flow
- For branch nodes, edges use `label: "true"` or `label: "false"` to indicate conditional paths
- Non-labeled edges are always followed when the source node completes
- Merge nodes wait for all incoming edges before continuing

### 8.4 State passing
Engine maintains a shared `map[string]any` state:
- `state["node.<id>.output"]` - Node execution output
- `state["vars.<name>"]` - Computed variables
- `state["input.<name>"]` - Run input values

**State resolution in expressions:**
- `vars.score` → `state["vars.score"]`
- `node.http_1.output.status` → `state["node.http_1.output"]["status"]`
- `input.mode` → `state["input.mode"]`

## 9. Execution semantics (Go engine)

### 9.1 Start nodes
- Any node with no incoming edges (indegree = 0) is a start node
- Multiple start nodes run in parallel
- Start nodes receive initial run input in state

### 9.2 Scheduling
- Queue-based execution with worker pool (goroutines)
- Nodes become ready when all upstream dependencies are satisfied
- Ready nodes execute concurrently (up to max workers)
- Configurable max concurrency (global default, per-run override planned)

### 9.3 Branching
- Branch nodes evaluate boolean conditions against state
- Condition syntax: `vars.score > 80`, `node.http_1.output.status == 200`
- Supported operators: `==`, `!=`, `>`, `<`, `>=`, `<=`
- Activates exactly one outgoing edge path (true or false)
- Non-selected branches are marked as skipped (not executed)

### 9.4 Merging
- Merge nodes wait until all incoming branches complete
- Acts as synchronization barrier before continuing downstream
- Merge strategies:
  - **namespaced** (default): Each input preserved under `merged[nodeID]`
  - **last_write_wins**: Map values merged, later overwrites earlier
- Skipped branches are excluded from merge (gracefully handled)

### 9.5 Retries
- Per-node retry_policy:
  - max_attempts
  - backoff_ms
  - backoff_strategy (fixed/exponential)
- Retry only for retryable errors:
  - network errors
  - 5xx errors from APIs
  - LLM transient errors
- No retry for:
  - invalid config
  - user expression parse errors

### 9.6 Timeouts and cancellation
- Each node executes with context timeout
- Cancel run:
  - marks run as CANCELED
  - cancels context for active workers
  - in-flight nodes complete gracefully

### 9.7 Human gate node
- On reaching human gate:
  - persist PAUSED run status
  - persist required payload (what user must approve)
  - stop scheduling downstream nodes
- Resume:
  - add human input into state
  - continue execution from next node(s)

## 10. APIs

### 10.1 Control Plane REST (frontend-facing)
Minimum endpoints:
- GET /health
- POST /auth/login (or NextAuth external)
- GET /prompts
- POST /prompts
- POST /prompts/{id}/publish
- GET /graphs
- POST /graphs
- GET /graphs/{id}/versions
- POST /graphs/{id}/versions
- POST /runs/start (calls engine gRPC)
- GET /runs
- GET /runs/{id}
- POST /runs/{id}/resume (calls engine gRPC)
- POST /runs/{id}/cancel (calls engine gRPC)

### 10.2 Engine gRPC
- Ping
- StartRun
- GetRun
- CancelRun
- ResumeRun
- StreamRunEvents (v1)

## 11. Security

MVP baseline:
- Auth required for all user resources
- Graphs/prompts scoped by owner
- Credentials stored encrypted:
  - use Django encryption approach or libsodium
- No arbitrary code execution in Transform node (MVP)
- Rate limiting:
  - per-user run start limits (basic)

## 12. Observability

MVP:
- Persist NodeRun logs, outputs, timings
- UI shows run trace from DB

v1:
- SSE/WebSocket live trace
- Structured logging in engine
- Metrics endpoint (Prometheus-ready) optional

## 13. UX flows (MVP)

### 13.1 Create and run workflow
1. User signs in
2. Opens prompt library
3. Clones a prompt into a graph
4. Adds HTTP node + branch + merge
5. Saves graph
6. Clicks Run
7. Watches execution
8. Sees result and per-node outputs
9. Saves graph version

### 13.2 Human gate flow
1. Workflow pauses at Human Gate
2. UI shows approval screen with context
3. User approves/edits
4. Resume triggers engine
5. Workflow continues

## 14. Success criteria

Technical:
- Start and run a graph with >= 5 nodes reliably
- Parallel branches execute concurrently
- Retries and timeouts work
- Human gate pause/resume works
- Run viewer displays node outputs/timings clearly

Product:
- Demo time ~90 seconds from login to result
- Clear "debug like software" trace experience
- Prompts library feels immediately useful

Portfolio:
- Demonstrates:
  - product thinking
  - Go concurrency
  - microservices boundaries
  - clean architecture
  - developer tooling UX
  - observability mindset

## 15. Development roadmap (broad)

- [x] Phase 0: monorepo scaffolding + docker + gRPC ping
- [x] Phase 1: Django models + auth + prompt library
- [x] Phase 2: Next graph builder + save/load JSON
- [x] Phase 3: Go engine basic execution (prompt/http/output)
- [x] Phase 4: Run viewer + persistence
- [x] Phase 5: branch/merge + retry/timeout
- [ ] Phase 6: human gate
- [ ] Phase 7: polish + demo workflows + docs

## 16. Open questions (track here)

- ~~Expression language for Branch/Transform (simple safe DSL vs JS subset)~~ → Resolved: Safe DSL with path resolution (vars.x, node.id.output) and comparison operators
- ~~Merge strategy (namespaced vs explicit key mapping)~~ → Resolved: Both supported - "namespaced" (default) and "last_write_wins"
- Credential vault approach
- Event streaming mechanism (DB polling vs SSE vs Redis Streams)

---
End of spec.
