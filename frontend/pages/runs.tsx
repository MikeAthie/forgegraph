import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { RefreshCw } from "lucide-react";

import DashboardLayout from "../components/DashboardLayout";
import ProtectedRoute from "../components/ProtectedRoute";
import { getApiErrorMessage, runsApi, type RunListItem } from "../lib/api";
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
} from "@/components/ui";

const formatDateTime = (isoString: string) => {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return isoString;
  }
  return date.toLocaleString();
};

const formatDuration = (durationMs: number | null) => {
  if (!durationMs && durationMs !== 0) return "-";
  if (durationMs < 1000) return `${durationMs}ms`;

  const totalSeconds = Math.floor(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${totalSeconds}s`;
};

const normalizeStatusLabel = (status: string) => {
  return status;
};

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "succeeded":
    case "success":
      return (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M9 12.5l2 2 4-5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"
            stroke="currentColor"
            strokeWidth="2"
          />
        </svg>
      );
    case "failed":
    case "error":
      return (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M15 9l-6 6M9 9l6 6"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <path
            d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"
            stroke="currentColor"
            strokeWidth="2"
          />
        </svg>
      );
    case "running":
      return (
        <svg viewBox="0 0 24 24" fill="none" className="animate-spin" aria-hidden="true">
          <path
            d="M12 2a10 10 0 1 0 10 10"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      );
    case "paused":
      return (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M9 7v10M15 7v10"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <path
            d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"
            stroke="currentColor"
            strokeWidth="2"
          />
        </svg>
      );
    case "canceled":
      return (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M7 7l10 10"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <path
            d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"
            stroke="currentColor"
            strokeWidth="2"
          />
        </svg>
      );
    case "pending":
    default:
      return (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M12 6v6l4 2"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"
            stroke="currentColor"
            strokeWidth="2"
          />
        </svg>
      );
  }
}

const getStatusBadgeClass = (status: string) => {
  switch (status) {
    case "succeeded":
    case "success":
      return "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    case "failed":
    case "error":
      return "border-rose-500/25 bg-rose-500/10 text-rose-700 dark:text-rose-300";
    case "running":
      return "border-blue-500/25 bg-blue-500/10 text-blue-700 dark:text-blue-300";
    case "pending":
      return "border-muted-foreground/25 bg-muted/40 text-muted-foreground";
    case "paused":
      return "border-amber-500/25 bg-amber-500/10 text-amber-800 dark:text-amber-300";
    case "canceled":
      return "border-muted-foreground/20 bg-muted/40 text-muted-foreground";
    default:
      return "border-muted-foreground/25 bg-muted/40 text-muted-foreground";
  }
};

export default function RunsPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [graphFilter, setGraphFilter] = useState<string>("all");

  const refreshRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await runsApi.list();
      setRuns(data);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to load runs."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshRuns();
  }, [refreshRuns]);

  const sortedRuns = useMemo(() => {
    return [...runs].sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? ""));
  }, [runs]);

  const graphOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const run of runs) {
      if (run.graph_id) {
        map.set(run.graph_id, run.graph_name);
      }
    }
    return [...map.entries()]
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [runs]);

  const filteredRuns = useMemo(() => {
    return sortedRuns.filter((run) => {
      if (statusFilter !== "all") {
        const label = normalizeStatusLabel(String(run.status));
        if (label !== statusFilter) return false;
      }

      if (graphFilter !== "all" && run.graph_id !== graphFilter) {
        return false;
      }

      return true;
    });
  }, [sortedRuns, statusFilter, graphFilter]);

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <div className="relative overflow-hidden rounded-2xl border border-border/50 bg-card/60 backdrop-blur-sm p-6">
            <div className="pointer-events-none absolute inset-0 bg-linear-to-br from-primary/12 via-violet-500/8 to-fuchsia-500/8" />
            <div className="relative flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight bg-linear-to-r from-primary via-violet-500 to-fuchsia-500 bg-clip-text text-transparent">
                  Runs
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Debug your workflows with node-by-node status, outputs, and timings.
                </p>
              </div>
              <Button variant="outline" onClick={() => void refreshRuns()} disabled={loading}>
                {loading ? <Spinner size="xs" /> : <RefreshCw aria-hidden="true" />}
                {loading ? "Refreshing..." : "Refresh"}
              </Button>
            </div>
          </div>

          <Card className="border-border/50 bg-card/60 backdrop-blur-sm">
            <CardHeader className="pb-2">
              <CardTitle className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <span>Run history</span>
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <Select value={statusFilter} onValueChange={setStatusFilter}>
                    <SelectTrigger className="w-full sm:w-[160px]">
                      <SelectValue placeholder="Status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All statuses</SelectItem>
                      <SelectItem value="pending">Pending</SelectItem>
                      <SelectItem value="running">Running</SelectItem>
                      <SelectItem value="succeeded">Succeeded</SelectItem>
                      <SelectItem value="failed">Failed</SelectItem>
                      <SelectItem value="paused">Paused</SelectItem>
                      <SelectItem value="canceled">Canceled</SelectItem>
                    </SelectContent>
                  </Select>

                  <Select value={graphFilter} onValueChange={setGraphFilter}>
                    <SelectTrigger className="w-full sm:w-[220px]">
                      <SelectValue placeholder="Graph" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All graphs</SelectItem>
                      {graphOptions.map((graph) => (
                        <SelectItem key={graph.id} value={graph.id}>
                          {graph.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {(statusFilter !== "all" || graphFilter !== "all") && (
                    <Button
                      variant="outline"
                      onClick={() => {
                        setStatusFilter("all");
                        setGraphFilter("all");
                      }}
                    >
                      Clear
                    </Button>
                  )}
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex items-center justify-center py-10">
                  <Spinner size="md" />
                  <span className="ml-3 text-sm text-muted-foreground">Loading runs...</span>
                </div>
              ) : filteredRuns.length === 0 ? (
                <EmptyState
                  title={runs.length === 0 ? "No runs yet" : "No runs match your filters"}
                  description={
                    runs.length === 0
                      ? "Once a graph run is created, it will show up here."
                      : "Try clearing filters to see more runs."
                  }
                />
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-border">
                    <thead className="bg-muted/40">
                      <tr>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">
                          Graph
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">
                          Status
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">
                          Started
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">
                          Duration
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">
                          Run
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {filteredRuns.map((run) => (
                        <tr
                          key={run.id}
                          className="hover:bg-muted/40 cursor-pointer transition-colors"
                          onClick={() => void router.push(`/runs/${run.id}`)}
                        >
                          <td className="px-4 py-3 text-sm font-medium text-foreground">
                            <div className="flex flex-col">
                              <span className="truncate max-w-[340px]">{run.graph_name}</span>
                              <span className="text-xs text-muted-foreground">
                                v{run.graph_version}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-sm">
                            <Badge
                              variant="outline"
                              className={getStatusBadgeClass(String(run.status))}
                            >
                              <StatusIcon status={String(run.status)} />
                              {normalizeStatusLabel(String(run.status))}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-sm text-muted-foreground">
                            {run.started_at ? formatDateTime(run.started_at) : "—"}
                          </td>
                          <td className="px-4 py-3 text-sm text-muted-foreground">
                            {formatDuration(run.duration_ms)}
                          </td>
                          <td className="px-4 py-3 text-sm">
                            <Button variant="outline" size="sm" asChild>
                              <Link
                                href={`/runs/${run.id}`}
                                onClick={(event) => {
                                  event.preventDefault();
                                  event.stopPropagation();
                                  void router.push(`/runs/${run.id}`);
                                }}
                              >
                                View
                              </Link>
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {error && (
                <Alert variant="destructive" className="mt-4">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
