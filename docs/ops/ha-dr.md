# HA And Disaster Recovery

Protect the canonical runtime facts first:

- workflow revisions
- executions and events
- decisions
- memory observations
- accounting facts

Projection tables are rebuildable and lower priority than canonical event data during recovery.
