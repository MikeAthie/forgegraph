# Atlas Onboarding Backend Contract

Atlas onboarding is a backend-owned contract for Hermes and Atlas operators. It is not a ForgeGraph UI contract and must not move durable onboarding state into a frontend, client, engine, event stream, or local operator file.

The backend remains the durable source of truth. Operators and future Atlas website clients should read and write onboarding through the company-ops API below.

## Endpoint

Base path:

```text
/api/company-ops/atlas-onboarding
```

Contract version:

```text
atlas_onboarding.v1
```

Authentication is required.

- `GET` requires viewer access to the company.
- `POST` requires member access to the company.
- `POST` requires an `Idempotency-Key` header.
- Inaccessible companies are hidden with `404`.

## GET Contract Snapshot

Use `GET` to inspect the current backend-owned onboarding status for a company.

```http
GET /api/company-ops/atlas-onboarding?company_id=<company_uuid>
```

Response shape:

```json
{
  "data": {
    "atlas_onboarding": {
      "company_id": "<company_uuid>",
      "generated_at": "2026-06-04T00:00:00+00:00",
      "contract_version": "atlas_onboarding.v1",
      "onboarding": {
        "summary": {
          "total": 6,
          "completed": 1,
          "in_progress": 0,
          "blocked": 1,
          "not_started": 4
        },
        "items": []
      },
      "connector_readiness": {
        "status": "blocked",
        "summary": {},
        "connectors": []
      },
      "required_fields": [],
      "missing_required_fields": [],
      "operator_next_steps": [],
      "next_actions": [],
      "latest_engagement": null,
      "latest_intake_summary": null
    }
  }
}
```

The snapshot is safe to render for operators. It must not include credentials, tokens, API keys, credential IDs, private provider config, or gateway connection secrets.

## POST Intake Upsert

Use `POST` to record or update operator-mediated onboarding intake.

```http
POST /api/company-ops/atlas-onboarding
Idempotency-Key: atlas-onboarding-<stable-client-key>
Content-Type: application/json
```

Request shape:

```json
{
  "company_id": "<company_uuid>",
  "client_name": "Signal House",
  "contact_name": "Alex Client",
  "contact_email": "alex@client.example",
  "website_url": "https://signal.example",
  "business_summary": "Retail brand expanding owned-channel demand.",
  "goals": ["Increase repeat purchases", "Improve launch reporting"],
  "target_audience": {"segments": ["repeat buyers", "vip customers"]},
  "brand_voice": "Direct, useful, premium.",
  "constraints": ["No discount-led messaging"],
  "approved_channels": ["email", "whatsapp"],
  "blocked_channels": ["tiktok"],
  "success_metrics": ["repeat purchase rate", "campaign revenue"],
  "budget_range": "$5k-$10k monthly",
  "timeline": "Launch in July",
  "service_slug": "digital-marketing-agency-engagement",
  "service_package": "Atlas growth operator package",
  "notes": "Operator-mediated intake.",
  "source": "hermes",
  "metadata": {
    "safe_context": "Visible to operators"
  }
}
```

The backend creates or updates one durable `ServiceEngagement` for the company:

```text
source_key = atlas-onboarding:<company_id>
catalog slug = atlas-operator-onboarding
```

The response returns the same `atlas_onboarding` snapshot as `GET`, including `latest_engagement.id`, `latest_engagement.status`, and `latest_engagement.intake_data_summary`.

## Forbidden Secret Fields

Do not send secrets through this contract.

Forbidden key tokens include:

```text
api_key, apikey, client_secret, credential, password, private, secret, token
```

Top-level unknown credential-like fields are rejected. Credential-like keys inside `metadata`, `target_audience`, or nested JSON are stripped before persistence or response rendering.

Examples of forbidden fields:

```json
{
  "api_key": "...",
  "access_token": "...",
  "password": "...",
  "credential_id": "...",
  "metadata": {
    "private_provider_config": {}
  }
}
```

Provider credentials must be configured through backend-owned connector and credential flows, not Atlas onboarding intake.

## Operator Flow

1. Hermes or an Atlas operator calls `GET` with `company_id`.
2. The operator reviews `missing_required_fields`, `operator_next_steps`, and `connector_readiness`.
3. The operator collects customer-facing onboarding details out of band.
4. The operator calls `POST` with an `Idempotency-Key`.
5. The backend upserts the Atlas onboarding `ServiceEngagement`.
6. The operator calls `GET` again or uses the `POST` response to confirm the updated snapshot.

## Connector Readiness Separation

Connector readiness is a separate backend-derived section. It is not intake data and must not be copied into service deliverable planning fields.

- Onboarding intake records what the client and operator know about the engagement.
- `connector_readiness` reports backend-observed connector availability and health.
- Deliverables and deployment planning should reference connector readiness by reading the backend contract, not by duplicating readiness state into `intake_data_json`.

## Future Atlas Website

A future Atlas website can call this endpoint directly after authenticating the user.

- Use `GET` for read-only status rendering.
- Use `POST` for operator-mediated intake updates.
- Reuse a stable idempotency key for client retries of the same submitted intake.
- Treat the response as a backend snapshot, not local durable state.
- Never cache onboarding state as authoritative in the browser.
