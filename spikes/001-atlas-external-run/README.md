# 001: Atlas External Run vs ForgeGraph Run

## Question

Given that Atlas produced better client work when run externally by Hermes, but ForgeGraph produced doodle-like media and an internal-report dump, can we reproduce the external quality and identify the prompt/tool-calling differences that explain the gap?

## What I ran

External Atlas-style spike using Hermes tools directly, not ForgeGraph's `codex_spec_renderer` path.

Artifacts:

- ZIP: `spikes/001-atlas-external-run/Legacy_Optical_Noir_EXTERNAL_ATLAS_SPIKE.zip`
- HTML: `spikes/001-atlas-external-run/out/Legacy_Optical_Noir_Approval_Handoff.html`
- PDF: `spikes/001-atlas-external-run/out/Legacy_Optical_Noir_Approval_Handoff.pdf`
- Contact sheet: `spikes/001-atlas-external-run/out/asset_contact_sheet.png`
- Full prompts/tool log: `spikes/001-atlas-external-run/prompts_and_tool_log.json`

Package inspection:

```json
{
  "zip_size": 8857522,
  "sha256": "540d47285b166a5bacb830ea1196cf63eb0d623fd759bfd5051eddd558eb8c7f",
  "html_text_chars": 3792,
  "pdf_bytes": 375215,
  "png_count": 7,
  "bad_visible_tokens": []
}
```

`bad_visible_tokens` checked for: `Source prompt`, `Department deliverables`, `media_job=`, `strategy_research`, `# Strategy Brief`, `Intended use`.

## Tools called

1. `image_generate` x6
   - Purpose: generate actual image artifacts from detailed visual prompts.
   - Key difference: this returns image files directly; it does not ask Codex for JSON and then rasterize shapes.
2. `write_file`
   - Wrote prompt/tool log and builder script.
3. `terminal`
   - Downloaded image artifacts, built HTML/PDF/ZIP, inspected package.
4. `vision_analyze`
   - Reviewed generated contact sheet for visual quality.
5. `read_file/search_files`
   - Compared ForgeGraph prompt/tool path against external path.

## Prompts used

### Strategy prompt

> Act as Atlas, a productized premium agency operator. Create a client-facing Legacy Optical Noir weekend social launch package. Keep internal execution separate from the client handoff. The handoff must read like an approval deck: Spanish-first, polished, concise, visual, and decision-oriented. It must not expose raw prompts, markdown syntax, media job IDs, internal department stages, or QA implementation details. The campaign is for sunglasses: premium noir, no people, no text in images, no logos, no live publishing claim, approval required before production launch.

### Client report prompt

> Write the client-facing handoff in Spanish-first language for Legacy Optical Noir. Structure it as: Resumen ejecutivo, Concepto creativo, Dirección visual, Galería de assets, Copy sugerido, Checklist de lanzamiento, Decisión solicitada. Do not include source prompts, internal stage names, media job IDs, UUIDs, or operational notes. Keep it polished and approval-oriented.

### Image prompts

1. **Post 01 / Hero noir**
   > Premium editorial product photography for a sunglasses weekend launch campaign, black acetate sunglasses as the only subject on smoked glass and black marble, cinematic noir lighting, controlled reflections, shallow depth of field, high-end optical catalog quality, subtle warm copper rim light, no text, no logos, no people, no hands, no watermark, square social crop.

2. **Post 02 / Ivory contrast**
   > Luxury still-life campaign image, sunglasses with deep charcoal lenses resting on ivory travertine stone beside a black lacquer plane, refined CDMX evening mood, fashion editorial lighting, crisp realistic materials, premium optical brand feel, clean negative space for later copy overlay, no text, no logos, no people, no watermark, square crop.

3. **Post 03 / Detail macro**
   > Cinematic product macro of premium sunglasses, close-up hinge and lens detail, black acetate, aged copper accents, glossy reflections, dark smoke background, sophisticated noir palette, realistic commercial photography, no typography, no logos, no people, no hands, no watermark, square social asset.

4. **Post 04 / City night reflection**
   > Editorial sunglasses still life for weekend social launch, one pair of black sunglasses on reflective wet glass with out-of-focus city night bokeh behind, elegant noir mood, premium fashion product ad quality, no people, no text, no logos, no watermark, square Instagram feed crop.

5. **Post 05 / Assortment flat lay**
   > High-end optical campaign flat lay, three distinct sunglasses silhouettes arranged on dark suede and brushed metal, restrained luxury palette of black, smoke grey, ivory and warm brass, real product photography aesthetic, no labels, no typography, no logos, no people, no watermark, square crop.

6. **Post 06 / Obsidian green lens**
   > Minimal luxury sunglasses hero shot, translucent dark green lenses and black frame suspended visually on polished obsidian surface, dramatic side light, premium noir editorial styling, sharp realistic reflections, sophisticated and commerce-ready, no text, no logos, no people, no hands, no watermark, square social crop.

## Visual QA

The external images are materially better than the ForgeGraph doodle run:

- They look like product photography / commercial still-life, not vector doodles.
- Each composition is distinct: marble hero, ivory product setup, macro hinge, city reflection, assortment flat lay, green-lens hero.
- No obvious embedded text, logos, or people in the contact sheet.
- Some AI-art caveats remain: Post 02 includes a large black prop/object that may distract from sunglasses; Post 05 has multiple frames and might need product-selection review; manual client QA is still required.

## ForgeGraph path observed

ForgeGraph currently does this:

1. `_media_prompts()` creates descriptive prompts.
2. `enqueue_codex_image_job()` stores a `MediaGenerationJob` with provider `codex`.
3. `CodexMediaWorker` sends this wrapper prompt:

```text
You are ForgeGraph's internal Codex media art director.
This is not a coding task and you must not inspect the workspace.
Return only strict JSON. No markdown fences, no prose.
Generate a safe visual spec for a square PNG renderer.
Required JSON keys: title, composition, palette, headline, notes.
Rules: no visible words, no logos, no people, no private data, no fake brand marks.
...
Creative prompt:
<media prompt>
```

4. ForgeGraph parses JSON.
5. `render_codex_image_spec_png()` ignores most of the visual richness and draws a deterministic sunglasses composition with primitive rectangles/ellipses.

That means Codex is not really generating art. Codex is generating a small art-direction JSON blob, and ForgeGraph is drawing the same hard-coded asset structure repeatedly.

## Core differences

| Dimension | External Atlas spike | ForgeGraph run |
|---|---|---|
| Media tool | Real image artifact generation via `image_generate` | Codex JSON spec + local rasterizer |
| Prompt target | Image model / artifact generator | JSON-only art director |
| Prompt richness preserved? | Mostly yes | Mostly discarded after JSON parse |
| Composition diversity | One prompt per distinct composition, model renders pixels | Hard-coded sunglasses renderer dominates all outputs |
| Report generation | Client-safe view model | Raw internal deliverables concatenated |
| QA | Visual inspection + forbidden-token text check | Job success + file format checks |
| Output label | Spike / approval handoff | Claims client-ready/review even with placeholder media |

## Troubleshooting hypotheses

1. **Primary media failure is tool boundary, not just prompt quality.**
   Better prompts alone will not fix the current ForgeGraph path because the renderer cannot express photorealistic/commercial still-life assets.

2. **Codex should not be the final media renderer unless it is allowed to write/export real artifacts.**
   If Codex is used only to return JSON, output should remain placeholder. A production path needs image generation provider calls or a Codex artifact-producing workflow.

3. **ForgeGraph needs a media provider contract.**
   A provider should declare whether it is `production_quality_capable`. `codex_spec_renderer` should be false; real image provider / Codex artifact agent can be true only after artifact and QA checks.

4. **Client report needs a presentation layer, not internal lineage passthrough.**
   Internal deliverables should feed a client-safe handoff view model. Raw lineage belongs in manifest/provenance.

5. **QA should check both artifact quality and presentation safety.**
   A successful job and a ZIP with allowed extensions is insufficient.

## Verdict: VALIDATED

Running Atlas externally with direct image-artifact tooling produced materially better assets and cleaner client-facing copy. This validates the diagnosis that ForgeGraph's weak result is caused mainly by tool-calling architecture and presentation pipeline:

- Media: ForgeGraph uses a placeholder renderer after Codex, not a real artifact generator.
- Report: ForgeGraph dumps internal deliverables instead of rendering a client-safe handoff.

## Recommendation for real build

Implement issues #74 and #77 as one product-quality PR sequence:

1. Add provider capability metadata and block client-ready delivery from `production_quality=false` media.
2. Add a real image provider or Codex artifact-producing agent path.
3. Replace raw deliverable concatenation with a client-safe handoff view model.
4. Add text forbidden-token gates and visual/manual QA hooks before WhatsApp delivery.
