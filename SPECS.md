# ForgeGraph — Project Spec (MVP Blueprint)

Version: 0.1
Status: Draft (MVP)
Owner: GreyX
Last updated: 2026-01-13

## 1. One-liner

A visual, high-performance workflow engine for AI agents and automation, built for production.

## 2. Core promise

Design agent workflows visually. Run them reliably at scale. Debug them like software.

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
Minimum set:

1) Prompt Node
- Calls LLM provider with prompt template + variables
- Writes output to state

2) HTTP Tool Node
- Calls external HTTP APIs
- Supports headers, query, body
- Writes response to state

3) Transform Node
- Simple transformations on state
- MVP: limited expressions only (no arbitrary code)
- Writes result to state

4) Branch Node
- Evaluates condition expression against state
- Routes execution to matching edge(s)

5) Merge Node
- Joins parallel branches
- Waits for all required predecessors
- Continues with merged state (merge strategy defined)

6) Human Gate Node
- Pauses run and awaits approval or input
- Resume continues execution

7) Output Node
- Finalizes run output
- Optionally triggers webhook (MVP optional)

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
- type (enum)
- name (string)
- config (object)
- retry_policy (object) optional
- timeout_ms (int) optional
- outputs (list of named outputs) optional

### 8.3 Edge schema
Each edge:
- id (string)
- from (node_id)
- to (node_id)
- condition (string) optional
- label (string) optional

### 8.4 State passing
- Engine maintains a State object:
  - map[string]any
- Each node reads from state and writes:
  - state["node.<id>.output"] = output
  - state["vars.<name>"] = computed variables
- Merge node defines merge strategy:
  - MVP: last-write-wins or namespaced outputs

## 9. Execution semantics (Go engine)

### 9.1 DAG execution
- Identify start nodes (indegree 0)
- Execute nodes when all dependencies satisfied
- Parallel execution for independent nodes

### 9.2 Concurrency model
- Worker pool (goroutines)
- Configurable max concurrency:
  - global default
  - per-run override (later)

### 9.3 Retries
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

### 9.4 Timeouts and cancellation
- Each node executes with context timeout
- Cancel run:
  - marks run as CANCELED
  - cancels context for active workers

### 9.5 Branch node
- Evaluates boolean expression against state
- Routes to first matching outgoing edge
- MVP: allow a default edge with no condition

### 9.6 Merge node
- Waits for all specified predecessors
- Combines outputs into state
- MVP merge strategy:
  - namespaced by node id

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

Phase 0: monorepo scaffolding + docker + gRPC ping
Phase 1: Django models + auth + prompt library
Phase 2: Next graph builder + save/load JSON
Phase 3: Go engine basic execution (prompt/http/output)
Phase 4: Run viewer + persistence
Phase 5: branch/merge + retry/timeout
Phase 6: human gate
Phase 7: polish + demo workflows + docs

## 16. Open questions (track here)
- Expression language for Branch/Transform (simple safe DSL vs JS subset)
- Merge strategy (namespaced vs explicit key mapping)
- Credential vault approach
- Event streaming mechanism (DB polling vs SSE vs Redis Streams)

---
End of spec.
