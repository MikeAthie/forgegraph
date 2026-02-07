# Template Library (V2)

ForgeGraph V2 ships a versioned template library designed for fast onboarding and safe cloning.

## Core Behaviors

- Templates are immutable source artifacts.
- Users clone templates into their own graphs/versions.
- Library supports:
  - versioning (`group_id`, `version`, `is_latest`)
  - usage analytics (clone/run success rate)
  - ratings
  - org sharing/unsharing

## Built-in Launch Templates

| Template | Category | Estimated Minutes | Primary Use |
| --- | --- | --- | --- |
| Personal Life Manager | productivity | 3 | Assistant flow for email/calendar/tasks |
| Investor Update Email (Human Gate) | communication | 3 | Draft + approval workflow |
| Research Brief | research | 2 | Summarize source material into an executive brief |
| Customer FAQ Generator | product | 2 | Generate FAQ set from product description |

## Quick-Start Cards

Frontend quick-start cards are derived from template metadata and popularity:

- Personal Assistant (Telegram + Gmail)
- WhatsApp Chatbot
- Recommended templates (fallback when specific matches are unavailable)

Preview includes:
- required credential providers
- sample input placeholders
- expected output summary
- template version/changelog context

## Launch Usage Pattern

1. Pick template.
2. Review credential requirements.
3. Clone with provider/model/credential overrides.
4. Run with sample input.
5. Rate/share/version after validation.

## API Endpoints

- List templates: `GET /api/templates/`
- Clone template: `POST /api/templates/{template_id}/clone`
- List versions: `GET /api/templates/{template_id}/versions`
- Create version: `POST /api/templates/{template_id}/versions`
- Rate template: `POST /api/templates/{template_id}/ratings`
- Share template: `POST /api/templates/{template_id}/shares`
- Unshare template: `DELETE /api/templates/{template_id}/shares/{organization_id}`

## Notes for Operators

- Keep template sample input current with node contracts.
- Use changelog text for version migration guidance.
- Monitor `usage_count`, `rating_average`, and `run_success_rate` to decide which templates remain launch defaults.
