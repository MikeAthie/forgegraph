# Event Model

Canonical event backbone:

- `Run`
- `RunEvent`
- `NodeRun`

Rules:

- projections must be rebuildable from runtime facts
- UI summaries must link back to runtime facts
- event order and timestamps are first-class for inspectability
