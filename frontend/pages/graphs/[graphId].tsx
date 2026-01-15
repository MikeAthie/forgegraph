import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import Header from "../../components/Header";
import ProtectedRoute from "../../components/ProtectedRoute";
import { getApiErrorMessage, graphsApi, type GraphDetail } from "../../lib/api";

const formatDateTime = (isoString: string) => {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return isoString;
  }
  return date.toLocaleString();
};

export default function GraphDetailPage() {
  const router = useRouter();
  const graphIdParam = router.query.graphId;
  const graphId = Array.isArray(graphIdParam) ? graphIdParam[0] : graphIdParam;

  const [graph, setGraph] = useState<GraphDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
      const data = await graphsApi.get(graphId);
      setGraph(data);
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

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gray-50">
        <Header />
        <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <Link
                  href="/graphs"
                  className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
                >
                  ← Back to graphs
                </Link>
              </div>
              <h1 className="mt-3 text-2xl font-bold text-gray-900">
                {graph?.name ?? "Graph"}
              </h1>
              <p className="mt-1 text-sm text-gray-600">
                Editor coming in Phase 2. You can manage metadata and view versions below.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void loadGraph()}
              disabled={loading || !graphId}
              className="inline-flex items-center px-3 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Refresh
            </button>
          </div>

          {error && (
            <div className="mt-6 rounded-md bg-red-50 p-4 border border-red-200">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          {loading ? (
            <div className="mt-10 flex items-center justify-center">
              <div className="flex items-center space-x-3 text-gray-600">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary" />
                <span className="text-sm">Loading graph...</span>
              </div>
            </div>
          ) : !graph ? (
            <div className="mt-10 bg-white rounded-lg border border-gray-200 p-10 text-center">
              <h2 className="text-lg font-semibold text-gray-900">Graph not found</h2>
              <p className="mt-2 text-sm text-gray-600">
                The graph may have been deleted or you may not have access.
              </p>
            </div>
          ) : (
            <div className="mt-8 grid gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2 space-y-6">
                <div className="bg-white rounded-lg border border-gray-200 p-6">
                  <h2 className="text-lg font-semibold text-gray-900">Details</h2>
                  <dl className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Created
                      </dt>
                      <dd className="mt-1 text-sm text-gray-900">
                        {formatDateTime(graph.created_at)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Updated
                      </dt>
                      <dd className="mt-1 text-sm text-gray-900">
                        {formatDateTime(graph.updated_at)}
                      </dd>
                    </div>
                    <div className="sm:col-span-2">
                      <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Description
                      </dt>
                      <dd className="mt-1 text-sm text-gray-900 whitespace-pre-wrap">
                        {graph.description || <span className="text-gray-400">No description</span>}
                      </dd>
                    </div>
                  </dl>
                </div>

                <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                  <div className="p-6 border-b border-gray-200">
                    <h2 className="text-lg font-semibold text-gray-900">Versions</h2>
                    <p className="mt-1 text-sm text-gray-600">
                      {graph.versions.length === 0
                        ? "No versions created yet."
                        : `${graph.versions.length} version${
                            graph.versions.length === 1 ? "" : "s"
                          }`}
                    </p>
                  </div>

                  {graph.versions.length === 0 ? (
                    <div className="p-6 text-sm text-gray-600">Create a version in Phase 2.</div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                          <tr>
                            <th
                              scope="col"
                              className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                            >
                              Version
                            </th>
                            <th
                              scope="col"
                              className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                            >
                              Created
                            </th>
                            <th
                              scope="col"
                              className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                            >
                              Checksum
                            </th>
                          </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                          {graph.versions
                            .slice()
                            .sort((a, b) => b.version - a.version)
                            .map((v) => (
                              <tr key={v.id}>
                                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                  v{v.version}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                                  {formatDateTime(v.created_at)}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600 font-mono">
                                  {v.checksum}
                                </td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>

              <div className="space-y-6">
                <div className="bg-white rounded-lg border border-gray-200 p-6">
                  <h2 className="text-lg font-semibold text-gray-900">Graph ID</h2>
                  <p className="mt-2 text-sm text-gray-600 break-all font-mono">{graph.id}</p>
                </div>

                <div className="bg-white rounded-lg border border-gray-200 p-6">
                  <h2 className="text-lg font-semibold text-gray-900">Owner</h2>
                  <p className="mt-2 text-sm text-gray-600 break-all font-mono">
                    {graph.owner_id}
                  </p>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </ProtectedRoute>
  );
}
