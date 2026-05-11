# Canonical Product Ontology

This document is the source of truth for ForgeGraph terminology.

If another product, design, test, or architecture document conflicts with this ontology, this document wins for product language. `docs/architecture/runtime-invariants.md` still wins for runtime ownership and durability rules.

## Product Model

ForgeGraph presents a company operating system:

- Company persists.
- Departments think.
- Operations act.
- Tasks execute.
- Deliverables result.
- Approvals unblock work.

The backend remains the only durable source of truth. The engine may execute work and keep ephemeral state, but it does not own durable company state.

## Primary Product Terms

Use these terms in primary UX, product docs, SEO, persona tests, and product-facing errors:

| Product term             | Meaning                                                              |
| ------------------------ | -------------------------------------------------------------------- |
| Organization             | The account and permission boundary.                                 |
| Company                  | The durable business entity the user creates and operates.           |
| Department               | A functional part of a company that thinks about a category of work. |
| Operation                | A live or historical unit of company work.                           |
| Task                     | A concrete unit of work inside an operation.                         |
| Skill                    | A capability assigned to a department.                               |
| Tool                     | A concrete external or internal capability a department can use.     |
| Deliverable              | The result a user can read, approve, use, or act on.                 |
| Approval                 | A human decision that can pause and resume an operation.             |
| Advanced operating model | The expert surface for direct structure editing.                     |

## Internal Terms

These terms are internal implementation language. They must not appear in primary UX, product docs, SEO, or user-facing errors:

| Internal term | Product translation                 |
| ------------- | ----------------------------------- |
| Graph         | Company or advanced operating model |
| GraphVersion  | Saved operating model version       |
| Node          | Department, skill, or tool          |
| NodeRun       | Task                                |
| Run           | Operation                           |
| Workflow      | Advanced operating model            |
| Execution     | Operation                           |
| Output JSON   | Deliverable                         |

Internal terms may remain in backend entities, API contracts, storage, migrations, engine code, logs, and advanced/internal tooling.

## Primary UX Forbidden Terms

Primary company surfaces must not use these terms in visible copy, user-facing errors, tutorial scripts, SEO copy, or persona-facing assertions:

- graph
- node
- run
- execution
- workflow
- agent
- output JSON
- LLM mode
- dead-letter
- projection
- runtime

Allowed exceptions:

- advanced/internal tooling, especially the advanced operating model editor
- backend, engine, migration, and stress-test implementation docs
- support-only identifiers inside clearly labeled technical details
- compatibility route names and API contracts that are translated before display

## Boundary Rule

Frontend product surfaces must not consume raw internal DTOs directly.

The allowed crossing points are:

- `frontend/domain/translation/`
- `frontend/domain/repositories/`
- explicitly advanced/internal tooling such as the graph editor

Everything else should consume product-safe ViewModels such as `CompanyVM`, `OperationVM`, `TaskVM`, `DeliverableVM`, `DepartmentVM`, and `ApprovalVM`.

## Error Rule

Raw backend and engine errors must be translated before display:

- engine errors become operation failures
- backend validation errors become user-actionable company or operation messages
- department-level failures become department issues
- output problems become deliverable problems
- paused human gates become approval blockers

## Route Rule

Canonical primary routes:

- `/companies`
- `/companies/[id]`
- `/runs`
- `/runs/[id]`
- `/approvals`

Legacy routes:

- `/executions` redirects to `/runs`
- `/executions/[id]` redirects to `/runs/[id]`
- `/inbox` redirects to `/approvals`

Advanced routes:

- `/workflows` is labeled "Advanced operating models"
- `/graphs` is hidden from primary navigation and reserved for advanced/internal editing
