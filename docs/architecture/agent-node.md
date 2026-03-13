# Agent Node

## Purpose
The `agent` node is the first runtime primitive in ForgeGraph that owns an internal model-to-tool loop.

This keeps the graph-level workflow acyclic while allowing agent behavior inside one node.

## V1 Scope
V1 agent behavior is intentionally narrow:
- one node owns the loop
- graph-level cycles are not required
- tool access is explicitly allow-listed per node
- execution stops on a small set of deterministic stop conditions

V1 is not:
- a multi-agent system
- an autonomous planner
- a background job system
- graph-wide freeform looping

## Node Type
- `type`: `agent`

## Config Contract
The V1 `agent` node accepts this config shape:

```json
{
  "instructions": "Resolve the user's request and use tools when needed.",
  "system_prompt": "You are a support agent.",
  "provider": "openai",
  "credential_id": "cred_123",
  "model": "gpt-4.1-mini",
  "tools": ["crm_lookup", "send_email"],
  "max_steps": 6,
  "max_tool_calls": 4,
  "temperature": 0.2,
  "approval_required_tools": ["send_email"],
  "stop_condition": "final_answer"
}
```

## Required Fields
- `model`
- `tools`

## Field Notes
- `instructions` is the task-specific instruction block injected into the internal agent prompt.
- `tools` is an array of tool names the agent is allowed to call.
- `approval_required_tools` must be a subset of `tools`.
- `max_tool_calls` cannot exceed `max_steps`.
- `stop_condition` is intentionally narrow in V1 and currently supports `final_answer`.

## Canonical Runtime State
The runtime should treat the following as the canonical V1 agent state:
- `messages`
- `scratchpad`
- `tool_results`
- `final_output`
- `step_count`

## Stop Reasons
V1 agent runs should be able to terminate for these reasons:
- final answer returned
- max steps reached
- max tool calls reached
- tool policy denied
- approval required

## Validation Expectations
Contract-layer validation must reject:
- missing `model`
- missing or empty `tools`
- blank tool names
- approval-required tools not present in `tools`
- invalid numeric limits
- `max_tool_calls` greater than `max_steps`

## Execution Model Boundary
This document defines the shared contract only.

It does not define:
- engine execution details
- event payload shapes
- persistence schema
- frontend authoring UX

Those belong to later implementation slices in `P0-F01`.
