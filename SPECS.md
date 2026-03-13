# ForgeGraph Specs

## Purpose
This document defines the stable P0 contracts for:
- persisted `graph_json` payloads
- graph versioning and checksum behavior
- the boundary between engine-relevant graph data and editor-only state

Related contracts:
- [Run Event Contract](docs/architecture/run-event-contract.md)
- [Marketplace Runtime Contract](docs/architecture/marketplace-runtime-contract.md)

## 1. Graph JSON

### 1.1 Top-level shape
`GraphVersion.graph_json` must be a JSON object with:

```json
{
  "nodes": [],
  "edges": [],
  "metadata": {},
  "editor_state": {}
}
```

Required fields:
- `nodes`: array
- `edges`: array

Optional fields:
- `metadata`: object
- `editor_state`: object
- `graph_id`: string
- `version_id`: string

Serializer-level validation currently guarantees only that `graph_json` is an object with `nodes` and `edges` arrays. Structural validation is enforced by `GraphValidator`.

## 2. Nodes

Each node must have:

```json
{
  "id": "node_id",
  "type": "prompt",
  "name": "Prompt Node",
  "config": {}
}
```

Supported `type` values in P0:
- `agent`
- `prompt`
- `http`
- `transform`
- `branch`
- `merge`
- `human_gate`
- `memory`
- `tool`
- `subgraph`
- `output`

Optional node fields:
- `disabled`: boolean
- `retry_policy`: object
- `timeout_ms`: integer
- `outputs`: array

### 2.1 Retry policy

```json
{
  "max_attempts": 3,
  "backoff_ms": 250,
  "backoff_strategy": "fixed"
}
```

Supported `backoff_strategy` values:
- `fixed`
- `exponential`

## 3. Edges

Each edge must have:

```json
{
  "id": "edge_id",
  "from": "source_node_id",
  "to": "target_node_id"
}
```

Optional edge fields:
- `condition`: string
- `label`: string

### 3.1 Sentinel endpoints
ForgeGraph uses LangGraph-style sentinels for graph entry and exit:
- `START -> node_id`
- `node_id -> END`

`START` and `END` are not real nodes and must only appear as edge endpoints.

## 4. Node Config Expectations

Node config is type-specific and validated in strict mode against backend schemas.

Important P0 expectations:
- `agent`
  - requires `model`
  - requires non-empty `tools`
  - `approval_required_tools` must be a subset of `tools`
  - `max_tool_calls` cannot exceed `max_steps`
- `prompt`
  - requires either `prompt_template` or `prompt_id`
- `http`
  - requires `url`
- `transform`
  - requires `expression`
- `tool`
  - requires `tool`

The canonical backend schemas live in:
- `backend/domain/value_objects/node_schemas.py`

## 5. Validation Rules

### 5.1 Core graph validation
`GraphValidator` is the source of truth for structural rules. In P0 it validates:
- node/edge structure
- START/END connectivity
- missing output nodes
- invalid references
- cycles by default

### 5.2 Cycles
Cycles are rejected by default.

To allow cycles, set:

```json
{
  "metadata": {
    "allow_cycles": true
  }
}
```

P0 agent loops do not require graph-level cycles because the `agent` node runs its own bounded internal loop.

## 6. Editor-only State

`editor_state` is persisted with the graph version but ignored by the engine.

Supported fields:
- `nodePositions`
- `viewport`
- `notes`

This section is the contract boundary for React Flow and other UI state. Engine execution must not depend on it.

## 7. Versioning and Checksum

Each saved graph version stores:
- `id`
- `version`
- `graph_json`
- `checksum`
- `created_at`

The backend computes checksum by JSON-serializing `graph_json` with:
- sorted keys
- compact separators
- SHA-256 hashing

Behavioral implication:
- semantically equivalent payloads with different key ordering produce the same checksum

## 8. Example

```json
{
  "nodes": [
    {
      "id": "tool_1",
      "type": "tool",
      "name": "Health Check",
      "config": {
        "tool": "playwright_runtime_health_check"
      }
    },
    {
      "id": "output_1",
      "type": "output",
      "name": "Output",
      "config": {}
    }
  ],
  "edges": [
    { "id": "edge_start", "from": "START", "to": "tool_1" },
    { "id": "edge_out", "from": "tool_1", "to": "output_1" },
    { "id": "edge_end", "from": "output_1", "to": "END" }
  ],
  "metadata": {
    "name": "Health Check Workflow"
  },
  "editor_state": {
    "viewport": { "x": 0, "y": 0, "zoom": 1 }
  }
}
```

## 9. Stability Rules

P0 stability means:
- new node types may be added, but existing node type strings must not change
- `START` / `END` semantics must not change
- existing top-level fields must remain backward-compatible
- live run event changes must be documented in the run event contract before frontend or engine behavior changes
