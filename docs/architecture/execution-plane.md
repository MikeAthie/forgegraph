# Execution Plane

The Go engine is the execution plane.

It owns:

- execution start and callback handling
- retries, pause, resume, replay
- execution step emission
- trace continuity

It does not own organization dashboards, agent registry semantics, or accounting aggregation.
