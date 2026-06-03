# Docs Cleanup

`docs/architecture/runtime-invariants.md` is canonical for runtime ownership. Product language is canonical in `docs/product/canonical-ontology.md`.

## Current Policy

- Keep architecture, product, backend, frontend, ops, testing, and reliability docs when they describe active contracts or historical evidence clearly.
- Keep dated evidence reports when the date and context are explicit.
- Keep embedded agent skill packs under `.agents/` and `.codex/skills/` as tool reference material, not product documentation.
- Remove generated temp output, copied PRD snapshots, raw tool reports, and files containing generated credentials or tunnel configuration.
- Do not commit TestSprite `tmp` directories or generated raw reports.

## Previous Cleanup

Removed from canonical docs:

- phased v1, v2, MVP, wizard, memory, and PR rollout documents
- builder-first user guide pages for the wizard and template library

Kept and rewritten:

- core architecture docs
- ops docs
- contributing
- test strategy
