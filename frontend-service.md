# Frontend Service

The frontend is the operator console for ForgeGraph.

It is a state observer and control surface, not a source of truth.

## Primary Navigation

- Overview
- Agents
- Tasks
- Inbox
- Memory
- Accounting
- Library
- Workflows
- Settings

## Important Routes

- Primary shell routes: `/overview`, `/agents`, `/tasks`, `/inbox`, `/memory`, `/accounting`, `/library`, `/workflows`, `/settings`
- Authentication routes: `/login`, `/register`
- Compatibility routes still in use: `/graphs`, `/runs`, `/approvals`
- Admin and specialist routes remain important secondary coverage: `/admin/*`, `/analytics/*`, `/prompts`, `/credentials`, `/onboarding`

## IA Rules

- State-first, not builder-first
- Summaries before logs
- Time and history visible on every major surface
- Raw traces remain reachable from every summary surface
- Read canonical state from the backend
- Use WebSockets for live updates such as run status, inbox notifications, alerts, and agent activity
- Do not infer truth from local heuristics when backend state is available

## Compatibility

- `/graphs` maps to the secondary `Workflows` workspace
- `/runs` maps to `Executions`
- `/approvals` maps to `Inbox`

## Test Automation Guidance

- Prefer the primary shell routes when generating new UI tests.
- Treat legacy workflow-builder routes as compatibility coverage, not the main product story.
- Authenticate through the UI for browser coverage instead of injecting tokens directly.
- Verify that the UI reads canonical state from backend APIs and reflects backend-driven updates over polling or WebSockets.
- Favor tests that move from summary surfaces into details: overview to execution details, inbox to decision review, agents/tasks to linked state, and accounting/memory to supporting records.

For deterministic hosted browser automation, the backend command `seed_testsprite_frontend_fixture` prepares the shared test user with:

- one editable prompt
- one pending approval
- one visible memory observation
- one visible credential
