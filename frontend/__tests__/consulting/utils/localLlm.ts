const LOCAL_LLM_BASE_URL = (
  process.env.OPENAI_BASE_URL ??
  process.env.LOCAL_LLM_BASE_URL ??
  process.env.PLAYWRIGHT_LOCAL_LLM_URL ??
  (process.env.PLAYWRIGHT_LLM_MOCK_URL ? `${process.env.PLAYWRIGHT_LLM_MOCK_URL}/v1` : "http://127.0.0.1:12434/v1")
).replace(/\/$/, "");

const LOCAL_LLM_API_KEY = process.env.OPENAI_API_KEY ?? "playwright-openai-key";
const CONFIGURED_MODEL = process.env.PLAYWRIGHT_CONSULTING_LLM_MODEL ?? process.env.OPENAI_MODEL;
let resolvedModelPromise: Promise<string> | null = null;
let resolvedChatCompletionsUrlPromise: Promise<string> | null = null;

function stripMarkdownFences(raw: string): string {
  return raw.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
}

function extractJsonObject(raw: string): string {
  const trimmed = stripMarkdownFences(raw.trim());
  const firstBrace = trimmed.indexOf("{");
  const lastBrace = trimmed.lastIndexOf("}");
  if (firstBrace === -1 || lastBrace === -1 || lastBrace < firstBrace) {
    throw new Error(`LLM response did not contain a JSON object: ${raw}`);
  }
  return trimmed.slice(firstBrace, lastBrace + 1);
}

function candidateBaseUrls(): string[] {
  const candidates = new Set<string>();
  const normalizedBase = LOCAL_LLM_BASE_URL.replace(/\/$/, "");
  candidates.add(normalizedBase);

  if (normalizedBase.endsWith("/v1")) {
    candidates.add(normalizedBase.slice(0, -3));
  } else {
    candidates.add(`${normalizedBase}/v1`);
  }

  return [...candidates].filter(Boolean);
}

async function tryFetchJson(url: string): Promise<Response | null> {
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${LOCAL_LLM_API_KEY}`,
    },
  });

  if (response.ok) {
    return response;
  }

  if (response.status === 404) {
    return null;
  }

  const errorBody = await response.text();
  throw new Error(`Local LLM request failed with ${response.status}: ${errorBody}`);
}

async function resolveModel(): Promise<string> {
  if (CONFIGURED_MODEL) {
    return CONFIGURED_MODEL;
  }
  if (!resolvedModelPromise) {
    resolvedModelPromise = (async () => {
      const responses = await Promise.all(candidateBaseUrls().map((baseUrl) => tryFetchJson(`${baseUrl}/models`)));
      const response = responses.find((candidate): candidate is Response => Boolean(candidate));

      if (!response) {
        throw new Error(
          `Local LLM model discovery failed with 404 across candidates: ${candidateBaseUrls().join(", ")}`,
        );
      }

      const body = (await response.json()) as {
        data?: Array<{
          id?: string | null;
        }>;
      };
      const discoveredModel = body.data?.find((entry) => typeof entry.id === "string" && entry.id.trim())?.id?.trim();
      if (!discoveredModel) {
        throw new Error(`Local LLM model discovery returned no usable model id: ${JSON.stringify(body)}`);
      }
      return discoveredModel;
    })();
  }
  return resolvedModelPromise;
}

async function resolveChatCompletionsUrl(): Promise<string> {
  if (!resolvedChatCompletionsUrlPromise) {
    resolvedChatCompletionsUrlPromise = (async () => {
      const candidates = candidateBaseUrls().flatMap((baseUrl) => [`${baseUrl}/chat/completions`]);

      const probeResults = await Promise.all(
        candidates.map(async (url) => {
          const probeResponse = await fetch(url, {
            method: "OPTIONS",
            headers: {
              Authorization: `Bearer ${LOCAL_LLM_API_KEY}`,
            },
          }).catch(() => null);
          return probeResponse && probeResponse.status !== 404 ? url : null;
        }),
      );

      return probeResults.find((url): url is string => Boolean(url)) ?? candidates[0] ?? `${LOCAL_LLM_BASE_URL}/chat/completions`;
    })();
  }

  return resolvedChatCompletionsUrlPromise;
}

export async function callLocalLlmJson<T>({
  systemPrompt,
  userPrompt,
  maxTokens = 700,
}: {
  systemPrompt: string;
  userPrompt: string;
  maxTokens?: number;
}): Promise<T> {
  const [model, chatCompletionsUrl] = await Promise.all([resolveModel(), resolveChatCompletionsUrl()]);
  const response = await fetch(chatCompletionsUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${LOCAL_LLM_API_KEY}`,
    },
    body: JSON.stringify({
      model,
      temperature: 0,
      max_tokens: maxTokens,
      stream: false,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt },
      ],
    }),
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`Local LLM request failed with ${response.status}: ${errorBody}`);
  }

  const body = (await response.json()) as {
    choices?: Array<{
      message?: {
        content?: string | null;
      };
    }>;
  };
  const rawContent = body.choices?.[0]?.message?.content;
  if (!rawContent) {
    throw new Error(`Local LLM response was missing choices[0].message.content: ${JSON.stringify(body)}`);
  }

  const jsonText = extractJsonObject(rawContent);
  try {
    return JSON.parse(jsonText) as T;
  } catch (error) {
    throw new Error(
      `Failed to parse local LLM JSON response: ${
        error instanceof Error ? error.message : String(error)
      }\nRaw content:\n${rawContent}`,
    );
  }
}
