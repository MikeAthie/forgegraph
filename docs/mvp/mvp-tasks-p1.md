# P1: Product Fit, Debugging, and Official Integrations

## Objective
Turn the P0 technical corrections into a product users can adopt quickly, trust during failures, and understand without engineering support.

If P0 makes ForgeGraph truthful, P1 makes it usable.

## What P1 Must Achieve
At the end of P1, ForgeGraph should be able to make the following promise:

"You can start from a supported workflow, connect the required credentials, run it, understand what happened, and rely on a small set of official integrations."

## Assumptions
P1 assumes P0 is complete or very close:
- real `agent` node exists
- marketplace/runtime semantics are coherent
- Cloud-safe execution policy exists
- graph and event contracts are documented

## What Is Already Done
The following foundations already exist in the repo and should be reused:
- template and onboarding surfaces
- run detail page with node runs and replay hooks
- approvals and HITL pause/resume
- budgets, quotas, usage analytics, and retention models
- quick-add marketplace UI and graph editor infrastructure

P1 is about polish, narrowing, and hardening those flows around the new P0 foundations.

## P1 Exit State
P1 is complete only when all of the following are true:
- [ ] The product has 1-2 narrow, credible MVP journeys.
- [ ] New users can reach first value quickly with clear preflight guidance.
- [ ] The debugger makes failures, branches, and agent steps understandable.
- [ ] Official integrations are verified, documented, and tested end-to-end.
- [ ] The MVP story can be demonstrated without deep repo knowledge or manual fixes.

## Implementation Readiness
This file is ready to drive implementation once P0 is stable enough for product-facing work.

Use these docs as the execution entry point:
- `docs/mvp/forgegraph-mvp-implementation-plan.md`
- `docs/mvp/mvp-tasks-p1.md`

Implementation order for P1:
1. `P1-F01`
2. `P1-F02`
3. `P1-F03`

Start work immediately with these first PRs:
- `P1-F01`: choose the 2 supported MVP journeys, prune template exposure, and add preflight requirements metadata
- `P1-F02`: improve run summary, stop-reason explanation, and agent step grouping before wider debugger polish
- `P1-F03`: define the verified package set and add marketplace metadata/docs before broadening test coverage

No additional phase-planning doc should be needed before opening the first P1 implementation PRs.

---

## P1-F01: Product Packaging and Onboarding Flow

### Feature Description
Refocus the current broad surface area into a small number of high-confidence user journeys with clear setup requirements and fast time-to-value.

This feature is about narrowing the product, not expanding it.

### Why This Is P1
- The repo already has templates, onboarding, credentials, runs, and analytics.
- What is missing is a tight user journey that makes the MVP easy to understand and sell.
- Without packaging, the platform still feels like an engineer-facing toolkit instead of a product.

### User-Facing Outcome
- A new user lands in a guided path.
- The user chooses one of a small set of supported workflows.
- The product checks prerequisites before the run.
- The first successful run happens fast and with minimal confusion.

### Non-Goals for P1
- marketplace breadth
- generic no-code onboarding for every node type
- broad industry templates
- multi-team onboarding paths

### Detailed Tasks

#### F01-T01: Choose the MVP journeys
- [ ] Define exactly 2 supported MVP journeys.
- [ ] Write a short JTBD statement for each journey.
- [ ] Define success output for each journey.
- [ ] Remove or de-emphasize flows that are outside those journeys.

#### F01-T02: Align templates to the journeys
- [ ] Audit existing templates and seeded demos.
- [ ] Keep only high-confidence templates on the MVP surface.
- [ ] Add per-template metadata:
  - purpose
  - required credentials
  - setup time
  - expected output
  - supported runtime mode
- [ ] Mark templates as:
  - recommended
  - experimental
  - internal/demo-only

#### F01-T03: Add run preflight checks
- [ ] Add preflight validation before run start for:
  - missing credentials
  - blocked policy
  - over-budget state
  - unavailable runtime packages
  - unsupported runtime mode
- [ ] Add actionable failure copy for each preflight category.
- [ ] Prevent users from entering a run that will fail immediately for known reasons.

#### F01-T04: Tighten onboarding UX
- [ ] Route new users into one of the supported journeys first.
- [ ] Add a guided setup sequence:
  - pick template
  - connect credential
  - confirm expected output
  - run
- [ ] Add progress state to onboarding so users can leave and resume.
- [ ] Reduce generic choices on the first-run path.

#### F01-T05: Add funnel instrumentation
- [ ] Track:
  - template selected
  - credential connected
  - preflight passed
  - first run started
  - first run succeeded
  - first run failed
- [ ] Add a lightweight internal dashboard or export path for those milestones.
- [ ] Ensure analytics distinguish setup failure from runtime failure.

### Success Criteria
- [ ] A new user can complete one supported workflow in under 5 minutes.
- [ ] Known blockers are surfaced before run dispatch.
- [ ] The first-run path is opinionated and not overloaded with generic options.
- [ ] Product teams can observe the first-run funnel with milestone data.

### Proof / Demo Feat
Create a new account, pick one supported template, connect one credential, pass preflight, and complete a first run without touching admin screens or raw graph internals.

---

## P1-F02: Debugger and Run Understanding UX

### Feature Description
Upgrade the current run experience into a workflow and agent debugger that helps users answer:
- what happened
- where it failed
- what path was taken
- what the agent did
- whether replay is safe

### Why This Is P1
- The backend already persists rich run and node data.
- The frontend already has a run page, node overlays, and replay hooks.
- The gap is not missing raw data; the gap is missing interpretation and presentation.

### User-Facing Outcome
- Users can inspect a run without reading raw JSON first.
- Agent steps and tool calls are visible in context.
- Replay options are understandable and safer to use.

### Non-Goals for P1
- full time-travel debugger
- full causal graph analysis
- distributed trace correlation with external systems

### Detailed Tasks

#### F02-T01: Improve run summary and failure explanation
- [ ] Add top-level run summaries:
  - final status
  - stop reason
  - failed node
  - paused node
  - replay source if applicable
- [ ] Add clearer failure messaging on the run page.
- [ ] Add pause summaries for HITL runs.

#### F02-T02: Add branch and path visibility
- [ ] Highlight the branch path actually taken in the graph view.
- [ ] Show skipped branches clearly.
- [ ] Make the active/failed path visually obvious in both desktop and smaller layouts.

#### F02-T03: Add agent step drill-down
- [ ] Show agent step timeline with:
  - step number
  - model decision summary
  - tool called
  - tool result summary
  - stop reason
- [ ] Group low-level events into readable step blocks.
- [ ] Allow expanding to raw payload details only when needed.

#### F02-T04: Improve replay UX
- [ ] Clarify replay scope:
  - whole run
  - from node
  - from checkpoint
- [ ] Add side-effect warnings for replay on workflows with external actions.
- [ ] Make replay provenance visible on the resulting run.
- [ ] Distinguish replayed runs from original runs in list and detail views.

#### F02-T05: Add support-grade export and trace tools
- [ ] Add trace export button for support/debug use.
- [ ] Add event timeline grouping for easier diagnosis.
- [ ] Ensure exported payloads respect redaction rules.

### Success Criteria
- [ ] Users can answer "what happened?" from the run page without inspecting raw tables directly.
- [ ] Agent runs expose readable step-level drill-down.
- [ ] Replay actions are understandable and visibly scoped.
- [ ] Exported traces are useful for support while remaining redacted.

### Proof / Demo Feat
Run an agent workflow that pauses, resumes, calls a tool, and then fails on a later step. From the run page alone, explain what happened and trigger a replay from the failing scope.

---

## P1-F03: Official Integration Package Hardening

### Feature Description
Define and ship a small set of verified official integrations instead of presenting a marketplace that looks broader than it is.

### Why This Is P1
- Once P0 makes package/runtime semantics truthful, P1 must make a small set of packages truly trustworthy.
- Buyers care more about a few integrations that work reliably than a large catalog with uneven confidence.

### User-Facing Outcome
- Users can choose from a small "ForgeGraph Verified" integration set.
- Each verified package has setup docs, expected behavior, and CI-backed tests.
- Unsupported or low-confidence packages are clearly labeled or hidden from the MVP surface.

### Non-Goals for P1
- public package ecosystem growth
- hundreds of integrations
- partner marketplace launch

### Candidate MVP Set
- Gmail
- Slack
- Notion
- Generic HTTP helper
- Telegram or WhatsApp, but not both for the first pass

### Detailed Tasks

#### F03-T01: Define the verified set
- [ ] Pick the final verified package list.
- [ ] Mark verified packages in marketplace metadata.
- [ ] Hide or downgrade low-confidence packages from default discovery surfaces.

#### F03-T02: Harden configuration and docs
- [ ] Add package docs covering:
  - required credential type
  - OAuth scopes or token requirements
  - sample input
  - sample output
  - expected errors
  - Cloud vs self-host constraints
- [ ] Add setup guidance directly in the package or node config UI where practical.

#### F03-T03: Add CI-backed execution validation
- [ ] Add end-to-end tests for each verified package.
- [ ] Add contract tests for package defaults and expected node config shape.
- [ ] Add negative tests for:
  - missing credentials
  - revoked credentials
  - policy denial
  - invalid runtime package state

#### F03-T04: Improve marketplace presentation
- [ ] Separate verified packages from all others in the UI.
- [ ] Add visible trust markers and support status.
- [ ] Show package health or last verified status where practical.

### Success Criteria
- [ ] Every verified package can be installed, configured, and executed in automated tests.
- [ ] Marketplace UI clearly separates verified packages from unsupported or experimental ones.
- [ ] Package docs are good enough for a user to complete setup without source-code reading.

### Proof / Demo Feat
Install a verified package, configure its credential, run it from a template, and show that the UI, docs, and execution behavior all tell the same story.

---

## Cross-Cutting P1 Tasks

### P1-X01: Scope Discipline
- [ ] Keep P1 focused on the 1-2 supported MVP journeys.
- [ ] Reject package additions or UX work that do not directly improve those journeys.

### P1-X02: Internal QA Matrix
- [ ] Build a QA matrix covering:
  - first-run flow
  - failed preflight
  - paused runs
  - replay
  - verified package setup
- [ ] Record known limitations and unsupported states.

### P1-X03: Internal Product Narrative
- [ ] Write one internal positioning note:
  - what ForgeGraph is for
  - what it is not for
  - which workflows are officially supported in MVP

---

## Suggested Build Order

### Week 1
- F01-T01 to F01-T03
- F02-T01 to F02-T02
- F03-T01

### Week 2
- F01-T04 to F01-T05
- F02-T03 to F02-T05
- F03-T02 to F03-T03

### Week 3
- F03-T04
- P1-X01 to P1-X03

## Final Definition of Done
- [ ] P1-F01 complete
- [ ] P1-F02 complete
- [ ] P1-F03 complete
- [ ] New users can reach first value through a narrow guided path
- [ ] The debugger explains real workflows and agent runs clearly
- [ ] Verified integrations are few, honest, and dependable
