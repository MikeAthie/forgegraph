# UI Rollout

Safe rollout sequence:

1. Ship the new shell and routes
2. Keep legacy routes live as wrappers
3. Move the default authenticated route to `/overview`
4. Validate projections against canonical execution facts
5. Retire builder-first primary navigation after adoption
