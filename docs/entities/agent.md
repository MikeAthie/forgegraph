# Agent

An agent is a supervised autonomous actor with a durable identity inside an organization.

Phase 1 implementation:

- Projected from `agent` nodes in workflow revisions
- Stored in `AgentRegistryEntry`
- Carries source workflow, source revision, source node, policy snapshot, model defaults, last execution, and status

The UI must never infer agent identity only from a transient node ID.
