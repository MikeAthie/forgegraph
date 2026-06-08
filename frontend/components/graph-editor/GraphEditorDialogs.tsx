import { NODE_TYPES } from "../../lib/graph-types";
import { AgentWizard } from "./wizard/AgentWizard";
import { PromptNodeWizardDialog } from "./PromptNodeWizardDialog";
import { NodeConfigDialog } from "./NodeConfigDialog";
import { MemoryConfigDialog } from "./dialogs/MemoryConfigDialog";
import { getNodeFormComponent } from "./forms/node-form-registry";
import type { GraphEditorController } from "./GraphEditor";

export function GraphEditorDialogs({ controller }: { controller: GraphEditorController }) {
  return (
    <>
      <AgentWizard
        onComplete={(payload) => {
          void controller.handleWizardComplete(payload);
          controller.restoreFocusableTarget();
        }}
        onExit={controller.restoreFocusableTarget}
      />
      <PromptNodeWizardDialog
        open={controller.promptWizardOpen}
        onOpenChange={(nextOpen) => {
          controller.setPromptWizardOpen(nextOpen);
          if (!nextOpen) {
            controller.setPromptWizardSourceNodeId(null);
            controller.restoreFocusableTarget();
          }
        }}
        onComplete={(config) => {
          controller.addExecutableNode(NODE_TYPES.PROMPT, {
            sourceNodeId: controller.promptWizardSourceNodeId,
            config,
          });
          controller.setPromptWizardSourceNodeId(null);
        }}
      />
      <NodeConfigDialog
        isOpen={controller.configDialogOpen}
        onClose={() => {
          controller.setConfigDialogOpen(false);
          controller.setConfigDialogNodeType(null);
          controller.setConfigDialogSourceNodeId(null);
          controller.setConfigDialogInitialConfig({});
          controller.setConfigDialogInitialLabel(null);
          controller.restoreFocusableTarget();
        }}
        nodeType={controller.configDialogNodeType}
        initialConfig={controller.configDialogInitialConfig}
        initialLabel={controller.configDialogInitialLabel ?? undefined}
        onSave={controller.handleConfigDialogComplete}
        FormComponent={
          controller.configDialogNodeType
            ? (getNodeFormComponent(controller.configDialogNodeType) ?? undefined)
            : undefined
        }
      />
      <MemoryConfigDialog
        graphId={controller.graphId ?? null}
        open={controller.memoryConfigOpen}
        onOpenChange={controller.handleMemoryConfigOpenChange}
      />
    </>
  );
}
