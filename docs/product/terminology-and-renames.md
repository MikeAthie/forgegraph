# Terminology And Renames

Public rename map:

- `Graph -> Workflow Definition`
- `GraphVersion -> Workflow Revision`
- `Run -> Execution`
- `NodeRun -> Execution Step`
- `ApprovalTask -> Decision`

Compatibility policy:

- Existing storage names remain in place during the migration window.
- Old API routes emit deprecation headers.
- New docs and UI use the new names first.
