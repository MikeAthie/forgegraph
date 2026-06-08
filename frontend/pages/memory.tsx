import { useCallback, useEffect, useMemo, useReducer, useRef, type ReactNode } from "react";
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
const RELATIVE_TIME_FORMATTER = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

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

  if (Math.abs(hours) < 24) {
    return RELATIVE_TIME_FORMATTER.format(hours, "hour");
  }

  const days = Math.round(hours / 24);
  return RELATIVE_TIME_FORMATTER.format(days, "day");
};

type MemoryBrowserState = {
  queryDraft: string;
  query: string;
  scopeFilter: string;
  typeFilter: string;
  observations: MemoryObservationVM[];
  listLoading: boolean;
  listError: string | null;
  selectedObservationId: string | null;
  selectedObservation: MemoryObservationVM | null;
  detailLoading: boolean;
  detailError: string | null;
  governance: { current_role_capabilities: OrganizationRoleCapabilities } | null;
};

type MemoryBrowserAction =
  | { type: "list-start" }
  | { type: "list-success"; observations: MemoryObservationVM[]; requestedObservationId: string | null }
  | { type: "list-error"; error: string }
  | { type: "sync-query"; query: string; scopeFilter: string; typeFilter: string; observationId: string | null }
  | { type: "query-draft"; queryDraft: string }
  | { type: "query-search"; query: string }
  | { type: "scope-filter"; scopeFilter: string }
  | { type: "type-filter"; typeFilter: string }
  | { type: "select-observation"; observation: MemoryObservationVM }
  | { type: "detail-empty" }
  | { type: "detail-start" }
  | { type: "detail-success"; observation: MemoryObservationVM }
  | { type: "detail-error"; error: string }
  | { type: "governance-success"; governance: { current_role_capabilities: OrganizationRoleCapabilities } }
  | { type: "governance-error" };

const initialMemoryBrowserState: MemoryBrowserState = {
  queryDraft: "",
  query: "",
  scopeFilter: "all",
  typeFilter: "all",
  observations: [],
  listLoading: true,
  listError: null,
  selectedObservationId: null,
  selectedObservation: null,
  detailLoading: false,
  detailError: null,
  governance: null,
};

function selectObservationFromList(
  observations: MemoryObservationVM[],
  currentId: string | null,
  requestedId: string | null,
  currentObservation: MemoryObservationVM | null,
) {
  const selectedId =
    currentId && observations.some((observation) => observation.id === currentId)
      ? currentId
      : requestedId && observations.some((observation) => observation.id === requestedId)
        ? requestedId
        : (observations[0]?.id ?? null);

  const selectedObservation =
    currentObservation && observations.some((observation) => observation.id === currentObservation.id)
      ? currentObservation
      : requestedId
        ? (observations.find((observation) => observation.id === requestedId) ?? observations[0] ?? null)
        : (observations[0] ?? null);

  return { selectedId, selectedObservation };
}

function memoryBrowserReducer(state: MemoryBrowserState, action: MemoryBrowserAction): MemoryBrowserState {
  switch (action.type) {
    case "list-start":
      return { ...state, listLoading: true, listError: null };
    case "list-success": {
      const selection = selectObservationFromList(
        action.observations,
        state.selectedObservationId,
        action.requestedObservationId,
        state.selectedObservation,
      );
      return {
        ...state,
        observations: action.observations,
        selectedObservationId: selection.selectedId,
        selectedObservation: selection.selectedObservation,
        listLoading: false,
        listError: null,
      };
    }
    case "list-error":
      return {
        ...state,
        observations: [],
        selectedObservationId: null,
        selectedObservation: null,
        listLoading: false,
        listError: action.error,
      };
    case "sync-query":
      return {
        ...state,
        queryDraft: action.query,
        query: action.query.trim(),
        scopeFilter: action.scopeFilter,
        typeFilter: action.typeFilter,
        selectedObservationId: action.observationId,
      };
    case "query-draft":
      return { ...state, queryDraft: action.queryDraft };
    case "query-search":
      return { ...state, query: action.query };
    case "scope-filter":
      return { ...state, scopeFilter: action.scopeFilter };
    case "type-filter":
      return { ...state, typeFilter: action.typeFilter };
    case "select-observation":
      return {
        ...state,
        selectedObservation: action.observation,
        selectedObservationId: action.observation.id,
        detailError: null,
      };
    case "detail-empty":
      return { ...state, selectedObservation: null, detailError: null, detailLoading: false };
    case "detail-start":
      return { ...state, detailLoading: true, detailError: null };
    case "detail-success":
      return { ...state, selectedObservation: action.observation, detailLoading: false, detailError: null };
    case "detail-error":
      return { ...state, detailLoading: false, detailError: action.error };
    case "governance-success":
      return { ...state, governance: action.governance };
    case "governance-error":
      return { ...state, governance: null };
    default:
      return state;
  }
}

function MemoryPostureInspector({
  currentRole,
  canDeleteObservations,
  canManageRetention,
  canExportMemoryData,
}: {
  currentRole: string;
  canDeleteObservations: boolean;
  canManageRetention: boolean;
  canExportMemoryData: boolean;
}) {
  return (
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
  );
}

function MemoryMetricsGrid({
  observationsCount,
  modeLabel,
  visibleScopes,
  freshestSeenAt,
  currentRole,
  canManageRetention,
}: {
  observationsCount: number;
  modeLabel: string;
  visibleScopes: number;
  freshestSeenAt: string | null;
  currentRole: string;
  canManageRetention: boolean;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-4">
      <MetricCard
        eyebrow="Visible records"
        value={String(observationsCount)}
        delta={`In the current ${modeLabel.toLowerCase()}`}
        icon={<DatabaseZap className="size-4" />}
      />
      <MetricCard
        eyebrow="Scopes"
        value={String(visibleScopes)}
        delta="Company, operation, and session slices"
        icon={<BookCopy className="size-4" />}
      />
      <MetricCard
        eyebrow="Freshest signal"
        value={formatRelativeDate(freshestSeenAt)}
        delta="Based on last-seen timestamps"
        icon={<BrainCircuit className="size-4" />}
      />
      <MetricCard
        eyebrow="Governance"
        value={currentRole}
        delta={canManageRetention ? "Retention and export controls available" : "Review-only on governed controls"}
        tone={canManageRetention ? "emerald" : "amber"}
        icon={<ShieldCheck className="size-4" />}
      />
    </div>
  );
}

function MemoryAccessAlert({
  currentRole,
  canDeleteObservations,
  canManageRetention,
  canExportMemoryData,
}: {
  currentRole: string;
  canDeleteObservations: boolean;
  canManageRetention: boolean;
  canExportMemoryData: boolean;
}) {
  return (
    <Alert className="border-zinc-900/10 bg-white/70 text-zinc-800 dark:border-white/10 dark:bg-white/5 dark:text-zinc-100">
      <ShieldCheck className="size-4" />
      <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <p className="text-sm font-medium capitalize">{currentRole} memory access</p>
          <p className="text-sm">
            You can view curated observations.{" "}
            {canDeleteObservations ? "You can delete observations." : "You cannot delete observations."}{" "}
            {canManageRetention ? "You can manage retention." : "Retention changes are limited to owner and admin."}{" "}
            {canExportMemoryData ? "You can export memory reporting." : "Exports are limited to owner and admin."}
          </p>
        </div>
        <Link href="/settings" className="inline-flex items-center gap-1 text-sm font-medium">
          Open settings
        </Link>
      </AlertDescription>
    </Alert>
  );
}

function MemoryBrowserHeader() {
  return (
    <SectionHeader
      eyebrow="Memory inspection"
      title="Browse the knowledge layer"
      description="Move from raw traces to a governed ledger of observations. Search by content, filter by scope, and inspect how memory records evolved over time."
    />
  );
}

function MemoryLedgerPanels({
  availableTypes,
  detailError,
  detailLoading,
  listLoading,
  modeLabel,
  observations,
  queryDraft,
  scopeFilter,
  selectedObservation,
  selectedObservationId,
  typeFilter,
  onQueryDraftChange,
  onQuerySearch,
  onRefresh,
  onScopeChange,
  onSelectObservation,
  onTypeChange,
}: {
  availableTypes: string[];
  detailError: string | null;
  detailLoading: boolean;
  listLoading: boolean;
  modeLabel: string;
  observations: MemoryObservationVM[];
  queryDraft: string;
  scopeFilter: string;
  selectedObservation: MemoryObservationVM | null;
  selectedObservationId: string | null;
  typeFilter: string;
  onQueryDraftChange: (value: string) => void;
  onQuerySearch: (value: string) => void;
  onRefresh: () => void;
  onScopeChange: (value: string) => void;
  onSelectObservation: (observation: MemoryObservationVM) => void;
  onTypeChange: (value: string) => void;
}) {
  return (
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
          onQueryDraftChange={onQueryDraftChange}
          onQuerySearch={onQuerySearch}
          onRefresh={onRefresh}
          onScopeChange={onScopeChange}
          onSelectObservation={onSelectObservation}
          onTypeChange={onTypeChange}
        />
      </Panel>

      <Panel title="Observation detail" description="Deep inspection for the selected memory record.">
        <MemoryObservationDetailPanel error={detailError} loading={detailLoading} observation={selectedObservation} />
      </Panel>
    </div>
  );
}

function MemoryBrowserContent({
  availableTypes,
  canDeleteObservations,
  canExportMemoryData,
  canManageRetention,
  currentRole,
  detailError,
  detailLoading,
  freshestSeenAt,
  inspector,
  listError,
  listLoading,
  modeLabel,
  observations,
  queryDraft,
  scopeFilter,
  selectedObservation,
  selectedObservationId,
  typeFilter,
  visibleScopes,
  onQueryDraftChange,
  onQuerySearch,
  onRefresh,
  onScopeChange,
  onSelectObservation,
  onTypeChange,
}: {
  availableTypes: string[];
  canDeleteObservations: boolean;
  canExportMemoryData: boolean;
  canManageRetention: boolean;
  currentRole: string;
  detailError: string | null;
  detailLoading: boolean;
  freshestSeenAt: string | null;
  inspector: ReactNode;
  listError: string | null;
  listLoading: boolean;
  modeLabel: string;
  observations: MemoryObservationVM[];
  queryDraft: string;
  scopeFilter: string;
  selectedObservation: MemoryObservationVM | null;
  selectedObservationId: string | null;
  typeFilter: string;
  visibleScopes: number;
  onQueryDraftChange: (value: string) => void;
  onQuerySearch: (value: string) => void;
  onRefresh: () => void;
  onScopeChange: (value: string) => void;
  onSelectObservation: (observation: MemoryObservationVM) => void;
  onTypeChange: (value: string) => void;
}) {
  return (
    <ProtectedRoute>
      <DashboardLayout inspector={inspector}>
        <div className="space-y-6">
          <MemoryBrowserHeader />

          <MemoryMetricsGrid
            observationsCount={observations.length}
            modeLabel={modeLabel}
            visibleScopes={visibleScopes}
            freshestSeenAt={freshestSeenAt}
            currentRole={currentRole}
            canManageRetention={canManageRetention}
          />

          <MemoryAccessAlert
            currentRole={currentRole}
            canDeleteObservations={canDeleteObservations}
            canManageRetention={canManageRetention}
            canExportMemoryData={canExportMemoryData}
          />

          {listError ? (
            <Alert variant="destructive">
              <AlertDescription>{listError}</AlertDescription>
            </Alert>
          ) : null}

          <MemoryLedgerPanels
            availableTypes={availableTypes}
            detailError={detailError}
            detailLoading={detailLoading}
            listLoading={listLoading}
            modeLabel={modeLabel}
            observations={observations}
            queryDraft={queryDraft}
            scopeFilter={scopeFilter}
            selectedObservation={selectedObservation}
            selectedObservationId={selectedObservationId}
            typeFilter={typeFilter}
            onQueryDraftChange={onQueryDraftChange}
            onQuerySearch={onQuerySearch}
            onRefresh={onRefresh}
            onScopeChange={onScopeChange}
            onSelectObservation={onSelectObservation}
            onTypeChange={onTypeChange}
          />
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}

export default function MemoryBrowserPage() {
  const router = useRouter();
  const { replace } = router;
  const { user } = useAuth();
  const requestedObservationIdRef = useRef<string | null>(null);
  const [
    {
      queryDraft,
      query,
      scopeFilter,
      typeFilter,
      observations,
      listLoading,
      listError,
      selectedObservationId,
      selectedObservation,
      detailLoading,
      detailError,
      governance,
    },
    dispatchMemory,
  ] = useReducer(memoryBrowserReducer, initialMemoryBrowserState);

  const hasQuery = query.trim().length > 0;
  const hasTypeFilter = typeFilter !== "all";
  const activeScope = scopeFilter === "all" ? undefined : (scopeFilter as MemoryScopeVM);
  const activeType = hasTypeFilter ? typeFilter : undefined;
  const isSearchMode = hasQuery || hasTypeFilter;

  const refreshObservations = useCallback(async () => {
    dispatchMemory({ type: "list-start" });

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

      dispatchMemory({
        type: "list-success",
        observations: data,
        requestedObservationId: requestedObservationIdRef.current,
      });
    } catch (err: unknown) {
      dispatchMemory({ type: "list-error", error: translateProductError(err, "knowledge") });
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
    dispatchMemory({
      type: "sync-query",
      query: nextQuery,
      scopeFilter: nextScope,
      typeFilter: nextType,
      observationId: nextObservation,
    });
  }, [router.isReady, router.query.observation, router.query.q, router.query.scope, router.query.type]);

  useEffect(() => {
    let cancelled = false;

    const loadGovernance = async () => {
      try {
        const response = await organizationsApi.me();
        if (!cancelled) {
          dispatchMemory({
            type: "governance-success",
            governance: { current_role_capabilities: response.governance.current_role_capabilities },
          });
        }
      } catch {
        if (!cancelled) {
          dispatchMemory({ type: "governance-error" });
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
      dispatchMemory({ type: "detail-empty" });
      return;
    }

    let cancelled = false;

    const fetchDetail = async () => {
      dispatchMemory({ type: "detail-start" });

      try {
        const detail = await memoryRepository.get(selectedObservationId);
        if (!cancelled) {
          dispatchMemory({ type: "detail-success", observation: detail });
        }
      } catch (err: unknown) {
        if (!cancelled) {
          dispatchMemory({ type: "detail-error", error: translateProductError(err, "knowledge") });
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
    return Array.from(types).toSorted((left, right) => left.localeCompare(right));
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

      void replace({ pathname: router.pathname, query: queryParams }, undefined, {
        shallow: true,
        scroll: false,
      });
    },
    [query, replace, router, scopeFilter, selectedObservationId, typeFilter],
  );

  const handleQuerySearch = useCallback(
    (value: string) => {
      const normalized = value.trim();
      dispatchMemory({ type: "query-search", query: normalized });
      replaceMemoryQuery({ q: normalized });
    },
    [replaceMemoryQuery],
  );

  const handleSelectObservation = useCallback(
    (observation: MemoryObservationVM) => {
      requestedObservationIdRef.current = observation.id;
      dispatchMemory({ type: "select-observation", observation });
      replaceMemoryQuery({ observation: observation.id });
    },
    [replaceMemoryQuery],
  );

  const handleScopeChange = useCallback(
    (value: string) => {
      dispatchMemory({ type: "scope-filter", scopeFilter: value });
      replaceMemoryQuery({ scope: value });
    },
    [replaceMemoryQuery],
  );

  const handleTypeChange = useCallback(
    (value: string) => {
      dispatchMemory({ type: "type-filter", typeFilter: value });
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
  const inspector = useMemo(
    () => (
      <MemoryPostureInspector
        currentRole={currentRole}
        canDeleteObservations={canDeleteObservations}
        canManageRetention={canManageRetention}
        canExportMemoryData={canExportMemoryData}
      />
    ),
    [canDeleteObservations, canExportMemoryData, canManageRetention, currentRole],
  );

  return (
    <MemoryBrowserContent
      availableTypes={availableTypes}
      canDeleteObservations={canDeleteObservations}
      canExportMemoryData={canExportMemoryData}
      canManageRetention={canManageRetention}
      currentRole={currentRole}
      detailError={detailError}
      detailLoading={detailLoading}
      freshestSeenAt={freshestSeenAt}
      inspector={inspector}
      listError={listError}
      listLoading={listLoading}
      modeLabel={modeLabel}
      observations={observations}
      queryDraft={queryDraft}
      scopeFilter={scopeFilter}
      selectedObservation={selectedObservation}
      selectedObservationId={selectedObservationId}
      typeFilter={typeFilter}
      visibleScopes={visibleScopes}
      onQueryDraftChange={(value) => dispatchMemory({ type: "query-draft", queryDraft: value })}
      onQuerySearch={handleQuerySearch}
      onRefresh={() => void refreshObservations()}
      onScopeChange={handleScopeChange}
      onSelectObservation={handleSelectObservation}
      onTypeChange={handleTypeChange}
    />
  );
}
