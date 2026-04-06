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
