# Mental Model

- Organization: the operating boundary
- Workflow Definition: the authored automation asset
- Workflow Revision: the immutable saved version of a workflow definition
- Agent: a supervised autonomous actor with a persistent organization identity
- Task: a projected unit of work attached to an execution and agent
- Decision: an auditable branch, approval, or intervention
- Memory: the inspectable knowledge layer
- Cost: append-only accounting facts and aggregates
- System State: time-scoped read models over all of the above

Everything in the OS view must drill down to canonical execution records.
