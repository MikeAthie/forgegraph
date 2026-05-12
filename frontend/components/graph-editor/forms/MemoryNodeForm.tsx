"use client";

import { useCallback } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/ui/form-field";
import { Separator } from "@/components/ui/separator";
import { AgentFields, type AgentConfig } from "./AgentFields";
import { AdvancedSettings, type AdvancedConfig } from "./AdvancedSettings";
import type { NodeFormProps } from "../NodeConfigDialog";

/**
 * Memory node specific configuration
 */
interface MemoryConfig extends AgentConfig, AdvancedConfig {
  memory_type?: "conversation" | "buffer" | "summary" | "vector";
  key?: string;
  memory_key?: string;
  max_messages?: number;
  max_tokens?: number;
  retrieval_query?: string;
  top_k?: number;
}

const MEMORY_TYPES = [
  {
    value: "conversation",
    label: "Conversation Buffer",
    description: "Store full conversation history",
  },
  {
    value: "buffer",
    label: "Rolling Buffer",
    description: "Keep last N messages",
  },
  {
    value: "summary",
    label: "Summary Memory",
    description: "Summarize older messages to save tokens",
  },
  {
    value: "vector",
    label: "Vector Store",
    description: "Semantic search over stored memories",
  },
] as const;

const MEMORY_DEPTH_OPTIONS = [
  { value: "short", label: "Short (last 10 messages)", bufferSize: 10 },
  { value: "medium", label: "Medium (last 20 messages)", bufferSize: 20 },
  { value: "long", label: "Long (last 50 messages)", bufferSize: 50 },
  { value: "extended", label: "Extended (last 100 messages)", bufferSize: 100 },
  { value: "custom", label: "Custom", bufferSize: null },
] as const;

export function MemoryNodeForm({ config, onChange }: NodeFormProps) {
  const memoryConfig = config as MemoryConfig;
  const resolvedKey = memoryConfig.key ?? memoryConfig.memory_key ?? "";
  const selectedDepth =
    MEMORY_DEPTH_OPTIONS.find((option) => option.bufferSize === memoryConfig.max_messages)?.value || "custom";

  const handleChange = useCallback(
    <K extends keyof MemoryConfig>(field: K, value: MemoryConfig[K]) => {
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

  const showBufferOptions = memoryConfig.memory_type === "buffer";
  const showVectorOptions = memoryConfig.memory_type === "vector";
  const showSummaryOptions = memoryConfig.memory_type === "summary";

  return (
    <div className="space-y-6">
      {/* Agent Context - Minimal for Memory */}
      <AgentFields
        config={memoryConfig}
        onChange={handleAgentChange}
        visibleSections={{ role: false, examples: false }}
      />

      <Separator />

      {/* Memory Configuration */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Memory Configuration</h3>

        <p className="text-sm text-muted-foreground">
          Configure how the agent stores and retrieves information across interactions.
        </p>

        <FormField label="Memory Type" htmlFor="memory-type" description="Strategy for storing and managing memory">
          <select
            id="memory-type"
            value={memoryConfig.memory_type || "conversation"}
            onChange={(e) => handleChange("memory_type", e.target.value as MemoryConfig["memory_type"])}
            className="w-full px-3 py-2 border rounded-md bg-background text-sm"
          >
            {MEMORY_TYPES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
        </FormField>

        <div className="p-3 bg-muted/50 rounded-md text-xs">
          {MEMORY_TYPES.find((t) => t.value === (memoryConfig.memory_type || "conversation"))?.description}
        </div>

        <FormField label="Memory Key" htmlFor="memory-key" description="State key to store/retrieve memory from">
          <Input
            id="memory-key"
            value={resolvedKey}
            onChange={(e) => onChange({ ...config, key: e.target.value })}
            placeholder="conversation_history"
            className="text-sm"
          />
        </FormField>

        {showBufferOptions && (
          <>
            <FormField
              label="Memory Depth"
              htmlFor="memory-depth"
              description="How many recent messages to keep in the rolling buffer"
            >
              <select
                id="memory-depth"
                value={selectedDepth}
                onChange={(e) => {
                  const option = MEMORY_DEPTH_OPTIONS.find((o) => o.value === e.target.value);
                  if (!option) return;
                  if (option.bufferSize) {
                    handleChange("max_messages", option.bufferSize);
                  } else {
                    handleChange("max_messages", undefined);
                  }
                }}
                className="w-full px-3 py-2 border rounded-md bg-background text-sm"
              >
                {MEMORY_DEPTH_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </FormField>

            {selectedDepth === "custom" && (
              <FormField
                label="Custom Buffer Size"
                htmlFor="max-messages"
                description="Maximum number of messages to keep in buffer"
              >
                <Input
                  id="max-messages"
                  type="number"
                  min={1}
                  max={1000}
                  value={memoryConfig.max_messages || ""}
                  onChange={(e) =>
                    handleChange("max_messages", e.target.value ? parseInt(e.target.value, 10) : undefined)
                  }
                  placeholder="100"
                  className="text-sm"
                />
              </FormField>
            )}
          </>
        )}

        {showSummaryOptions && (
          <FormField label="Max Tokens" htmlFor="max-tokens" description="Token limit before triggering summarization">
            <Input
              id="max-tokens"
              type="number"
              min={100}
              max={100000}
              value={memoryConfig.max_tokens || ""}
              onChange={(e) => handleChange("max_tokens", e.target.value ? parseInt(e.target.value, 10) : undefined)}
              placeholder="4000"
              className="text-sm"
            />
          </FormField>
        )}

        {showVectorOptions && (
          <>
            <FormField
              label="Retrieval Query"
              htmlFor="retrieval-query"
              description="Template for generating retrieval queries"
            >
              <Textarea
                id="retrieval-query"
                value={memoryConfig.retrieval_query || ""}
                onChange={(e) => handleChange("retrieval_query", e.target.value)}
                placeholder="{{input.question}}"
                rows={2}
                className="text-sm resize-none font-mono"
              />
            </FormField>

            <FormField label="Top K Results" htmlFor="top-k" description="Number of similar memories to retrieve">
              <Input
                id="top-k"
                type="number"
                min={1}
                max={100}
                value={memoryConfig.top_k || ""}
                onChange={(e) => handleChange("top_k", e.target.value ? parseInt(e.target.value, 10) : undefined)}
                placeholder="5"
                className="text-sm"
              />
            </FormField>
          </>
        )}
      </div>

      <Separator />

      {/* Advanced Settings */}
      <AdvancedSettings config={memoryConfig} onChange={handleAdvancedChange} />
    </div>
  );
}
