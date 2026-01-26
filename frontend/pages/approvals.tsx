import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { RefreshCw } from "lucide-react";

import DashboardLayout from "../components/DashboardLayout";
import ProtectedRoute from "../components/ProtectedRoute";
import { approvalsApi, getApiErrorMessage, type ApprovalTask } from "../lib/api";
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

const getStatusBadgeClass = (status: string) => {
  switch (status) {
    case "pending":
      return "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-200";
    case "approved":
      return "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-200";
    case "rejected":
      return "bg-destructive/10 text-destructive border-destructive/30";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
};

export default function ApprovalsPage() {
  const router = useRouter();

  const [tasks, setTasks] = useState<ApprovalTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<"pending" | "approved" | "rejected" | "all">("pending");

  const fetchApprovals = useCallback(
    async (opts?: { silent?: boolean }) => {
      const silent = opts?.silent ?? false;
      if (!silent) {
        setLoading(true);
      } else {
        setIsRefreshing(true);
      }
      setError(null);

      try {
        const data = await approvalsApi.list(statusFilter);
        setTasks(data);
      } catch (err: unknown) {
        setError(getApiErrorMessage(err, "Failed to load approvals."));
      } finally {
        if (!silent) {
          setLoading(false);
        }
        setIsRefreshing(false);
      }
    },
    [statusFilter],
  );

  useEffect(() => {
    void fetchApprovals();
  }, [fetchApprovals]);

  const titleLabel = useMemo(() => {
    if (statusFilter === "all") return "Approvals";
    return `Approvals (${statusFilter})`;
  }, [statusFilter]);

  const emptyCopy = useMemo(() => {
    if (statusFilter === "pending") {
      return {
        title: "No pending approvals",
        description: "Human-in-the-loop steps will appear here when a run pauses at a Human Gate node.",
      };
    }
    return {
      title: "No approvals found",
      description: "Try switching the status filter to see more tasks.",
    };
  }, [statusFilter]);

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="space-y-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-foreground">Approvals</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Review Human Gate tasks and jump directly to the paused run.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                onClick={() => void fetchApprovals({ silent: true })}
                disabled={loading || isRefreshing}
                className="gap-2"
              >
                {isRefreshing ? (
                  <>
                    <Spinner size="xs" />
                    Refreshing...
                  </>
                ) : (
                  <>
                    <RefreshCw className="h-4 w-4" />
                    Refresh
                  </>
                )}
              </Button>
            </div>
          </div>

          <Card className="border-border/50 bg-card/60 backdrop-blur-sm">
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center justify-between gap-3">
                <span>{titleLabel}</span>
                <div className="flex items-center gap-2">
                  <Select
                    value={statusFilter}
                    onValueChange={(value) => setStatusFilter(value as typeof statusFilter)}
                  >
                    <SelectTrigger className="w-[170px]">
                      <SelectValue placeholder="Status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="pending">Pending</SelectItem>
                      <SelectItem value="approved">Approved</SelectItem>
                      <SelectItem value="rejected">Rejected</SelectItem>
                      <SelectItem value="all">All</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </CardTitle>
            </CardHeader>

            <CardContent>
              {loading ? (
                <div className="flex items-center justify-center py-10">
                  <Spinner size="md" />
                  <span className="ml-3 text-sm text-muted-foreground">Loading approvals...</span>
                </div>
              ) : tasks.length === 0 ? (
                <EmptyState title={emptyCopy.title} description={emptyCopy.description} />
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-border">
                    <thead className="bg-muted/40">
                      <tr>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">
                          Graph
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">
                          Node
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">
                          Status
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">
                          Created
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">
                          Run
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {tasks.map((task) => (
                        <tr
                          key={task.id}
                          className="hover:bg-muted/40 cursor-pointer transition-colors"
                          onClick={() => void router.push(`/runs/${task.run_id}#approval`)}
                        >
                          <td className="px-4 py-3 text-sm font-medium text-foreground">
                            <div className="flex flex-col">
                              <span className="truncate max-w-[340px]">{task.graph_name}</span>
                              {task.prompt_message ? (
                                <span className="text-xs text-muted-foreground truncate max-w-[360px]">
                                  {task.prompt_message}
                                </span>
                              ) : (
                                <span className="text-xs text-muted-foreground">—</span>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3 text-sm text-muted-foreground">
                            <span className="truncate max-w-[260px] inline-block align-bottom">
                              {task.node_name}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm">
                            <Badge variant="outline" className={getStatusBadgeClass(task.status)}>
                              {task.status}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-sm text-muted-foreground">
                            {formatDateTime(task.created_at)}
                          </td>
                          <td className="px-4 py-3 text-sm">
                            <Button variant="outline" size="sm" asChild>
                              <Link
                                href={`/runs/${task.run_id}#approval`}
                                onClick={(event) => {
                                  event.preventDefault();
                                  event.stopPropagation();
                                  void router.push(`/runs/${task.run_id}#approval`);
                                }}
                              >
                                Review
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
