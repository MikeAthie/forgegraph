# UI Rollout

The product direction is company-first.

Current rollout rules:

1. Default authenticated navigation should favor company operations.
2. `/companies`, `/companies/[companyId]`, `/runs`, `/runs/[runId]`, and `/approvals` are primary product routes.
3. `/workflows`, `/graphs`, `/executions`, `/inbox`, `/agents`, and `/overview` may remain as advanced, compatibility, or redirect surfaces.
4. Compatibility routes must not drive primary product vocabulary.
5. Product surfaces must translate raw graph/run/node language through the frontend domain layer.
6. All visible state must trace back to backend-owned records or backend-owned projections.

Runtime ownership still follows [../architecture/runtime-invariants.md](../architecture/runtime-invariants.md).
