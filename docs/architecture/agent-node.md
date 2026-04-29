# Agent Node

> Internal terminology notice: These terms are INTERNAL and not user-facing. Product surfaces must translate them through the canonical ontology and frontend domain ViewModels.

The `agent` node remains the execution-time source for agent behavior.

Phase 1 OS change:

- agent nodes are projected into durable `AgentRegistryEntry` records
- the UI and APIs use registry identity for supervision surfaces
- raw node configuration remains the underlying authored source
