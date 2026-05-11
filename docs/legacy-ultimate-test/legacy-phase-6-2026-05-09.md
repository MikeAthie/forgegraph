# Legacy Phase 6 Evidence Packet

## Commands
```json
[
  "uv run python manage.py legacy_glasswear_first_run --database postgres --json --strict",
  "uv run python manage.py seed_legacy_phase6_mock_objective --email legacy.glasswear.test@example.com --company-id 1b99ce06-d01d-46a4-9dad-bbd14396fb40 --json",
  "PLAYWRIGHT_LEGACY_MOCK_PROVIDER_RESPONSE=true PLAYWRIGHT_LEGACY_PHASE6_TEST=true npx playwright test frontend/__tests__/legacy-ultimate-test/specs/legacy_phase6_operator_surface.spec.ts"
]
```

## Observed Data
```json
{
  "company_id": "1b99ce06-d01d-46a4-9dad-bbd14396fb40",
  "visual_run_id": "7768d46f-6302-4787-9e8e-ab64962495df",
  "judge_run_id": "2043a538-13da-4800-87c1-812187a1cbf7",
  "judge_task_id": "6a00223e-3ae1-4120-a1a1-efca9345eed6",
  "judge_id": "6bb88279-2820-4cf4-aff6-76d5faae69d2",
  "judge_grade": "100/100",
  "products_imported": 21,
  "active_units_imported": 62,
  "stock_semantics_report": {
    "active_count": 12,
    "low_stock_count": 1,
    "last_piece_count": 2,
    "sold_out_count": 6,
    "definition_used": "Only active products are counted; sold_out means available_units == 0, last_piece means available_units == 1, low_stock means available_units == 2, and active means available_units >= 3."
  },
  "gemini_credential_id": null,
  "mock_provider_response": true,
  "mock_objective_seed": {
    "company_id": "1b99ce06-d01d-46a4-9dad-bbd14396fb40",
    "generated_at": "2026-05-09T05:24:29.832366+00:00",
    "graph_id": "a1d6c025-03c2-4efc-984a-c384a81a540a",
    "graph_version_id": "7e04c1f9-1246-4047-b5d7-6171a9fa899d",
    "mock_provider_response": true,
    "node_run_id": "537d7532-f703-406e-ab8a-d19a683c8ab0",
    "objective_contract_id": "745f3a07-cccf-46d5-b919-0efd50328917",
    "required_briefs_present": [
      "GAGA",
      "HENDRIX",
      "MAVERICK",
      "WATSON",
      "WINEHOUSE"
    ],
    "run_id": "7768d46f-6302-4787-9e8e-ab64962495df",
    "schema": "legacy_phase6_mock_objective_seed.v1",
    "source_evidence_path": "C:\\Users\\mathi\\projects\\forgegraph\\logs\\legacy-phase6-2026-05-08.json",
    "task_id": "7ee1320c-2e27-4fdb-abc8-73f532b53b00",
    "visual_asset_brief_count": 5
  },
  "visual_asset_briefs": [
    {
      "product_name": "GAGA",
      "sku": "NC-29046",
      "stock_state": "low_stock",
      "shot_list": [
        "Close-up on GAGA frames, highlighting unique design.",
        "Lifestyle shot with model wearing GAGA, natural light.",
        "Detail shot of temple arm engraving."
      ],
      "caption_angle": "Don't miss out on the iconic GAGA frames – stock is running low! Grab yours before they're gone.",
      "background_or_prop_needs": [
        "Clean, minimalist background (white or light grey)",
        "Natural light setting (e.g., near a window)",
        "Simple, neutral-colored fabric drape (if available)"
      ],
      "approval_task_title": "Approve Visual Brief for GAGA Frames"
    },
    {
      "product_name": "HENDRIX",
      "sku": "NC-29026",
      "stock_state": "last_piece",
      "shot_list": [
        "Hero shot of HENDRIX frames, front view.",
        "Side profile shot, emphasizing frame shape.",
        "Shot showcasing the unique texture/material of the frames."
      ],
      "caption_angle": "This is it! The very last pair of HENDRIX frames. Secure this unique piece of style before it's gone forever.",
      "background_or_prop_needs": [
        "Darker, moody background to create drama",
        "Single spotlight or directional light source (if available)",
        "Small, natural element like a smooth stone or dried leaf (if available, zero-cost)"
      ],
      "approval_task_title": "Approve Visual Brief for HENDRIX Frames"
    },
    {
      "product_name": "WINEHOUSE",
      "sku": "YD-GN1127T",
      "stock_state": "last_piece",
      "shot_list": [
        "Elegant flat lay of WINEHOUSE frames with a subtle accessory.",
        "Model wearing WINEHOUSE, looking sophisticated.",
        "Close-up on the bridge and nose pads for comfort detail."
      ],
      "caption_angle": "The final curtain call for WINEHOUSE. Don't miss your chance to own this timeless design. Only one left!",
      "background_or_prop_needs": [
        "Vintage-inspired background (e.g., old book, wooden surface)",
        "Soft, diffused lighting",
        "Small, elegant prop like a pearl necklace or silk scarf (if available, zero-cost)"
      ],
      "approval_task_title": "Approve Visual Brief for WINEHOUSE Frames"
    },
    {
      "product_name": "WATSON",
      "sku": "NG-1059",
      "stock_state": "active",
      "shot_list": [
        "Dynamic shot of WATSON frames in an active setting.",
        "Close-up on the lens clarity and frame durability.",
        "Model wearing WATSON, showcasing versatility for everyday wear."
      ],
      "caption_angle": "Discover the versatile WATSON frames – perfect for any adventure. Style meets durability.",
      "background_or_prop_needs": [
        "Bright, outdoor-inspired background (e.g., blurred greenery, concrete wall)",
        "Natural daylight",
        "Minimalist, functional props like a notebook or a coffee cup (if available, zero-cost)"
      ],
      "approval_task_title": "Approve Visual Brief for WATSON Frames"
    },
    {
      "product_name": "MAVERICK",
      "sku": "NC-39025",
      "stock_state": "active",
      "shot_list": [
        "Bold, front-facing shot of MAVERICK frames.",
        "Profile shot emphasizing the unique frame architecture.",
        "Model wearing MAVERICK, exuding confidence and individuality."
      ],
      "caption_angle": "Unleash your inner rebel with MAVERICK frames. Stand out from the crowd with this distinctive design.",
      "background_or_prop_needs": [
        "Urban, slightly gritty background (e.g., brick wall, industrial texture)",
        "Strong, directional lighting to create shadows",
        "No specific props needed, focus on the frames and attitude"
      ],
      "approval_task_title": "Approve Visual Brief for MAVERICK Frames"
    }
  ],
  "next_run_plan": [
    "Review and approve the visual asset briefs for GAGA, HENDRIX, WINEHOUSE, WATSON, and MAVERICK.",
    "Upon approval, schedule an internal photography session using existing equipment and available models/staff for the approved visual briefs.",
    "Prepare product inventory (GAGA, HENDRIX, WINEHOUSE, WATSON, MAVERICK) for the scheduled photography session.",
    "Draft initial social media copy and website descriptions for each product based on the approved caption angles, awaiting visual assets."
  ],
  "publication_drafts": [
    {
      "id": "2cf63e29-e494-4859-a4b1-c02d98772e7b",
      "company_id": "1b99ce06-d01d-46a4-9dad-bbd14396fb40",
      "signal_id": null,
      "opportunity_id": null,
      "origin_operation_id": "1ad02306-579e-496f-a8a4-8c22f3fe4f4f",
      "asset_id": null,
      "asset_version_id": null,
      "media_job_id": null,
      "approval_task_id": "edfe2455-6d6e-4cdc-9ca2-e7669e4ac53a",
      "title": "Approve Visual Brief for GAGA Frames",
      "channel": "instagram_draft",
      "audience": "Legacy Glasswear followers",
      "body": "Product: GAGA (NC-29046) Stock state: low_stock Caption angle: Don't miss out on the iconic GAGA frames – stock is running low! Grab yours before they're gone. Shot list: Close-up on GAGA frames, highlighting unique design.; Lifestyle shot with model wearing GAGA, natural light.; Detail shot of temple arm engraving. Props/background: Clean, minimalist background (white or light grey); Natural light setting (e.g., near a window); Simple, neutral-colored fabric drape (if available)",
      "call_to_action": "Hold for human approval before any external post.",
      "status": "approval_requested",
      "approved_at": null,
      "published_at": null,
      "metadata": {},
      "created_at": "2026-05-09T05:24:38.419123+00:00",
      "updated_at": "2026-05-09T05:24:40.666890+00:00"
    },
    {
      "id": "bfa6a5ed-a42a-4899-8d36-e42db0160556",
      "company_id": "1b99ce06-d01d-46a4-9dad-bbd14396fb40",
      "signal_id": null,
      "opportunity_id": null,
      "origin_operation_id": "c202cb4e-c540-4429-99be-4109fe6d8324",
      "asset_id": null,
      "asset_version_id": null,
      "media_job_id": null,
      "approval_task_id": "212e76df-588c-443d-aeac-4d0ba6f421a0",
      "title": "Approve Visual Brief for HENDRIX Frames",
      "channel": "instagram_draft",
      "audience": "Legacy Glasswear followers",
      "body": "Product: HENDRIX (NC-29026) Stock state: last_piece Caption angle: This is it! The very last pair of HENDRIX frames. Secure this unique piece of style before it's gone forever. Shot list: Hero shot of HENDRIX frames, front view.; Side profile shot, emphasizing frame shape.; Shot showcasing the unique texture/material of the frames. Props/background: Darker, moody background to create drama; Single spotlight or directional light source (if available); Small, natural element like a smooth stone or dried leaf (if available, zero-cost)",
      "call_to_action": "Hold for human approval before any external post.",
      "status": "approval_requested",
      "approved_at": null,
      "published_at": null,
      "metadata": {},
      "created_at": "2026-05-09T05:24:42.773147+00:00",
      "updated_at": "2026-05-09T05:24:45.015096+00:00"
    },
    {
      "id": "39eb4e63-32aa-4c2f-a9b4-d6117cafccaa",
      "company_id": "1b99ce06-d01d-46a4-9dad-bbd14396fb40",
      "signal_id": null,
      "opportunity_id": null,
      "origin_operation_id": "499c4715-2604-41b5-b866-59ad59ca63dd",
      "asset_id": null,
      "asset_version_id": null,
      "media_job_id": null,
      "approval_task_id": "ba41e6f1-7fa5-488b-bdf5-00c86613c4b3",
      "title": "Approve Visual Brief for WINEHOUSE Frames",
      "channel": "instagram_draft",
      "audience": "Legacy Glasswear followers",
      "body": "Product: WINEHOUSE (YD-GN1127T) Stock state: last_piece Caption angle: The final curtain call for WINEHOUSE. Don't miss your chance to own this timeless design. Only one left! Shot list: Elegant flat lay of WINEHOUSE frames with a subtle accessory.; Model wearing WINEHOUSE, looking sophisticated.; Close-up on the bridge and nose pads for comfort detail. Props/background: Vintage-inspired background (e.g., old book, wooden surface); Soft, diffused lighting; Small, elegant prop like a pearl necklace or silk scarf (if available, zero-cost)",
      "call_to_action": "Hold for human approval before any external post.",
      "status": "approval_requested",
      "approved_at": null,
      "published_at": null,
      "metadata": {},
      "created_at": "2026-05-09T05:24:47.092930+00:00",
      "updated_at": "2026-05-09T05:24:49.336144+00:00"
    },
    {
      "id": "a60df2c4-2864-4662-8ef2-f40c37a4e042",
      "company_id": "1b99ce06-d01d-46a4-9dad-bbd14396fb40",
      "signal_id": null,
      "opportunity_id": null,
      "origin_operation_id": "1f7818cf-95ba-463b-914c-9718353b7286",
      "asset_id": null,
      "asset_version_id": null,
      "media_job_id": null,
      "approval_task_id": "77a82c2d-a2e0-431e-8f4b-42541df30748",
      "title": "Approve Visual Brief for WATSON Frames",
      "channel": "instagram_draft",
      "audience": "Legacy Glasswear followers",
      "body": "Product: WATSON (NG-1059) Stock state: active Caption angle: Discover the versatile WATSON frames – perfect for any adventure. Style meets durability. Shot list: Dynamic shot of WATSON frames in an active setting.; Close-up on the lens clarity and frame durability.; Model wearing WATSON, showcasing versatility for everyday wear. Props/background: Bright, outdoor-inspired background (e.g., blurred greenery, concrete wall); Natural daylight; Minimalist, functional props like a notebook or a coffee cup (if available, zero-cost)",
      "call_to_action": "Hold for human approval before any external post.",
      "status": "approval_requested",
      "approved_at": null,
      "published_at": null,
      "metadata": {},
      "created_at": "2026-05-09T05:24:51.413425+00:00",
      "updated_at": "2026-05-09T05:24:53.633350+00:00"
    },
    {
      "id": "2b334dce-355e-4093-abed-dd1f11c0a9b8",
      "company_id": "1b99ce06-d01d-46a4-9dad-bbd14396fb40",
      "signal_id": null,
      "opportunity_id": null,
      "origin_operation_id": "b14b79e2-1dca-4ea8-bc20-52816e4d6242",
      "asset_id": null,
      "asset_version_id": null,
      "media_job_id": null,
      "approval_task_id": "2896ecaa-ace8-40c2-bf97-83f6a3e54365",
      "title": "Approve Visual Brief for MAVERICK Frames",
      "channel": "instagram_draft",
      "audience": "Legacy Glasswear followers",
      "body": "Product: MAVERICK (NC-39025) Stock state: active Caption angle: Unleash your inner rebel with MAVERICK frames. Stand out from the crowd with this distinctive design. Shot list: Bold, front-facing shot of MAVERICK frames.; Profile shot emphasizing the unique frame architecture.; Model wearing MAVERICK, exuding confidence and individuality. Props/background: Urban, slightly gritty background (e.g., brick wall, industrial texture); Strong, directional lighting to create shadows; No specific props needed, focus on the frames and attitude",
      "call_to_action": "Hold for human approval before any external post.",
      "status": "approval_requested",
      "approved_at": null,
      "published_at": null,
      "metadata": {},
      "created_at": "2026-05-09T05:24:55.713290+00:00",
      "updated_at": "2026-05-09T05:24:57.952163+00:00"
    }
  ],
  "procurement_draft": {
    "id": "a6f2855f-74b5-4202-8ebb-398bc3bb3894",
    "company_id": "1b99ce06-d01d-46a4-9dad-bbd14396fb40",
    "origin_operation_id": "9f688d34-1b72-4b3c-acc3-0c4a935b7142",
    "approval_task_id": "5af314ce-f7fc-4df5-836a-a5f0999b7fb0",
    "title": "Legacy Phase 6 zero-cash procurement review",
    "rationale": "Approval-gated reorder review only. No procurement execution and no cash spend.",
    "budget_amount": "0.00",
    "currency": "mxn",
    "status": "approval_requested",
    "approved_at": null,
    "metadata": {},
    "lines": [
      {
        "id": "62560080-ca04-4209-8c82-2aaff765fcd1",
        "product_id": "a33ae1c0-bb9e-4356-a03d-48fb7a7c3d63",
        "sku": "NC-29046",
        "description": "GAGA zero-cash-spend review line",
        "quantity": 1,
        "unit_cost_amount": "0.00",
        "currency": "mxn",
        "metadata": {
          "phase": "legacy_phase_6",
          "stock_state": "low_stock"
        }
      },
      {
        "id": "03e5ad7b-7302-4fad-977b-3798159befb1",
        "product_id": "cefa1b80-7516-40b2-a659-1f31fdfe5897",
        "sku": "NC-29026",
        "description": "HENDRIX zero-cash-spend review line",
        "quantity": 1,
        "unit_cost_amount": "0.00",
        "currency": "mxn",
        "metadata": {
          "phase": "legacy_phase_6",
          "stock_state": "last_piece"
        }
      },
      {
        "id": "7414b920-e9f4-48b7-a627-4d65dbebeffa",
        "product_id": "ff4cc245-78c1-4613-b67b-79a19f034390",
        "sku": "YD-GN1127T",
        "description": "WINEHOUSE zero-cash-spend review line",
        "quantity": 1,
        "unit_cost_amount": "0.00",
        "currency": "mxn",
        "metadata": {
          "phase": "legacy_phase_6",
          "stock_state": "last_piece"
        }
      },
      {
        "id": "3bf59620-9b54-4277-a41e-c85ddcb06c2d",
        "product_id": "d418d68f-39a0-490b-89f0-b2115253ff3b",
        "sku": "NG-1059",
        "description": "WATSON zero-cash-spend review line",
        "quantity": 1,
        "unit_cost_amount": "0.00",
        "currency": "mxn",
        "metadata": {
          "phase": "legacy_phase_6",
          "stock_state": "active"
        }
      },
      {
        "id": "768668b1-80d7-495c-8427-be16167d60be",
        "product_id": "4f53fcb5-9bf3-4bbf-a9d7-ad26d5d52de4",
        "sku": "NC-39025",
        "description": "MAVERICK zero-cash-spend review line",
        "quantity": 1,
        "unit_cost_amount": "0.00",
        "currency": "mxn",
        "metadata": {
          "phase": "legacy_phase_6",
          "stock_state": "active"
        }
      }
    ],
    "created_at": "2026-05-09T05:25:00.050225+00:00",
    "updated_at": "2026-05-09T05:25:02.310990+00:00"
  },
  "reservation_proof": {
    "reservation": {
      "id": "d22f7400-987d-413d-a181-72a85c5be18e",
      "company_id": "1b99ce06-d01d-46a4-9dad-bbd14396fb40",
      "product_id": "009e05c5-b8c3-4be4-a664-1b7eb0fdad50",
      "product_sku": "ZD-8809T",
      "product_model": "DEPP",
      "status": "active",
      "quantity": 1,
      "buyer_alias": "phase6-dry-run",
      "channel": "manual",
      "note": "Phase 6 dry-run reservation proof.",
      "expires_at": "2026-05-09T05:54:34.248561+00:00",
      "released_at": null,
      "converted_at": null,
      "order_shell": null,
      "created_at": "2026-05-09T05:24:34.248753+00:00",
      "updated_at": "2026-05-09T05:24:34.248756+00:00"
    },
    "released": {
      "id": "d22f7400-987d-413d-a181-72a85c5be18e",
      "company_id": "1b99ce06-d01d-46a4-9dad-bbd14396fb40",
      "product_id": "009e05c5-b8c3-4be4-a664-1b7eb0fdad50",
      "product_sku": "ZD-8809T",
      "product_model": "DEPP",
      "status": "released",
      "quantity": 1,
      "buyer_alias": "phase6-dry-run",
      "channel": "manual",
      "note": "Phase 6 dry-run reservation proof.",
      "expires_at": "2026-05-09T05:54:34.248561+00:00",
      "released_at": "2026-05-09T05:24:36.336157+00:00",
      "converted_at": null,
      "order_shell": null,
      "created_at": "2026-05-09T05:24:34.248753+00:00",
      "updated_at": "2026-05-09T05:24:36.336251+00:00"
    }
  }
}
```

## Verification Result
```json
{
  "passed": true,
  "bootstrap": {
    "checks": {
      "inventory_active_units_62": true,
      "inventory_products_21": true,
      "inventory_zero_warnings": true,
      "phase0_single_company": true,
      "stock_semantics_agree": true
    },
    "failures": [],
    "passed": true,
    "warnings": [
      "Updated existing Legacy user password.",
      "Created Legacy Glasswear graph version 51."
    ]
  },
  "judge_status": "passed",
  "judge_score": 100,
  "acceptance": {
    "operator_surface_verified": true,
    "stock_semantics_consistent": true,
    "visual_briefs_actionable": true,
    "zero_budget_policy_respected": true,
    "approval_gates_present": true,
    "no_private_customer_data_sent_to_llm": true,
    "evidence_packet_complete": true,
    "next_run_plan_clear": true,
    "visual_run_id": "7768d46f-6302-4787-9e8e-ab64962495df",
    "publication_draft_count": 5,
    "procurement_draft_status": "approval_requested"
  }
}
```

## Bugs Or Gaps
```json
[]
```

## Decision
Legacy is ready for approval-gated visual/content preparation, not live sales or public-channel autonomy.
