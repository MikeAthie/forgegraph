# Legacy Phase 1 Media Proof Video Evaluation: 2026-05-08

## Capture

- Command: `PLAYWRIGHT_RUNTIME_TARGET=docker PLAYWRIGHT_REUSE_EXISTING_SERVER=true PLAYWRIGHT_DEMO_CAPTURE=true PLAYWRIGHT_LEGACY_PHASE1_CAPTURE=true PLAYWRIGHT_DEMO_CAPTURE_DIR=logs/legacy-phase1-media-playwright-output npx playwright test --config=playwright.demo.config.ts __tests__/demo-captures/legacy-phase1-media-videos.spec.ts --project=demo-chromium`
- Stable output: `01-openrouter-image-draft.webm`

## Observed Data

```json
{
  "company_id": "1b99ce06-d01d-46a4-9dad-bbd14396fb40",
  "credential_id": "2881a7a5-242f-4fc7-8b3a-632984857de0",
  "image_model": "black-forest-labs/flux.2-klein-4b",
  "existing_image_reused": true,
  "image_assets_visible": 1,
  "latest_image_asset_id": "d20d62fb-11b8-4174-ad2a-dabe3a7b491c",
  "latest_image_version_id": "a0d5d443-b60c-4c5b-be9b-a2e355cf5e89",
  "image_metrics": {
    "naturalWidth": 1024,
    "naturalHeight": 768,
    "renderedWidth": 427,
    "renderedHeight": 320.25
  },
  "social_publication_draft_id": "a88ec512-29f9-4ce3-8185-176363b81982",
  "social_publication_channel": "instagram,facebook",
  "social_publication_status": "approval_requested",
  "social_publication_approval_task_id": "6c710435-0853-45f1-bf6c-bc35f3b6eee5",
  "commercial_package_visible": true,
  "approval_gated": true,
  "final_result_visible": true
}
```

## Evaluation

- The recording shows the Legacy workspace, media draft controls, sanitized prompt, image generation action, backend-owned draft status, and the generated image rendered from the archive content API.
- The image is visible in the final frame and loaded with non-zero natural dimensions.
- The generated image is converted into an Instagram/Facebook publication package with caption, CTA, and human approval status visible in the product surface.
- The capture avoids raw logs, customer data, payment data, addresses, API keys, and publishing actions.

## Decision

Use this as the Phase 1 commercial media operation proof. Video-generation evidence should be kept in the Phase 1 evidence packet because Veo polling can outlive a short tutorial recording.
