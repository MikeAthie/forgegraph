## Media provider policy clarification

Product boundary from Mike: ForgeGraph features must run independently of Hermes. Hermes Agent can be used as a reference implementation, but ForgeGraph must not depend on Hermes runtime tools, profiles, auth files, cache paths, gateway, or credentials.

For media quality specifically:

1. `openai_codex_image_generation` is the primary production media provider.
2. ForgeGraph must own Codex image-generation setup/configuration/credentials/token validation.
3. If `openai_codex_image_generation` is not configured, media delivery should enter an explicit configuration-required/blocked state with setup guidance.
4. Gemini is a true redundancy fallback only when Codex is configured but temporarily unavailable/failing and Gemini is explicitly configured/permitted.
5. Gemini must not silently become the primary path just because Codex setup is missing.
6. `codex_spec_renderer` remains placeholder-only and must never satisfy client-ready media gates.

Plan files updated:

- `.hermes/plans/2026-06-09_220823-forgegraph-media-quality-plan.md`
- `.hermes/plans/codex-image-generation-hermes-findings.md`
