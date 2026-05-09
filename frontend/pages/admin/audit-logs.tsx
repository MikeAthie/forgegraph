import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
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
  FormField,
  Input,
  Spinner,
} from "@/components/ui";

const PAGE_SIZE = 50;

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
  const router = useRouter();
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

  useEffect(() => {
    if (!router.isReady) {
      return;
    }

    const action = typeof router.query.action === "string" ? router.query.action : "";
    const resourceType = typeof router.query.resource_type === "string" ? router.query.resource_type : "";
    const resourceId = typeof router.query.resource_id === "string" ? router.query.resource_id : "";
    const actorEmail = typeof router.query.actor_email === "string" ? router.query.actor_email : "";
    const createdFrom = typeof router.query.created_from === "string" ? router.query.created_from : "";
    const createdTo = typeof router.query.created_to === "string" ? router.query.created_to : "";
    const tenantId = typeof router.query.tenant_id === "string" ? router.query.tenant_id : "";
    const nextOffset = typeof router.query.offset === "string" ? Math.max(0, Number(router.query.offset) || 0) : 0;

    setActionFilter(action);
    setResourceFilter(resourceType);
    setResourceIdFilter(resourceId);
    setActorFilter(actorEmail);
    setCreatedFromFilter(createdFrom);
    setCreatedToFilter(createdTo);
    setTenantFilter(tenantId);
    setOffset(nextOffset);
    setAppliedFilters({
      action: action.trim() || undefined,
      resource_type: resourceType.trim() || undefined,
      resource_id: resourceId.trim() || undefined,
      actor_email: actorEmail.trim() || undefined,
      created_from: toIsoDateTime(createdFrom),
      created_to: toIsoDateTime(createdTo),
      tenant_id: tenantId.trim() || undefined,
    });
  }, [
    router.isReady,
    router.query.action,
    router.query.actor_email,
    router.query.created_from,
    router.query.created_to,
    router.query.offset,
    router.query.resource_id,
    router.query.resource_type,
    router.query.tenant_id,
  ]);

  const canGoBack = offset > 0;
  const canGoNext = offset + PAGE_SIZE < totalCount;

  const replaceAuditQuery = useCallback(
    (next: {
      action?: string;
      resource_type?: string;
      resource_id?: string;
      actor_email?: string;
      created_from?: string;
      created_to?: string;
      tenant_id?: string;
      offset?: number;
    }) => {
      if (!router.isReady) {
        return;
      }

      const queryParams = { ...router.query };
      for (const key of [
        "action",
        "resource_type",
        "resource_id",
        "actor_email",
        "created_from",
        "created_to",
        "tenant_id",
        "offset",
      ]) {
        delete queryParams[key];
      }

      if (next.action?.trim()) queryParams.action = next.action.trim();
      if (next.resource_type?.trim()) queryParams.resource_type = next.resource_type.trim();
      if (next.resource_id?.trim()) queryParams.resource_id = next.resource_id.trim();
      if (next.actor_email?.trim()) queryParams.actor_email = next.actor_email.trim();
      if (next.created_from) queryParams.created_from = next.created_from;
      if (next.created_to) queryParams.created_to = next.created_to;
      if (next.tenant_id?.trim()) queryParams.tenant_id = next.tenant_id.trim();
      queryParams.offset = String(next.offset ?? 0);

      void router.replace({ pathname: router.pathname, query: queryParams }, undefined, {
        shallow: true,
        scroll: false,
      });
    },
    [router],
  );

  const applyFilters = useCallback(() => {
    setOffset(0);
    const nextFilters = {
      action: actionFilter.trim() || undefined,
      resource_type: resourceFilter.trim() || undefined,
      resource_id: resourceIdFilter.trim() || undefined,
      actor_email: actorFilter.trim() || undefined,
      created_from: toIsoDateTime(createdFromFilter),
      created_to: toIsoDateTime(createdToFilter),
      tenant_id: tenantFilter.trim() || undefined,
    };
    setAppliedFilters(nextFilters);
    replaceAuditQuery({
      action: actionFilter,
      resource_type: resourceFilter,
      resource_id: resourceIdFilter,
      actor_email: actorFilter,
      created_from: createdFromFilter,
      created_to: createdToFilter,
      tenant_id: tenantFilter,
      offset: 0,
    });
  }, [
    actionFilter,
    actorFilter,
    createdFromFilter,
    createdToFilter,
    replaceAuditQuery,
    resourceFilter,
    resourceIdFilter,
    tenantFilter,
  ]);

  const updateOffset = useCallback(
    (nextOffset: number) => {
      setOffset(nextOffset);
      if (!router.isReady) {
        return;
      }
      void router.replace(
        {
          pathname: router.pathname,
          query: { ...router.query, offset: String(nextOffset) },
        },
        undefined,
        { shallow: true, scroll: false },
      );
    },
    [router],
  );

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
                <FormField label="Action" htmlFor="audit-action-filter">
                  <Input
                    id="audit-action-filter"
                    name="action"
                    autoComplete="off"
                    value={actionFilter}
                    onChange={(event) => setActionFilter(event.target.value)}
                    placeholder="operation.started"
                  />
                </FormField>
                <FormField label="Resource type" htmlFor="audit-resource-type-filter">
                  <Input
                    id="audit-resource-type-filter"
                    name="resource_type"
                    autoComplete="off"
                    value={resourceFilter}
                    onChange={(event) => setResourceFilter(event.target.value)}
                    placeholder="operation"
                  />
                </FormField>
                <FormField label="Resource ID" htmlFor="audit-resource-id-filter">
                  <Input
                    id="audit-resource-id-filter"
                    name="resource_id"
                    autoComplete="off"
                    value={resourceIdFilter}
                    onChange={(event) => setResourceIdFilter(event.target.value)}
                    placeholder="Resource ID"
                  />
                </FormField>
                <FormField label="Actor email" htmlFor="audit-actor-filter">
                  <Input
                    id="audit-actor-filter"
                    name="actor_email"
                    type="email"
                    inputMode="email"
                    autoComplete="email"
                    value={actorFilter}
                    onChange={(event) => setActorFilter(event.target.value)}
                    placeholder="operator@example.com"
                  />
                </FormField>
                <FormField label="Created from" htmlFor="audit-created-from-filter">
                  <Input
                    id="audit-created-from-filter"
                    name="created_from"
                    type="datetime-local"
                    value={createdFromFilter}
                    onChange={(event) => setCreatedFromFilter(event.target.value)}
                  />
                </FormField>
                <FormField label="Created to" htmlFor="audit-created-to-filter">
                  <Input
                    id="audit-created-to-filter"
                    name="created_to"
                    type="datetime-local"
                    value={createdToFilter}
                    onChange={(event) => setCreatedToFilter(event.target.value)}
                  />
                </FormField>
                <FormField label="Tenant ID" htmlFor="audit-tenant-filter">
                  <Input
                    id="audit-tenant-filter"
                    name="tenant_id"
                    autoComplete="off"
                    value={tenantFilter}
                    onChange={(event) => setTenantFilter(event.target.value)}
                    placeholder="Tenant ID"
                  />
                </FormField>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Button onClick={applyFilters} disabled={loading}>
                  {loading ? (
                    <>
                      <Spinner size="xs" className="mr-2" />
                      Loading
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
                    replaceAuditQuery({ offset: 0 });
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
                  onClick={() => updateOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!canGoNext || loading}
                  onClick={() => updateOffset(offset + PAGE_SIZE)}
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
