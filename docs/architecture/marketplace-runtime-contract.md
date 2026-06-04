# Marketplace Runtime Contract

> Internal terminology notice: These terms are INTERNAL and not user-facing. Product surfaces must translate them through the canonical ontology and frontend domain ViewModels.

Marketplace packages remain runtime delivery artifacts.

Phase 1 change:

- the marketplace is reframed as part of the Library surface
- package review is exposed as a decision type in the operator mental model

## Future Work: Reviewed Improvement Agent

ForgeGraph should eventually support a backend-owned improvement loop for shared
skills, tools, and marketplace packages.

The improvement agent may use memory observations, tool execution receipts,
failed runs, connector diagnostics, and operator corrections to propose source
changes. It may inspect repository files through reviewed source connectors such
as GitHub MCP and draft pull requests, but it must not directly mutate runtime
tools, engine state, or shared package releases.

Required guardrails:

- proposals are durable backend records with provenance links to the memories,
  receipts, diagnostics, or failures that motivated them
- generated code changes happen on reviewable branches or pull requests, never
  as direct writes to deployed package state
- runtime manifests may only reference existing reviewed backend handlers
- marketplace releases remain backend-owned and review-gated
- the engine receives only projected context and executable manifests; it does
  not own proposals, skills, releases, or deployment state

This intentionally adapts the useful part of dynamic skill systems without
copying their agent-owned mutable skill store.
