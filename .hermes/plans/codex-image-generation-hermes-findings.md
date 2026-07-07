# Hermes Agent Codex Image Generation Patterns for ForgeGraph Media Quality

## Why this addendum exists

Mike wants ForgeGraph client-ready media to use the paid Codex/ChatGPT subscription path instead of Gemini/FAL where possible. The key question was whether Hermes Agent has an implementation we can copy.

Short answer: **yes, mostly.** Hermes Agent has a bundled `openai-codex` image generation plugin that uses ChatGPT/Codex OAuth credentials to call the Codex Responses API with the `image_generation` tool and `gpt-image-2`.

Important correction: the earlier external Atlas spike's generated URLs were `fal.media` URLs, so that spike proved the workflow/prompt boundary, not that the specific images were Codex-generated. The Hermes codebase, however, contains the Codex-backed implementation we can adapt.

## Upstream Hermes references inspected

Repository inspected:

```text
https://github.com/NousResearch/hermes-agent
```

Local clone used for inspection:

```text
/tmp/hermes-agent-inspect
```

Relevant source files:

```text
plugins/image_gen/openai-codex/__init__.py
plugins/image_gen/openai-codex/plugin.yaml
agent/image_gen_provider.py
agent/image_gen_registry.py
tools/image_generation_tool.py
agent/auxiliary_client.py
```

Relevant tests:

```text
tests/plugins/image_gen/test_openai_codex_provider.py
tests/tools/test_image_generation_plugin_dispatch.py
tests/agent/test_image_gen_registry.py
```

Relevant upstream issues:

```text
https://github.com/NousResearch/hermes-agent/issues/24965
https://github.com/NousResearch/hermes-agent/issues/19505
https://github.com/NousResearch/hermes-agent/issues/35861
https://github.com/NousResearch/hermes-agent/issues/21661
https://github.com/NousResearch/hermes-agent/issues/14959
```

## Copyable implementation pattern

Hermes' `openai-codex` image provider does not ask Codex to describe an image and then locally render doodles. It calls the Codex backend with the Responses `image_generation` tool required.

Request shape from `plugins/image_gen/openai-codex/__init__.py`:

```py
{
    "model": "gpt-5.5",
    "store": False,
    "instructions": (
        "You are an assistant that must fulfill image generation requests by "
        "using the image_generation tool when provided."
    ),
    "input": [{
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": prompt}],
    }],
    "tools": [{
        "type": "image_generation",
        "model": "gpt-image-2",
        "size": size,
        "quality": quality,
        "output_format": "png",
        "background": "opaque",
        "partial_images": 1,
    }],
    "tool_choice": {
        "type": "allowed_tools",
        "mode": "required",
        "tools": [{"type": "image_generation"}],
    },
    "stream": True,
}
```

Then Hermes streams:

```text
POST https://chatgpt.com/backend-api/codex/responses
```

with Codex OAuth headers, parses SSE events, extracts either:

```text
image_generation_call.result
partial_image_b64
```

and saves the base64 image to disk as a real PNG:

```text
$HERMES_HOME/cache/images/openai_codex_<tier>_<timestamp>_<uuid>.png
```

The important architecture distinction for ForgeGraph:

```text
Wrong current path:
rich prompt → Codex JSON visual spec → local deterministic renderer → placeholder PNG

Desired Codex path:
rich prompt → Codex Responses image_generation tool → gpt-image-2 PNG bytes → persisted AssetVersion
```

## Provider contract to copy/adapt

Hermes uses a small provider interface:

```py
class ImageGenProvider(abc.ABC):
    @property
    def name(self) -> str: ...
    @property
    def display_name(self) -> str: ...
    def is_available(self) -> bool: ...
    def list_models(self) -> list[dict[str, Any]]: ...
    def default_model(self) -> str | None: ...
    def get_setup_schema(self) -> dict[str, Any]: ...
    def generate(self, prompt: str, aspect_ratio: str = "landscape", **kwargs) -> dict[str, Any]: ...
```

Return shape:

```py
{
    "success": True,
    "image": "/absolute/path/to/image.png",
    "model": "gpt-image-2-medium",
    "prompt": prompt,
    "aspect_ratio": "square",
    "provider": "openai-codex",
    "size": "1024x1024",
    "quality": "medium",
}
```

Error shape:

```py
{
    "success": False,
    "image": None,
    "error": "...",
    "error_type": "auth_required|missing_dependency|api_error|empty_response|io_error|invalid_argument",
    "model": "gpt-image-2-medium",
    "provider": "openai-codex",
}
```

ForgeGraph does not need Hermes' plugin system wholesale. It should copy the narrower provider boundary and implement a ForgeGraph `CodexImageGenerationProvider` behind the existing media worker.

## Model tiers to support

Hermes exposes three virtual tiers over the same underlying image model:

```py
API_MODEL = "gpt-image-2"

_MODELS = {
    "gpt-image-2-low": {
        "quality": "low",
        "speed": "~15s",
        "strengths": "Fast iteration, lowest cost",
    },
    "gpt-image-2-medium": {
        "quality": "medium",
        "speed": "~40s",
        "strengths": "Balanced — default",
    },
    "gpt-image-2-high": {
        "quality": "high",
        "speed": "~2min",
        "strengths": "Highest fidelity, strongest prompt adherence",
    },
}
```

Sizes:

```py
{
    "landscape": "1536x1024",
    "square": "1024x1024",
    "portrait": "1024x1536",
}
```

ForgeGraph recommendation:

- default to `gpt-image-2-medium` for client draft packages;
- allow `gpt-image-2-high` for final hero assets or when manual QA rejects medium;
- never use the local spec renderer for client-ready assets.

## Auth/header details to copy carefully

Hermes relies on Codex OAuth, not `OPENAI_API_KEY`.

Availability check:

```py
_read_codex_access_token() is not None
httpx import works
```

Headers from `agent/auxiliary_client.py`:

```py
{
    "User-Agent": "codex_cli_rs/0.0.0 (Hermes Agent)",
    "originator": "codex_cli_rs",
    "ChatGPT-Account-ID": "<decoded from JWT if present>",
    "Accept": "text/event-stream",
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}
```

The `originator` and `User-Agent` matter because Hermes notes Cloudflare can return 403 challenges for non-first-party-looking callers.

ForgeGraph should avoid directly reading Hermes profile auth files if possible. Preferred options:

1. **Short-term local/dev:** call a local Hermes/Codex image helper or reuse Hermes auth path in the developer environment.
2. **Product path:** add ForgeGraph-owned Codex OAuth credentials/config, then use the same request/header/SSE pattern.
3. **Fallback:** if Codex auth is unavailable, mark `no_production_media_provider_configured` rather than falling back to doodles.

## SSE parsing behavior to copy

Hermes intentionally parses raw SSE instead of relying on an SDK, because event shapes drift.

Copyable behavior:

- accept `event:` and `data:` SSE lines;
- ignore comments and `[DONE]`;
- recursively scan dict/list payloads for:
  - `type == "image_generation_call"` with `result`;
  - `partial_image_b64`;
- keep the newest image b64 seen;
- treat no image as `empty_response`.

## Tests to copy/adapt

Hermes tests worth porting conceptually:

1. Provider metadata:
   - provider name is `openai-codex`;
   - default model is `gpt-image-2-medium`;
   - model list is low/medium/high.

2. Availability:
   - unavailable without Codex token;
   - available with Codex token;
   - `OPENAI_API_KEY` alone does not make Codex provider available.

3. Request shape:
   - host model is `gpt-5.5`;
   - `store` is false;
   - `tool_choice` requires `image_generation`;
   - image tool model is `gpt-image-2`;
   - requested size matches aspect ratio;
   - output format is PNG.

4. Streaming parser:
   - handles `response.output_item.done` with `image_generation_call.result`;
   - handles `response.image_generation_call.partial_image`;
   - recursively finds final image in `response.completed`;
   - empty stream returns `empty_response`.

5. Persistence:
   - saves b64 PNG to disk;
   - persists provider/model/quality/size/prompt metadata into ForgeGraph `AssetVersion` lineage;
   - marks capability snapshot as `production_quality_capable=True` only for this provider.

## Known upstream caveats

Do not copy blindly without accounting for these issues:

### #24965 — closed

Confirms the desired use case exactly:

> Use paid ChatGPT/Codex subscription for image generation without configuring FAL_KEY.

This is the strongest evidence that the path is intended and copyable.

### #19505 — closed

Historical bug where Codex image generation failed because the request shape/tool choice drifted. Current source uses the newer shape above. ForgeGraph should isolate this behind tests so backend drift becomes obvious.

### #35861 — open

Current/possible bug:

```text
OpenAI image generation via Codex auth failed: 'NoneType' object is not iterable
```

ForgeGraph should wrap Codex calls defensively and never degrade to placeholder delivery on provider failure.

### #21661 — open

Image editing is not complete for `openai-codex`. Not relevant to first media-quality PR unless ForgeGraph wants reference-image/edit workflows later.

### #14959 — open

Local file output is not automatically deliverable to all HTTP clients. ForgeGraph should persist generated bytes into its own asset store and expose them through existing asset/package delivery, not raw local paths.

## Non-negotiable product boundary

ForgeGraph features must be able to run independently of Hermes. Hermes Agent is a useful reference implementation, not a runtime dependency, credential source, orchestration layer, or required local tool.

Implications:

- Do not call Hermes tools from ForgeGraph production code.
- Do not require Hermes profiles, Hermes auth files, Hermes cache directories, or Hermes gateways.
- Copy/adapt the implementation pattern into ForgeGraph-owned services.
- ForgeGraph must own provider configuration, credentials, token refresh/validation, asset persistence, QA state, and fallback policy.
- If Codex image generation is not configured, ForgeGraph should surface configuration-required state and setup guidance; it should not silently switch to another provider as the primary path.

## Updated ForgeGraph implementation recommendation

First media-quality PR should be:

### 1. Mark current `codex_spec_renderer` as placeholder-only

Add provider/capability metadata:

```py
provider_key="codex_spec_renderer"
artifact_kind="placeholder_png"
production_quality_capable=False
quality_tier="placeholder"
```

Atlas delivery cannot mark these client-ready.

### 2. Add `openai_codex_image_generation` production provider

Create a provider that implements the Hermes request shape:

```text
Codex OAuth token
→ POST /backend-api/codex/responses
→ required image_generation tool
→ gpt-image-2 PNG b64
→ persist AssetVersion
```

Suggested ForgeGraph provider key:

```text
openai_codex_image_generation
```

Capabilities:

```py
artifact_kind="image/png"
production_quality_capable=True
quality_tier="production"
```

### 3. Wire Atlas media worker selection

For client-ready requested media:

1. If `openai_codex_image_generation` is configured and available, use it as the primary production media provider.
2. If it is not configured, return an explicit configuration-required/blocked status with setup guidance for ForgeGraph-owned Codex image generation. Do not silently use Gemini as the primary path.
3. If `openai_codex_image_generation` is configured but unavailable or fails at runtime, use Gemini only as a true redundancy fallback when Gemini is explicitly configured and permitted for the engagement.
4. If neither production provider can produce a real image artifact, fail/hold with `no_production_media_provider_configured` or provider-specific blocked status.
5. Never silently fall back to `codex_spec_renderer` for client-ready media.

### 4. Persist provenance

For each generated asset version, persist:

```text
provider_key
provider_display_name
model=tier id, e.g. gpt-image-2-medium
api_model=gpt-image-2
quality=medium/high
size=1024x1024 etc.
prompt
prompt_sha256
mime_type=image/png
byte_size
width
height
source=codex_responses_image_generation
qa_status
```

### 5. Add smoke command before enabling client-ready route

Add a local management command or pytest-marked integration smoke:

```text
python manage.py generate_media_smoke --provider openai_codex_image_generation --prompt "single premium sunglasses product photo, no text, no people" --aspect square
```

The smoke should verify:

- provider selected;
- PNG bytes saved;
- dimensions match expected aspect;
- `AssetVersion` persisted;
- QA gate says production-capable;
- no placeholder renderer was involved.

## Immediate open design decision

How should ForgeGraph-owned Codex OAuth/config be implemented so `openai_codex_image_generation` can be configured, refreshed, validated, audited, and run without depending on Hermes profiles, auth files, cache paths, gateways, or tools?

Recommendation:

- Treat `openai_codex_image_generation` as the primary production image provider.
- Add ForgeGraph-owned setup/configuration state for Codex image generation.
- If Codex is not configured, block client-ready media with a clear configuration-required status and setup guidance.
- Use Gemini only as a redundancy fallback when Codex is configured but temporarily unavailable/failing and Gemini is explicitly configured/permitted.
- Copy Hermes' request/header/SSE behavior as reference implementation only; do not call Hermes at runtime.
