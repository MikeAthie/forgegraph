import { useCallback, useEffect, useMemo, useState } from "react";
import { BrainCircuit, DatabaseZap, Layers3 } from "lucide-react";

import DashboardLayout from "../components/DashboardLayout";
import ProtectedRoute from "../components/ProtectedRoute";
import { MemoryObservationDetailPanel } from "../components/memory/MemoryObservationDetailPanel";
import { MemoryObservationList } from "../components/memory/MemoryObservationList";
import {
  getApiErrorMessage,
  memoryApi,
  type MemoryObservation,
} from "../lib/api";
import { Alert, AlertDescription, Badge, Card, CardContent } from "@/components/ui";

const RESULT_LIMIT = 24;

const formatRelativeDate = (value: string | null) => {
  if (!value) {
    return "No observations yet";
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
  const [queryDraft, setQueryDraft] = useState("");
  const [query, setQuery] = useState("");
  const [scopeFilter, setScopeFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");

  const [observations, setObservations] = useState<MemoryObservation[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [selectedObservationId, setSelectedObservationId] = useState<string | null>(null);
  const [selectedObservation, setSelectedObservation] = useState<MemoryObservation | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const hasQuery = query.trim().length > 0;
  const hasTypeFilter = typeFilter !== "all";
  const activeScope = scopeFilter === "all" ? undefined : scopeFilter;
  const activeType = hasTypeFilter ? typeFilter : undefined;
  const isSearchMode = hasQuery || hasTypeFilter;

  const refreshObservations = useCallback(async () => {
    setListLoading(true);
    setListError(null);

    try {
      const data = isSearchMode
        ? await memoryApi.search({
            query: hasQuery ? query.trim() : undefined,
            scope: activeScope,
            type: activeType,
            limit: RESULT_LIMIT,
          })
        : await memoryApi.timeline({
            scope: activeScope,
            limit: RESULT_LIMIT,
          });

      setObservations(data);
      setSelectedObservationId((currentId) => {
        if (currentId && data.some((observation) => observation.id === currentId)) {
          return currentId;
        }
        return data[0]?.id ?? null;
      });
      setSelectedObservation((currentObservation) => {
        if (currentObservation && data.some((observation) => observation.id === currentObservation.id)) {
          return currentObservation;
        }
        return data[0] ?? null;
      });
    } catch (err: unknown) {
      setObservations([]);
      setSelectedObservationId(null);
      setSelectedObservation(null);
      setListError(getApiErrorMessage(err, "Failed to load curated memory."));
    } finally {
      setListLoading(false);
    }
  }, [activeScope, activeType, hasQuery, isSearchMode, query]);

  useEffect(() => {
    void refreshObservations();
  }, [refreshObservations]);

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
        const detail = await memoryApi.get(selectedObservationId);
        if (!cancelled) {
          setSelectedObservation(detail);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setDetailError(getApiErrorMessage(err, "Failed to load observation detail."));
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

  const visibleScopes = useMemo(() => {
    return new Set(observations.map((observation) => observation.scope)).size;
  }, [observations]);

  const freshestSeenAt = observations[0]?.last_seen_at ?? selectedObservation?.last_seen_at ?? null;

  const handleQuerySearch = useCallback((value: string) => {
    const normalized = value.trim();
    setQuery((currentValue) => {
      if (currentValue === normalized) {
        return currentValue;
      }
      return normalized;
    });
  }, []);

  const handleSelectObservation = useCallback((observation: MemoryObservation) => {
    setSelectedObservation(observation);
    setDetailError(null);
    setSelectedObservationId(observation.id);
  }, []);

  const handleScopeChange = useCallback((value: string) => {
    setScopeFilter(value);
  }, []);

  const handleTypeChange = useCallback((value: string) => {
    setTypeFilter(value);
  }, []);

  const modeLabel = isSearchMode ? "Search results" : "Timeline";

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <section className="relative overflow-hidden rounded-[2rem] border border-border/50 bg-card/80 p-6 shadow-lg backdrop-blur-sm sm:p-8">
            <div
              className="pointer-events-none absolute inset-0 opacity-90"
              style={{
                backgroundImage:
                  "radial-gradient(circle at 0% 0%, rgba(14, 165, 233, 0.2), transparent 38%), radial-gradient(circle at 85% 20%, rgba(245, 158, 11, 0.18), transparent 34%), linear-gradient(135deg, rgba(15, 23, 42, 0.06), rgba(255, 255, 255, 0))",
              }}
            />
            <div className="relative flex flex-col gap-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-3xl">
                  <Badge variant="outline" className="mb-4 border-sky-500/30 text-sky-700 dark:text-sky-300">
                    Curated Memory Browser
                  </Badge>
                  <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                    Browse what the system decided was worth keeping.
                  </h1>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground sm:text-base">
                    Move from raw run traces to a clean ledger of observations. Search by content, skim recent activity,
                    and inspect how each record evolved over time.
                  </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <Card className="border-border/50 bg-background/80">
                    <CardContent className="space-y-2 p-4">
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <DatabaseZap className="h-4 w-4" aria-hidden="true" />
                        <span className="text-xs uppercase tracking-[0.24em]">Visible</span>
                      </div>
                      <p className="text-2xl font-semibold text-foreground">{observations.length}</p>
                      <p className="text-xs text-muted-foreground">Records in the current {modeLabel.toLowerCase()}.</p>
                    </CardContent>
                  </Card>
                  <Card className="border-border/50 bg-background/80">
                    <CardContent className="space-y-2 p-4">
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <Layers3 className="h-4 w-4" aria-hidden="true" />
                        <span className="text-xs uppercase tracking-[0.24em]">Scopes</span>
                      </div>
                      <p className="text-2xl font-semibold text-foreground">{visibleScopes}</p>
                      <p className="text-xs text-muted-foreground">Graph, run, and session slices currently visible.</p>
                    </CardContent>
                  </Card>
                  <Card className="border-border/50 bg-background/80">
                    <CardContent className="space-y-2 p-4">
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <BrainCircuit className="h-4 w-4" aria-hidden="true" />
                        <span className="text-xs uppercase tracking-[0.24em]">Freshest signal</span>
                      </div>
                      <p className="text-base font-semibold text-foreground">{formatRelativeDate(freshestSeenAt)}</p>
                      <p className="text-xs text-muted-foreground">Based on the latest observation in view.</p>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </div>
          </section>

          {listError ? (
            <Alert variant="destructive">
              <AlertDescription>{listError}</AlertDescription>
            </Alert>
          ) : null}

          <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
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

            <MemoryObservationDetailPanel
              error={detailError}
              loading={detailLoading}
              observation={selectedObservation}
            />
          </div>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
