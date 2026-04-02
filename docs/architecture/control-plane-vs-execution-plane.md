# Control Plane Vs Execution Plane

Control plane:

- owns product APIs
- owns tenancy and governance
- owns projections and summaries
- owns marketplace governance, accounting, and decisions

Execution plane:

- runs workflow revisions
- emits execution events
- handles pause, resume, retry, replay

Rule: product-level system state belongs in the control plane, not in the engine.
