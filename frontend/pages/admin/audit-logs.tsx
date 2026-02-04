import { useCallback, useEffect, useMemo, useState } from "react";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
import { auditLogsApi, type AuditLogEntry } from "../../lib/api";
import { getApiErrorMessage } from "../../lib/api";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Spinner } from "@/components/ui";

const PAGE_SIZE = 100;

const formatTimestamp = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const formatMetadata = (metadata: Record<string, unknown>) => {
  try {
    return JSON.stringify(metadata, null, 2);
  } catch {
    return String(metadata);
  }
};

export default function AuditLogsPage() {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionFilter, setActionFilter] = useState("");
  const [resourceFilter, setResourceFilter] = useState("");
  const [actorFilter, setActorFilter] = useState("");
  const [tenantFilter, setTenantFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [totalCount, setTotalCount] = useState(0);

  const filters = useMemo(
    () => ({
      action: actionFilter.trim() || undefined,
      resource_type: resourceFilter.trim() || undefined,
      actor_email: actorFilter.trim() || undefined,
      tenant_id: tenantFilter.trim() || undefined,
      limit: PAGE_SIZE,
      offset,
    }),
    [actionFilter, resourceFilter, actorFilter, tenantFilter, offset],
  );

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await auditLogsApi.list(filters);
      setEntries(response.data);
      setTotalCount(response.meta.pagination?.totalCount ?? response.data.length);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to load audit logs."));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void fetchLogs();
  }, [fetchLogs]);

  const canGoBack = offset > 0;
  const canGoNext = offset + PAGE_SIZE < totalCount;

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <h1 className="text-2xl sm:text-3xl font-semibold">Audit Logs</h1>
            <p className="text-sm text-muted-foreground">
              Append-only activity log for credentials, runs, and approvals.
            </p>
          </div>

          <Card className="border-border/60 bg-card/60 backdrop-blur-sm">
            <CardHeader>
              <CardTitle className="text-base">Filters</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                <Input
                  value={actionFilter}
                  onChange={(event) => setActionFilter(event.target.value)}
                  placeholder="Action (e.g., run.started)"
                />
                <Input
                  value={resourceFilter}
                  onChange={(event) => setResourceFilter(event.target.value)}
                  placeholder="Resource type (e.g., run)"
                />
                <Input
                  value={actorFilter}
                  onChange={(event) => setActorFilter(event.target.value)}
                  placeholder="Actor email"
                />
                <Input
                  value={tenantFilter}
                  onChange={(event) => setTenantFilter(event.target.value)}
                  placeholder="Tenant ID"
                />
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Button onClick={() => void fetchLogs()} disabled={loading}>
                  {loading ? (
                    <>
                      <Spinner size="xs" className="mr-2" />
                      Loading...
                    </>
                  ) : (
                    "Apply filters"
                  )}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setActionFilter("");
                    setResourceFilter("");
                    setActorFilter("");
                    setTenantFilter("");
                    setOffset(0);
                  }}
                  disabled={loading}
                >
                  Reset
                </Button>
                <div className="ml-auto text-xs text-muted-foreground">
                  Showing {Math.min(offset + 1, totalCount)}–{Math.min(offset + PAGE_SIZE, totalCount)} of {totalCount}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/60 bg-card/60 backdrop-blur-sm">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">Recent activity</CardTitle>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!canGoBack || loading}
                  onClick={() => setOffset((prev) => Math.max(0, prev - PAGE_SIZE))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!canGoNext || loading}
                  onClick={() => setOffset((prev) => prev + PAGE_SIZE)}
                >
                  Next
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {error && <p className="text-sm text-destructive">Error: {error}</p>}
              {!error && entries.length === 0 && !loading && (
                <p className="text-sm text-muted-foreground">No audit logs found.</p>
              )}
              <div className="divide-y divide-border/60">
                {entries.map((entry) => (
                  <div key={entry.id} className="py-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{entry.action}</Badge>
                      <span className="text-sm font-medium">{entry.resource_type}</span>
                      <span className="text-xs text-muted-foreground font-mono">
                        {entry.resource_id}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {formatTimestamp(entry.created_at)}
                      </span>
                    </div>
                    <div className="mt-2 grid gap-2 text-xs text-muted-foreground md:grid-cols-3">
                      <div>
                        <span className="font-semibold text-foreground">Actor:</span>{" "}
                        {entry.actor_email ?? "System"}
                      </div>
                      <div>
                        <span className="font-semibold text-foreground">Tenant:</span>{" "}
                        {entry.tenant_id}
                      </div>
                      <div>
                        <span className="font-semibold text-foreground">Metadata:</span>
                        <pre className="mt-1 max-h-40 overflow-auto rounded-md bg-muted px-3 py-2 text-xs text-foreground">
                          {formatMetadata(entry.metadata)}
                        </pre>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
