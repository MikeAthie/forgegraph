"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, type SetStateAction } from "react";

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

type PromptWizardState = {
  mode: WizardMode;
  stepIndex: number;
  wizardError: string | null;
  role: string;
  task: string;
  taskError: string | null;
  examples: PromptWizardExample[];
  outputPreset: PromptWizardOutputPreset;
  outputInstructions: string;
  title: string;
  titleError: string | null;
  saveToLibrary: boolean;
  existingPromptId: string;
  existingPrompt: PromptDetail | null;
  existingPromptError: string | null;
  loadingExisting: boolean;
  submitting: boolean;
};

type PromptWizardAction = {
  patch: Partial<PromptWizardState> | ((state: PromptWizardState) => Partial<PromptWizardState>);
};

const initialPromptWizardState: PromptWizardState = {
  mode: "create",
  stepIndex: 0,
  wizardError: null,
  role: "",
  task: "",
  taskError: null,
  examples: [{ input: "", output: "" }],
  outputPreset: "none",
  outputInstructions: "",
  title: "",
  titleError: null,
  saveToLibrary: true,
  existingPromptId: "",
  existingPrompt: null,
  existingPromptError: null,
  loadingExisting: false,
  submitting: false,
};

function promptWizardReducer(state: PromptWizardState, action: PromptWizardAction): PromptWizardState {
  const patch = typeof action.patch === "function" ? action.patch(state) : action.patch;
  return { ...state, ...patch };
}

function resolveWizardStateAction<T>(value: SetStateAction<T>, current: T): T {
  return typeof value === "function" ? (value as (current: T) => T)(current) : value;
}

type PromptWizardStepProps = {
  mode: WizardMode;
  step: string;
  role: string;
  task: string;
  taskError: string | null;
  examples: PromptWizardExample[];
  outputPreset: PromptWizardOutputPreset;
  outputInstructions: string;
  title: string;
  titleError: string | null;
  saveToLibrary: boolean;
  existingPromptId: string;
  existingPrompt: PromptDetail | null;
  existingPromptError: string | null;
  loadingExisting: boolean;
  submitting: boolean;
  onModeChange: (mode: WizardMode) => void;
  onRoleChange: (value: string) => void;
  onTaskChange: (value: string) => void;
  onTaskErrorChange: (value: string | null) => void;
  onExampleFieldChange: (index: number, field: "input" | "output", value: string) => void;
  onExampleAdd: () => void;
  onExampleRemove: (index: number) => void;
  onOutputPresetChange: (value: PromptWizardOutputPreset) => void;
  onOutputInstructionsChange: (value: string) => void;
  onTitleChange: (value: string) => void;
  onSaveToLibraryChange: (value: boolean) => void;
  onExistingPromptIdChange: (value: string) => void;
  onLoadExistingPrompt: () => void;
};

function PromptWizardStep({
  mode,
  step,
  role,
  task,
  taskError,
  examples,
  outputPreset,
  outputInstructions,
  title,
  titleError,
  saveToLibrary,
  existingPromptId,
  existingPrompt,
  existingPromptError,
  loadingExisting,
  submitting,
  onModeChange,
  onRoleChange,
  onTaskChange,
  onTaskErrorChange,
  onExampleFieldChange,
  onExampleAdd,
  onExampleRemove,
  onOutputPresetChange,
  onOutputInstructionsChange,
  onTitleChange,
  onSaveToLibraryChange,
  onExistingPromptIdChange,
  onLoadExistingPrompt,
}: PromptWizardStepProps) {
  if (mode === "existing") {
    if (step === "Select") {
      return (
        <div className="space-y-4">
          <div className="text-sm text-muted-foreground">Attach a prompt template from your Prompt Library by ID.</div>
          <FormField
            label="Prompt ID"
            required
            error={existingPromptError ?? undefined}
            description="Find prompt IDs in the Prompts page."
          >
            <div className="flex gap-2">
              <Input
                value={existingPromptId}
                onChange={(event) => onExistingPromptIdChange(event.target.value)}
                placeholder="e.g. 0f2f4d7d-example"
                className="text-sm"
              />
              <Button type="button" variant="secondary" onClick={onLoadExistingPrompt} disabled={loadingExisting}>
                {loadingExisting ? (
                  <>
                    <Spinner size="sm" />
                    Loading
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
          <div className="text-sm text-muted-foreground">Define who the AI should be. This sets context and tone.</div>

          <FormField
            label="AI Role / Persona"
            description="Example: You are a software developer who writes clear, production-ready code."
          >
            <Input
              value={role}
              onChange={(event) => onRoleChange(event.target.value)}
              placeholder="You are a"
              className="text-sm"
            />
          </FormField>

          <div className="rounded-lg border border-border bg-muted/10 p-3">
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Advanced</div>
            <div className="mt-2 flex flex-col gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => onModeChange("existing")}
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
              onChange={(event) => {
                onTaskChange(event.target.value);
                onTaskErrorChange(null);
              }}
              placeholder="Write a clear task description"
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
            Provide examples to demonstrate the desired input to output. (Optional)
          </div>

          <div className="space-y-4">
            {examples.map((example, index) => (
              <div key={`${example.input}\u0000${example.output}`} className="rounded-lg border border-border p-3 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-foreground">Example {index + 1}</div>
                  {examples.length > 1 ? (
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => onExampleRemove(index)}
                      className="text-destructive hover:text-destructive"
                    >
                      Remove
                    </Button>
                  ) : null}
                </div>

                <FormField label="Example Input">
                  <Textarea
                    value={example.input}
                    onChange={(event) => onExampleFieldChange(index, "input", event.target.value)}
                    placeholder="User input"
                    rows={4}
                    className="text-sm"
                  />
                </FormField>

                <FormField label="Example Output">
                  <Textarea
                    value={example.output}
                    onChange={(event) => onExampleFieldChange(index, "output", event.target.value)}
                    placeholder="Ideal assistant output"
                    rows={4}
                    className="text-sm"
                  />
                </FormField>
              </div>
            ))}
          </div>

          <Button type="button" variant="secondary" onClick={onExampleAdd}>
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
            <Select value={outputPreset} onValueChange={(value) => onOutputPresetChange(value as PromptWizardOutputPreset)}>
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
              onChange={(event) => onOutputInstructionsChange(event.target.value)}
              placeholder={
                outputPreset === "json"
                  ? "Describe the JSON shape (optional)"
                  : outputPreset === "bullet_list"
                    ? "Any extra bullet-list constraints (optional)"
                    : "Format constraints (optional)"
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
              onChange={(event) => onTitleChange(event.target.value)}
              placeholder="e.g. Draft Email Reply"
              className="text-sm"
            />
          </FormField>

          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={saveToLibrary}
              onChange={(event) => onSaveToLibraryChange(event.target.checked)}
              disabled={submitting}
              className="mt-0.5 size-4 rounded border border-input"
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
}

function usePromptNodeWizardDialogController({
  open,
  onOpenChange,
  onComplete,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onComplete: (config: PromptNodeWizardResult) => void;
}) {
  const [state, dispatchState] = useReducer(promptWizardReducer, initialPromptWizardState);
  const {
    mode,
    stepIndex,
    wizardError,
    role,
    task,
    taskError,
    examples,
    outputPreset,
    outputInstructions,
    title,
    titleError,
    saveToLibrary,
    existingPromptId,
    existingPrompt,
    existingPromptError,
    loadingExisting,
    submitting,
  } = state;
  const titleTouchedRef = useRef(false);
  const setWizardField = useCallback(
    <K extends keyof PromptWizardState>(key: K, value: SetStateAction<PromptWizardState[K]>) => {
      dispatchState({
        patch: (current) =>
          ({
            [key]: resolveWizardStateAction(value, current[key]),
          }) as Partial<PromptWizardState>,
      });
    },
    [],
  );
  const setMode = useCallback((value: SetStateAction<WizardMode>) => setWizardField("mode", value), [setWizardField]);
  const setStepIndex = useCallback(
    (value: SetStateAction<number>) => setWizardField("stepIndex", value),
    [setWizardField],
  );
  const setWizardError = useCallback(
    (value: SetStateAction<string | null>) => setWizardField("wizardError", value),
    [setWizardField],
  );
  const setRole = useCallback((value: SetStateAction<string>) => setWizardField("role", value), [setWizardField]);
  const setTask = useCallback((value: SetStateAction<string>) => setWizardField("task", value), [setWizardField]);
  const setTaskError = useCallback(
    (value: SetStateAction<string | null>) => setWizardField("taskError", value),
    [setWizardField],
  );
  const setExamples = useCallback(
    (value: SetStateAction<PromptWizardExample[]>) => setWizardField("examples", value),
    [setWizardField],
  );
  const setOutputPreset = useCallback(
    (value: SetStateAction<PromptWizardOutputPreset>) => setWizardField("outputPreset", value),
    [setWizardField],
  );
  const setOutputInstructions = useCallback(
    (value: SetStateAction<string>) => setWizardField("outputInstructions", value),
    [setWizardField],
  );
  const setTitle = useCallback((value: SetStateAction<string>) => setWizardField("title", value), [setWizardField]);
  const setTitleError = useCallback(
    (value: SetStateAction<string | null>) => setWizardField("titleError", value),
    [setWizardField],
  );
  const setSaveToLibrary = useCallback(
    (value: SetStateAction<boolean>) => setWizardField("saveToLibrary", value),
    [setWizardField],
  );
  const setExistingPromptId = useCallback(
    (value: SetStateAction<string>) => setWizardField("existingPromptId", value),
    [setWizardField],
  );
  const setExistingPrompt = useCallback(
    (value: SetStateAction<PromptDetail | null>) => setWizardField("existingPrompt", value),
    [setWizardField],
  );
  const setExistingPromptError = useCallback(
    (value: SetStateAction<string | null>) => setWizardField("existingPromptError", value),
    [setWizardField],
  );
  const setLoadingExisting = useCallback(
    (value: SetStateAction<boolean>) => setWizardField("loadingExisting", value),
    [setWizardField],
  );
  const setSubmitting = useCallback(
    (value: SetStateAction<boolean>) => setWizardField("submitting", value),
    [setWizardField],
  );

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

    titleTouchedRef.current = false;
    dispatchState({
      patch: {
        ...initialPromptWizardState,
        examples: [{ input: "", output: "" }],
      },
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (mode !== "create") return;
    if (titleTouchedRef.current) return;

    setTitle(suggestPromptTitle({ role, task }));
  }, [mode, open, role, task]);

  useEffect(() => {
    if (!open) return;
    dispatchState({
      patch: {
        stepIndex: 0,
        wizardError: null,
        taskError: null,
        titleError: null,
        existingPromptError: null,
      },
    });
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

  const handleTitleChange = (value: string) => {
    titleTouchedRef.current = true;
    setTitle(value);
    setTitleError(null);
  };

  return {
    mode,
    stepIndex,
    wizardError,
    role,
    task,
    taskError,
    examples,
    outputPreset,
    outputInstructions,
    title,
    titleError,
    saveToLibrary,
    existingPromptId,
    existingPrompt,
    existingPromptError,
    loadingExisting,
    submitting,
    steps,
    promptTemplate,
    canGoBack,
    isLastStep,
    canGoNext,
    canFinish,
    handleOpenChange,
    setMode,
    setRole,
    setTask,
    setTaskError,
    setExampleField,
    addExample,
    removeExample,
    setOutputPreset,
    setOutputInstructions,
    handleTitleChange,
    setSaveToLibrary,
    setExistingPromptId,
    loadExistingPrompt,
    goBack,
    goNext,
    submit,
  };
}

type PromptNodeWizardDialogController = ReturnType<typeof usePromptNodeWizardDialogController>;

function PromptWizardModeHeader({ wizard }: { wizard: PromptNodeWizardDialogController }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="text-xs text-muted-foreground">
        Step {Math.min(wizard.stepIndex + 1, wizard.steps.length)} of {wizard.steps.length}:{" "}
        <span className="text-foreground font-medium">{wizard.steps[wizard.stepIndex]}</span>
      </div>
      <div className="flex gap-2">
        <Button
          type="button"
          variant={wizard.mode === "create" ? "default" : "outline"}
          size="sm"
          onClick={() => wizard.setMode("create")}
          disabled={wizard.submitting || wizard.loadingExisting}
        >
          Create new
        </Button>
        <Button
          type="button"
          variant={wizard.mode === "existing" ? "default" : "outline"}
          size="sm"
          onClick={() => wizard.setMode("existing")}
          disabled={wizard.submitting || wizard.loadingExisting}
        >
          Use existing
        </Button>
      </div>
    </div>
  );
}

function PromptWizardStepPanel({ wizard }: { wizard: PromptNodeWizardDialogController }) {
  return (
    <div className="min-w-0">
      {wizard.wizardError ? (
        <div className="mb-4 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {wizard.wizardError}
        </div>
      ) : null}

      <PromptWizardStep
        mode={wizard.mode}
        step={wizard.steps[wizard.stepIndex] ?? wizard.steps[0] ?? ""}
        role={wizard.role}
        task={wizard.task}
        taskError={wizard.taskError}
        examples={wizard.examples}
        outputPreset={wizard.outputPreset}
        outputInstructions={wizard.outputInstructions}
        title={wizard.title}
        titleError={wizard.titleError}
        saveToLibrary={wizard.saveToLibrary}
        existingPromptId={wizard.existingPromptId}
        existingPrompt={wizard.existingPrompt}
        existingPromptError={wizard.existingPromptError}
        loadingExisting={wizard.loadingExisting}
        submitting={wizard.submitting}
        onModeChange={wizard.setMode}
        onRoleChange={wizard.setRole}
        onTaskChange={wizard.setTask}
        onTaskErrorChange={wizard.setTaskError}
        onExampleFieldChange={wizard.setExampleField}
        onExampleAdd={wizard.addExample}
        onExampleRemove={wizard.removeExample}
        onOutputPresetChange={wizard.setOutputPreset}
        onOutputInstructionsChange={wizard.setOutputInstructions}
        onTitleChange={wizard.handleTitleChange}
        onSaveToLibraryChange={wizard.setSaveToLibrary}
        onExistingPromptIdChange={wizard.setExistingPromptId}
        onLoadExistingPrompt={wizard.loadExistingPrompt}
      />
    </div>
  );
}

function PromptWizardPreview({ mode, promptTemplate }: { mode: WizardMode; promptTemplate: string }) {
  return (
    <div className="min-w-0">
      <div className="rounded-lg border border-border bg-muted/5 p-3">
        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Prompt Preview</div>
        <Textarea
          value={promptTemplate}
          readOnly
          placeholder={mode === "existing" ? "Load a prompt to preview it" : "Start typing to see the preview"}
          rows={18}
          className="mt-2 font-mono text-xs"
        />
        <div className="mt-2 text-[11px] text-muted-foreground">
          This is embedded into the node config as <code>prompt_template</code>.
        </div>
      </div>
    </div>
  );
}

function PromptWizardFooter({
  wizard,
  onCancel,
}: {
  wizard: PromptNodeWizardDialogController;
  onCancel: () => void;
}) {
  return (
    <DialogFooter>
      <Button
        type="button"
        variant="outline"
        onClick={onCancel}
        disabled={wizard.submitting || wizard.loadingExisting}
      >
        Cancel
      </Button>

      <div className="flex-1" />

      <Button type="button" variant="outline" onClick={wizard.goBack} disabled={!wizard.canGoBack}>
        Back
      </Button>

      {!wizard.isLastStep ? (
        <Button type="button" onClick={wizard.goNext} disabled={!wizard.canGoNext}>
          Next
        </Button>
      ) : (
        <Button type="button" onClick={wizard.submit} disabled={!wizard.canFinish}>
          {wizard.submitting ? (
            <>
              <Spinner size="sm" />
              Creating
            </>
          ) : (
            "Finish"
          )}
        </Button>
      )}
    </DialogFooter>
  );
}

export function PromptNodeWizardDialog({
  open,
  onOpenChange,
  onComplete,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onComplete: (config: PromptNodeWizardResult) => void;
}) {
  const wizard = usePromptNodeWizardDialogController({ open, onOpenChange, onComplete });

  return (
    <Dialog open={open} onOpenChange={wizard.handleOpenChange}>
      <DialogContent className="sm:max-w-3xl" showCloseButton={!wizard.submitting && !wizard.loadingExisting}>
        <DialogHeader>
          <DialogTitle>Prompt Node Wizard</DialogTitle>
          <DialogDescription>Build a high-quality prompt template with best-practice structure.</DialogDescription>
        </DialogHeader>

        <PromptWizardModeHeader wizard={wizard} />

        <div className="grid grid-cols-1 gap-6 sm:grid-cols-[1fr_360px]">
          <PromptWizardStepPanel wizard={wizard} />
          <PromptWizardPreview mode={wizard.mode} promptTemplate={wizard.promptTemplate} />
        </div>

        <PromptWizardFooter wizard={wizard} onCancel={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}
