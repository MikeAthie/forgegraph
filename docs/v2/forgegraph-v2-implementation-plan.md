# ForgeGraph V2 Implementation Plan (P0-P3)

## Executive Summary
V2 focuses on closing the gap between ForgeGraph and leading graph/automation platforms for production-ready agent workflows. The plan prioritizes:
- Core graph runtime completeness (conditional flows, loops, durable checkpoints, streaming).
- Agent capabilities (prompt/tool/memory nodes with strong configuration UX).
- Integration readiness (Telegram, WhatsApp, Gmail, Google Calendar/Tasks, HTTP/Webhook).
- Stability and launch hardening (error flows, observability, scalability, credential safety).

This plan keeps the current architecture (Go engine, Django/DRF + Channels, Next.js, gRPC, Docker) and converts requirements into executable phase files.

## Timeline (Proposed)
- Weeks 1-2: P0 (Core runtime + agent execution path).
- Weeks 3-4: P1 (Visual builder, wizard, and discoverability UX).
- Weeks 5-7: P2 (Integration nodes + credential UX + quick setup shortcuts).
- Weeks 8-9: P3 (Performance, reliability, governance, launch QA).

## P0: Core Runtime + Agent Execution (Weeks 1-2)
Goals:
- Branch/Merge + loop behavior executes deterministically.
- Runs are resumable through durable checkpoints and pause/resume.
- Prompt node supports streaming and complete model configuration.
- Tool and memory nodes are production-ready for external calls and cross-run context.

See detailed tasks: `docs/v2/v2-tasks-p0.md`.

## P1: Visual Builder + Wizard UX (Weeks 3-4)
Goals:
- Drag/drop and linking are smooth and error-resistant.
- Wizard can create usable agents without manual graph editing.
- Node palette is searchable and complete.
- Onboarding, templates, and keyboard productivity improve activation.

See detailed tasks: `docs/v2/v2-tasks-p1.md`.

## P2: Integrations + Credentials (Weeks 5-7)
Goals:
- Ship core communication and productivity integrations end-to-end.
- Provide low-friction credential and OAuth setup.
- Add quick-setup presets and test actions for fast validation.

See detailed tasks: `docs/v2/v2-tasks-p2.md`.

## P3: Stability, Governance, and Launch QA (Weeks 8-9)
Goals:
- Reliable execution under load and long-running graphs.
- Robust error recovery and auditable run history.
- Secure credential handling and rate-limit resilience.
- Formal launch checklist and pass/fail gates.

See detailed tasks: `docs/v2/v2-tasks-p3.md`.

## V2 Readiness Checklist
Core Runtime:
- [ ] Branch/Merge workflows execute correctly including looped paths.
- [ ] Run checkpoints support replay and pause/resume for interrupted runs.
- [ ] Prompt responses stream incrementally in run details UI.

Agent Nodes:
- [ ] Prompt node supports provider/model, prompt templates, temperature, and max tokens.
- [ ] Tool nodes can call external APIs and user-defined functions.
- [ ] Memory GET/SET persists and is retrievable across separate runs.

Editor + Wizard:
- [ ] Canvas interactions are smooth for drag, connect, pan, and zoom.
- [ ] Wizard can produce a working agent without direct JSON edits.
- [ ] Searchable palette can find all supported node types quickly.

Integrations:
- [ ] Telegram and WhatsApp can receive and send messages end-to-end.
- [ ] Gmail can list unread emails and send replies via OAuth.
- [ ] Google Calendar/Tasks can read and create events/tasks via OAuth.
- [ ] HTTP/Webhook nodes can integrate unlisted services.

Stability + Governance:
- [ ] onError flow behavior supports retry/skip/fallback.
- [ ] Run logs/history include author, timestamp, and version context.
- [ ] Credentials are encrypted and sensitive values are redacted from logs.
- [ ] LLM/API rate limits are handled with bounded retries and clear errors.

Launch Quality:
- [ ] Functional, integration, UX, performance, and security QA gates pass.
- [ ] Quickstart docs and template library are updated for launch.
