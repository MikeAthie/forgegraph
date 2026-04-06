import { useCallback, useEffect, useState } from "react";
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

export default function GraphDetailPage() {
  const router = useRouter();
  const graphIdParam = router.query.graphId ?? router.query.workflowId;
  const graphId = Array.isArray(graphIdParam) ? graphIdParam[0] : graphIdParam;

  const [graph, setGraph] = useState<GraphDetail | null>(null);
  const [activeVersion, setActiveVersion] = useState<GraphVersion | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loadingVersion, setLoadingVersion] = useState(false);

  const loadGraph = useCallback(async () => {
    if (!graphId) {
      setGraph(null);
      setError("Missing workflow id.");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const [graphData, versionData] = await Promise.all([graphsApi.get(graphId), graphsApi.getLatestVersion(graphId)]);
      setGraph(graphData);
      setActiveVersion(versionData);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to load workflow."));
    } finally {
      setLoading(false);
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

      setSaving(true);
      try {
        const newVersion = await graphsApi.createVersion(graphId, {
          graph_json: graphJson,
        });
        setActiveVersion(newVersion);
        setGraph((prev) => {
          if (!prev) return prev;
          const exists = prev.versions.some((v) => v.id === newVersion.id);
          if (exists) return prev;
          return {
            ...prev,
            versions: [
              ...prev.versions,
              {
                id: newVersion.id,
                version: newVersion.version,
                checksum: newVersion.checksum,
                created_at: newVersion.created_at,
              },
            ],
          };
        });
        showSuccess(`Saved as version ${newVersion.version}`);
        // Refresh graph data to update version list
        const updatedGraph = await graphsApi.get(graphId);
        setGraph(updatedGraph);
      } catch (err: unknown) {
        showError("Save failed", getApiErrorMessage(err, ERROR_FALLBACKS.graph.update));
        throw err;
      } finally {
        setSaving(false);
      }
    },
    [graphId],
  );

  const handleSelectVersion = useCallback(
    async (versionId: string) => {
      if (!graphId) return;

      setLoadingVersion(true);
      try {
        const version = await graphsApi.getVersion(graphId, versionId);
        setActiveVersion(version);
      } catch (err: unknown) {
        showError("Load failed", getApiErrorMessage(err, ERROR_FALLBACKS.graph.load));
        throw err;
      } finally {
        setLoadingVersion(false);
      }
    },
    [graphId],
  );

  const handleUpdateMetadata = useCallback(
    async (name: string, description: string) => {
      if (!graphId) return;

      try {
        const updated = await graphsApi.update(graphId, { name, description });
        setGraph((prev) => (prev ? { ...prev, name: updated.name, description: updated.description } : null));
        showSuccess("Workflow info updated");
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
            <div className="flex items-center space-x-3 text-muted-foreground">
              <Spinner size="md" />
              <span className="text-sm">Loading workflow...</span>
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
                {error ? "Error Loading Workflow" : "Workflow Not Found"}
              </h2>
              <p className="mt-2 text-sm text-muted-foreground">
                {error ?? "The workflow may have been deleted or you may not have access."}
              </p>
              <Link
                href="/workflows"
                className="mt-4 inline-block text-sm font-medium text-primary hover:text-primary/90"
              >
                Back to workflows
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
            ← Back
          </Link>
          <div className="h-4 w-px bg-border" />
          <h1 aria-label={graph.name} className="text-sm font-semibold text-foreground truncate">
            {graph.name}
          </h1>
          <span className="hidden sm:inline text-xs text-muted-foreground">Workflow Editor</span>
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
