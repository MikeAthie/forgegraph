# Rollback Runbook

## Definition

Rollback means redeploying the previous known-good image set without rerunning forward-only migrations.

## Preconditions

- previous backend, engine, and frontend image references are recorded
- current migration state is backward-compatible with the previous app release

## Flow

1. stop current rollout
2. redeploy prior backend, engine, and frontend images
3. verify backend `/ready`, engine `/ready`, frontend availability
4. run authenticated backend smoke
5. confirm queue depth and stale reconciliation are stable

## Do not do

- do not attempt destructive schema rollback unless a tested reverse migration exists
- do not re-point callback secrets on only one side

