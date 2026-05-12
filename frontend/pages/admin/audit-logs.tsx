import { useCallback, useEffect, useMemo, useReducer } from "react";
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

type AuditLogFilters = {
  action?: string;
  resource_type?: string;
  resource_id?: string;
  actor_email?: string;
  created_from?: string;
  created_to?: string;
  tenant_id?: string;
};

type AuditFilterDraft = {
  action: string;
  resourceType: string;
  resourceId: string;
  actorEmail: string;
  createdFrom: string;
  createdTo: string;
  tenantId: string;
};

type AuditLogsPageState = {
  entries: AuditLogEntry[];
  loading: boolean;
  error: string | null;
  draft: AuditFilterDraft;
  appliedFilters: AuditLogFilters;
  offset: number;
  totalCount: number;
};

type AuditLogsPageAction =
  | { type: "fetch-start" }
  | { type: "fetch-success"; entries: AuditLogEntry[]; totalCount: number }
  | { type: "fetch-error"; error: string }
  | { type: "sync-query"; draft: AuditFilterDraft; offset: number; appliedFilters: AuditLogFilters }
  | { type: "draft-field"; field: keyof AuditFilterDraft; value: string }
  | { type: "apply-filters"; appliedFilters: AuditLogFilters }
  | { type: "reset" }
  | { type: "offset"; offset: number };

const emptyAuditDraft: AuditFilterDraft = {
  action: "",
  resourceType: "",
  resourceId: "",
  actorEmail: "",
  createdFrom: "",
  createdTo: "",
  tenantId: "",
};

const initialAuditLogsPageState: AuditLogsPageState = {
  entries: [],
  loading: false,
  error: null,
  draft: emptyAuditDraft,
  appliedFilters: {},
  offset: 0,
  totalCount: 0,
};

function toAuditLogFilters(draft: AuditFilterDraft): AuditLogFilters {
  return {
    action: draft.action.trim() || undefined,
    resource_type: draft.resourceType.trim() || undefined,
    resource_id: draft.resourceId.trim() || undefined,
    actor_email: draft.actorEmail.trim() || undefined,
    created_from: toIsoDateTime(draft.createdFrom),
    created_to: toIsoDateTime(draft.createdTo),
    tenant_id: draft.tenantId.trim() || undefined,
  };
}

function auditLogsPageReducer(state: AuditLogsPageState, action: AuditLogsPageAction): AuditLogsPageState {
  switch (action.type) {
    case "fetch-start":
      return { ...state, loading: true, error: null };
    case "fetch-success":
      return { ...state, entries: action.entries, totalCount: action.totalCount, loading: false, error: null };
    case "fetch-error":
      return { ...state, loading: false, error: action.error };
    case "sync-query":
      return { ...state, draft: action.draft, offset: action.offset, appliedFilters: action.appliedFilters };
    case "draft-field":
      return { ...state, draft: { ...state.draft, [action.field]: action.value } };
    case "apply-filters":
      return { ...state, offset: 0, appliedFilters: action.appliedFilters };
    case "reset":
      return { ...state, draft: emptyAuditDraft, offset: 0, appliedFilters: {} };
    case "offset":
      return { ...state, offset: action.offset };
    default:
      return state;
  }
}

function AuditFiltersCard({
  draft,
  loading,
  offset,
  totalCount,
  onDraftFieldChange,
  onApply,
  onReset,
}: {
  draft: AuditFilterDraft;
  loading: boolean;
  offset: number;
  totalCount: number;
  onDraftFieldChange: (field: keyof AuditFilterDraft, value: string) => void;
  onApply: () => void;
  onReset: () => void;
}) {
  return (
    <Card className="border-border/60 bg-card/60 backdrop-blur-sm">
      <CardHeader>
        <CardTitle className="text-base">Filters</CardTitle>
        <CardDescription>Filter by actor, action, resource, or date range before drilling into metadata.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          <FormField label="Action" htmlFor="audit-action-filter">
            <Input
              id="audit-action-filter"
              name="action"
              autoComplete="off"
              value={draft.action}
              onChange={(event) => onDraftFieldChange("action", event.target.value)}
              placeholder="operation.started"
            />
          </FormField>
          <FormField label="Resource type" htmlFor="audit-resource-type-filter">
            <Input
              id="audit-resource-type-filter"
              name="resource_type"
              autoComplete="off"
              value={draft.resourceType}
              onChange={(event) => onDraftFieldChange("resourceType", event.target.value)}
              placeholder="operation"
            />
          </FormField>
          <FormField label="Resource ID" htmlFor="audit-resource-id-filter">
            <Input
              id="audit-resource-id-filter"
              name="resource_id"
              autoComplete="off"
              value={draft.resourceId}
              onChange={(event) => onDraftFieldChange("resourceId", event.target.value)}
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
              value={draft.actorEmail}
              onChange={(event) => onDraftFieldChange("actorEmail", event.target.value)}
              placeholder="operator@example.com"
            />
          </FormField>
          <FormField label="Created from" htmlFor="audit-created-from-filter">
            <Input
              id="audit-created-from-filter"
              name="created_from"
              type="datetime-local"
              value={draft.createdFrom}
              onChange={(event) => onDraftFieldChange("createdFrom", event.target.value)}
            />
          </FormField>
          <FormField label="Created to" htmlFor="audit-created-to-filter">
            <Input
              id="audit-created-to-filter"
              name="created_to"
              type="datetime-local"
              value={draft.createdTo}
              onChange={(event) => onDraftFieldChange("createdTo", event.target.value)}
            />
          </FormField>
          <FormField label="Tenant ID" htmlFor="audit-tenant-filter">
            <Input
              id="audit-tenant-filter"
              name="tenant_id"
              autoComplete="off"
              value={draft.tenantId}
              onChange={(event) => onDraftFieldChange("tenantId", event.target.value)}
              placeholder="Tenant ID"
            />
          </FormField>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button onClick={onApply} disabled={loading}>
            {loading ? (
              <>
                <Spinner size="xs" className="mr-2" />
                Loading
              </>
            ) : (
              "Apply filters"
            )}
          </Button>
          <Button variant="outline" onClick={onReset} disabled={loading}>
            Reset
          </Button>
          <div className="ml-auto text-xs text-muted-foreground">
            Showing {Math.min(offset + 1, totalCount)}-{Math.min(offset + PAGE_SIZE, totalCount)} of {totalCount}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function AuditLogsPage() {
  const router = useRouter();
  const { replace } = router;
  const [{ entries, loading, error, draft, appliedFilters, offset, totalCount }, dispatchAuditLogs] = useReducer(
    auditLogsPageReducer,
    initialAuditLogsPageState,
  );

  const filters = useMemo(
    () => ({
      ...appliedFilters,
      limit: PAGE_SIZE,
      offset,
    }),
    [appliedFilters, offset],
  );

  const fetchLogs = useCallback(async () => {
    dispatchAuditLogs({ type: "fetch-start" });
    try {
      const response = await auditLogsApi.list(filters);
      dispatchAuditLogs({
        type: "fetch-success",
        entries: response.data,
        totalCount: response.meta.pagination?.totalCount ?? response.data.length,
      });
    } catch (err: unknown) {
      dispatchAuditLogs({ type: "fetch-error", error: getApiErrorMessage(err, "Failed to load audit logs.") });
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
    const nextDraft = {
      action,
      resourceType,
      resourceId,
      actorEmail,
      createdFrom,
      createdTo,
      tenantId,
    };

    dispatchAuditLogs({
      type: "sync-query",
      draft: nextDraft,
      offset: nextOffset,
      appliedFilters: toAuditLogFilters(nextDraft),
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

      void replace({ pathname: router.pathname, query: queryParams }, undefined, {
        shallow: true,
        scroll: false,
      });
    },
    [router, replace],
  );

  const applyFilters = useCallback(() => {
    dispatchAuditLogs({ type: "apply-filters", appliedFilters: toAuditLogFilters(draft) });
    replaceAuditQuery({
      action: draft.action,
      resource_type: draft.resourceType,
      resource_id: draft.resourceId,
      actor_email: draft.actorEmail,
      created_from: draft.createdFrom,
      created_to: draft.createdTo,
      tenant_id: draft.tenantId,
      offset: 0,
    });
  }, [draft, replaceAuditQuery]);

  const updateOffset = useCallback(
    (nextOffset: number) => {
      dispatchAuditLogs({ type: "offset", offset: nextOffset });
      if (!router.isReady) {
        return;
      }
      void replace(
        {
          pathname: router.pathname,
          query: { ...router.query, offset: String(nextOffset) },
        },
        undefined,
        { shallow: true, scroll: false },
      );
    },
    [router, replace],
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

          <AuditFiltersCard
            draft={draft}
            loading={loading}
            offset={offset}
            totalCount={totalCount}
            onDraftFieldChange={(field, value) => dispatchAuditLogs({ type: "draft-field", field, value })}
            onApply={applyFilters}
            onReset={() => {
              dispatchAuditLogs({ type: "reset" });
              replaceAuditQuery({ offset: 0 });
            }}
          />

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
                            <UserRound className="size-3.5" aria-hidden="true" />
                            <span className="font-semibold">Actor</span>
                          </div>
                          <p className="mt-1">{entry.actor_email ?? "System"}</p>
                        </div>
                        <div className="rounded-xl border border-border/40 bg-muted/30 p-3">
                          <div className="flex items-center gap-2 text-foreground">
                            <CalendarRange className="size-3.5" aria-hidden="true" />
                            <span className="font-semibold">Tenant</span>
                          </div>
                          <p className="mt-1 font-mono">{entry.tenant_id}</p>
                        </div>
                        <div className="rounded-xl border border-border/40 bg-muted/30 p-3">
                          <div className="flex items-center gap-2 text-foreground">
                            <Filter className="size-3.5" aria-hidden="true" />
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
