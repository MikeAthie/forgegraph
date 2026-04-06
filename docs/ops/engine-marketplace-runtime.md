# Engine Marketplace Runtime

Runtime package delivery remains an execution concern, but package approval and visibility are product concerns handled by the control plane.

Operational rule:

- runtime integrity is validated at execution time
- review state is tracked separately as decision context
- backend policy resolves what runtime package contract the engine is allowed to execute
