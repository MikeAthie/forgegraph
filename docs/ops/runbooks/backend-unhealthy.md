# Backend Unhealthy

1. Check `/ready` and confirm which check failed.
2. Inspect recent deploy, migration, and secret changes.
3. Verify DB connectivity, Redis connectivity, and engine reachability if required.
4. If the issue began with a rollout, execute the rollback runbook.

