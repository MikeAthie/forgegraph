# Decision

A decision is any auditable branch that requires review or produces an explicit resolution.

Decision types currently include:

- human approval
- policy guardrail
- marketplace review
- operator intervention

Phase 1 implementation:

- `ApprovalTask` remains canonical for human gates
- `DecisionRecord` becomes the unified decision ledger
