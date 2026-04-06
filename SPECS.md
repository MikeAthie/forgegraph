# ForgeGraph Specs

This file defines the public product vocabulary and the Phase 1 compatibility rules.

## Public Terminology

- Workflow Definition: authored automation structure currently stored as `Graph`
- Workflow Revision: immutable saved version currently stored as `GraphVersion`
- Execution: runtime instance currently stored as `Run`
- Execution Step: low-level runtime step currently stored as `NodeRun`
- Decision: auditable branch or review item; `ApprovalTask` is one subtype

## Compatibility Rules

- Existing database tables and engine contracts remain in place.
- Old API routes stay live with deprecation headers while new aliases ship.
- The frontend defaults to `/overview`.
- Builder routes remain available through `/workflows` and compatibility wrappers from `/graphs`.

## Runtime Source Of Truth

The source of truth remains:

- `Run`
- `RunEvent`
- `NodeRun`
- `ApprovalTask`
- `MemoryObservation`
- `LLMUsage`
- `AuditLog`

The OS layer is projection-based and must remain inspectable back to those records.
