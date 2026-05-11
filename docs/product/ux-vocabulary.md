# UX Vocabulary

Canonical terminology lives in [canonical-ontology.md](./canonical-ontology.md). This document gives copy-level translation examples.

## Translation Rule

If a UI element exposes engine language, translate it into company language.

Internal names may remain in storage, APIs, logs, and migration layers. User-facing product surfaces should default to company language.

## Required Mapping

| Internal concept | User-facing language               | Usage rule                                                                                                                              |
| ---------------- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `Graph`          | Company / advanced operating model | Use `company` in primary UX and `advanced operating model` only in expert tooling.                                                      |
| `GraphVersion`   | Saved operating model version      | Use when referring to a saved revision a user can review or restore.                                                                    |
| `Run`            | Operation                          | Use for an active or historical piece of company work.                                                                                  |
| `Node`           | Department / skill                 | Use `department` when the node represents a functional unit of the company; use `skill` when the node is better framed as a capability. |
| `NodeRun`        | Task                               | Use for a specific unit of work inside an operation.                                                                                    |
| Prompt node      | Department task / AI worker        | Prefer department task in primary UX. Use AI worker only in advanced setup where the user is configuring a capability.                  |
| Tool node        | Tool action                        | Use when the system performs a concrete tool-driven step.                                                                               |
| HITL node        | Approval required                  | Use when human intervention is needed before work can continue.                                                                         |
| Runtime failure  | Needs attention                    | Use for the primary status language on command surfaces.                                                                                |
| Output JSON      | Deliverable                        | Use when showing the result the company produced.                                                                                       |
| LLM provider     | Intelligence provider              | Use only when provider framing is necessary. Prefer `AI access mode` when that is sufficient.                                           |
| Managed / BYOK   | AI access mode                     | Present as a product operating choice, not raw technical configuration.                                                                 |

## Product Writing Rules

- Prefer `company`, `department`, `operation`, `task`, `deliverable`, and `approval`.
- Avoid `graph`, `node`, `run`, and `JSON` in primary UI copy.
- Avoid `agent`, `workflow`, `dead-letter`, `projection`, `runtime`, and `LLM mode` in primary UI copy.
- Use `advanced operating model` instead of `workflow definition` on expert surfaces.
- Use `saved operating model version` instead of `workflow revision` or `graph version`.
- Use `operation` instead of `execution` except in low-level technical drill-downs.
- Use `needs attention` instead of `runtime failure` in summary surfaces.
- Use `recovery item` instead of `dead letter` on primary task and command surfaces.
- Use `freshness` instead of `projection lag` unless the user is in an ops/debug surface.
- Use `processing delay` instead of `runtime intent lag` unless the user is in an ops/debug surface.

## Exposure Rules

- Builder surfaces may expose internal structure only after the company framing is established.
- Inspection surfaces may show internal identifiers when necessary, but labels should still use company language first.
- Compatibility routes and API aliases do not justify graph-centric UI copy.

## Example Conversions

- `Launch run` becomes `Launch operation`
- `Edit workflow` becomes `Update advanced operating model`
- `Graph validation failed` becomes `Operating model needs attention`
- `Output JSON available` becomes `Deliverable ready`
