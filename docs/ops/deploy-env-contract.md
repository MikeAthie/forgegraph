# Deploy Environment Contract

Production deployments require managed secret injection and explicit environment configuration.

## Required backend runtime variables

- `SECRET_KEY`
- `ENCRYPTION_KEY`
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `REDIS_HOST`, `REDIS_PORT`
- `FRONTEND_URL`
- `ENGINE_HOST`, `ENGINE_PORT`
- `ENGINE_CALLBACK_SECRET`

Optional but required when enabled:

- `ENGINE_GRPC_TLS_ENABLED=true` -> `ENGINE_GRPC_TLS_CA_FILE`, `ENGINE_GRPC_TLS_SERVER_NAME`
- billing enabled -> `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`
- OAuth/SSO enabled -> provider client IDs and client secrets

## Required engine runtime variables

- `ENGINE_RUN_STATE_MODE=control-plane-http`
- `CONTROL_PLANE_URL`
- `ENGINE_CALLBACK_SECRET`
- `GRPC_PORT`
- `METRICS_PORT`

Optional but required when enabled:

- gRPC TLS -> `GRPC_TLS_CERT_FILE`, `GRPC_TLS_KEY_FILE`
- mTLS -> `GRPC_TLS_CLIENT_CA_FILE`

## Release workflow variables

- GitHub Actions variable `RELEASE_FRONTEND_API_URL`

The frontend image is environment-specific at build time because `NEXT_PUBLIC_API_URL` is compiled into the bundle.

## Operational rules

- production secrets must come from a managed secret store, not committed `.env` files
- runtime validation must fail startup when required production variables are missing
- callback secrets must be rotated on a defined cadence and updated on backend + engine together

