# Contributing

When contributing to ForgeGraph:

- treat [docs/architecture/runtime-invariants.md](architecture/runtime-invariants.md) as the single runtime source of truth
- if another doc conflicts with it, follow `runtime-invariants.md` and fix the conflicting doc
- use the OS terminology in new code, docs, and UI copy
- preserve compatibility with canonical runtime storage during the migration window
- treat projections as derived state
- avoid introducing new builder-first navigation or product framing
