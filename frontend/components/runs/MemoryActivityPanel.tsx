import { Badge, Card, CardContent, CardHeader, CardTitle, Separator } from "@/components/ui";
import type {
  MemoryObservationPreview,
  NodeMemoryActivity,
  NodeRunItem,
  RunDetail,
  RunMemoryActivitySummary,
  RunMemoryOperation,
} from "@/lib/api";

const OPERATION_LABELS: Record<string, string> = {
  save: "Saved observation",
  search: "Searched curated memory",
  context: "Built curated context",
  timeline: "Reviewed observation timeline",
  context_use: "Used curated memory",
};

const CATEGORY_STYLES: Record<string, string> = {
  save: "border-l-emerald-500/70 bg-emerald-500/5",
  retrieval: "border-l-sky-500/70 bg-sky-500/5",
  influence: "border-l-amber-500/70 bg-amber-500/5",
};

const CATEGORY_BADGES: Record<string, string> = {
  save: "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  retrieval: "border-sky-500/25 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  influence: "border-amber-500/25 bg-amber-500/10 text-amber-800 dark:text-amber-300",
};

const isObject = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

export const getNodeRunMemoryActivity = (nodeRun: NodeRunItem | null): NodeMemoryActivity | null => {
  if (!nodeRun || !isObject(nodeRun.memory_activity)) {
    return null;
  }
  return nodeRun.memory_activity as NodeMemoryActivity;
};

export const deriveRunMemoryActivity = (run: RunDetail | null): RunMemoryActivitySummary | null => {
  if (!run) {
    return null;
  }

  const operations: RunMemoryOperation[] = [];
  let saveNodeCount = 0;
  let savedObservationCount = 0;
  let retrievalNodeCount = 0;
  let retrievedObservationCount = 0;
  let influencedNodeCount = 0;
  let influencedObservationCount = 0;
  let degraded = false;

  for (const nodeRun of run.node_runs ?? []) {
    const activity = getNodeRunMemoryActivity(nodeRun);
    if (!activity) {
      continue;
    }

    const operation: RunMemoryOperation = {
      ...activity,
      node_id: nodeRun.node_id,
      node_type: nodeRun.node_type,
      status: nodeRun.status,
      attempt: nodeRun.attempt,
      duration_ms: nodeRun.duration_ms,
    };
    operations.push(operation);

    if (activity.category === "save") {
      saveNodeCount += 1;
      savedObservationCount += Number(activity.saved_observation_count ?? 0);
    } else if (activity.category === "retrieval") {
      retrievalNodeCount += 1;
      retrievedObservationCount += Number(activity.count ?? 0);
    } else if (activity.category === "influence") {
      influencedNodeCount += 1;
      influencedObservationCount += Number(activity.observation_count ?? 0);
    }

    degraded = degraded || Boolean(activity.degraded);
  }

  if (operations.length === 0) {
    if (run.memory_activity?.has_activity) {
      return run.memory_activity;
    }
    return null;
  }

  return {
    has_activity: true,
    save_node_count: saveNodeCount,
    saved_observation_count: savedObservationCount,
    retrieval_node_count: retrievalNodeCount,
    retrieved_observation_count: retrievedObservationCount,
    influenced_node_count: influencedNodeCount,
    influenced_observation_count: influencedObservationCount,
    degraded,
    operations,
  };
};

const getOperationLabel = (activity: Pick<NodeMemoryActivity, "operation" | "category">) => {
  const operation = String(activity.operation ?? "").trim();
  if (operation && operation in OPERATION_LABELS) {
    return OPERATION_LABELS[operation];
  }
  if (activity.category === "save") {
    return "Saved observation";
  }
  if (activity.category === "retrieval") {
    return "Retrieved curated memory";
  }
  if (activity.category === "influence") {
    return "Curated memory influenced execution";
  }
  return "Memory activity";
};

const getCategoryStyle = (category: string | undefined) => {
  if (!category) {
    return "border-l-border bg-muted/20";
  }
  return CATEGORY_STYLES[category] ?? "border-l-border bg-muted/20";
};

const getCategoryBadgeClass = (category: string | undefined) => {
  if (!category) {
    return "border-border/40 bg-muted/40 text-muted-foreground";
  }
  return CATEGORY_BADGES[category] ?? "border-border/40 bg-muted/40 text-muted-foreground";
};

const formatObservationLabel = (observation: MemoryObservationPreview) => {
  return observation.title || observation.type || observation.id || "Observation";
};

const formatOperationCount = (activity: NodeMemoryActivity) => {
  if (activity.category === "save") {
    return `${String(activity.saved_observation_count ?? 0)} saved`;
  }
  if (activity.category === "retrieval") {
    return `${String(activity.count ?? 0)} retrieved`;
  }
  if (activity.category === "influence") {
    return `${String(activity.observation_count ?? 0)} used`;
  }
  return null;
};

const getObservationItems = (activity: NodeMemoryActivity): MemoryObservationPreview[] => {
  const observations = Array.isArray(activity.observations) ? activity.observations : [];
  if (observations.length > 0) {
    return observations.slice(0, 3);
  }
  if (activity.observation && isObject(activity.observation)) {
    return [activity.observation as MemoryObservationPreview];
  }
  return [];
};

function ObservationPreviewList({ observations }: { observations: MemoryObservationPreview[] }) {
  if (observations.length === 0) {
    return null;
  }

  return (
    <div className="grid gap-2 md:grid-cols-2">
      {observations.map((observation, index) => (
        <div
          key={`${observation.id ?? observation.title ?? observation.content_preview ?? "observation"}-${index}`}
          className="rounded-lg border border-border/50 bg-background/70 p-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-foreground">{formatObservationLabel(observation)}</p>
            {observation.type ? (
              <Badge variant="outline" className="border-border/50 bg-muted/40 text-[11px] text-muted-foreground">
                {observation.type}
              </Badge>
            ) : null}
            {observation.scope ? (
              <Badge variant="outline" className="border-border/50 bg-muted/40 text-[11px] text-muted-foreground">
                {observation.scope}
              </Badge>
            ) : null}
          </div>
          {observation.topic_key ? (
            <p className="mt-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Topic {observation.topic_key}
            </p>
          ) : null}
          {observation.content_preview ? (
            <p className="mt-2 text-sm text-foreground/90 whitespace-pre-wrap">{observation.content_preview}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function MemoryActivityBody({ activity }: { activity: NodeMemoryActivity }) {
  const observations = getObservationItems(activity);
  const countLabel = formatOperationCount(activity);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className={getCategoryBadgeClass(activity.category)}>
          {getOperationLabel(activity)}
        </Badge>
        {countLabel ? (
          <Badge variant="outline" className="border-border/50 bg-background/70 text-muted-foreground">
            {countLabel}
          </Badge>
        ) : null}
        {activity.scope ? (
          <Badge variant="outline" className="border-border/50 bg-background/70 text-muted-foreground">
            {activity.scope}
          </Badge>
        ) : null}
        {activity.degraded ? (
          <Badge variant="outline" className="border-amber-500/25 bg-amber-500/10 text-amber-800 dark:text-amber-300">
            Degraded fallback
          </Badge>
        ) : null}
      </div>

      {activity.query ? (
        <div className="rounded-lg border border-border/50 bg-background/70 px-3 py-2">
          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Query</p>
          <p className="mt-1 text-sm text-foreground">{activity.query}</p>
        </div>
      ) : null}

      {Array.isArray(activity.strategies) && activity.strategies.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          {activity.strategies.map((strategy) => (
            <Badge
              key={strategy}
              variant="outline"
              className="border-border/50 bg-muted/30 text-[11px] uppercase tracking-[0.12em] text-muted-foreground"
            >
              {strategy}
            </Badge>
          ))}
        </div>
      ) : null}

      <ObservationPreviewList observations={observations} />

      {activity.category === "influence" &&
      Array.isArray(activity.curated_context_paths) &&
      activity.curated_context_paths.length > 0 ? (
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Context sources</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {activity.curated_context_paths.map((path) => (
              <Badge
                key={path}
                variant="outline"
                className="border-border/50 bg-background/70 font-mono text-[11px] text-muted-foreground"
              >
                {path}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

type RunMemoryActivityPanelProps = {
  summary: RunMemoryActivitySummary | null;
  getNodeLabel: (nodeId: string) => string;
  onSelectNode?: (nodeId: string, attempt: number) => void;
};

export function RunMemoryActivityPanel({ summary, getNodeLabel, onSelectNode }: RunMemoryActivityPanelProps) {
  if (!summary?.has_activity) {
    return null;
  }

  const operations = Array.isArray(summary.operations) ? summary.operations : [];

  return (
    <Card className="border-border/50 bg-[linear-gradient(135deg,rgba(244,247,240,0.92),rgba(235,245,245,0.82))] backdrop-blur-sm dark:bg-[linear-gradient(135deg,rgba(22,27,24,0.94),rgba(14,28,30,0.92))]">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-3">
          <span>Curated memory</span>
          {summary.degraded ? (
            <Badge variant="outline" className="border-amber-500/25 bg-amber-500/10 text-amber-800 dark:text-amber-300">
              Degraded retrieval seen
            </Badge>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-3 md:grid-cols-4">
          <div className="rounded-lg border border-border/50 bg-background/70 p-3">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Saved</p>
            <p className="mt-2 text-2xl font-semibold text-foreground">{summary.saved_observation_count}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {summary.save_node_count} department step{summary.save_node_count === 1 ? "" : "s"}
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-background/70 p-3">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Retrieved</p>
            <p className="mt-2 text-2xl font-semibold text-foreground">{summary.retrieved_observation_count}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {summary.retrieval_node_count} operation{summary.retrieval_node_count === 1 ? "" : "s"}
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-background/70 p-3">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Influenced</p>
            <p className="mt-2 text-2xl font-semibold text-foreground">{summary.influenced_observation_count}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {summary.influenced_node_count} department step{summary.influenced_node_count === 1 ? "" : "s"}
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-background/70 p-3">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Operations</p>
            <p className="mt-2 text-2xl font-semibold text-foreground">{operations.length}</p>
            <p className="mt-1 text-xs text-muted-foreground">save, retrieval, and influence events</p>
          </div>
        </div>

        {operations.length > 0 ? (
          <>
            <Separator />
            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                Operation memory timeline
              </p>
              <div className="space-y-3">
                {operations.map((operation) => {
                  const label = getNodeLabel(operation.node_id);
                  const cardBody = (
                    <div
                      className={`rounded-xl border border-border/50 border-l-4 p-4 ${getCategoryStyle(operation.category)}`}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-foreground">{getOperationLabel(operation)}</p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {label} · attempt {operation.attempt}
                            {typeof operation.duration_ms === "number" ? ` · ${operation.duration_ms}ms` : ""}
                          </p>
                        </div>
                        <div className="flex flex-wrap justify-end gap-2">
                          <Badge variant="outline" className={getCategoryBadgeClass(operation.category)}>
                            {operation.category ?? "memory"}
                          </Badge>
                          <Badge variant="outline" className="border-border/50 bg-background/70 text-muted-foreground">
                            {operation.status}
                          </Badge>
                        </div>
                      </div>
                      <div className="mt-3">
                        <MemoryActivityBody activity={operation} />
                      </div>
                    </div>
                  );

                  if (!onSelectNode) {
                    return <div key={`${operation.node_id}:${operation.attempt}`}>{cardBody}</div>;
                  }

                  return (
                    <button
                      key={`${operation.node_id}:${operation.attempt}`}
                      type="button"
                      onClick={() => onSelectNode(operation.node_id, operation.attempt)}
                      className="block w-full text-left"
                    >
                      {cardBody}
                    </button>
                  );
                })}
              </div>
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function NodeMemoryActivityPanel({ activity }: { activity: NodeMemoryActivity | null }) {
  if (!activity) {
    return null;
  }

  return (
    <div className={`rounded-xl border border-border/50 border-l-4 p-4 ${getCategoryStyle(activity.category)}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">Curated memory activity</p>
          <p className="mt-1 text-xs text-muted-foreground">This activity recorded explicit curated-memory behavior.</p>
        </div>
        <Badge variant="outline" className={getCategoryBadgeClass(activity.category)}>
          {getOperationLabel(activity)}
        </Badge>
      </div>
      <div className="mt-4">
        <MemoryActivityBody activity={activity} />
      </div>
    </div>
  );
}
