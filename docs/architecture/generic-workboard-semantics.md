# Generic Workboard Semantics

Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is canonical.

## Status

Accepted for pre-beta hardening.

## Decision

`WorkWhiteboard` is the transitional durable object for a generic
company-scoped workboard/project board. It is not a marketing-only core model.

Core workboard semantics are:

- intake/context gathering
- project objective and constraints
- durable board projection from `TaskRoutingRecord`
- customer-visible versus internal card filtering
- links to backend-owned artifacts, evaluations, approvals, and deliverables

Marketing, content, deployment, performance, commerce, or other vertical phases
belong in pack configuration, phase contracts, or service metadata.

`WorkWhiteboard` stores generic fields beside legacy compatibility fields. The
generic fields are canonical for primary company/workboard surfaces:

- `work_status`: `draft`, `intake`, `ready_for_planning`, `planning`,
  `in_progress`, `review`, `delivery`, `measurement`, `closed`
- `project_name`: generic alias for legacy `client_name`
- `stakeholder_context_json`: generic alias for legacy `target_audience_json`
- `resource_context_json`: generic alias for legacy `product_context_json` plus
  nested legacy `brand_context_json`
- `delivery_context_json`: generic alias for legacy `channel_context_json`
- `work_missing_fields_json`: generic context gaps such as `objective`,
  `scope`, `timeline`, `stakeholders`, `resources`, `constraints`,
  `approval_owner`, `success_metrics`, and `delivery_readiness`

Legacy status mapping is:

| Legacy `status` | Generic `work_status` |
| --- | --- |
| `draft` | `draft` |
| `onboarding` | `intake` |
| `ready_for_strategy` | `ready_for_planning` |
| `in_strategy` | `planning` |
| `in_content` | `in_progress` |
| `in_approval` | `review` |
| `in_deployment` | `delivery` |
| `in_optimization` | `measurement` |
| `closed` | `closed` |

Legacy strategy routes remain compatibility aliases. Primary workboard clients
should use planning route names.

## Consequences

- New core statuses should be generic work states, not vertical phase names.
- Existing phase names such as strategy/content/deployment/optimization are
  compatibility terms until pack-owned phase contracts replace them.
- Redis workboard snapshots are non-authoritative projections and must be
  rebuildable from Postgres. They must have explicit TTLs and loss of Redis
  must degrade to direct Postgres reconstruction instead of becoming hidden
  state.
- Customer-visible board payloads must hide internal reasoning, raw evidence,
  raw tool outputs, prompts, and private links by default.
