"use client";

import { useCallback } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/ui/form-field";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { AgentFields, type AgentConfig } from "./AgentFields";
import { AdvancedSettings, type AdvancedConfig } from "./AdvancedSettings";
import { AlertTriangle } from "lucide-react";
import type { NodeFormProps } from "../NodeConfigDialog";

/**
 * Human gate node specific configuration
 */
interface HumanGateConfig extends AgentConfig, AdvancedConfig {
  prompt_message?: string;
  approval_message?: string;
  instructions?: string;
  timeout_hours?: number;
  auto_approve_after_timeout?: boolean;
  require_comment?: boolean;
  notify_emails?: string[];
  show_context?: boolean;
}

export function HumanGateNodeForm({ config, onChange }: NodeFormProps) {
  const gateConfig = config as HumanGateConfig;

  const handleChange = useCallback(
    <K extends keyof HumanGateConfig>(field: K, value: HumanGateConfig[K]) => {
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

  const handleEmailsChange = useCallback(
    (value: string) => {
      const emails = value
        .split(",")
        .map((e) => e.trim())
        .filter(Boolean);
      handleChange("notify_emails", emails);
    },
    [handleChange],
  );

  return (
    <div className="space-y-6">
      {/* Agent Context - Minimal for Human Gate */}
      <AgentFields config={gateConfig} onChange={handleAgentChange} showRole={false} showExamples={false} />

      <Separator />

      {/* Human Gate Configuration */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Approval Configuration</h3>

        <p className="text-sm text-muted-foreground">
          Pause the workflow and wait for human approval before proceeding. The reviewer can approve, reject, or modify
          the data.
        </p>

        <FormField
          label="Approval Message"
          htmlFor="approval-message"
          description="Message shown to the reviewer"
          required
        >
          <Textarea
            id="approval-message"
            value={gateConfig.prompt_message || gateConfig.approval_message || ""}
            onChange={(e) => {
              const value = e.target.value;
              onChange({ ...config, prompt_message: value, approval_message: value });
            }}
            placeholder="Please review the generated content before it is sent to the customer."
            rows={2}
            className="text-sm resize-none"
          />
        </FormField>

        <FormField label="Instructions" htmlFor="instructions" description="Detailed instructions for the reviewer">
          <Textarea
            id="instructions"
            value={gateConfig.instructions || ""}
            onChange={(e) => handleChange("instructions", e.target.value)}
            placeholder="Check for accuracy, tone, and compliance with brand guidelines..."
            rows={3}
            className="text-sm resize-none"
          />
        </FormField>

        <Separator />

        <h4 className="text-sm font-medium">Timeout & Notifications</h4>

        <div className="grid grid-cols-2 gap-4">
          <FormField label="Timeout (hours)" htmlFor="timeout-hours" description="Max wait time before timeout action">
            <Input
              id="timeout-hours"
              type="number"
              min={0}
              max={720}
              value={gateConfig.timeout_hours || ""}
              onChange={(e) => handleChange("timeout_hours", e.target.value ? parseInt(e.target.value, 10) : undefined)}
              placeholder="24"
              className="text-sm"
            />
          </FormField>

          <FormField label="Notify Emails" htmlFor="notify-emails" description="Comma-separated email addresses">
            <Input
              id="notify-emails"
              value={(gateConfig.notify_emails || []).join(", ")}
              onChange={(e) => handleEmailsChange(e.target.value)}
              placeholder="reviewer@example.com"
              className="text-sm"
            />
          </FormField>
        </div>

        <Separator />

        <h4 className="text-sm font-medium">Options</h4>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">Auto-approve on timeout</div>
              <div className="text-xs text-muted-foreground">Automatically approve if no response within timeout</div>
            </div>
            <Switch
              checked={gateConfig.auto_approve_after_timeout || false}
              onCheckedChange={(checked) => handleChange("auto_approve_after_timeout", checked)}
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">Require comment</div>
              <div className="text-xs text-muted-foreground">Reviewer must provide a comment with their decision</div>
            </div>
            <Switch
              checked={gateConfig.require_comment || false}
              onCheckedChange={(checked) => handleChange("require_comment", checked)}
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">Show context</div>
              <div className="text-xs text-muted-foreground">Display upstream node outputs to the reviewer</div>
            </div>
            <Switch
              checked={gateConfig.show_context ?? true}
              onCheckedChange={(checked) => handleChange("show_context", checked)}
            />
          </div>
        </div>

        {gateConfig.auto_approve_after_timeout && (
          <div className="flex items-start gap-2 p-3 bg-amber-500/10 border border-amber-500/20 rounded-md text-xs text-amber-600 dark:text-amber-400">
            <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-medium">Auto-approval warning</p>
              <p className="mt-1">
                The workflow will continue automatically if not reviewed within {gateConfig.timeout_hours || 24} hours.
                Ensure this is acceptable for your use case.
              </p>
            </div>
          </div>
        )}
      </div>

      <Separator />

      {/* Advanced Settings */}
      <AdvancedSettings config={gateConfig} onChange={handleAdvancedChange} />
    </div>
  );
}

export default HumanGateNodeForm;
