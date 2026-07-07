## Bug Description
The Atlas prompt delivery path can still package and send `codex_spec_renderer` outputs as a client handoff even though those assets are placeholder-quality drawings, not production-quality campaign media.

In the latest Docker verification run, the ForgeGraph package met the basic structural constraints (HTML/PDF/PNG/manifest, no Markdown, lineage manifest), but visual inspection showed obvious placeholder/doodle sunglasses assets. Five of six PNGs were essentially the same generic vector sunglasses composition, with only minor palette changes.

## Evidence
Latest successful WhatsApp delivery run:

- run_id: `atlas_prompt_codex_media_20260610_034350`
- engagement_id: `d3dc8dbd-9eb4-4361-a24d-7d1006e57cf9`
- whiteboard_id: `f4f52d28-502b-449f-b133-f6caba760113`
- receipt_id: `5a090024-c47b-4594-9e28-d9a90d111e8c`
- package_sha256: `2706813e2a177d589e596f1224d9fc1cdff781dc99e8b40f2b00f8f8cc56fee0`

Package inspection:

```json
{
  "entries": [
    "Legacy_Optical_Noir_Handoff.html",
    "Legacy_Optical_Noir_Handoff.pdf",
    "assets/legacy_optical_noir_post_01.png",
    "assets/legacy_optical_noir_post_02.png",
    "assets/legacy_optical_noir_post_03.png",
    "assets/legacy_optical_noir_post_04.png",
    "assets/legacy_optical_noir_post_05.png",
    "assets/legacy_optical_noir_post_06.png",
    "manifest.json"
  ],
  "markdown_entries": [],
  "html_text_chars": 12410,
  "pdf_bytes": 14606,
  "png_count": 6,
  "deliverable_count": 6,
  "media_count": 6
}
```

Persisted media jobs all completed, but with placeholder quality metadata:

```text
media_jobs 6
<job> succeeded placeholder False True 64840
<job> succeeded placeholder False True 64840
<job> succeeded placeholder False True 64840
<job> succeeded placeholder False True 64840
<job> succeeded placeholder False True 64840
<job> succeeded placeholder False True 217007
```

## Expected Behavior
If a run/prompt requests client-ready or production-quality assets, ForgeGraph should either:

1. route to a real image provider / real Codex artifact-producing agent path and persist production-quality outputs, or
2. block/caveat delivery when only `codex_spec_renderer` placeholder output is available.

## Actual Behavior
ForgeGraph can complete the delivery and persist a handled WhatsApp receipt while the media outputs are explicitly `quality_tier=placeholder` and `production_quality=false`.

## Suggested Fix
- Add a package/delivery quality gate: do not allow client-ready handoff delivery when any packaged media asset has `production_quality=false`, unless the run is explicitly marked internal/test.
- Add provider selection/upgrade path for real artifact generation (Gemini/OpenAI/FAL or Codex agent that writes actual files), separate from the JSON spec renderer.
- Surface quality status in the package manifest and handoff copy so operators cannot mistake placeholder assets for client-ready creative.

## Environment
- Docker Compose backend container
- Command: `python manage.py run_atlas_prompt_delivery ... --json`
- WhatsApp bridge: local bridge via `host.docker.internal:3008`
