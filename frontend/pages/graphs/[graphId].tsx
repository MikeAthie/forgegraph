import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import dynamic from "next/dynamic";

import ProtectedRoute from "../../components/ProtectedRoute";
import { Spinner } from "@/components/ui/spinner";
import { showSuccess, showError } from "../../lib/toast";
import {
  getApiErrorMessage,
  graphsApi,
  type GraphDetail,
} from "../../lib/api";
import type { GraphJson, GraphVersion } from "../../lib/graph-types";

// Dynamic import for the GraphEditor to avoid SSR issues with React Flow
const GraphEditor = dynamic(
  () => import("../../components/graph-editor/GraphEditor").then((mod) => mod.GraphEditor),
  {
    ssr: false,
    loading: () => (
      <div className="flex-1 flex items-center justify-center">
        <Spinner size="lg" />
      </div>
    ),
  }
);

export default function GraphDetailPage() {
  const router = useRouter();
  const graphIdParam = router.query.graphId;
  const graphId = Array.isArray(graphIdParam) ? graphIdParam[0] : graphIdParam;

  const [graph, setGraph] = useState<GraphDetail | null>(null);
  const [latestVersion, setLatestVersion] = useState<GraphVersion | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const loadGraph = useCallback(async () => {
    if (!graphId) {
      setGraph(null);
      setError("Missing graph id.");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const [graphData, versionData] = await Promise.all([
        graphsApi.get(graphId),
        graphsApi.getLatestVersion(graphId),
      ]);
      setGraph(graphData);
      setLatestVersion(versionData);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to load graph."));
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
        setLatestVersion(newVersion);
        showSuccess(`Saved as version ${newVersion.version}`);
        // Refresh graph data to update version list
        const updatedGraph = await graphsApi.get(graphId);
        setGraph(updatedGraph);
      } catch (err: unknown) {
        showError(getApiErrorMessage(err, "Failed to save graph"));
        throw err;
      } finally {
        setSaving(false);
      }
    },
    [graphId]
  );

  const handleUpdateMetadata = useCallback(
    async (name: string, description: string) => {
      if (!graphId) return;

      try {
        const updated = await graphsApi.update(graphId, { name, description });
        setGraph((prev) =>
          prev ? { ...prev, name: updated.name, description: updated.description } : null
        );
        showSuccess("Graph info updated");
      } catch (err: unknown) {
        showError(getApiErrorMessage(err, "Failed to update graph info"));
        throw err;
      }
    },
    [graphId]
  );

  if (loading) {
    return (
      <ProtectedRoute>
        <div className="h-screen flex flex-col bg-gray-50">
          <div className="flex-1 flex items-center justify-center">
            <div className="flex items-center space-x-3 text-gray-600">
              <Spinner size="md" />
              <span className="text-sm">Loading graph...</span>
            </div>
          </div>
        </div>
      </ProtectedRoute>
    );
  }

  if (error || !graph) {
    return (
      <ProtectedRoute>
        <div className="h-screen flex flex-col bg-gray-50">
          <main className="flex-1 flex items-center justify-center">
            <div className="bg-white rounded-lg border border-gray-200 p-10 text-center max-w-md">
              <h2 className="text-lg font-semibold text-gray-900">
                {error ? "Error Loading Graph" : "Graph Not Found"}
              </h2>
              <p className="mt-2 text-sm text-gray-600">
                {error ?? "The graph may have been deleted or you may not have access."}
              </p>
              <Link
                href="/graphs"
                className="mt-4 inline-block text-sm font-medium text-primary hover:text-primary/90"
              >
                Back to graphs
              </Link>
            </div>
          </main>
        </div>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <div className="h-screen flex flex-col bg-gray-100">
        {/* Header with back button */}
        <div className="bg-white border-b border-gray-200 px-4 py-2 flex items-center gap-4">
          <Link
            href="/graphs"
            className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
          >
            ← Back
          </Link>
          <div className="h-4 w-px bg-gray-300" />
          <h1
            aria-label={graph.name}
            className="text-sm font-semibold text-gray-900 truncate"
          >
            Graph Editor
          </h1>
        </div>

        {/* Editor */}
        <div className="flex-1 overflow-hidden">
          <GraphEditor
            graphId={graph.id}
            graphName={graph.name}
            graphDescription={graph.description}
            initialGraphJson={latestVersion?.graph_json ?? null}
            currentVersion={latestVersion?.version ?? null}
            onSave={handleSave}
            onUpdateMetadata={handleUpdateMetadata}
            saving={saving}
          />
        </div>
      </div>
    </ProtectedRoute>
  );
}
