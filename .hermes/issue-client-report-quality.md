## Bug Description
The Atlas prompt delivery report/PDF is structurally present but not client-ready. It dumps internal strategy notes, Markdown-style headings, operational prompt text, department names, media job IDs, asset IDs, and QA internals into a customer-facing handoff.

This makes the package read like an internal lineage export rather than a polished client deliverable.

## Evidence
The generated report includes content like:

```text
Department deliverables:
Legacy Optical Noir Strategy Brief
# Strategy Brief: Legacy Optical Noir Weekend Social Launch
## Engagement Context
**Client:** Legacy
**Stage:** strategy_research
**Run owner:** ForgeGraph
**Intended use:** Internal lineage for downstream HTML/PDF packaging
...
Legacy Channel Asset Map
Post 01: media_job=65bc74af-b5e9-41f4-8eee-cae5dcd12269,
asset=c026b7d6-f63b-4797-af24-20cce3c01e1e, status=succeeded
...
Source prompt:
Create a client-ready Legacy Optical Noir weekend social launch package...
```

## Expected Behavior
The client-facing report should be a polished approval deck / handoff, not a raw dump of internal deliverables.

It should include:

- A concise executive summary in Spanish-first client language.
- Campaign concept and rationale, rewritten for the client.
- Visual direction/mood board explanation.
- Asset gallery with human-readable captions/use cases, not file paths as the main content.
- Copy platform: captions, WhatsApp/DM scripts, CTAs, approval checklist.
- Measurement plan summarized as a client-facing launch checklist.
- Clear approval request and next steps.
- Optional appendix with lineage IDs only if marked internal or audit appendix.

It should not include in the main client report:

- Markdown syntax (`#`, `##`, `**`) leaked from source deliverables.
- Source prompt text.
- Internal stage names like `strategy_research`.
- Media job UUIDs / asset UUIDs as client content.
- Operational instructions such as “Markdown files must not be sent”.
- “Department deliverables” as a raw section label.
- QA claiming `ready for review` when media is placeholder-quality.

## Root Cause
`atlas_prompt_delivery._client_package_text()` and `_client_html()` currently concatenate raw `deliverable_sections` into the report:

```py
for section in deliverable_sections:
    lines.extend(["", section["title"], section["content"]])
```

`_deliverable_sections()` pulls `inline_content` from internal asset provenance. That fixed the empty report problem but created a new product-quality problem: internal lineage is now exposed directly to the client.

## Suggested Fix
Split internal lineage from client presentation:

1. Add a `ClientHandoffViewModel` / serializer that converts internal deliverables into client-safe sections.
2. Keep raw strategy/deliverables in `manifest.json` or internal asset provenance, not in the main PDF/HTML body.
3. Add text quality gates that fail if customer-facing HTML/PDF contains markdown syntax, `Source prompt`, `media_job=`, raw UUID-heavy asset maps, or internal stage IDs.
4. Make QA status depend on both media quality and report quality.
5. Rename the report from “client handoff” to something client-facing like “Legacy Optical Noir — Paquete de aprobación”.

## Acceptance Criteria
- Generated HTML/PDF contains no Markdown syntax artifacts in visible text.
- Generated HTML/PDF contains no source prompt, internal stage IDs, media job IDs, or asset IDs in the main body.
- Client report includes polished sections: summary, concept, gallery, copy, launch checklist, approval request.
- Raw lineage remains available in manifest/provenance for audit.
- Tests fail if raw internal deliverable content is dumped into client-facing report.

## Environment
- Docker Compose backend
- Run: `atlas_prompt_codex_media_20260610_034350`
- Related issue: placeholder media quality gate in #74
