"use client";

import { useCallback, useEffect, useMemo, useReducer } from "react";
import Link from "next/link";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/ui/form-field";
import { Button } from "@/components/ui/button";
import { KeyValueEditor } from "@/components/ui/key-value-editor";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { AgentFields, type AgentConfig } from "./AgentFields";
import { AdvancedSettings, type AdvancedConfig } from "./AdvancedSettings";
import { validateUrl, validateJson } from "@/lib/form-validation";
import { getApiErrorMessage, integrationsApi, type Credential, type HttpNodeTestResult } from "@/lib/api";
import { useCredentialOptions } from "./useCredentialOptions";
import type { NodeFormProps } from "../NodeConfigDialog";

/**
 * HTTP node specific configuration
 */
interface HttpConfig extends AgentConfig, AdvancedConfig {
  [key: string]: unknown;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  url?: string;
  headers?: Record<string, string>;
  provider?: string;
  credential_id?: string;
  body?: string;
  output_key?: string;
}

const HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"] as const;
const PROVIDERS = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "google", label: "Google AI" },
  { value: "gmail", label: "Gmail" },
  { value: "google_calendar", label: "Google Calendar" },
  { value: "google_tasks", label: "Google Tasks" },
  { value: "notion", label: "Notion" },
  { value: "slack", label: "Slack" },
  { value: "jira", label: "Jira" },
  { value: "linear", label: "Linear" },
  { value: "hubspot", label: "HubSpot" },
  { value: "google_drive", label: "Google Drive" },
  { value: "telegram", label: "Telegram" },
  { value: "twilio", label: "Twilio" },
];

type HttpFormState = {
  isRunningTest: boolean;
  testResult: HttpNodeTestResult | null;
  testError: string | null;
  twilioAccountSid: string;
};

type HttpFormAction =
  | { type: "twilio-account-sid"; value: string }
  | { type: "test-start" }
  | { type: "test-success"; result: HttpNodeTestResult }
  | { type: "test-error"; error: string };

const initialHttpFormState: HttpFormState = {
  isRunningTest: false,
  testResult: null,
  testError: null,
  twilioAccountSid: "",
};

function httpFormReducer(state: HttpFormState, action: HttpFormAction): HttpFormState {
  switch (action.type) {
    case "twilio-account-sid":
      return { ...state, twilioAccountSid: action.value };
    case "test-start":
      return { ...state, isRunningTest: true, testResult: null, testError: null };
    case "test-success":
      return { ...state, isRunningTest: false, testResult: action.result, testError: null };
    case "test-error":
      return { ...state, isRunningTest: false, testResult: null, testError: action.error };
    default:
      return state;
  }
}

function HttpTestPanel({
  provider,
  providerHint,
  providerDocsUrl,
  isRunningTest,
  testError,
  testResult,
  twilioAccountSid,
  onRunTest,
  onTwilioAccountSidChange,
}: {
  provider: string;
  providerHint: string;
  providerDocsUrl: string | null;
  isRunningTest: boolean;
  testError: string | null;
  testResult: HttpNodeTestResult | null;
  twilioAccountSid: string;
  onRunTest: () => void;
  onTwilioAccountSidChange: (value: string) => void;
}) {
  return (
    <div className="space-y-3 rounded-md border border-border bg-muted/30 p-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium">Run test</p>
          <p className="text-xs text-muted-foreground">{providerHint}</p>
          {providerDocsUrl ? (
            <a href={providerDocsUrl} target="_blank" rel="noopener noreferrer" className="text-xs underline underline-offset-2">
              Provider docs
            </a>
          ) : null}
        </div>
        <Button type="button" variant="outline" onClick={onRunTest} disabled={isRunningTest}>
          {isRunningTest ? (
            <>
              <Spinner className="mr-2 size-3.5" />
              Testing…
            </>
          ) : (
            "Run test"
          )}
        </Button>
      </div>

      {provider === "twilio" ? (
        <FormField
          label="Twilio Account SID (test)"
          htmlFor="twilio-account-sid"
          description="Required when testing Twilio endpoints so auth can be generated."
        >
          <Input
            id="twilio-account-sid"
            value={twilioAccountSid}
            onChange={(event) => onTwilioAccountSidChange(event.target.value)}
            placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            className="text-sm font-mono"
          />
        </FormField>
      ) : null}

      {testError ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {testError}
        </div>
      ) : null}

      {testResult ? (
        <div className="space-y-2 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs">
          <p className="font-medium text-emerald-700 dark:text-emerald-300">
            Test result: {testResult.status_code} {testResult.ok ? "(ok)" : "(failed)"}
          </p>
          <pre className="max-h-44 overflow-auto rounded border border-border bg-background/80 p-2 font-mono text-[11px]">
            {JSON.stringify(testResult.body, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

function HttpCredentialSection({
  provider,
  filteredCredentials,
  selectedCredential,
  credentialsLoading,
  credentialsError,
  onProviderChange,
  onCredentialChange,
}: {
  provider: string;
  filteredCredentials: Credential[];
  selectedCredential: Credential | undefined;
  credentialsLoading: boolean;
  credentialsError: string | null;
  onProviderChange: (provider: string) => void;
  onCredentialChange: (credentialId: string | undefined) => void;
}) {
  return (
    <>
      <div className="grid grid-cols-2 gap-4">
        <FormField label="Credential Provider" htmlFor="provider">
          <select
            id="provider"
            value={provider}
            onChange={(event) => onProviderChange(event.target.value)}
            className="w-full px-3 py-2 border rounded-md bg-background text-sm"
          >
            {PROVIDERS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </FormField>

        <FormField label="Credential" htmlFor="credential-id" description="Optional stored secret for this integration.">
          <select
            id="credential-id"
            value={selectedCredential?.id || ""}
            onChange={(event) => onCredentialChange(event.target.value || undefined)}
            className="w-full px-3 py-2 border rounded-md bg-background text-sm"
          >
            <option value="">Use manual/env auth</option>
            {filteredCredentials.map((cred) => (
              <option key={cred.id} value={cred.id}>
                {cred.name} ({cred.key_hint})
              </option>
            ))}
          </select>
          {credentialsLoading ? (
            <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
              <Spinner className="size-3" />
              Loading credentials…
            </div>
          ) : null}
          {!credentialsLoading && credentialsError ? (
            <div className="mt-2 text-xs text-destructive">{credentialsError}</div>
          ) : null}
          {!credentialsLoading && !credentialsError && filteredCredentials.length === 0 ? (
            <div className="mt-2 text-xs text-muted-foreground">
              No credentials found for this provider. Add one in the Credentials page.{" "}
              <Link href={`/credentials?provider=${encodeURIComponent(provider)}`} className="underline underline-offset-2">
                Open credentials
              </Link>
            </div>
          ) : null}
        </FormField>
      </div>

      {selectedCredential && selectedCredential.health_status !== "healthy" ? (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          <p className="font-medium">
            {selectedCredential.health_status === "expired"
              ? "Selected credential is expired."
              : "Selected credential is expiring soon."}
          </p>
          {selectedCredential.health_message ? <p className="mt-1">{selectedCredential.health_message}</p> : null}
          {selectedCredential.requires_reauth ? (
            <Link
              href={`/credentials?provider=${encodeURIComponent(provider)}`}
              className="mt-1 inline-block underline underline-offset-2"
            >
              Reconnect this credential in Credentials
            </Link>
          ) : null}
        </div>
      ) : null}
    </>
  );
}

export function HttpNodeForm({ config, onChange, errors, setErrors }: NodeFormProps) {
  const httpConfig = config as HttpConfig;
  const { credentials, loading: credentialsLoading, error: credentialsError } = useCredentialOptions();
  const [{ isRunningTest, testResult, testError, twilioAccountSid }, dispatchHttpForm] = useReducer(
    httpFormReducer,
    initialHttpFormState,
  );
  const reportErrors = useCallback((nextErrors: Record<string, string>) => setErrors(nextErrors), [setErrors]);
  const effectiveMethod = httpConfig.method ?? "GET";
  const configuredCredential = useMemo(
    () => credentials.find((item) => item.id === httpConfig.credential_id),
    [credentials, httpConfig.credential_id],
  );
  const provider = httpConfig.provider || configuredCredential?.provider || "openai";
  const filteredCredentials = useMemo(
    () => credentials.filter((item) => item.provider === provider),
    [credentials, provider],
  );
  const selectedCredential = useMemo(
    () => filteredCredentials.find((item) => item.id === httpConfig.credential_id),
    [filteredCredentials, httpConfig.credential_id],
  );
  const contentTypeHeader = useMemo(() => {
    const headers = httpConfig.headers || {};
    const contentTypeEntry = Object.entries(headers).find(([key]) => key.trim().toLowerCase() === "content-type");
    return (contentTypeEntry?.[1] || "").toString().toLowerCase();
  }, [httpConfig.headers]);
  const shouldValidateJsonBody =
    effectiveMethod !== "GET" &&
    (contentTypeHeader.includes("application/json") || contentTypeHeader.trim().length === 0);

  const handleChange = useCallback(
    <K extends keyof HttpConfig>(field: K, value: HttpConfig[K]) => {
      onChange({ ...config, [field]: value });
    },
    [config, onChange],
  );

  const handleAgentChange = useCallback(
    (agentConfig: AgentConfig) => {
      onChange({ ...config, ...agentConfig });
    },
    [config, onChange],
  );

  const handleAdvancedChange = useCallback(
    (advancedConfig: AdvancedConfig) => {
      onChange({ ...config, ...advancedConfig });
    },
    [config, onChange],
  );

  const handleProviderChange = useCallback(
    (nextProvider: string) => {
      const nextConfig: HttpConfig = { ...httpConfig, provider: nextProvider };
      if (httpConfig.credential_id && provider !== nextProvider) {
        delete nextConfig.credential_id;
      }
      onChange(nextConfig);
    },
    [httpConfig, onChange, provider],
  );

  useEffect(() => {
    const newErrors: Record<string, string> = {};

    const urlError = validateUrl(httpConfig.url || "", "URL");
    if (urlError && httpConfig.url) {
      newErrors.url = urlError.message;
    }

    if (httpConfig.body && shouldValidateJsonBody) {
      const bodyError = validateJson(httpConfig.body, "Body");
      if (bodyError) {
        newErrors.body = bodyError.message;
      }
    }

    reportErrors(newErrors);
  }, [httpConfig.url, httpConfig.body, shouldValidateJsonBody, reportErrors]);

  useEffect(() => {
    if (provider !== "twilio") return;
    if (twilioAccountSid.trim()) return;
    const match = (httpConfig.url || "").match(/Accounts\/([^/]+)/i);
    if (match?.[1]) {
      dispatchHttpForm({ type: "twilio-account-sid", value: decodeURIComponent(match[1]) });
    }
  }, [httpConfig.url, provider, twilioAccountSid]);

  const providerDocsUrl = useMemo(() => {
    switch (provider) {
      case "telegram":
        return "https://core.telegram.org/bots/api";
      case "twilio":
        return "https://www.twilio.com/docs/whatsapp/api";
      case "gmail":
        return "https://developers.google.com/gmail/api/reference/rest";
      case "google_calendar":
        return "https://developers.google.com/calendar/api/v3/reference";
      case "google_tasks":
        return "https://developers.google.com/tasks/reference/rest";
      default:
        return null;
    }
  }, [provider]);

  const providerHint = useMemo(() => {
    switch (provider) {
      case "telegram":
        return "Use bot token credential and keep /bot{{credentials.telegram_token}} in the URL.";
      case "twilio":
        return "Use Twilio credential + Account SID; auth header is generated as Basic auth during test.";
      case "gmail":
        return "OAuth credential should include gmail.readonly / gmail.send scopes depending on endpoint.";
      case "google_calendar":
        return "Use timeMin/timeMax ISO timestamps for event listing to avoid empty results.";
      case "google_tasks":
        return "Provide task list id and ensure Google Tasks OAuth scopes are enabled.";
      default:
        return "Configure provider, credentials, and endpoint before running the test request.";
    }
  }, [provider]);

  const handleRunTest = useCallback(async () => {
    const trimmedUrl = (httpConfig.url || "").trim();
    if (!trimmedUrl) {
      dispatchHttpForm({ type: "test-error", error: "URL is required before running a test." });
      return;
    }

    const urlError = validateUrl(trimmedUrl, "URL");
    if (urlError) {
      dispatchHttpForm({ type: "test-error", error: urlError.message });
      return;
    }

    if (httpConfig.body && shouldValidateJsonBody) {
      const bodyError = validateJson(httpConfig.body, "Body");
      if (bodyError) {
        dispatchHttpForm({ type: "test-error", error: bodyError.message });
        return;
      }
    }

    dispatchHttpForm({ type: "test-start" });
    try {
      const result = await integrationsApi.runHttpNodeTest({
        method: effectiveMethod,
        url: trimmedUrl,
        headers: httpConfig.headers || {},
        body: effectiveMethod === "GET" ? undefined : httpConfig.body || "",
        provider,
        credential_id: httpConfig.credential_id,
        account_sid: provider === "twilio" ? twilioAccountSid.trim() || undefined : undefined,
      });
      dispatchHttpForm({ type: "test-success", result });
    } catch (err: unknown) {
      dispatchHttpForm({ type: "test-error", error: getApiErrorMessage(err, "HTTP test failed.") });
    }
  }, [
    effectiveMethod,
    httpConfig.body,
    httpConfig.credential_id,
    httpConfig.headers,
    httpConfig.url,
    provider,
    shouldValidateJsonBody,
    twilioAccountSid,
  ]);

  const showBody = effectiveMethod !== "GET";

  return (
    <div className="space-y-6">
      {/* Agent Context - Minimal for HTTP */}
      <AgentFields
        config={httpConfig}
        onChange={handleAgentChange}
        visibleSections={{ role: false, examples: false }}
      />

      <Separator />

      {/* HTTP Configuration */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">HTTP Request</h3>

        <div className="flex gap-2">
          <FormField label="Method" htmlFor="method" className="w-32">
            <select
              id="method"
              value={effectiveMethod}
              onChange={(e) => handleChange("method", e.target.value as HttpConfig["method"])}
              className="w-full px-3 py-2 border rounded-md bg-background text-sm"
            >
              {HTTP_METHODS.map((method) => (
                <option key={method} value={method}>
                  {method}
                </option>
              ))}
            </select>
          </FormField>

          <FormField label="URL" htmlFor="url" className="flex-1" required error={errors.url}>
            <Input
              id="url"
              value={httpConfig.url || ""}
              onChange={(e) => handleChange("url", e.target.value)}
              placeholder="https://api.example.com/endpoint"
              className="text-sm font-mono"
            />
          </FormField>
        </div>

        <FormField label="Headers" description="HTTP headers to include with the request">
          <KeyValueEditor
            value={httpConfig.headers || {}}
            onChange={(headers) => handleChange("headers", headers)}
            keyPlaceholder="Header name"
            valuePlaceholder="Header value"
          />
        </FormField>

        <HttpCredentialSection
          provider={provider}
          filteredCredentials={filteredCredentials}
          selectedCredential={selectedCredential}
          credentialsLoading={credentialsLoading}
          credentialsError={credentialsError}
          onProviderChange={handleProviderChange}
          onCredentialChange={(credentialId) => handleChange("credential_id", credentialId)}
        />

        {showBody && (
          <FormField
            label="Request Body"
            htmlFor="body"
            description={
              shouldValidateJsonBody
                ? "JSON body for the request. Use {{variable}} for interpolation."
                : "Raw body for the request. Use {{variable}} for interpolation."
            }
            error={errors.body}
          >
            <Textarea
              id="body"
              value={httpConfig.body || ""}
              onChange={(e) => handleChange("body", e.target.value)}
              placeholder={shouldValidateJsonBody ? '{"key": "{{value}}"}' : "key=value&flag=true"}
              rows={5}
              className="text-sm resize-none font-mono"
            />
          </FormField>
        )}

        <FormField label="Output Key" htmlFor="output-key" description="Key to store the response under in state">
          <Input
            id="output-key"
            value={httpConfig.output_key || ""}
            onChange={(e) => handleChange("output_key", e.target.value)}
            placeholder="response"
            className="text-sm"
          />
        </FormField>

        <HttpTestPanel
          provider={provider}
          providerHint={providerHint}
          providerDocsUrl={providerDocsUrl}
          isRunningTest={isRunningTest}
          testError={testError}
          testResult={testResult}
          twilioAccountSid={twilioAccountSid}
          onRunTest={() => void handleRunTest()}
          onTwilioAccountSidChange={(value) => dispatchHttpForm({ type: "twilio-account-sid", value })}
        />
      </div>

      <Separator />

      {/* Advanced Settings */}
      <AdvancedSettings config={httpConfig} onChange={handleAdvancedChange} />
    </div>
  );
}
