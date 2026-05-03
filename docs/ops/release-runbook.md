# Release Runbook

## Contract

Release order is:

1. local production evidence gate is runnable or has a documented environment-only exception
2. full CI passes
3. dependency audit passes
4. images are built from the exact CI commit SHA, scanned, and published
5. migration contract runs
6. services are deployed
7. smoke checks pass
8. release metadata is recorded

Use [production-evidence-gate.md](production-evidence-gate.md) for the local
gate, failure classification, capacity evidence, and operator walkthrough.

## Integrity Rule

- release checkout must be exactly `workflow_run.head_sha`
- release image tags must use `sha-<commit>` only
- branch image tags are not release artifacts and must not be deployed
- the build must fail if the checkout has uncommitted or staged changes
- deploy commands must reference the immutable `sha-<commit>` backend, engine, and frontend images

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
- workflow creation, version creation, run start, and run dispatch to `running`
- signed engine callback path

## Promotion rule

- do not promote or mark a release healthy until smoke passes
- if smoke fails, retain the prior image set as the active rollback target
