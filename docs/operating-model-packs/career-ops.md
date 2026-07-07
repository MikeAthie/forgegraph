# Career Operations Operating Model Pack

`career_ops.v1` turns ForgeGraph into a backend-owned career operations company.

The source-of-truth company graph is:

```text
docs/operating-model-packs/career-ops-company-graph.mmd
```

Every department, stage, durable record, and deliverable in the pack must map to the Mermaid graph.

## Runtime invariant

ForgeGraph backend state is authoritative. Local files, Mermaid diagrams, worker memory, and events are documentation/execution aids only; durable career search state is stored in ForgeGraph backend records.

## Daily discovery invariant

CareerOps is designed for a backend-owned 10:00 AM daily discovery automation once ForgeGraph automation schedules are available. The automation may discover, evaluate, draft, and queue options for approval; it must not submit applications.

## Base CV invariant

A canonical `cv_source` / base CV asset version is required before tailoring any resume. Tailored CVs, cover letters, and application answers must cite source refs from the base CV, proof points, profile, and target opportunity.

## Native mapping

CareerOps is implemented as native ForgeGraph workflows/executions/tasks/decisions/memory/accounting/artifacts/projections, not as a copied local-file CLI. See:

```text
docs/operating-model-packs/career-ops-native-forgegraph-mapping.md
```
