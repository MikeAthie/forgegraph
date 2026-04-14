# Migration Safety Rules

## Required approach

- use expand -> migrate/backfill -> contract for schema-breaking changes
- add indexes before traffic depends on them
- isolate destructive cleanup into a later release whenever possible

## Rules

- direct rollback of destructive migrations is unsupported unless an explicit reverse path exists
- large backfills must be resumable and observable
- backward compatibility must be preserved for at least one release window
- deployment automation must run migrations before new app instances receive traffic

## Checklist

- schema change classified as expand or contract
- backward compatibility verified
- migration runtime estimated
- restore plan documented
- rollback image target identified
- smoke checks defined for post-migration behavior

