import { type Ref } from "react";
import { Brain, Play, Save as SaveIcon, Wand2 } from "lucide-react";

import { useWizard } from "@/contexts/WizardContext";
import type { GraphEditorController } from "./GraphEditor";

export function GraphPrimaryActions({ controller }: { controller: GraphEditorController }) {
  return (
    <>
      <WizardButton buttonRef={controller.wizardButtonRef} onBeforeStart={controller.captureFocusableTarget} />
      <button
        ref={controller.memoryButtonRef}
        type="button"
        aria-label="Memory settings"
        onClick={controller.handleOpenMemoryConfig}
        className="bg-background/60 backdrop-blur-sm border border-border text-muted-foreground px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-accent/50 hover:text-foreground transition-colors shadow-sm flex items-center gap-1.5"
      >
        <Brain aria-hidden="true" className="size-4" />
        <span className="hidden sm:inline">Memory</span>
      </button>
      <button
        type="button"
        aria-label={controller.runDisabledReason ?? "Launch test operation"}
        onClick={() => void controller.handleRunWorkflow()}
        disabled={Boolean(controller.runDisabledReason)}
        title={controller.runDisabledReason ?? "Launch test operation"}
        className="bg-emerald-600 text-white px-4 py-1.5 rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
      >
        {controller.startingRun ? "Starting" : <Play aria-hidden="true" className="size-4" />}
      </button>
      <button
        type="button"
        aria-label={controller.saving ? "Saving" : "Save"}
        onClick={() => void controller.handleSave()}
        disabled={controller.saving || !controller.isDirty}
        className="bg-primary text-white px-4 py-1.5 rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
      >
        {controller.saving ? "Saving" : <SaveIcon aria-hidden="true" className="size-4" />}
      </button>
    </>
  );
}

function WizardButton({
  buttonRef,
  onBeforeStart,
}: {
  buttonRef?: Ref<HTMLButtonElement>;
  onBeforeStart?: () => void;
}) {
  const { startWizard, state } = useWizard();

  return (
    <button
      ref={buttonRef}
      type="button"
      aria-label="Operating Model Wizard"
      onClick={() => {
        onBeforeStart?.();
        startWizard(false);
      }}
      disabled={state.isActive}
      title="Open Operating Model Wizard (Ctrl+W / Ctrl+Shift+W)"
      className="bg-violet-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm flex items-center gap-1.5"
    >
      <Wand2 aria-hidden="true" className="size-4" />
      <span className="hidden sm:inline">Wizard</span>
    </button>
  );
}
