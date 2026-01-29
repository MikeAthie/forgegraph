"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/ui/form-field";
import { cn } from "@/lib/utils";

/**
 * Retry policy configuration
 */
export interface RetryPolicy {
  max_attempts?: number;
  backoff_ms?: number;
  backoff_strategy?: "fixed" | "exponential";
}

/**
 * Advanced settings for node configuration
 */
export interface AdvancedConfig {
  cache_enabled?: boolean;
  cache_ttl_ms?: number;
  timeout_ms?: number;
  retry_policy?: RetryPolicy;
}

export interface AdvancedSettingsProps {
  config: AdvancedConfig;
  onChange: (config: AdvancedConfig) => void;
  defaultExpanded?: boolean;
  className?: string;
}

/**
 * Collapsible advanced settings section for node configuration.
 * Includes caching, timeout, and retry policy settings.
 */
export function AdvancedSettings({
  config,
  onChange,
  defaultExpanded = false,
  className,
}: AdvancedSettingsProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const handleChange = <K extends keyof AdvancedConfig>(
    field: K,
    value: AdvancedConfig[K]
  ) => {
    onChange({ ...config, [field]: value });
  };

  const handleRetryChange = <K extends keyof RetryPolicy>(
    field: K,
    value: RetryPolicy[K]
  ) => {
    onChange({
      ...config,
      retry_policy: { ...config.retry_policy, [field]: value },
    });
  };

  return (
    <div className={cn("border rounded-lg", className)}>
      {/* Header */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors rounded-lg"
      >
        <span>Advanced Settings</span>
        {isExpanded ? (
          <ChevronDown className="w-4 h-4" />
        ) : (
          <ChevronRight className="w-4 h-4" />
        )}
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="px-3 pb-3 space-y-4 border-t">
          <div className="pt-3 space-y-4">
            {/* Caching */}
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="cache-enabled"
                  checked={config.cache_enabled || false}
                  onChange={(e) => handleChange("cache_enabled", e.target.checked)}
                  className="rounded border-input"
                />
                <label htmlFor="cache-enabled" className="text-sm font-medium">
                  Enable Caching
                </label>
              </div>

              {config.cache_enabled && (
                <FormField
                  label="Cache TTL (ms)"
                  htmlFor="cache-ttl"
                  description="How long to cache results (in milliseconds)"
                >
                  <Input
                    id="cache-ttl"
                    type="number"
                    min={0}
                    value={config.cache_ttl_ms || ""}
                    onChange={(e) =>
                      handleChange(
                        "cache_ttl_ms",
                        e.target.value ? parseInt(e.target.value, 10) : undefined
                      )
                    }
                    placeholder="60000"
                    className="text-sm"
                  />
                </FormField>
              )}
            </div>

            {/* Timeout */}
            <FormField
              label="Timeout (ms)"
              htmlFor="timeout"
              description="Maximum time to wait for this node to complete"
            >
              <Input
                id="timeout"
                type="number"
                min={0}
                value={config.timeout_ms || ""}
                onChange={(e) =>
                  handleChange(
                    "timeout_ms",
                    e.target.value ? parseInt(e.target.value, 10) : undefined
                  )
                }
                placeholder="30000"
                className="text-sm"
              />
            </FormField>

            {/* Retry Policy */}
            <div className="space-y-3">
              <label className="text-sm font-medium">Retry Policy</label>

              <div className="grid grid-cols-2 gap-3">
                <FormField label="Max Attempts" htmlFor="retry-max">
                  <Input
                    id="retry-max"
                    type="number"
                    min={1}
                    max={10}
                    value={config.retry_policy?.max_attempts || ""}
                    onChange={(e) =>
                      handleRetryChange(
                        "max_attempts",
                        e.target.value ? parseInt(e.target.value, 10) : undefined
                      )
                    }
                    placeholder="3"
                    className="text-sm"
                  />
                </FormField>

                <FormField label="Backoff (ms)" htmlFor="retry-backoff">
                  <Input
                    id="retry-backoff"
                    type="number"
                    min={0}
                    value={config.retry_policy?.backoff_ms || ""}
                    onChange={(e) =>
                      handleRetryChange(
                        "backoff_ms",
                        e.target.value ? parseInt(e.target.value, 10) : undefined
                      )
                    }
                    placeholder="1000"
                    className="text-sm"
                  />
                </FormField>
              </div>

              <FormField label="Backoff Strategy" htmlFor="retry-strategy">
                <select
                  id="retry-strategy"
                  value={config.retry_policy?.backoff_strategy || "exponential"}
                  onChange={(e) =>
                    handleRetryChange(
                      "backoff_strategy",
                      e.target.value as "fixed" | "exponential"
                    )
                  }
                  className="w-full px-3 py-2 border rounded-md bg-background text-sm"
                >
                  <option value="exponential">Exponential</option>
                  <option value="fixed">Fixed</option>
                </select>
              </FormField>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AdvancedSettings;
