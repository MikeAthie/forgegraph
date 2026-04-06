# Task

A task is the operator-facing unit of work for an agent during an execution.

Phase 1 implementation:

- Projected from `Run`, `NodeRun`, queue state, and pause state
- Stored in `TaskRecord`
- Includes current step, current decision, priority, summary, and timestamps

Tasks make execution detail supervisable without hiding raw trace data.
