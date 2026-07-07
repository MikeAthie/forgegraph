## Bug Description
The Docker Compose backend container can appear `unhealthy` in `docker compose ps` even while `GET /health` returns HTTP 200 with `status: ok`.

During the Atlas prompt delivery verification, `docker compose ps` reported:

```text
forgegraph-backend   Up ... (unhealthy)   127.0.0.1:8000->8000/tcp
```

But the health endpoint returned HTTP 200:

```json
{
  "status": "ok",
  "watchdog": {
    "enabled": true,
    "healthy": true,
    "errors": [
      "could not translate host name \"postgres\" to address: Name or service not known\n"
    ]
  }
}
```

## Expected Behavior
Docker health status and `/health` semantics should agree, or the endpoint should clearly expose degraded/unhealthy state when infrastructure errors are present.

## Actual Behavior
Operators see conflicting signals:

- Docker says backend is unhealthy.
- `/health` says `status: ok` and watchdog `healthy: true`.
- The response still contains a PostgreSQL DNS error.

## Suggested Fix
- Review Docker healthcheck command vs `/health` response interpretation.
- Decide whether stale/non-fatal watchdog errors should mark the endpoint degraded.
- If PostgreSQL is optional in this mode, clear stale errors or annotate them as non-blocking.
- If PostgreSQL is required, make `/health` return non-ok/degraded consistently.

## Environment
- Windows Docker Desktop
- ForgeGraph Docker Compose backend
- Observed while running `run_atlas_prompt_delivery` from the backend container
