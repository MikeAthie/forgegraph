# Runtime Standards P0

This document defines the P0 runtime contract introduced for ForgeGraph's control-plane to engine handoff.

## Contract Boundary

- Persisted graph JSON remains the editor contract.
- Dispatched graph JSON becomes the engine contract.
- `START` and `END` are editor-only sentinels. They may exist in persisted graphs and exports, but they are stripped before execution dispatch.
- `prepare_graph_for_engine()` is the canonical dispatch transformer. It applies:
  - sentinel-edge stripping
  - subgraph expansion
  - prompt template resolution
  - memory namespacing
  - policy injection
  - trace metadata injection
  - runtime limit injection

The dispatched graph metadata now includes:

```json
{
  "engine_contract_version": "2",
  "dispatch_transformations": [
    "strip_sentinel_edges",
    "expand_subgraphs",
    "namespace_memory",
    "resolve_prompt_templates",
    "normalize_runtime_tools",
    "inject_execution_policy",
    "inject_trace_context",
    "inject_runtime_limits"
  ],
  "trace": {
    "trace_id": "0123456789abcdef0123456789abcdef",
    "span_id": "0123456789abcdef",
    "traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
    "tracestate": ""
  },
  "runtime_limits": {
    "max_run_duration_ms": 300000,
    "max_tool_calls_total": 32,
    "max_llm_calls_total": 32
  }
}
```

The engine accepts `engine_contract_version = "2"`. Legacy graphs without an explicit version are still accepted for backwards-compatible direct engine tests and old checkpoints.

## Runtime Tool Contract

Agent-autonomous tools now use a stricter runtime shape:

```json
{
  "name": "crm_lookup",
  "version": "1.0.0",
  "kind": "http",
  "description": "Lookup a CRM record",
  "input_schema": {
    "type": "object"
  },
  "output_schema": {
    "type": "object"
  }
}
```

Rules:

- `input_schema` is required for agent-autonomous tools.
- `output_schema` is optional, but when present it must be a JSON Schema object.
- Tools without `input_schema` can still be used as direct tool nodes, but they are not eligible for agent autonomy.
- OpenAI-backed agent nodes use provider-native tool calling when the runtime registry can resolve all allowed tools with schemas.
- If the runtime cannot resolve a native OpenAI tool spec, the engine falls back to the legacy JSON planning path for compatibility.

## Structured Outputs

Prompt nodes with `output_schema` use the following order:

1. OpenAI structured output when provider support is available.
2. Local schema validation as a fallback.

Prompt execution records:

- `raw_response`
- `structured_response` when available
- `schema_validation` with `valid` and `errors`

## Tracing and Event Correlation

ForgeGraph now propagates W3C trace context from the backend to the engine through:

- `StartRunRequest.traceparent`
- `StartRunRequest.tracestate`
- `ResumeRunRequest.traceparent`
- `ResumeRunRequest.tracestate`

Persistence surfaces also carry correlation identifiers:

- `Run.trace_id`
- `RunEvent.trace_id`
- `RunEvent.span_id`
- `NodeRun.trace_id`
- `NodeRun.span_id`

OpenTelemetry spans are additive to existing Prometheus metrics:

- backend dispatch spans for start, invoke, replay, resume, and webhook-triggered starts
- engine run span
- engine node spans

## CloudEvents

Engine callbacks now use a CloudEvents 1.0 JSON envelope for engine-facing integration, while backend-to-frontend broadcast payloads remain unchanged.

Example:

```json
{
  "specversion": "1.0",
  "source": "forgegraph.engine",
  "type": "forgegraph.node.completed",
  "id": "evt_123",
  "time": "2026-03-31T18:30:00Z",
  "datacontenttype": "application/json",
  "data": {
    "type": "node_completed",
    "run_id": "run_123",
    "node_id": "prompt_1",
    "node_type": "prompt",
    "trace_id": "0123456789abcdef0123456789abcdef",
    "span_id": "0123456789abcdef"
  }
}
```

Existing S2S signed callback headers remain mandatory.

## Error Surfaces

New engine-facing and integration-oriented error paths can return RFC 9457 `application/problem+json`.

This rollout is intentionally partial:

- engine callback validation and related integration errors may emit problem details
- existing frontend-facing v1 envelopes are preserved

## Runtime Limits

Runtime limits are enforced per run inside the engine:

- maximum run duration
- total tool calls
- total LLM calls

These are separate from tenant-level quotas, budgets, and rate limits enforced in the control plane.

## Prompt Guidance

Prompt standards are documentation-only in P0. They are intended for prompt templates, agent instructions, and approval UX content.

### Planner

- Produce a short, verifiable plan.
- Do not call tools.
- Cap step count.
- Emit explicit assumptions and stop conditions.

### Executor

- Choose one of:
  - final answer
  - tool request
  - human approval request
- Avoid destructive side effects without an approval gate.
- Keep tool arguments schema-shaped.

### Verifier

- Check requirement fit.
- Flag uncertainty explicitly.
- Check for prompt injection and unsafe output handling patterns before side effects.

### Human-in-the-Loop

- Keep approval summaries short.
- Include the proposed action, evidence, and policy reason.
- Avoid secrets in approval prompts.
- Prefer `approval_required_tools` or `human_gate` for state-changing operations.
