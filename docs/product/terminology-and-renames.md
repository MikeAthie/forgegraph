# Terminology And Renames

Use [ux-vocabulary.md](./ux-vocabulary.md) as the authoritative translation map.

Current user-facing rename direction:

- `Graph -> Company operating model`
- `GraphVersion -> Saved operating model version`
- `Run -> Operation`
- `Node -> Department / skill`
- `NodeRun -> Task execution`
- `Prompt node -> AI worker`
- `Tool node -> Tool action`
- `HITL node -> Approval required`
- `Runtime failure -> Needs attention`
- `Output JSON -> Deliverable`
- `Managed/BYOK -> AI access mode`

Compatibility policy:

- Existing storage names may remain in place during migration.
- Existing API aliases and routes may remain in place during migration.
- New docs and new UI should use company language first.
