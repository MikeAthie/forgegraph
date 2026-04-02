import type { MemoryObservation } from "@/lib/api";
import { EmptyBlock, StatusBadge, formatDateTime } from "@/components/os/operations-ui";
import { Button, SearchInput, Spinner } from "@/components/ui";
import { cn } from "@/lib/utils";

const SCOPE_OPTIONS = [
  { value: "all", label: "All scopes" },
  { value: "graph", label: "Workflow" },
  { value: "run", label: "Execution" },
  { value: "session", label: "Session" },
] as const;

const formatRelativeTime = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  const deltaMs = date.getTime() - Date.now();
  const minutes = Math.round(deltaMs / 60_000);
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

  if (Math.abs(minutes) < 60) {
    return formatter.format(minutes, "minute");
  }

  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) {
    return formatter.format(hours, "hour");
  }

  const days = Math.round(hours / 24);
  return formatter.format(days, "day");
};

const toLabelCase = (value: string) => {
  if (!value) {
    return "Untyped";
  }
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
};

const summarizeContent = (content: string) => {
  if (content.length <= 170) {
    return content;
  }
  return `${content.slice(0, 167)}...`;
};

interface MemoryObservationListProps {
  availableTypes: string[];
  loading: boolean;
  modeLabel: string;
  observations: MemoryObservation[];
  queryDraft: string;
  selectedObservationId: string | null;
  typeFilter: string;
  scopeFilter: string;
  onQueryDraftChange: (value: string) => void;
  onQuerySearch: (value: string) => void;
  onRefresh: () => void;
  onScopeChange: (value: string) => void;
  onSelectObservation: (observation: MemoryObservation) => void;
  onTypeChange: (value: string) => void;
}

export function MemoryObservationList({
  availableTypes,
  loading,
  modeLabel,
  observations,
  queryDraft,
  selectedObservationId,
  typeFilter,
  scopeFilter,
  onQueryDraftChange,
  onQuerySearch,
  onRefresh,
  onScopeChange,
  onSelectObservation,
  onTypeChange,
}: MemoryObservationListProps) {
  const showEmptyState = !loading && observations.length === 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">{modeLabel}</p>
          <h3 className="mt-2 text-lg font-semibold text-slate-950 dark:text-slate-50">Observation ledger</h3>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Search explicit memory records, skim recency, and pivot across workflow, execution, or session scopes.
          </p>
        </div>
        <Button variant="outline" className="rounded-full" onClick={onRefresh} disabled={loading}>
          {loading ? <Spinner size="xs" /> : "Refresh"}
        </Button>
      </div>

      <SearchInput
        value={queryDraft}
        onChange={onQueryDraftChange}
        onSearch={onQuerySearch}
        debounceMs={250}
        placeholder="Search title, content, or topic key"
        aria-label="Search observations"
        className="rounded-[1.2rem]"
      />

      <div className="flex flex-wrap gap-2">
        {SCOPE_OPTIONS.map((option) => (
          <Button
            key={option.value}
            type="button"
            size="sm"
            variant={scopeFilter === option.value ? "default" : "outline"}
            className="rounded-full"
            onClick={() => onScopeChange(option.value)}
          >
            {option.label}
          </Button>
        ))}
      </div>

      {availableTypes.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant={typeFilter === "all" ? "default" : "outline"}
            className="rounded-full"
            onClick={() => onTypeChange("all")}
          >
            All types
          </Button>
          {availableTypes.map((type) => (
            <Button
              key={type}
              type="button"
              size="sm"
              variant={typeFilter === type ? "default" : "outline"}
              className="rounded-full"
              onClick={() => onTypeChange(type)}
            >
              {toLabelCase(type)}
            </Button>
          ))}
        </div>
      ) : null}

      {loading ? (
        <div className="flex min-h-72 items-center justify-center gap-3 rounded-[1.4rem] border border-slate-900/8 bg-[var(--panel-muted)] dark:border-white/8">
          <Spinner size="md" />
          <span className="text-sm text-slate-500 dark:text-slate-400">Loading knowledge records...</span>
        </div>
      ) : null}

      {showEmptyState ? (
        <EmptyBlock
          title="No observations matched"
          description="Try a broader query or switch back to the timeline view."
        />
      ) : null}

      {!loading && observations.length > 0 ? (
        <div className="space-y-3">
          {observations.map((observation) => {
            const isActive = observation.id === selectedObservationId;
            return (
              <button
                key={observation.id}
                type="button"
                onClick={() => onSelectObservation(observation)}
                className={cn(
                  "w-full rounded-[1.25rem] border px-4 py-4 text-left transition-colors",
                  isActive
                    ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                    : "border-slate-900/8 bg-white hover:bg-[var(--panel-muted)] dark:border-white/8 dark:bg-white/4 dark:hover:bg-white/8",
                )}
              >
                <div className="flex flex-col gap-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-semibold">{observation.title || "Untitled observation"}</p>
                        <StatusBadge status="pending" label={toLabelCase(observation.scope)} />
                        <StatusBadge status={observation.is_deleted ? "failed" : "active"} label={toLabelCase(observation.type)} />
                      </div>
                      <p className={cn("mt-2 text-sm leading-6", isActive ? "text-white/80 dark:text-slate-700" : "text-slate-600 dark:text-slate-300")}>
                        {summarizeContent(observation.content)}
                      </p>
                    </div>
                    <p className={cn("text-xs", isActive ? "text-white/70 dark:text-slate-600" : "text-slate-500 dark:text-slate-400")}>
                      {formatRelativeTime(observation.last_seen_at)}
                    </p>
                  </div>

                  <div className={cn("flex flex-wrap gap-2 text-xs", isActive ? "text-white/70 dark:text-slate-600" : "text-slate-500 dark:text-slate-400")}>
                    {observation.topic_key ? <span>Topic {observation.topic_key}</span> : null}
                    {observation.tool_name ? <span>Tool {observation.tool_name}</span> : null}
                    <span>Recorded {formatDateTime(observation.created_at)}</span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
