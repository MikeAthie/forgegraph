import { useCallback, useEffect, useReducer } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import dynamic from "next/dynamic";

import ProtectedRoute from "../../components/ProtectedRoute";
import { Spinner } from "@/components/ui/spinner";
import { showSuccess, showError } from "../../lib/toast";
import { getApiErrorMessage, graphsApi, type GraphDetail } from "../../lib/api";
import { ERROR_FALLBACKS } from "../../lib/error-messages";
import type { GraphJson, GraphVersion } from "../../lib/graph-types";

// Dynamic import for the GraphEditor to avoid SSR issues with React Flow
const GraphEditor = dynamic(() => import("../../components/graph-editor/GraphEditor").then((mod) => mod.GraphEditor), {
  ssr: false,
  loading: () => (
    <div className="flex-1 flex items-center justify-center">
      <Spinner size="lg" />
    </div>
  ),
});

type GraphDetailState = {
  graph: GraphDetail | null;
  activeVersion: GraphVersion | null;
  loading: boolean;
  error: string | null;
  saving: boolean;
  loadingVersion: boolean;
};

type GraphDetailAction =
  | { type: "load-start" }
  | { type: "load-missing" }
  | { type: "load-success"; graph: GraphDetail; activeVersion: GraphVersion | null }
  | { type: "load-error"; error: string }
  | { type: "save-start" }
  | { type: "save-success"; version: GraphVersion; graph: GraphDetail }
  | { type: "save-end" }
  | { type: "version-load-start" }
  | { type: "version-load-success"; version: GraphVersion }
  | { type: "version-load-end" }
  | { type: "metadata-success"; name: string; description: string };

const initialGraphDetailState: GraphDetailState = {
  graph: null,
  activeVersion: null,
  loading: true,
  error: null,
  saving: false,
  loadingVersion: false,
};

function graphDetailReducer(state: GraphDetailState, action: GraphDetailAction): GraphDetailState {
  switch (action.type) {
    case "load-start":
      return { ...state, loading: true, error: null };
    case "load-missing":
      return { ...state, graph: null, activeVersion: null, loading: false, error: "Missing operating model id." };
    case "load-success":
      return { ...state, graph: action.graph, activeVersion: action.activeVersion, loading: false, error: null };
    case "load-error":
      return { ...state, loading: false, error: action.error };
    case "save-start":
      return { ...state, saving: true };
    case "save-success":
      return { ...state, graph: action.graph, activeVersion: action.version };
    case "save-end":
      return { ...state, saving: false };
    case "version-load-start":
      return { ...state, loadingVersion: true };
    case "version-load-success":
      return { ...state, activeVersion: action.version };
    case "version-load-end":
      return { ...state, loadingVersion: false };
    case "metadata-success":
      return state.graph
        ? { ...state, graph: { ...state.graph, name: action.name, description: action.description } }
        : state;
    default:
      return state;
  }
}

export default function GraphDetailPage() {
  const router = useRouter();
  const graphIdParam = router.query.graphId ?? router.query.workflowId;
  const graphId = Array.isArray(graphIdParam) ? graphIdParam[0] : graphIdParam;

  const [{ graph, activeVersion, loading, error, saving, loadingVersion }, dispatchGraph] = useReducer(
    graphDetailReducer,
    initialGraphDetailState,
  );

  const loadGraph = useCallback(async () => {
    if (!graphId) {
      dispatchGraph({ type: "load-missing" });
      return;
    }

    dispatchGraph({ type: "load-start" });
    try {
      const [graphData, versionData] = await Promise.all([graphsApi.get(graphId), graphsApi.getLatestVersion(graphId)]);
      dispatchGraph({ type: "load-success", graph: graphData, activeVersion: versionData });
    } catch (err: unknown) {
      dispatchGraph({
        type: "load-error",
        error: getApiErrorMessage(err, "Failed to load the advanced operating model."),
      });
    }
  }, [graphId]);

  useEffect(() => {
    if (!router.isReady) {
      return;
    }
    void loadGraph();
  }, [router.isReady, loadGraph]);

  const handleSave = useCallback(
    async (graphJson: GraphJson) => {
      if (!graphId) return;

      dispatchGraph({ type: "save-start" });
      try {
        const newVersion = await graphsApi.createVersion(graphId, {
          graph_json: graphJson,
        });
        showSuccess(`Saved as version ${newVersion.version}`);
        const updatedGraph = await graphsApi.get(graphId);
        dispatchGraph({ type: "save-success", version: newVersion, graph: updatedGraph });
      } catch (err: unknown) {
        showError("Save failed", getApiErrorMessage(err, ERROR_FALLBACKS.graph.update));
        throw err;
      } finally {
        dispatchGraph({ type: "save-end" });
      }
    },
    [graphId],
  );

  const handleSelectVersion = useCallback(
    async (versionId: string) => {
      if (!graphId) return;

      dispatchGraph({ type: "version-load-start" });
      try {
        const version = await graphsApi.getVersion(graphId, versionId);
        dispatchGraph({ type: "version-load-success", version });
      } catch (err: unknown) {
        showError("Load failed", getApiErrorMessage(err, ERROR_FALLBACKS.graph.load));
        throw err;
      } finally {
        dispatchGraph({ type: "version-load-end" });
      }
    },
    [graphId],
  );

  const handleUpdateMetadata = useCallback(
    async (name: string, description: string) => {
      if (!graphId) return;

      try {
        const updated = await graphsApi.update(graphId, { name, description });
        dispatchGraph({ type: "metadata-success", name: updated.name, description: updated.description });
        showSuccess("Operating model info updated");
      } catch (err: unknown) {
        showError("Update failed", getApiErrorMessage(err, ERROR_FALLBACKS.graph.update));
        throw err;
      }
    },
    [graphId],
  );

  if (loading) {
    return (
      <ProtectedRoute>
        <div className="h-screen flex flex-col bg-background">
          <div className="flex-1 flex items-center justify-center">
            <div className="flex items-center gap-x-3 text-muted-foreground">
              <Spinner size="md" />
              <span className="text-sm">Loading advanced operating model</span>
            </div>
          </div>
        </div>
      </ProtectedRoute>
    );
  }

  if (error || !graph) {
    return (
      <ProtectedRoute>
        <div className="h-screen flex flex-col bg-background">
          <main className="flex-1 flex items-center justify-center">
            <div className="bg-card rounded-lg border border-border p-10 text-center max-w-md shadow-sm">
              <h2 className="text-lg font-semibold text-foreground">
                {error ? "Error Loading Operating Model" : "Operating Model Not Found"}
              </h2>
              <p className="mt-2 text-sm text-muted-foreground">
                {error ?? "The operating model may have been deleted or you may not have access."}
              </p>
              <Link
                href="/workflows"
                className="mt-4 inline-block text-sm font-medium text-primary hover:text-primary/90"
              >
                Back to advanced mode
              </Link>
            </div>
          </main>
        </div>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <div className="h-screen flex flex-col bg-background">
        {/* Header with back button */}
        <div className="bg-background/80 backdrop-blur-lg border-b border-border px-4 py-2 flex items-center gap-4">
          <Link
            href="/workflows"
            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            ← Back to advanced mode
          </Link>
          <div className="h-4 w-px bg-border" />
          <h1 aria-label={graph.name} className="text-sm font-semibold text-foreground truncate">
            {graph.name}
          </h1>
          <span className="hidden sm:inline text-xs text-muted-foreground">Advanced Operating Model Editor</span>
        </div>

        {/* Editor */}
        <div className="flex-1 overflow-hidden">
          <GraphEditor
            graphId={graph.id}
            graphName={graph.name}
            graphDescription={graph.description}
            initialGraphJson={activeVersion?.graph_json ?? null}
            currentVersion={activeVersion?.version ?? null}
            currentVersionId={activeVersion?.id ?? null}
            availableVersions={graph.versions.map((v) => ({ id: v.id, version: v.version }))}
            loadingVersion={loadingVersion}
            onSelectVersion={handleSelectVersion}
            onSave={handleSave}
            onUpdateMetadata={handleUpdateMetadata}
            saving={saving}
          />
        </div>
      </div>
    </ProtectedRoute>
  );
}
