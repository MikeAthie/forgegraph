# Redis Degradation

Inspect Redis health, runtime intent stream lag, dead-letter stream depth,
consumer group pending entries, and engine callback spool growth. Keep backend
truth in Postgres authoritative; restart or fail over Redis only after recording
the affected tenants and replay plan.
