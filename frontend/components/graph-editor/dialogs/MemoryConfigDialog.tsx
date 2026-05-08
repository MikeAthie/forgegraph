"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { getApiErrorMessage, graphsApi, type MemoryConfig } from "@/lib/api";
import { showError, showSuccess } from "@/lib/toast";

type MemoryDepth = "short" | "medium" | "long" | "extended" | "custom";

const MEMORY_DEPTH_OPTIONS: Array<{ value: MemoryDepth; label: string; bufferSize: number | null }> = [
  { value: "short", label: "Short (last 10 messages)", bufferSize: 10 },
  { value: "medium", label: "Medium (last 20 messages)", bufferSize: 20 },
  { value: "long", label: "Long (last 50 messages)", bufferSize: 50 },
  { value: "extended", label: "Extended (last 100 messages)", bufferSize: 100 },
  { value: "custom", label: "Custom", bufferSize: null },
];

type MemoryConfigFormState = {
  memoryDepth: MemoryDepth;
  customBufferSize?: number;
  enablePersistence: boolean;
  autoPrepend: boolean;
  summaryTtlHours: number;
  factsTtlDays: number;
  vectorEnabled: boolean;
  vectorTopK: number;
  vectorThreshold: number;
  vectorRecencyWeight: number;
  embeddingModel: string;
  summarizationEnabled: boolean;
  summarizationThreshold: number;
  summarizationKeepRecent: number;
  summarizationModel: string;
  showAdvanced: boolean;
};

export interface MemoryConfigDialogProps {
  graphId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const deriveMemoryDepth = (bufferSize: number): MemoryDepth => {
  const preset = MEMORY_DEPTH_OPTIONS.find((option) => option.bufferSize === bufferSize);
  return preset?.value ?? "custom";
};

const toHours = (seconds: number) => Math.max(1, Math.round(seconds / 3600));
const toDays = (seconds: number) => Math.max(1, Math.round(seconds / 86400));

export function MemoryConfigDialog({ graphId, open, onOpenChange }: MemoryConfigDialogProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<MemoryConfig | null>(null);
  const [formState, setFormState] = useState<MemoryConfigFormState>({
    memoryDepth: "medium",
    customBufferSize: undefined,
    enablePersistence: false,
    autoPrepend: true,
    summaryTtlHours: 24,
    factsTtlDays: 7,
    vectorEnabled: false,
    vectorTopK: 5,
    vectorThreshold: 0.7,
    vectorRecencyWeight: 0.2,
    embeddingModel: "text-embedding-ada-002",
    summarizationEnabled: false,
    summarizationThreshold: 30,
    summarizationKeepRecent: 10,
    summarizationModel: "gpt-4",
    showAdvanced: false,
  });

  const bufferSize = useMemo(() => {
    const option = MEMORY_DEPTH_OPTIONS.find((entry) => entry.value === formState.memoryDepth);
    if (!option || option.bufferSize === null) {
      return formState.customBufferSize ?? config?.buffer_size ?? 20;
    }
    return option.bufferSize;
  }, [config?.buffer_size, formState.customBufferSize, formState.memoryDepth]);

  const loadConfig = useCallback(async () => {
    if (!graphId) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await graphsApi.getMemoryConfig(graphId);
      setConfig(data);
      setFormState((prev) => ({
        ...prev,
        memoryDepth: deriveMemoryDepth(data.buffer_size),
        customBufferSize: deriveMemoryDepth(data.buffer_size) === "custom" ? data.buffer_size : undefined,
        enablePersistence: data.redis_enabled,
        autoPrepend: data.auto_prepend,
        summaryTtlHours: toHours(data.redis_summary_ttl),
        factsTtlDays: toDays(data.redis_facts_ttl),
        vectorEnabled: data.vector_enabled,
        vectorTopK: data.vector_top_k,
        vectorThreshold: data.vector_threshold,
        vectorRecencyWeight: data.vector_recency_weight,
        embeddingModel: data.embedding_model || "text-embedding-ada-002",
        summarizationEnabled: data.summarization_enabled,
        summarizationThreshold: data.summarization_threshold,
        summarizationKeepRecent: data.summarization_keep_recent,
        summarizationModel: data.summarization_model || "gpt-4",
      }));
    } catch (err) {
      const message = getApiErrorMessage(err, "Failed to load memory settings.");
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [graphId]);

  useEffect(() => {
    if (!open) {
      return;
    }
    void loadConfig();
  }, [open, loadConfig]);

  const handleSave = useCallback(async () => {
    if (!graphId) {
      showError("Select a graph to configure memory.");
      return;
    }
    if (!bufferSize || bufferSize < 1 || bufferSize > 200) {
      showError("Buffer size must be between 1 and 200.");
      return;
    }
    if (formState.summarizationEnabled && formState.summarizationThreshold < formState.summarizationKeepRecent + 10) {
      showError("Summarization threshold must be at least keep recent + 10.");
      return;
    }
    if (formState.vectorEnabled && (formState.vectorThreshold < 0.5 || formState.vectorThreshold > 0.99)) {
      showError("Vector threshold must be between 0.5 and 0.99.");
      return;
    }
    if (formState.vectorEnabled && (formState.vectorRecencyWeight < 0 || formState.vectorRecencyWeight > 1)) {
      showError("Vector recency weight must be between 0 and 1.");
      return;
    }
    if (formState.vectorEnabled && (formState.vectorTopK < 1 || formState.vectorTopK > 50)) {
      showError("Vector top-k must be between 1 and 50.");
      return;
    }

    setSaving(true);
    try {
      const payload: Partial<MemoryConfig> = {
        buffer_enabled: config?.buffer_enabled ?? true,
        buffer_size: bufferSize,
        auto_prepend: formState.autoPrepend,
        redis_enabled: formState.enablePersistence,
        redis_summary_ttl: Math.max(1, formState.summaryTtlHours) * 3600,
        redis_facts_ttl: Math.max(1, formState.factsTtlDays) * 86400,
        vector_enabled: formState.vectorEnabled,
        vector_top_k: Math.max(1, formState.vectorTopK),
        vector_threshold: formState.vectorThreshold,
        vector_recency_weight: formState.vectorRecencyWeight,
        embedding_model: formState.embeddingModel.trim() || "text-embedding-ada-002",
        summarization_enabled: formState.summarizationEnabled,
        summarization_threshold: Math.max(1, formState.summarizationThreshold),
        summarization_keep_recent: Math.max(1, formState.summarizationKeepRecent),
        summarization_model: formState.summarizationModel.trim() || "gpt-4",
      };
      const updated = await graphsApi.updateMemoryConfig(graphId, payload);
      setConfig(updated);
      showSuccess("Memory settings saved.");
      onOpenChange(false);
    } catch (err) {
      const message = getApiErrorMessage(err, "Failed to save memory settings.");
      setError(message);
      showError(message);
    } finally {
      setSaving(false);
    }
  }, [bufferSize, config, formState, graphId, onOpenChange]);

  const handleToggleAdvanced = useCallback(() => {
    setFormState((prev) => ({ ...prev, showAdvanced: !prev.showAdvanced }));
  }, []);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Memory Settings</DialogTitle>
          <DialogDescription>Control how much context your agent retains across prompts.</DialogDescription>
        </DialogHeader>

        {loading ? (
          <p className="text-sm text-muted-foreground">Loading memory configuration…</p>
        ) : (
          <div className="space-y-4">
            {error && <p className="text-sm text-destructive">{error}</p>}

            <FormField label="Memory Depth" htmlFor="memory-depth">
              <select
                id="memory-depth"
                value={formState.memoryDepth}
                onChange={(event) =>
                  setFormState((prev) => ({
                    ...prev,
                    memoryDepth: event.target.value as MemoryDepth,
                  }))
                }
                className="w-full px-3 py-2 border rounded-md bg-background text-sm"
              >
                {MEMORY_DEPTH_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </FormField>

            {formState.memoryDepth === "custom" && (
              <FormField label="Custom Buffer Size" htmlFor="custom-buffer-size">
                <Input
                  id="custom-buffer-size"
                  type="number"
                  min={1}
                  max={200}
                  value={formState.customBufferSize ?? ""}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      customBufferSize: event.target.value ? Number(event.target.value) : undefined,
                    }))
                  }
                />
              </FormField>
            )}

            <FormField label="Enable Persistence" htmlFor="enable-persistence">
              <Switch
                id="enable-persistence"
                checked={formState.enablePersistence}
                onCheckedChange={(checked) => setFormState((prev) => ({ ...prev, enablePersistence: checked }))}
              />
            </FormField>

            <Separator />

            <button
              type="button"
              onClick={handleToggleAdvanced}
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              {formState.showAdvanced ? "Hide advanced settings" : "Show advanced settings"}
            </button>

            {formState.showAdvanced && (
              <div className="space-y-4">
                <FormField label="Auto-prepend memory" htmlFor="auto-prepend">
                  <Switch
                    id="auto-prepend"
                    checked={formState.autoPrepend}
                    onCheckedChange={(checked) => setFormState((prev) => ({ ...prev, autoPrepend: checked }))}
                  />
                </FormField>

                <Separator />

                <FormField
                  label="Enable vector memory"
                  htmlFor="vector-enabled"
                  description="Retrieve long-term memories via semantic search."
                >
                  <Switch
                    id="vector-enabled"
                    checked={formState.vectorEnabled}
                    onCheckedChange={(checked) => setFormState((prev) => ({ ...prev, vectorEnabled: checked }))}
                  />
                </FormField>

                {formState.vectorEnabled && (
                  <>
                    <FormField
                      label="Vector top-k"
                      htmlFor="vector-top-k"
                      description="How many memory chunks to retrieve per prompt."
                    >
                      <Input
                        id="vector-top-k"
                        type="number"
                        min={1}
                        max={50}
                        value={formState.vectorTopK}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            vectorTopK: Number(event.target.value),
                          }))
                        }
                      />
                    </FormField>

                    <FormField
                      label="Vector threshold"
                      htmlFor="vector-threshold"
                      description="Minimum similarity score for a memory to be included."
                    >
                      <Input
                        id="vector-threshold"
                        type="number"
                        step="0.01"
                        min={0.5}
                        max={0.99}
                        value={formState.vectorThreshold}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            vectorThreshold: Number(event.target.value),
                          }))
                        }
                      />
                    </FormField>

                    <FormField
                      label="Recency weight"
                      htmlFor="vector-recency-weight"
                      description="Weight recent memories vs semantic similarity (0-1)."
                    >
                      <Input
                        id="vector-recency-weight"
                        type="number"
                        step="0.05"
                        min={0}
                        max={1}
                        value={formState.vectorRecencyWeight}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            vectorRecencyWeight: Number(event.target.value),
                          }))
                        }
                      />
                    </FormField>

                    <FormField
                      label="Embedding model"
                      htmlFor="embedding-model"
                      description="Model used for generating embeddings."
                    >
                      <Input
                        id="embedding-model"
                        type="text"
                        value={formState.embeddingModel}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            embeddingModel: event.target.value,
                          }))
                        }
                      />
                    </FormField>
                  </>
                )}

                <FormField
                  label="Summary TTL (hours)"
                  htmlFor="summary-ttl"
                  description="How long summarized memory persists in Redis."
                >
                  <Input
                    id="summary-ttl"
                    type="number"
                    min={1}
                    max={720}
                    value={formState.summaryTtlHours}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        summaryTtlHours: Number(event.target.value),
                      }))
                    }
                  />
                </FormField>

                <FormField
                  label="Facts TTL (days)"
                  htmlFor="facts-ttl"
                  description="How long extracted facts persist in Redis."
                >
                  <Input
                    id="facts-ttl"
                    type="number"
                    min={1}
                    max={365}
                    value={formState.factsTtlDays}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        factsTtlDays: Number(event.target.value),
                      }))
                    }
                  />
                </FormField>

                <Separator />

                <FormField
                  label="Enable summarization"
                  htmlFor="summarization-enabled"
                  description="Summarize long conversations and extract facts."
                >
                  <Switch
                    id="summarization-enabled"
                    checked={formState.summarizationEnabled}
                    onCheckedChange={(checked) => setFormState((prev) => ({ ...prev, summarizationEnabled: checked }))}
                  />
                </FormField>

                <FormField
                  label="Summarization threshold (messages)"
                  htmlFor="summarization-threshold"
                  description="Trigger summarization after this many new messages."
                >
                  <Input
                    id="summarization-threshold"
                    type="number"
                    min={10}
                    max={200}
                    value={formState.summarizationThreshold}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        summarizationThreshold: Number(event.target.value),
                      }))
                    }
                  />
                </FormField>

                <FormField
                  label="Keep recent messages"
                  htmlFor="summarization-keep-recent"
                  description="How many recent messages remain after summarization."
                >
                  <Input
                    id="summarization-keep-recent"
                    type="number"
                    min={1}
                    max={100}
                    value={formState.summarizationKeepRecent}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        summarizationKeepRecent: Number(event.target.value),
                      }))
                    }
                  />
                </FormField>

                <FormField
                  label="Summarization model"
                  htmlFor="summarization-model"
                  description="Model used for summarization requests."
                >
                  <Input
                    id="summarization-model"
                    type="text"
                    value={formState.summarizationModel}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        summarizationModel: event.target.value,
                      }))
                    }
                  />
                </FormField>
              </div>
            )}
          </div>
        )}

        <DialogFooter className="gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSave} disabled={saving || loading}>
            {saving ? "Saving" : "Save Settings"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default MemoryConfigDialog;
