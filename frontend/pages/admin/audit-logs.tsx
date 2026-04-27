import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarRange, Filter, UserRound } from "lucide-react";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
import { auditLogsApi, type AuditLogEntry } from "../../lib/api";
import { getApiErrorMessage } from "../../lib/api";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Spinner,
} from "@/components/ui";

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
  const [resourceIdFilter, setResourceIdFilter] = useState("");
  const [actorFilter, setActorFilter] = useState("");
  const [createdFromFilter, setCreatedFromFilter] = useState("");
  const [createdToFilter, setCreatedToFilter] = useState("");
  const [tenantFilter, setTenantFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [appliedFilters, setAppliedFilters] = useState<{
    action?: string;
    resource_type?: string;
    resource_id?: string;
    actor_email?: string;
    created_from?: string;
    created_to?: string;
    tenant_id?: string;
  }>({});

  const filters = useMemo(
    () => ({
      ...appliedFilters,
      limit: PAGE_SIZE,
      offset,
    }),
    [appliedFilters, offset],
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

  const applyFilters = useCallback(() => {
    setOffset(0);
    setAppliedFilters({
      action: actionFilter.trim() || undefined,
      resource_type: resourceFilter.trim() || undefined,
      resource_id: resourceIdFilter.trim() || undefined,
      actor_email: actorFilter.trim() || undefined,
      created_from: toIsoDateTime(createdFromFilter),
      created_to: toIsoDateTime(createdToFilter),
      tenant_id: tenantFilter.trim() || undefined,
    });
  }, [actionFilter, resourceFilter, resourceIdFilter, actorFilter, createdFromFilter, createdToFilter, tenantFilter]);

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <h1 className="text-2xl sm:text-3xl font-semibold">Activity Log</h1>
            <p className="text-sm text-muted-foreground">
              Search the operator trail across operations, credentials, access, retention, and curated knowledge.
            </p>
          </div>

          <Card className="border-border/60 bg-card/60 backdrop-blur-sm">
            <CardHeader>
              <CardTitle className="text-base">Filters</CardTitle>
              <CardDescription>
                Filter by actor, action, resource, or date range before drilling into metadata.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
                <Input
                  value={actionFilter}
                  onChange={(event) => setActionFilter(event.target.value)}
                  placeholder="Action (e.g., operation.started)"
                />
                <Input
                  value={resourceFilter}
                  onChange={(event) => setResourceFilter(event.target.value)}
                  placeholder="Resource type (e.g., operation)"
                />
                <Input
                  value={resourceIdFilter}
                  onChange={(event) => setResourceIdFilter(event.target.value)}
                  placeholder="Resource ID"
                />
                <Input
                  value={actorFilter}
                  onChange={(event) => setActorFilter(event.target.value)}
                  placeholder="Actor email"
                />
                <Input
                  type="datetime-local"
                  value={createdFromFilter}
                  onChange={(event) => setCreatedFromFilter(event.target.value)}
                  aria-label="Created from"
                />
                <Input
                  type="datetime-local"
                  value={createdToFilter}
                  onChange={(event) => setCreatedToFilter(event.target.value)}
                  aria-label="Created to"
                />
                <Input
                  value={tenantFilter}
                  onChange={(event) => setTenantFilter(event.target.value)}
                  placeholder="Tenant ID"
                />
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Button onClick={applyFilters} disabled={loading}>
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
                    setResourceIdFilter("");
                    setActorFilter("");
                    setCreatedFromFilter("");
                    setCreatedToFilter("");
                    setTenantFilter("");
                    setOffset(0);
                    setAppliedFilters({});
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
                    <div className="flex flex-col gap-3 rounded-2xl border border-border/40 bg-background/70 p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline">{entry.action}</Badge>
                        <Badge variant="secondary">{entry.resource_type}</Badge>
                        <span className="text-xs text-muted-foreground">{formatTimestamp(entry.created_at)}</span>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-foreground">{entry.description}</p>
                        <p className="mt-1 text-xs font-mono text-muted-foreground">{entry.resource_id}</p>
                      </div>
                      <div className="grid gap-3 text-xs text-muted-foreground md:grid-cols-3">
                        <div className="rounded-xl border border-border/40 bg-muted/30 p-3">
                          <div className="flex items-center gap-2 text-foreground">
                            <UserRound className="h-3.5 w-3.5" aria-hidden="true" />
                            <span className="font-semibold">Actor</span>
                          </div>
                          <p className="mt-1">{entry.actor_email ?? "System"}</p>
                        </div>
                        <div className="rounded-xl border border-border/40 bg-muted/30 p-3">
                          <div className="flex items-center gap-2 text-foreground">
                            <CalendarRange className="h-3.5 w-3.5" aria-hidden="true" />
                            <span className="font-semibold">Tenant</span>
                          </div>
                          <p className="mt-1 font-mono">{entry.tenant_id}</p>
                        </div>
                        <div className="rounded-xl border border-border/40 bg-muted/30 p-3">
                          <div className="flex items-center gap-2 text-foreground">
                            <Filter className="h-3.5 w-3.5" aria-hidden="true" />
                            <span className="font-semibold">Metadata</span>
                          </div>
                          <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-background px-3 py-2 text-xs text-foreground">
                            {formatMetadata(entry.metadata)}
                          </pre>
                        </div>
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

function toIsoDateTime(value: string): string | undefined {
  if (!value) {
    return undefined;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return undefined;
  }
  return date.toISOString();
}
