"use client";

import { useCallback, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/ui/form-field";
import { KeyValueEditor } from "@/components/ui/key-value-editor";
import { Separator } from "@/components/ui/separator";
import { AgentFields, type AgentConfig } from "./AgentFields";
import { AdvancedSettings, type AdvancedConfig } from "./AdvancedSettings";
import { validateUrl, validateJson } from "@/lib/form-validation";
import type { NodeFormProps } from "../NodeConfigDialog";

/**
 * HTTP node specific configuration
 */
interface HttpConfig extends AgentConfig, AdvancedConfig {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  url?: string;
  headers?: Record<string, string>;
  body?: string;
  output_key?: string;
}

const HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"] as const;

export function HttpNodeForm({ config, onChange, errors, setErrors }: NodeFormProps) {
  const httpConfig = config as HttpConfig;

  const handleChange = useCallback(
    <K extends keyof HttpConfig>(field: K, value: HttpConfig[K]) => {
      onChange({ ...config, [field]: value });
    },
    [config, onChange]
  );

  const handleAgentChange = useCallback(
    (agentConfig: AgentConfig) => {
      onChange({ ...config, ...agentConfig });
    },
    [config, onChange]
  );

  const handleAdvancedChange = useCallback(
    (advancedConfig: AdvancedConfig) => {
      onChange({ ...config, ...advancedConfig });
    },
    [config, onChange]
  );

  // Validate URL and body on change
  useEffect(() => {
    const newErrors: Record<string, string> = {};

    const urlError = validateUrl(httpConfig.url || "", "URL");
    if (urlError && httpConfig.url) {
      newErrors.url = urlError.message;
    }

    if (httpConfig.body && httpConfig.method !== "GET") {
      const bodyError = validateJson(httpConfig.body, "Body");
      if (bodyError) {
        newErrors.body = bodyError.message;
      }
    }

    setErrors(newErrors);
  }, [httpConfig.url, httpConfig.body, httpConfig.method, setErrors]);

  const showBody = httpConfig.method !== "GET";

  return (
    <div className="space-y-6">
      {/* Agent Context - Minimal for HTTP */}
      <AgentFields
        config={httpConfig}
        onChange={handleAgentChange}
        showRole={false}
        showExamples={false}
      />

      <Separator />

      {/* HTTP Configuration */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">HTTP Request</h3>

        <div className="flex gap-2">
          <FormField label="Method" htmlFor="method" className="w-32">
            <select
              id="method"
              value={httpConfig.method || "GET"}
              onChange={(e) =>
                handleChange("method", e.target.value as HttpConfig["method"])
              }
              className="w-full px-3 py-2 border rounded-md bg-background text-sm"
            >
              {HTTP_METHODS.map((method) => (
                <option key={method} value={method}>
                  {method}
                </option>
              ))}
            </select>
          </FormField>

          <FormField
            label="URL"
            htmlFor="url"
            className="flex-1"
            required
            error={errors.url}
          >
            <Input
              id="url"
              value={httpConfig.url || ""}
              onChange={(e) => handleChange("url", e.target.value)}
              placeholder="https://api.example.com/endpoint"
              className="text-sm font-mono"
            />
          </FormField>
        </div>

        <FormField
          label="Headers"
          description="HTTP headers to include with the request"
        >
          <KeyValueEditor
            value={httpConfig.headers || {}}
            onChange={(headers) => handleChange("headers", headers)}
            keyPlaceholder="Header name"
            valuePlaceholder="Header value"
          />
        </FormField>

        {showBody && (
          <FormField
            label="Request Body"
            htmlFor="body"
            description="JSON body for the request. Use {{variable}} for interpolation."
            error={errors.body}
          >
            <Textarea
              id="body"
              value={httpConfig.body || ""}
              onChange={(e) => handleChange("body", e.target.value)}
              placeholder='{"key": "{{value}}"}'
              rows={5}
              className="text-sm resize-none font-mono"
            />
          </FormField>
        )}

        <FormField
          label="Output Key"
          htmlFor="output-key"
          description="Key to store the response under in state"
        >
          <Input
            id="output-key"
            value={httpConfig.output_key || ""}
            onChange={(e) => handleChange("output_key", e.target.value)}
            placeholder="response"
            className="text-sm"
          />
        </FormField>
      </div>

      <Separator />

      {/* Advanced Settings */}
      <AdvancedSettings config={httpConfig} onChange={handleAdvancedChange} />
    </div>
  );
}

export default HttpNodeForm;
