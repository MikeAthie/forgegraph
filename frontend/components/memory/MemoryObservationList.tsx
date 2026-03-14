import type { MemoryObservation } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  SearchInput,
  Spinner,
} from "@/components/ui";
import { cn } from "@/lib/utils";

const SCOPE_OPTIONS = [
  { value: "all", label: "All scopes" },
  { value: "graph", label: "Graph" },
  { value: "run", label: "Run" },
  { value: "session", label: "Session" },
] as const;

const formatDateTime = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
};

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
  if (Math.abs(days) < 30) {
    return formatter.format(days, "day");
  }

  return date.toLocaleDateString();
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
  if (content.length <= 160) {
    return content;
  }
  return `${content.slice(0, 157)}...`;
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
    <Card className="border-border/50 bg-card/70 shadow-sm backdrop-blur-sm">
      <CardHeader className="gap-4 pb-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <Badge variant="outline" className="border-sky-500/30 text-sky-700 dark:text-sky-300">
              {modeLabel}
            </Badge>
            <CardTitle className="text-xl font-semibold tracking-tight">Observation ledger</CardTitle>
            <p className="max-w-xl text-sm text-muted-foreground">
              Search explicit memory records, inspect recency, and pivot across graph, run, or session scopes.
            </p>
          </div>
          <Button variant="outline" onClick={onRefresh} disabled={loading}>
            {loading ? <Spinner size="xs" /> : "Refresh"}
          </Button>
        </div>

        <SearchInput
          value={queryDraft}
          onChange={onQueryDraftChange}
          onSearch={onQuerySearch}
          debounceMs={250}
          placeholder="Search titles, content, or topic keys"
          aria-label="Search observations"
        />

        <div className="flex flex-wrap gap-2">
          {SCOPE_OPTIONS.map((option) => (
            <Button
              key={option.value}
              type="button"
              size="sm"
              variant={scopeFilter === option.value ? "secondary" : "outline"}
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
              variant={typeFilter === "all" ? "secondary" : "outline"}
              onClick={() => onTypeChange("all")}
            >
              All types
            </Button>
            {availableTypes.map((type) => (
              <Button
                key={type}
                type="button"
                size="sm"
                variant={typeFilter === type ? "secondary" : "outline"}
                onClick={() => onTypeChange(type)}
              >
                {toLabelCase(type)}
              </Button>
            ))}
          </div>
        ) : null}
      </CardHeader>

      <CardContent className="space-y-3">
        {loading ? (
          <div className="flex min-h-72 items-center justify-center gap-3 rounded-2xl border border-dashed border-border/60 bg-muted/20">
            <Spinner size="md" />
            <span className="text-sm text-muted-foreground">Loading curated memory…</span>
          </div>
        ) : null}

        {showEmptyState ? (
          <EmptyState
            title="No observations matched"
            description="Try a broader query or switch back to the default timeline view."
            className="min-h-72 rounded-2xl border border-dashed border-border/60 bg-muted/20"
          />
        ) : null}

        {!loading && observations.length > 0 ? (
          <div className="grid gap-3">
            {observations.map((observation) => {
              const isActive = observation.id === selectedObservationId;
              return (
                <button
                  key={observation.id}
                  type="button"
                  onClick={() => onSelectObservation(observation)}
                  className={cn(
                    "group w-full rounded-2xl border px-4 py-4 text-left transition-all",
                    "hover:border-sky-500/40 hover:bg-sky-500/5",
                    isActive ? "border-sky-500/40 bg-sky-500/10 shadow-sm" : "border-border/50 bg-background/70",
                  )}
                >
                  <div className="flex flex-col gap-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="space-y-1">
                        <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
                          {toLabelCase(observation.scope)}
                        </p>
                        <h3 className="text-base font-semibold text-foreground">
                          {observation.title || "Untitled observation"}
                        </h3>
                      </div>
                      <div className="flex flex-wrap justify-end gap-2">
                        <Badge variant="outline">{toLabelCase(observation.type)}</Badge>
                        {observation.is_deleted ? <Badge variant="destructive">Deleted</Badge> : null}
                      </div>
                    </div>

                    <p className="text-sm leading-6 text-muted-foreground">{summarizeContent(observation.content)}</p>

                    <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                      {observation.topic_key ? (
                        <span className="rounded-full border border-border/60 px-2 py-1">
                          Topic {observation.topic_key}
                        </span>
                      ) : null}
                      {observation.tool_name ? (
                        <span className="rounded-full border border-border/60 px-2 py-1">
                          Tool {observation.tool_name}
                        </span>
                      ) : null}
                      <span className="rounded-full border border-border/60 px-2 py-1">
                        Last seen {formatRelativeTime(observation.last_seen_at)}
                      </span>
                      <span className="rounded-full border border-border/60 px-2 py-1">
                        Recorded {formatDateTime(observation.created_at)}
                      </span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
