## Bug Description
`run_atlas_prompt_delivery` sends the WhatsApp text message before validating that the media file path is visible to the local WhatsApp bridge. If `/send-media` fails, the recipient can receive a partial text-only handoff and ForgeGraph raises before persisting a receipt.

This happened during the Docker verification run when `FORGEGRAPH_HOST_BACKEND_PATH` was set to an MSYS-style host path (`/c/Users/...`). The bridge, running on the Windows host, needed a Windows-readable path (`C:/Users/...`). The text send completed first, then media failed with HTTP 404.

## Steps to Reproduce
1. Run ForgeGraph in Docker Compose on Windows/Git Bash.
2. Use the local WhatsApp bridge through `http://host.docker.internal:3008`.
3. Execute:

```bash
MSYS_NO_PATHCONV=1 docker compose exec -T \
  -e FORGEGRAPH_HOST_BACKEND_PATH=/c/Users/<user>/projects/forgegraph/backend \
  backend python manage.py run_atlas_prompt_delivery \
  --prompt-file /app/.hermes/docker_atlas_prompt.txt \
  --phone '<recipient>' \
  --whatsapp-bridge-url http://host.docker.internal:3008 \
  --codex-workdir /app/.hermes/codex_media_workdir \
  --codex-timeout-seconds 600 \
  --json
```

## Actual Behavior
The command raises after the media request:

```text
requests.exceptions.HTTPError: 404 Client Error: Not Found for url: http://host.docker.internal:3008/send-media
```

The code path currently posts `/send` first, then `/send-media`:

```py
text_response = requests.post(f"{bridge_url.rstrip('/')}/send", ...)
text_response.raise_for_status()
media_response = requests.post(f"{bridge_url.rstrip('/')}/send-media", ...)
media_response.raise_for_status()
```

## Expected Behavior
ForgeGraph should avoid partial WhatsApp delivery and make bridge-visible file path failures explicit before sending any text.

## Suggested Fix
- Before posting `/send`, validate the bridge-visible package path exists from the bridge/host perspective.
- On Windows, normalize Docker `/app/...` paths to `C:/Users/...` rather than MSYS `/c/Users/...` for bridge file uploads.
- Consider sending media first with caption, or creating a pending receipt and marking it failed if text succeeds but media fails.
- Include the `/send-media` response body in the raised/logged error so operators can immediately see `File not found: ...`.

## Workaround Used
Setting:

```bash
FORGEGRAPH_HOST_BACKEND_PATH=C:/Users/<user>/projects/forgegraph/backend
```

allowed ForgeGraph to complete delivery and persist receipt `5a090024-c47b-4594-9e28-d9a90d111e8c`.

## Environment
- Windows host, Git Bash/MSYS terminal
- Docker Compose backend container bind-mounted at `/app`
- Local WhatsApp bridge on `127.0.0.1:3008`, reached from container via `host.docker.internal:3008`
