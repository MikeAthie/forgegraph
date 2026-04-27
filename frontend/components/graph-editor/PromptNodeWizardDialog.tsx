"use client";

import { useEffect, useMemo, useState } from "react";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  FormField,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
  Textarea,
} from "@/components/ui";
import { getApiErrorMessage, promptsApi, type PromptDetail } from "@/lib/api";
import {
  buildPromptTemplate,
  suggestPromptTitle,
  type PromptWizardExample,
  type PromptWizardOutputPreset,
} from "@/lib/prompt-wizard";
import { showError, showSuccess } from "@/lib/toast";

type WizardMode = "create" | "existing";

type PromptNodeWizardResult = {
  prompt_template: string;
  prompt_id?: string;
};

export function PromptNodeWizardDialog({
  open,
  onOpenChange,
  onComplete,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onComplete: (config: PromptNodeWizardResult) => void;
}) {
  const [mode, setMode] = useState<WizardMode>("create");
  const [stepIndex, setStepIndex] = useState(0);
  const [wizardError, setWizardError] = useState<string | null>(null);

  const [role, setRole] = useState("");
  const [task, setTask] = useState("");
  const [taskError, setTaskError] = useState<string | null>(null);

  const [examples, setExamples] = useState<PromptWizardExample[]>([{ input: "", output: "" }]);

  const [outputPreset, setOutputPreset] = useState<PromptWizardOutputPreset>("none");
  const [outputInstructions, setOutputInstructions] = useState("");

  const [title, setTitle] = useState("");
  const [titleTouched, setTitleTouched] = useState(false);
  const [titleError, setTitleError] = useState<string | null>(null);
  const [saveToLibrary, setSaveToLibrary] = useState(true);

  const [existingPromptId, setExistingPromptId] = useState("");
  const [existingPrompt, setExistingPrompt] = useState<PromptDetail | null>(null);
  const [existingPromptError, setExistingPromptError] = useState<string | null>(null);
  const [loadingExisting, setLoadingExisting] = useState(false);

  const [submitting, setSubmitting] = useState(false);

  const steps = useMemo(() => {
    if (mode === "existing") {
      return ["Select", "Review"];
    }
    return ["Role", "Task", "Examples", "Output", "Review"];
  }, [mode]);

  const promptTemplate = useMemo(() => {
    if (mode === "existing") {
      return existingPrompt?.content ?? "";
    }
    return buildPromptTemplate({
      role,
      task,
      examples,
      outputPreset,
      outputInstructions,
    });
  }, [examples, existingPrompt?.content, mode, outputInstructions, outputPreset, role, task]);

  useEffect(() => {
    if (!open) return;

    setMode("create");
    setStepIndex(0);
    setWizardError(null);

    setRole("");
    setTask("");
    setTaskError(null);

    setExamples([{ input: "", output: "" }]);
    setOutputPreset("none");
    setOutputInstructions("");

    setTitle("");
    setTitleTouched(false);
    setTitleError(null);
    setSaveToLibrary(true);

    setExistingPromptId("");
    setExistingPrompt(null);
    setExistingPromptError(null);
    setLoadingExisting(false);
    setSubmitting(false);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (mode !== "create") return;
    if (titleTouched) return;

    setTitle(suggestPromptTitle({ role, task }));
  }, [mode, open, role, task, titleTouched]);

  useEffect(() => {
    if (!open) return;
    setStepIndex(0);
    setWizardError(null);
    setTaskError(null);
    setTitleError(null);
    setExistingPromptError(null);
  }, [mode, open]);

  const handleOpenChange = (nextOpen: boolean) => {
    if (submitting || loadingExisting) return;
    onOpenChange(nextOpen);
  };

  const canGoBack = stepIndex > 0 && !submitting && !loadingExisting;
  const isLastStep = stepIndex === steps.length - 1;

  const canGoNext = useMemo(() => {
    if (submitting || loadingExisting) return false;

    if (mode === "existing") {
      if (steps[stepIndex] === "Select") {
        return Boolean(existingPrompt);
      }
      return true;
    }

    if (steps[stepIndex] === "Task") {
      return task.trim().length > 0;
    }

    return true;
  }, [existingPrompt, loadingExisting, mode, stepIndex, steps, submitting, task]);

  const canFinish = useMemo(() => {
    if (submitting || loadingExisting) return false;
    if (!isLastStep) return false;

    if (mode === "existing") {
      return Boolean(existingPrompt?.content);
    }

    return task.trim().length > 0 && title.trim().length > 0;
  }, [existingPrompt?.content, isLastStep, loadingExisting, mode, submitting, task, title]);

  const goNext = () => {
    setWizardError(null);
    setTaskError(null);
    setExistingPromptError(null);

    if (mode === "create" && steps[stepIndex] === "Task" && task.trim().length === 0) {
      setTaskError("Task description is required.");
      return;
    }

    if (mode === "existing" && steps[stepIndex] === "Select" && !existingPrompt) {
      setExistingPromptError("Load a prompt to continue.");
      return;
    }

    setStepIndex((prev) => Math.min(prev + 1, steps.length - 1));
  };

  const goBack = () => {
    if (!canGoBack) return;
    setWizardError(null);
    setTaskError(null);
    setTitleError(null);
    setExistingPromptError(null);
    setStepIndex((prev) => Math.max(prev - 1, 0));
  };

  const loadExistingPrompt = async () => {
    const id = existingPromptId.trim();
    setExistingPromptError(null);
    setWizardError(null);
    setExistingPrompt(null);

    if (!id) {
      setExistingPromptError("Prompt ID is required.");
      return;
    }

    setLoadingExisting(true);
    try {
      const prompt = await promptsApi.get(id);
      setExistingPrompt(prompt);
      showSuccess("Prompt loaded", `"${prompt.title}" is ready to use.`);
    } catch (err: unknown) {
      const message = getApiErrorMessage(err, "Failed to load prompt.");
      setExistingPromptError(message);
      showError("Failed to load prompt", message);
    } finally {
      setLoadingExisting(false);
    }
  };

  const submit = async () => {
    setWizardError(null);
    setTaskError(null);
    setTitleError(null);
    setExistingPromptError(null);

    if (mode === "existing") {
      if (!existingPrompt?.content) {
        setExistingPromptError("Load a prompt to continue.");
        return;
      }

      onComplete({
        prompt_template: existingPrompt.content,
        prompt_id: existingPrompt.id,
      });
      onOpenChange(false);
      return;
    }

    if (!task.trim()) {
      setTaskError("Task description is required.");
      return;
    }
    if (!title.trim()) {
      setTitleError("Title is required.");
      return;
    }

    const content = promptTemplate;
    if (!content) {
      setWizardError("Prompt template is empty.");
      return;
    }

    if (!saveToLibrary) {
      onComplete({ prompt_template: content });
      onOpenChange(false);
      return;
    }

    setSubmitting(true);
    try {
      const created = await promptsApi.create({
        title: title.trim(),
        description: "",
        category: "other",
        content,
        variables_schema: {},
      });

      showSuccess("Prompt created", `"${created.title}" has been added to your library.`);
      onComplete({ prompt_template: content, prompt_id: created.id });
      onOpenChange(false);
    } catch (err: unknown) {
      const message = getApiErrorMessage(err, "Failed to create prompt.");
      setWizardError(message);
      showError("Failed to create prompt", message);
    } finally {
      setSubmitting(false);
    }
  };

  const setExampleField = (index: number, field: "input" | "output", value: string) => {
    setExamples((prev) => prev.map((ex, i) => (i === index ? { ...ex, [field]: value } : ex)));
  };

  const addExample = () => {
    setExamples((prev) => [...prev, { input: "", output: "" }]);
  };

  const removeExample = (index: number) => {
    setExamples((prev) => prev.filter((_, i) => i !== index));
  };

  const renderStep = () => {
    const step = steps[stepIndex];

    if (mode === "existing") {
      if (step === "Select") {
        return (
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground">
              Attach a prompt template from your Prompt Library by ID.
            </div>
            <FormField
              label="Prompt ID"
              required
              error={existingPromptError ?? undefined}
              description="Find prompt IDs in the Prompts page."
            >
              <div className="flex gap-2">
                <Input
                  value={existingPromptId}
                  onChange={(e) => setExistingPromptId(e.target.value)}
                  placeholder="e.g. 0f2f4d7d-..."
                  className="text-sm"
                />
                <Button type="button" variant="secondary" onClick={loadExistingPrompt} disabled={loadingExisting}>
                  {loadingExisting ? (
                    <>
                      <Spinner size="sm" />
                      Loading...
                    </>
                  ) : (
                    "Load"
                  )}
                </Button>
              </div>
            </FormField>
            {existingPrompt ? (
              <div className="rounded-lg border border-border bg-muted/10 p-3 text-sm">
                <div className="font-medium text-foreground">{existingPrompt.title}</div>
                <div className="text-xs text-muted-foreground mt-1">{existingPrompt.description}</div>
              </div>
            ) : null}
          </div>
        );
      }

      return (
        <div className="space-y-3">
          <div className="text-sm text-muted-foreground">Review the prompt content before adding the step.</div>
          {existingPrompt ? (
            <div className="rounded-lg border border-border bg-muted/10 p-3 text-sm">
              <div className="font-medium text-foreground">{existingPrompt.title}</div>
              <div className="text-xs text-muted-foreground mt-1">
                This step will embed the prompt content for execution.
              </div>
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">No prompt loaded.</div>
          )}
        </div>
      );
    }

    switch (step) {
      case "Role":
        return (
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground">
              Define who the AI should be. This sets context and tone.
            </div>

            <FormField
              label="AI Role / Persona"
              description="Example: You are a software developer who writes clear, production-ready code."
            >
              <Input
                value={role}
                onChange={(e) => setRole(e.target.value)}
                placeholder="You are a..."
                className="text-sm"
              />
            </FormField>

            <div className="rounded-lg border border-border bg-muted/10 p-3">
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Advanced</div>
              <div className="mt-2 flex flex-col gap-2">
                <Button
                  type="button"
                  variant={(mode as WizardMode) === "existing" ? "default" : "outline"}
                  onClick={() => setMode("existing")}
                  disabled={submitting || loadingExisting}
                >
                  Use an existing prompt ID instead
                </Button>
                <div className="text-xs text-muted-foreground">
                  Already have a prompt in your library? Switch to load it by ID.
                </div>
              </div>
            </div>
          </div>
        );

      case "Task":
        return (
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground">
              Describe what you want the AI to do. Be specific about inputs, constraints, and success criteria.
            </div>

            <FormField
              label="Task Description"
              required
              error={taskError ?? undefined}
              description="This is the core instruction the model will follow."
            >
              <Textarea
                value={task}
                onChange={(e) => {
                  setTask(e.target.value);
                  setTaskError(null);
                }}
                placeholder="Write a clear task description..."
                rows={8}
                className="text-sm"
              />
            </FormField>
          </div>
        );

      case "Examples":
        return (
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground">
              Provide examples to demonstrate the desired input → output. (Optional)
            </div>

            <div className="space-y-4">
              {examples.map((example, index) => (
                <div key={index} className="rounded-lg border border-border p-3 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium text-foreground">Example {index + 1}</div>
                    {examples.length > 1 ? (
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => removeExample(index)}
                        className="text-destructive hover:text-destructive"
                      >
                        Remove
                      </Button>
                    ) : null}
                  </div>

                  <FormField label="Example Input">
                    <Textarea
                      value={example.input}
                      onChange={(e) => setExampleField(index, "input", e.target.value)}
                      placeholder="User input..."
                      rows={4}
                      className="text-sm"
                    />
                  </FormField>

                  <FormField label="Example Output">
                    <Textarea
                      value={example.output}
                      onChange={(e) => setExampleField(index, "output", e.target.value)}
                      placeholder="Ideal assistant output..."
                      rows={4}
                      className="text-sm"
                    />
                  </FormField>
                </div>
              ))}
            </div>

            <Button type="button" variant="secondary" onClick={addExample}>
              Add another example
            </Button>
          </div>
        );

      case "Output":
        return (
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground">
              Specify the expected output format. Structured outputs improve reliability. (Optional)
            </div>

            <FormField label="Output format preset">
              <Select
                value={outputPreset}
                onValueChange={(value) => setOutputPreset(value as PromptWizardOutputPreset)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Choose a format" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No specific format</SelectItem>
                  <SelectItem value="bullet_list">Bullet list</SelectItem>
                  <SelectItem value="json">JSON</SelectItem>
                  <SelectItem value="custom">Custom</SelectItem>
                </SelectContent>
              </Select>
            </FormField>

            <FormField
              label="Additional format instructions"
              description="Example: Use keys {name: string, age: number} and nothing else."
            >
              <Textarea
                value={outputInstructions}
                onChange={(e) => setOutputInstructions(e.target.value)}
                placeholder={
                  outputPreset === "json"
                    ? "Describe the JSON shape (optional)..."
                    : outputPreset === "bullet_list"
                      ? "Any extra bullet-list constraints (optional)..."
                      : "Format constraints (optional)..."
                }
                rows={6}
                className="text-sm"
              />
            </FormField>
          </div>
        );

      case "Review":
        return (
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground">Give your prompt a name and confirm the final template.</div>

            <FormField
              label="Prompt title"
              required
              error={titleError ?? undefined}
              description="This title appears in your Prompt Library."
            >
              <Input
                value={title}
                onChange={(e) => {
                  setTitleTouched(true);
                  setTitle(e.target.value);
                  setTitleError(null);
                }}
                placeholder="e.g. Draft Email Reply"
                className="text-sm"
              />
            </FormField>

            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={saveToLibrary}
                onChange={(e) => setSaveToLibrary(e.target.checked)}
                disabled={submitting}
                className="mt-0.5 h-4 w-4 rounded border border-input"
              />
              <span>
                Save to Prompt Library{" "}
                <span className="block text-xs text-muted-foreground">
                  Creates a reusable prompt template (recommended).
                </span>
              </span>
            </label>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-3xl" showCloseButton={!submitting && !loadingExisting}>
        <DialogHeader>
          <DialogTitle>Prompt Node Wizard</DialogTitle>
          <DialogDescription>Build a high-quality prompt template with best-practice structure.</DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between gap-3">
          <div className="text-xs text-muted-foreground">
            Step {Math.min(stepIndex + 1, steps.length)} of {steps.length}:{" "}
            <span className="text-foreground font-medium">{steps[stepIndex]}</span>
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant={mode === "create" ? "default" : "outline"}
              size="sm"
              onClick={() => setMode("create")}
              disabled={submitting || loadingExisting}
            >
              Create new
            </Button>
            <Button
              type="button"
              variant={mode === "existing" ? "default" : "outline"}
              size="sm"
              onClick={() => setMode("existing")}
              disabled={submitting || loadingExisting}
            >
              Use existing
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 sm:grid-cols-[1fr_360px]">
          <div className="min-w-0">
            {wizardError ? (
              <div className="mb-4 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
                {wizardError}
              </div>
            ) : null}

            {renderStep()}
          </div>

          <div className="min-w-0">
            <div className="rounded-lg border border-border bg-muted/5 p-3">
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Prompt Preview</div>
              <Textarea
                value={promptTemplate}
                readOnly
                placeholder={
                  mode === "existing" ? "Load a prompt to preview it..." : "Start typing to see the preview..."
                }
                rows={18}
                className="mt-2 font-mono text-xs"
              />
              <div className="mt-2 text-[11px] text-muted-foreground">
                This is embedded into the node config as <code>prompt_template</code>.
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting || loadingExisting}
          >
            Cancel
          </Button>

          <div className="flex-1" />

          <Button type="button" variant="outline" onClick={goBack} disabled={!canGoBack}>
            Back
          </Button>

          {!isLastStep ? (
            <Button type="button" onClick={goNext} disabled={!canGoNext}>
              Next
            </Button>
          ) : (
            <Button type="button" onClick={submit} disabled={!canFinish}>
              {submitting ? (
                <>
                  <Spinner size="sm" />
                  Creating...
                </>
              ) : (
                "Finish"
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
