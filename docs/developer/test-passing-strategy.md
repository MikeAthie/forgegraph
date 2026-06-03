# Test Passing Strategy

Priority checks for current product work:

- company workspace flows render with authenticated backend-owned data
- operation detail and approval flows reconcile with canonical backend facts
- whiteboard, deployment, performance, memory, and accounting surfaces show backend provenance
- projections reconcile with canonical records and never become durable source of truth
- advanced graph/workflow routes remain functional as compatibility and expert surfaces

Do not treat summary correctness as optional. Operator trust depends on it.

Runtime-sensitive tests must follow [../architecture/runtime-invariants.md](../architecture/runtime-invariants.md): backend state is authoritative; engine, client state, events, Redis, Kafka, and WebSockets are not.
