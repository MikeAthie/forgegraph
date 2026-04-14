# Release Runbook

## Contract

Release order is:

1. full CI passes
2. dependency audit passes
3. images are built, scanned, and published
4. migration contract runs
5. services are deployed
6. smoke checks pass
7. release metadata is recorded

## Migration rule

- schema migration is a dedicated deploy step
- app container startup must not run `migrate`
- rollback reuses the previous image set and must not rerun forward-only migrations

## Smoke requirements

Release smoke must verify:

- backend `/health`
- backend `/ready`
- engine `/ready`
- engine `/metrics`
- frontend root page availability
- backend authenticated API call
- signed engine callback path

## Promotion rule

- do not promote or mark a release healthy until smoke passes
- if smoke fails, retain the prior image set as the active rollback target

