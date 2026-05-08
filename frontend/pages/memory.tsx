import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import DashboardLayout from "@/components/DashboardLayout";
import ProtectedRoute from "@/components/ProtectedRoute";
import { useAuth } from "@/contexts/AuthContext";
import { MemoryObservationDetailPanel } from "@/components/memory/MemoryObservationDetailPanel";
import { MemoryObservationList } from "@/components/memory/MemoryObservationList";
import { InspectorPanel, MetricCard, Panel, SectionHeader, StatusBadge } from "@/components/os/operations-ui";
import { organizationsApi, type OrganizationRoleCapabilities } from "@/lib/api";
import { translateProductError } from "@/domain/errors";
import { memoryRepository } from "@/domain/repositories";
import type { MemoryObservationVM, MemoryScopeVM } from "@/domain/repositories/memoryRepository";
import { Alert, AlertDescription } from "@/components/ui";
import { BookCopy, BrainCircuit, DatabaseZap, ShieldCheck } from "lucide-react";

const RESULT_LIMIT = 24;

const isMemoryScopeQuery = (value: unknown): value is MemoryScopeVM =>
  value === "all" || value === "company" || value === "operation" || value === "session";

const formatRelativeDate = (value: string | null) => {
  if (!value) {
    return "No recent signal";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  const deltaMs = date.getTime() - Date.now();
  const hours = Math.round(deltaMs / 3_600_000);
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

  if (Math.abs(hours) < 24) {
    return formatter.format(hours, "hour");
  }

  const days = Math.round(hours / 24);
  return formatter.format(days, "day");
};

export default function MemoryBrowserPage() {
  const router = useRouter();
  const { user } = useAuth();
  const requestedObservationIdRef = useRef<string | null>(null);
  const [queryDraft, setQueryDraft] = useState("");
  const [query, setQuery] = useState("");
  const [scopeFilter, setScopeFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");

  const [observations, setObservations] = useState<MemoryObservationVM[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [selectedObservationId, setSelectedObservationId] = useState<string | null>(null);
  const [selectedObservation, setSelectedObservation] = useState<MemoryObservationVM | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [governance, setGovernance] = useState<{
    current_role_capabilities: OrganizationRoleCapabilities;
  } | null>(null);

  const hasQuery = query.trim().length > 0;
  const hasTypeFilter = typeFilter !== "all";
  const activeScope = scopeFilter === "all" ? undefined : (scopeFilter as MemoryScopeVM);
  const activeType = hasTypeFilter ? typeFilter : undefined;
  const isSearchMode = hasQuery || hasTypeFilter;

  const refreshObservations = useCallback(async () => {
    setListLoading(true);
    setListError(null);

    try {
      const data = isSearchMode
        ? await memoryRepository.search({
            query: hasQuery ? query.trim() : undefined,
            scope: activeScope,
            type: activeType,
            limit: RESULT_LIMIT,
          })
        : await memoryRepository.timeline({
            scope: activeScope,
            limit: RESULT_LIMIT,
          });

      setObservations(data);
      const requestedObservationId = requestedObservationIdRef.current;
      setSelectedObservationId((currentId) => {
        if (currentId && data.some((observation) => observation.id === currentId)) {
          return currentId;
        }
        if (requestedObservationId && data.some((observation) => observation.id === requestedObservationId)) {
          return requestedObservationId;
        }
        return data[0]?.id ?? null;
      });
      setSelectedObservation((currentObservation) => {
        if (currentObservation && data.some((observation) => observation.id === currentObservation.id)) {
          return currentObservation;
        }
        if (requestedObservationId) {
          const requestedObservation = data.find((observation) => observation.id === requestedObservationId);
          if (requestedObservation) {
            return requestedObservation;
          }
        }
        return data[0] ?? null;
      });
    } catch (err: unknown) {
      setObservations([]);
      setSelectedObservationId(null);
      setSelectedObservation(null);
      setListError(translateProductError(err, "knowledge"));
    } finally {
      setListLoading(false);
    }
  }, [activeScope, activeType, hasQuery, isSearchMode, query]);

  useEffect(() => {
    void refreshObservations();
  }, [refreshObservations]);

  useEffect(() => {
    if (!router.isReady) {
      return;
    }

    const nextQuery = typeof router.query.q === "string" ? router.query.q : "";
    const nextScope = isMemoryScopeQuery(router.query.scope) ? router.query.scope : "all";
    const nextType = typeof router.query.type === "string" && router.query.type ? router.query.type : "all";
    const nextObservation =
      typeof router.query.observation === "string" && router.query.observation ? router.query.observation : null;

    requestedObservationIdRef.current = nextObservation;
    setQueryDraft(nextQuery);
    setQuery(nextQuery.trim());
    setScopeFilter(nextScope);
    setTypeFilter(nextType);
    setSelectedObservationId(nextObservation);
  }, [router.isReady, router.query.observation, router.query.q, router.query.scope, router.query.type]);

  useEffect(() => {
    let cancelled = false;

    const loadGovernance = async () => {
      try {
        const response = await organizationsApi.me();
        if (!cancelled) {
          setGovernance({ current_role_capabilities: response.governance.current_role_capabilities });
        }
      } catch {
        if (!cancelled) {
          setGovernance(null);
        }
      }
    };

    void loadGovernance();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedObservationId) {
      setSelectedObservation(null);
      setDetailError(null);
      setDetailLoading(false);
      return;
    }

    let cancelled = false;

    const fetchDetail = async () => {
      setDetailLoading(true);
      setDetailError(null);

      try {
        const detail = await memoryRepository.get(selectedObservationId);
        if (!cancelled) {
          setSelectedObservation(detail);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setDetailError(translateProductError(err, "knowledge"));
        }
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
        }
      }
    };

    void fetchDetail();

    return () => {
      cancelled = true;
    };
  }, [selectedObservationId]);

  const availableTypes = useMemo(() => {
    const types = new Set<string>();
    for (const observation of observations) {
      if (observation.type) {
        types.add(observation.type);
      }
    }
    if (selectedObservation?.type) {
      types.add(selectedObservation.type);
    }
    return [...types].sort((left, right) => left.localeCompare(right));
  }, [observations, selectedObservation]);

  const visibleScopes = useMemo(
    () => new Set(observations.map((observation) => observation.scope)).size,
    [observations],
  );
  const freshestSeenAt = observations[0]?.lastSeenAt ?? selectedObservation?.lastSeenAt ?? null;

  const replaceMemoryQuery = useCallback(
    (next: { q?: string; scope?: string; type?: string; observation?: string | null }) => {
      if (!router.isReady) {
        return;
      }

      const queryParams = { ...router.query };
      delete queryParams.q;
      delete queryParams.scope;
      delete queryParams.type;
      delete queryParams.observation;

      const nextQuery = next.q ?? query;
      const nextScope = next.scope ?? scopeFilter;
      const nextType = next.type ?? typeFilter;
      const nextObservation =
        next.observation !== undefined
          ? next.observation
          : (selectedObservationId ?? requestedObservationIdRef.current);

      if (nextQuery.trim()) {
        queryParams.q = nextQuery.trim();
      }
      queryParams.scope = nextScope;
      if (nextType && nextType !== "all") {
        queryParams.type = nextType;
      }
      if (nextObservation) {
        queryParams.observation = nextObservation;
      }

      void router.replace({ pathname: router.pathname, query: queryParams }, undefined, {
        shallow: true,
        scroll: false,
      });
    },
    [query, router, scopeFilter, selectedObservationId, typeFilter],
  );

  const handleQuerySearch = useCallback(
    (value: string) => {
      const normalized = value.trim();
      setQuery((currentValue) => (currentValue === normalized ? currentValue : normalized));
      replaceMemoryQuery({ q: normalized });
    },
    [replaceMemoryQuery],
  );

  const handleSelectObservation = useCallback(
    (observation: MemoryObservationVM) => {
      requestedObservationIdRef.current = observation.id;
      setSelectedObservation(observation);
      setDetailError(null);
      setSelectedObservationId(observation.id);
      replaceMemoryQuery({ observation: observation.id });
    },
    [replaceMemoryQuery],
  );

  const handleScopeChange = useCallback(
    (value: string) => {
      setScopeFilter(value);
      replaceMemoryQuery({ scope: value });
    },
    [replaceMemoryQuery],
  );

  const handleTypeChange = useCallback(
    (value: string) => {
      setTypeFilter(value);
      replaceMemoryQuery({ type: value });
    },
    [replaceMemoryQuery],
  );

  const modeLabel = isSearchMode ? "Search results" : "Timeline";
  const currentRole = user?.organization_role ?? "member";
  const canDeleteObservations =
    governance?.current_role_capabilities.can_delete_observations ?? currentRole !== "viewer";
  const canManageRetention =
    governance?.current_role_capabilities.can_manage_retention ?? (currentRole === "owner" || currentRole === "admin");
  const canExportMemoryData =
    governance?.current_role_capabilities.can_export_memory_data ??
    (currentRole === "owner" || currentRole === "admin");

  return (
    <ProtectedRoute>
      <DashboardLayout
        inspector={
          <InspectorPanel
            title="Memory posture"
            subtitle="Memory is presented as an inspectable knowledge layer, not as hidden retrieval infrastructure."
            sections={[
              {
                title: "Current role",
                content: currentRole,
              },
              {
                title: "Capabilities",
                content: (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span>View records</span>
                      <StatusBadge status="active" label="Allowed" />
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Delete records</span>
                      <StatusBadge
                        status={canDeleteObservations ? "active" : "pending"}
                        label={canDeleteObservations ? "Allowed" : "Restricted"}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Retention</span>
                      <StatusBadge
                        status={canManageRetention ? "active" : "pending"}
                        label={canManageRetention ? "Manageable" : "Restricted"}
                      />
                    </div>
                  </div>
                ),
              },
              {
                title: "Export posture",
                content: canExportMemoryData
                  ? "Memory exports are available from governed surfaces."
                  : "Exports are restricted to owner and admin roles.",
              },
            ]}
          />
        }
      >
        <div className="space-y-6">
          <SectionHeader
            eyebrow="Memory inspection"
            title="Browse the knowledge layer"
            description="Move from raw traces to a governed ledger of observations. Search by content, filter by scope, and inspect how memory records evolved over time."
          />

          <div className="grid gap-4 xl:grid-cols-4">
            <MetricCard
              eyebrow="Visible records"
              value={String(observations.length)}
              delta={`In the current ${modeLabel.toLowerCase()}`}
              icon={<DatabaseZap className="h-4 w-4" />}
            />
            <MetricCard
              eyebrow="Scopes"
              value={String(visibleScopes)}
              delta="Company, operation, and session slices"
              icon={<BookCopy className="h-4 w-4" />}
            />
            <MetricCard
              eyebrow="Freshest signal"
              value={formatRelativeDate(freshestSeenAt)}
              delta="Based on last-seen timestamps"
              icon={<BrainCircuit className="h-4 w-4" />}
            />
            <MetricCard
              eyebrow="Governance"
              value={currentRole}
              delta={
                canManageRetention ? "Retention and export controls available" : "Review-only on governed controls"
              }
              tone={canManageRetention ? "emerald" : "amber"}
              icon={<ShieldCheck className="h-4 w-4" />}
            />
          </div>

          <Alert className="border-slate-900/10 bg-white/70 text-slate-800 dark:border-white/10 dark:bg-white/5 dark:text-slate-100">
            <ShieldCheck className="h-4 w-4" />
            <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="space-y-1">
                <p className="text-sm font-medium capitalize">{currentRole} memory access</p>
                <p className="text-sm">
                  You can view curated observations.{" "}
                  {canDeleteObservations ? "You can delete observations." : "You cannot delete observations."}{" "}
                  {canManageRetention
                    ? "You can manage retention."
                    : "Retention changes are limited to owner and admin."}{" "}
                  {canExportMemoryData ? "You can export memory reporting." : "Exports are limited to owner and admin."}
                </p>
              </div>
              <Link href="/settings" className="inline-flex items-center gap-1 text-sm font-medium">
                Open settings
              </Link>
            </AlertDescription>
          </Alert>

          {listError ? (
            <Alert variant="destructive">
              <AlertDescription>{listError}</AlertDescription>
            </Alert>
          ) : null}

          <div className="grid gap-6 xl:grid-cols-[1.02fr_0.98fr]">
            <Panel title="Observation ledger" description="Search and filter the records the system decided to keep.">
              <MemoryObservationList
                availableTypes={availableTypes}
                loading={listLoading}
                modeLabel={modeLabel}
                observations={observations}
                queryDraft={queryDraft}
                selectedObservationId={selectedObservationId}
                scopeFilter={scopeFilter}
                typeFilter={typeFilter}
                onQueryDraftChange={setQueryDraft}
                onQuerySearch={handleQuerySearch}
                onRefresh={() => void refreshObservations()}
                onScopeChange={handleScopeChange}
                onSelectObservation={handleSelectObservation}
                onTypeChange={handleTypeChange}
              />
            </Panel>

            <Panel title="Observation detail" description="Deep inspection for the selected memory record.">
              <MemoryObservationDetailPanel
                error={detailError}
                loading={detailLoading}
                observation={selectedObservation}
              />
            </Panel>
          </div>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
