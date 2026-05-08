"use client";

import { useCallback } from "react";
import { Plus, X, HelpCircle } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { cn } from "@/lib/utils";

/**
 * Example input/output pair for agent training
 */
export interface AgentExample {
  input: string;
  output: string;
}

/**
 * Agent-specific configuration fields
 */
export interface AgentConfig {
  role?: string;
  jobDescription?: string;
  examples?: AgentExample[];
  notes?: string;
}

export interface AgentFieldsProps {
  config: AgentConfig;
  onChange: (config: AgentConfig) => void;
  showRole?: boolean;
  showJobDescription?: boolean;
  showExamples?: boolean;
  showNotes?: boolean;
  className?: string;
}

/**
 * Reusable component for agent-related configuration fields.
 * Includes Role, Job Description, Examples, and Notes.
 */
export function AgentFields({
  config,
  onChange,
  showRole = true,
  showJobDescription = true,
  showExamples = true,
  showNotes = true,
  className,
}: AgentFieldsProps) {
  const handleChange = useCallback(
    <K extends keyof AgentConfig>(field: K, value: AgentConfig[K]) => {
      onChange({ ...config, [field]: value });
    },
    [config, onChange],
  );

  const handleAddExample = useCallback(() => {
    const examples = config.examples || [];
    onChange({
      ...config,
      examples: [...examples, { input: "", output: "" }],
    });
  }, [config, onChange]);

  const handleRemoveExample = useCallback(
    (index: number) => {
      const examples = config.examples || [];
      onChange({
        ...config,
        examples: examples.filter((_, i) => i !== index),
      });
    },
    [config, onChange],
  );

  const handleExampleChange = useCallback(
    (index: number, field: "input" | "output", value: string) => {
      const examples = [...(config.examples || [])];
      examples[index] = { ...examples[index], [field]: value };
      onChange({ ...config, examples });
    },
    [config, onChange],
  );

  return (
    <div className={cn("space-y-4", className)}>
      {/* Agent Context Header */}
      <div className="flex items-center gap-2 pb-2 border-b">
        <span className="text-sm font-medium text-muted-foreground">Agent Context</span>
        <HelpCircle className="w-3.5 h-3.5 text-muted-foreground" />
      </div>

      {/* Role Field */}
      {showRole && (
        <FormField
          label="Role / Persona"
          htmlFor="agent-role"
          description="Define the agent's role or persona (e.g., 'Customer Support Agent at Acme Corp')"
        >
          <Input
            id="agent-role"
            value={config.role || ""}
            onChange={(e) => handleChange("role", e.target.value)}
            placeholder="e.g., Senior Software Engineer at OpenAI"
            className="text-sm"
          />
        </FormField>
      )}

      {/* Job Description Field */}
      {showJobDescription && (
        <FormField
          label="Primary Objective"
          htmlFor="agent-job"
          description="What is the main task or goal this agent should accomplish?"
        >
          <Textarea
            id="agent-job"
            value={config.jobDescription || ""}
            onChange={(e) => handleChange("jobDescription", e.target.value)}
            placeholder="e.g., Help customers resolve technical issues by providing accurate information and step-by-step solutions"
            rows={3}
            className="text-sm resize-none"
          />
          <div className="flex justify-end">
            <span className="text-xs text-muted-foreground">{(config.jobDescription || "").length} characters</span>
          </div>
        </FormField>
      )}

      {/* Examples Field */}
      {showExamples && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium">
              Examples
              <span className="text-muted-foreground font-normal ml-1">(optional)</span>
            </label>
            <span className="text-xs text-muted-foreground">{(config.examples || []).length} example(s)</span>
          </div>
          <p className="text-xs text-muted-foreground -mt-1">
            Provide input/output examples to guide the agent&apos;s behavior
          </p>

          {/* Example List */}
          <div className="space-y-3">
            {(config.examples || []).map((example, index) => (
              <div key={index} className="relative p-3 border rounded-lg bg-muted/30 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground">Example {index + 1}</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => handleRemoveExample(index)}
                    className="text-muted-foreground hover:text-destructive"
                  >
                    <X className="w-3.5 h-3.5" />
                  </Button>
                </div>
                <div className="space-y-2">
                  <div>
                    <label className="text-xs text-muted-foreground">Input</label>
                    <Textarea
                      value={example.input}
                      onChange={(e) => handleExampleChange(index, "input", e.target.value)}
                      placeholder="Example input or user message"
                      rows={2}
                      className="text-sm resize-none mt-1"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Expected Output</label>
                    <Textarea
                      value={example.output}
                      onChange={(e) => handleExampleChange(index, "output", e.target.value)}
                      placeholder="Expected agent response"
                      rows={2}
                      className="text-sm resize-none mt-1"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>

          <Button type="button" variant="outline" size="sm" onClick={handleAddExample} className="w-full">
            <Plus className="w-4 h-4 mr-1" />
            Add Example
          </Button>
        </div>
      )}

      {/* Notes Field */}
      {showNotes && (
        <FormField
          label="Additional Notes"
          htmlFor="agent-notes"
          description="Any special instructions, constraints, or context for this node"
        >
          <Textarea
            id="agent-notes"
            value={config.notes || ""}
            onChange={(e) => handleChange("notes", e.target.value)}
            placeholder="e.g., Always respond in formal English. Use the provided template for output formatting."
            rows={3}
            className="text-sm resize-none"
          />
        </FormField>
      )}
    </div>
  );
}

export default AgentFields;
