import { useCallback, useEffect, useMemo, useReducer, type SetStateAction } from "react";
import {
  BookCheck,
  ClipboardCheck,
  FileStack,
  GitBranch,
  CalendarClock,
  Play,
  ListChecks,
  PackagePlus,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Wrench,
} from "lucide-react";

import { EmptyBlock, MicroExplanation, Panel, StatusBadge, formatDateTime } from "@/components/os/operations-ui";
import {
  Alert,
  AlertDescription,
  Button,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
  Textarea,
} from "@/components/ui";
import { operatingModelRepository } from "@/domain/repositories";
import { translateProductError } from "@/domain/errors";
import type {
  AssertionKindVM,
  AssertionRecordVM,
  CapabilityModuleVM,
  CompanyOperatingModelVM,
  CompanyProgramVM,
  EvaluationRunVM,
  ArtifactLineageVM,
  MetricSnapshotVM,
  OperatingModelPackVM,
  OperationTemplateVM,
  PeriodicReviewVM,
  PolicyEvaluationVM,
  ProgramOperationVM,
  ReportRunVM,
  ReworkPlanVM,
  StageOutputGenerationVM,
  StateProjectionVM,
  ToolExecutionReceiptVM,
  ValidationPacketVM,
  WorkArtifactVM,
} from "@/lib/operating-model-packs";
import { showError, showSuccess } from "@/lib/toast";

type OperatingModelWorkspaceProps = {
  companyId: string;
  companyName: string;
};

type OperatingModelWorkspaceState = {
  packs: OperatingModelPackVM[];
  model: CompanyOperatingModelVM | null;
  programs: CompanyProgramVM[];
  assertions: AssertionRecordVM[];
  artifacts: WorkArtifactVM[];
  projections: StateProjectionVM[];
  serviceHistoryProjections: StateProjectionVM[];
  periodicReviews: PeriodicReviewVM[];
  metricPeriods: MetricSnapshotVM[];
  reportRuns: ReportRunVM[];
  evaluation: EvaluationRunVM | null;
  policyEvaluation: PolicyEvaluationVM | null;
  validationPacket: ValidationPacketVM | null;
  reworkPlan: ReworkPlanVM | null;
  artifactLineage: ArtifactLineageVM | null;
  launchedOperation: ProgramOperationVM | null;
  packageReceipt: ToolExecutionReceiptVM | null;
  stageOutput: StageOutputGenerationVM | null;
  selectedModuleId: string;
  selectedProgramId: string;
  selectedArtifactId: string;
  loading: boolean;
  busyAction: string | null;
  error: string | null;
  programTitle: string;
  programObjective: string;
  assertionKind: AssertionKindVM["kind"];
  assertionCategory: string;
  assertionStatement: string;
  assertionSource: string;
  artifactType: string;
  artifactTitle: string;
  artifactContent: string;
  evaluationProfileId: string;
  evaluationContent: string;
  evaluationInputs: string;
  metricPeriodInputs: string;
  policyActionType: string;
  policyBudget: string;
  revisionContent: string;
};

type OperatingModelWorkspaceAction =
  | { type: "patch"; patch: Partial<OperatingModelWorkspaceState> }
  | { type: "setField"; key: keyof OperatingModelWorkspaceState; value: unknown };

const initialOperatingModelWorkspaceState: OperatingModelWorkspaceState = {
  packs: [],
  model: null,
  programs: [],
  assertions: [],
  artifacts: [],
  projections: [],
  serviceHistoryProjections: [],
  periodicReviews: [],
  metricPeriods: [],
  reportRuns: [],
  evaluation: null,
  policyEvaluation: null,
  validationPacket: null,
  reworkPlan: null,
  artifactLineage: null,
  launchedOperation: null,
  packageReceipt: null,
  stageOutput: null,
  selectedModuleId: "",
  selectedProgramId: "",
  selectedArtifactId: "",
  loading: true,
  busyAction: null,
  error: null,
  programTitle: "",
  programObjective: "",
  assertionKind: "FACT",
  assertionCategory: "",
  assertionStatement: "",
  assertionSource: "",
  artifactType: "",
  artifactTitle: "",
  artifactContent: "",
  evaluationProfileId: "",
  evaluationContent: "",
  evaluationInputs: "",
  metricPeriodInputs: "",
  policyActionType: "",
  policyBudget: "0",
  revisionContent: "",
};

function resolveStateAction<T>(value: SetStateAction<T>, current: T): T {
  return typeof value === "function" ? (value as (currentValue: T) => T)(current) : value;
}

function operatingModelWorkspaceReducer(
  state: OperatingModelWorkspaceState,
  action: OperatingModelWorkspaceAction,
): OperatingModelWorkspaceState {
  if (action.type === "patch") {
    return { ...state, ...action.patch };
  }

  return {
    ...state,
    [action.key]: resolveStateAction(
      action.value as SetStateAction<OperatingModelWorkspaceState[typeof action.key]>,
      state[action.key],
    ),
  };
}

const fallbackAssertionKinds: AssertionKindVM[] = [
  { kind: "FACT", label: "Fact" },
  { kind: "OPINION", label: "Opinion" },
  { kind: "ASSUMPTION", label: "Assumption" },
  { kind: "QUESTION", label: "Question" },
];

function firstInstalledPack(
  packs: OperatingModelPackVM[],
  model: CompanyOperatingModelVM | null,
): OperatingModelPackVM | null {
  const installedIds = new Set((model?.installedPacks ?? []).map((pack) => pack.id));
  return packs.find((pack) => installedIds.has(pack.id)) ?? packs[0] ?? null;
}

function titleFromTemplate(template: string, companyName: string, fallback: string) {
  const rendered = template.replaceAll("{{ company_name }}", companyName).trim();
  return rendered || fallback;
}

function compactJson(value: Record<string, unknown>) {
  return Object.keys(value).length ? JSON.stringify(value, null, 2) : "No structured state yet.";
}

function parseJsonInput(value: string): Record<string, unknown> {
  if (!value.trim()) {
    return {};
  }
  const parsed = JSON.parse(value) as unknown;
  return recordValue(parsed);
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function stringListValue(value: unknown): string[] {
  return Array.isArray(value) ? value.flatMap((item) => {
    const text = String(item);
    return text ? [text] : [];
  }) : [];
}

function labelFromSchemaId(value: string) {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function expectedOutputLabels(stageState: Record<string, unknown>) {
  const template = recordValue(stageState.template);
  const direct = stringListValue(template.expected_artifact_schema_ids);
  const families = Array.isArray(template.channel_families)
    ? template.channel_families.flatMap((family) => stringListValue(recordValue(family).artifact_schema_ids))
    : [];
  return [...direct, ...families].slice(0, 8).map(labelFromSchemaId);
}

function hasStageOutputs(stageState: Record<string, unknown>) {
  const template = recordValue(stageState.template);
  return Boolean(template.expected_artifact_schema_ids || template.channel_families || template.signal_taxonomy_id);
}

function PackServiceModelPanel({ pack }: { pack: OperatingModelPackVM }) {
  if (!pack.serviceSections.length) {
    return null;
  }
  return (
    <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
          <BookCheck className="size-4" />
          <p className="text-sm font-semibold">Service Model</p>
        </div>
        <StatusBadge status="available" label={`${pack.serviceSections.length}`} />
      </div>
      <div className="mt-3 space-y-2">
        {pack.serviceSections.map((section) => (
          <div
            key={section.id}
            className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5"
          >
            <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{section.label}</p>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-zinc-500 dark:text-zinc-400">
              {section.description}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {section.items.slice(0, 4).map((item) => (
                <span
                  key={item}
                  className="rounded-full border border-zinc-900/10 bg-white px-2.5 py-1 text-[11px] text-zinc-600 dark:border-white/10 dark:bg-white/6 dark:text-zinc-300"
                >
                  {item}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ScorecardPanel({ evaluation }: { evaluation: EvaluationRunVM | null }) {
  if (!evaluation?.scorecard?.metrics.length) {
    return null;
  }
  return (
    <div className="mt-3 rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Scorecard</p>
        <StatusBadge status={evaluation.status} label={`${evaluation.scorecard.compositeScore}`} />
      </div>
      <div className="mt-3 space-y-2">
        {evaluation.scorecard.metrics.slice(0, 6).map((metric) => (
          <div key={metric.metricId} className="flex items-center justify-between gap-3 text-xs">
            <span className="min-w-0 truncate text-zinc-600 dark:text-zinc-300">
              {metric.label}
              {metric.trend.movement && metric.trend.movement !== "new" ? (
                <span className="ml-2 text-[11px] text-zinc-400">
                  {metric.trend.movement}
                  {metric.trend.numericDelta == null ? "" : ` (${metric.trend.numericDelta})`}
                </span>
              ) : null}
            </span>
            <StatusBadge status={metric.level} label={metric.levelLabel} />
          </div>
        ))}
      </div>
    </div>
  );
}

function RecommendedOperationsPanel({
  evaluation,
  operationTemplates,
  onLaunch,
}: {
  evaluation: EvaluationRunVM | null;
  operationTemplates: OperationTemplateVM[];
  onLaunch?: (operation: OperationTemplateVM, reason: string) => void;
}) {
  const operationsById = new Map(operationTemplates.map((operation) => [operation.id, operation]));
  const recommended =
    evaluation?.scorecard?.metrics.flatMap((metric) =>
      metric.recommendedOperationIds.map((operationId) => ({
        operationId,
        reason: `${metric.label}: ${metric.levelLabel}`,
      })),
    ) ??
    evaluation?.recommendedOperationIds.map((operationId) => ({ operationId, reason: "Recommended" })) ??
    [];
  const deduped = recommended.filter(
    (item, index) => recommended.findIndex((candidate) => candidate.operationId === item.operationId) === index,
  );
  if (!deduped.length) {
    return null;
  }
  return (
    <div className="mt-3 rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
      <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Recommended Operations</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {deduped.slice(0, 6).map(({ operationId, reason }) => {
          const operation = operationsById.get(operationId);
          return (
            <Button
              key={operationId}
              type="button"
              variant="outline"
              size="sm"
              onClick={() => operation && onLaunch?.(operation, reason)}
              disabled={!operation || !onLaunch}
              title={reason}
            >
              <Play className="size-3.5" />
              {operation?.label ?? operationId}
            </Button>
          );
        })}
      </div>
    </div>
  );
}

function PeriodicReviewsPanel({
  reviews,
  metricPeriods,
  reportRuns,
  onStart,
}: {
  reviews: PeriodicReviewVM[];
  metricPeriods: MetricSnapshotVM[];
  reportRuns: ReportRunVM[];
  onStart: (review: PeriodicReviewVM, metricPeriod: MetricSnapshotVM) => void;
}) {
  if (!reviews.length) {
    return null;
  }
  return (
    <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
          <CalendarClock className="size-4" />
          <p className="text-sm font-semibold">Periodic Reviews</p>
        </div>
        <StatusBadge status="active" label={`${reviews.length}`} />
      </div>
      <div className="mt-3 space-y-2">
        {reviews.map((review) => {
          const latestMetricPeriod = metricPeriods.find((item) => item.reviewDefinitionId === review.id);
          const latestReport = reportRuns.find((item) => item.reviewDefinitionId === review.id);
          return (
            <div
              key={review.id}
              className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{review.label}</p>
                  <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                    {review.cadence} · {review.evaluationProfileId}
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={!latestMetricPeriod}
                  onClick={() => latestMetricPeriod && onStart(review, latestMetricPeriod)}
                >
                  <ListChecks className="size-3.5" />
                  Start Review
                </Button>
              </div>
              {latestMetricPeriod ? (
                <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                  Metric period {latestMetricPeriod.periodStart} to {latestMetricPeriod.periodEnd} ·{" "}
                  {Object.keys(latestMetricPeriod.metricValues).length} metrics
                </p>
              ) : null}
              {latestReport?.artifact ? (
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  Latest report: {latestReport.artifact.title}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ServiceHistoryPanel({ projection }: { projection: StateProjectionVM | null }) {
  if (!projection) {
    return null;
  }
  const artifacts = Array.isArray(projection.state.service_artifacts)
    ? projection.state.service_artifacts.slice(0, 5)
    : [];
  const nextActions = Array.isArray(projection.state.next_actions) ? projection.state.next_actions.slice(0, 5) : [];
  return (
    <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
          <FileStack className="size-4" />
          <p className="text-sm font-semibold">{projection.label}</p>
        </div>
        <StatusBadge status="active" label={`${artifacts.length} refs`} />
      </div>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zinc-700 dark:text-zinc-200">
        {projection.markdownSummary || compactJson(projection.state)}
      </p>
      {nextActions.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {nextActions.map((action) => {
            const item = recordValue(action);
            const label = String(item.operation_template_id || item.reason || "Next action");
            return (
              <span
                key={label}
                className="rounded-full border border-zinc-900/10 bg-white px-2.5 py-1 text-xs text-zinc-600 dark:border-white/10 dark:bg-white/6 dark:text-zinc-300"
              >
                {label}
              </span>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function PackSummary({
  pack,
  installed,
  installing,
  onInstall,
}: {
  pack: OperatingModelPackVM;
  installed: boolean;
  installing: boolean;
  onInstall: () => void;
}) {
  return (
    <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{pack.name}</p>
            <StatusBadge status={installed ? "active" : "available"} label={installed ? "Installed" : "Available"} />
          </div>
          <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{pack.description}</p>
          <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
            {pack.companyTypeLabel} · v{pack.version}
          </p>
        </div>
        <Button size="sm" className="rounded-full" onClick={onInstall} disabled={installed || installing}>
          {installing ? <Spinner size="xs" className="mr-2" /> : <PackagePlus className="size-4" />}
          {installed ? "Installed" : "Install"}
        </Button>
      </div>
    </div>
  );
}

function ProgramTimeline({
  program,
  operationTemplates,
  modules,
  selectedModuleId,
  busyAction,
  stageOutput,
  onSelectModule,
  onAdvanceStage,
  onLaunchOperation,
  onGenerateOutputs,
}: {
  program: CompanyProgramVM;
  operationTemplates: OperationTemplateVM[];
  modules: CapabilityModuleVM[];
  selectedModuleId: string;
  busyAction: string | null;
  stageOutput: StageOutputGenerationVM | null;
  onSelectModule: (moduleId: string) => void;
  onAdvanceStage: (stageId: string, status: string) => void;
  onLaunchOperation: (stageId: string, operationTemplateId: string) => void;
  onGenerateOutputs: (stageId: string) => void;
}) {
  const operationsById = new Map(operationTemplates.map((operation) => [operation.id, operation]));
  const selectedModule = modules.find((module) => module.id === selectedModuleId) ?? null;
  const selectedOperationIds = new Set(selectedModule?.operationTemplateIds ?? []);
  if (!program.stages.length) {
    return <EmptyBlock title="No stages recorded" description="The selected program does not have stage state yet." />;
  }

  return (
    <div className="space-y-3">
      {modules.length ? (
        <Select
          value={selectedModuleId || "all"}
          onValueChange={(value) => onSelectModule(value === "all" ? "" : value)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Capability module" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All modules</SelectItem>
            {modules.map((module) => (
              <SelectItem key={module.id} value={module.id}>
                {module.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : null}
      {program.stages.map((stage, index) => (
        <div key={stage.id} className="grid grid-cols-[1rem_1fr] gap-3">
          <div className="flex flex-col items-center pt-1">
            <span className="size-2.5 rounded-full bg-zinc-400 dark:bg-zinc-500" />
            {index < program.stages.length - 1 ? (
              <span className="mt-2 h-full w-px bg-zinc-900/10 dark:bg-white/10" />
            ) : null}
          </div>
          <div className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{stage.label}</p>
              <StatusBadge status={stage.status} label={stage.status.replaceAll("_", " ")} />
            </div>
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">Stage {stage.sequence}</p>
            {expectedOutputLabels(stage.state).length ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {expectedOutputLabels(stage.state)
                  .slice(0, 4)
                  .map((label) => (
                    <span
                      key={label}
                      className="rounded-full border border-zinc-900/10 bg-white px-2.5 py-1 text-[11px] text-zinc-600 dark:border-white/10 dark:bg-white/6 dark:text-zinc-300"
                    >
                      {label}
                    </span>
                  ))}
              </div>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2">
              {hasStageOutputs(stage.state) ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 rounded-full px-3 text-xs"
                  disabled={busyAction === `outputs:${stage.stageId}`}
                  onClick={() => onGenerateOutputs(stage.stageId)}
                >
                  <FileStack className="size-3.5" />
                  Generate outputs
                </Button>
              ) : null}
              <Button
                size="sm"
                variant="outline"
                className="h-8 rounded-full px-3 text-xs"
                disabled={busyAction === `stage:${stage.stageId}:awaiting_validation`}
                onClick={() => onAdvanceStage(stage.stageId, "awaiting_validation")}
              >
                Await validation
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-8 rounded-full px-3 text-xs"
                disabled={busyAction === `stage:${stage.stageId}:completed`}
                onClick={() => onAdvanceStage(stage.stageId, "completed")}
              >
                Complete
              </Button>
            </div>
            {stage.operationTemplateIds.length ? (
              <div className="mt-3 space-y-2">
                {stage.operationTemplateIds
                  .flatMap((operationId) => {
                    const operation = operationsById.get(operationId);
                    if (!operation) {
                      return [];
                    }
                    if (!selectedModule) {
                      return [operation];
                    }
                    return selectedOperationIds.has(operation.id) || operation.moduleIds.includes(selectedModule.id)
                      ? [operation]
                      : [];
                  })
                  .slice(0, 3)
                  .map((operation) => (
                    <div
                      key={operation.id}
                      className="flex items-center justify-between gap-2 rounded-[0.8rem] border border-zinc-900/8 bg-zinc-50 px-2.5 py-2 dark:border-white/8 dark:bg-white/5"
                    >
                      <span className="min-w-0 truncate text-xs font-medium text-zinc-700 dark:text-zinc-200">
                        {operation.label}
                      </span>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7 shrink-0"
                        aria-label={`Launch ${operation.label}`}
                        disabled={busyAction === `operation:${stage.stageId}:${operation.id}`}
                        onClick={() => onLaunchOperation(stage.stageId, operation.id)}
                      >
                        <Play className="size-3.5" />
                      </Button>
                    </div>
                  ))}
              </div>
            ) : null}
            {stageOutput?.stageId === stage.stageId ? (
              <div className="mt-3 rounded-[0.8rem] border border-zinc-900/8 bg-zinc-50 px-2.5 py-2 dark:border-white/8 dark:bg-white/5">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={stageOutput.status} label={stageOutput.status.replaceAll("_", " ")} />
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    {stageOutput.createdArtifacts.length} outputs · {stageOutput.signalCount} signals
                  </span>
                </div>
                {stageOutput.blockers.length ? (
                  <p className="mt-2 text-xs leading-5 text-amber-700 dark:text-amber-300">
                    {String(stageOutput.blockers[0]?.message ?? "Output generation is blocked.")}
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

export function OperatingModelWorkspace({ companyId, companyName }: OperatingModelWorkspaceProps) {
  const [workspaceState, dispatchWorkspaceState] = useReducer(
    operatingModelWorkspaceReducer,
    initialOperatingModelWorkspaceState,
  );
  const {
    packs,
    model,
    programs,
    assertions,
    artifacts,
    projections,
    serviceHistoryProjections,
    periodicReviews,
    metricPeriods,
    reportRuns,
    evaluation,
    policyEvaluation,
    validationPacket,
    reworkPlan,
    artifactLineage,
    launchedOperation,
    packageReceipt,
    stageOutput,
    selectedModuleId,
    selectedProgramId,
    selectedArtifactId,
    loading,
    busyAction,
    error,
    programTitle,
    programObjective,
    assertionKind,
    assertionCategory,
    assertionStatement,
    assertionSource,
    artifactType,
    artifactTitle,
    artifactContent,
    evaluationProfileId,
    evaluationContent,
    evaluationInputs,
    metricPeriodInputs,
    policyActionType,
    policyBudget,
    revisionContent,
  } = workspaceState;

  const setField = <K extends keyof OperatingModelWorkspaceState>(
    key: K,
    value: SetStateAction<OperatingModelWorkspaceState[K]>,
  ) => dispatchWorkspaceState({ type: "setField", key, value });
  const setPrograms = (value: SetStateAction<CompanyProgramVM[]>) => setField("programs", value);
  const setEvaluation = (value: SetStateAction<EvaluationRunVM | null>) => setField("evaluation", value);
  const setPolicyEvaluation = (value: SetStateAction<PolicyEvaluationVM | null>) => setField("policyEvaluation", value);
  const setValidationPacket = (value: SetStateAction<ValidationPacketVM | null>) => setField("validationPacket", value);
  const setReworkPlan = (value: SetStateAction<ReworkPlanVM | null>) => setField("reworkPlan", value);
  const setArtifactLineage = (value: SetStateAction<ArtifactLineageVM | null>) => setField("artifactLineage", value);
  const setLaunchedOperation = (value: SetStateAction<ProgramOperationVM | null>) =>
    setField("launchedOperation", value);
  const setPackageReceipt = (value: SetStateAction<ToolExecutionReceiptVM | null>) =>
    setField("packageReceipt", value);
  const setStageOutput = (value: SetStateAction<StageOutputGenerationVM | null>) => setField("stageOutput", value);
  const setProjections = (value: SetStateAction<StateProjectionVM[]>) => setField("projections", value);
  const setMetricPeriods = (value: SetStateAction<MetricSnapshotVM[]>) => setField("metricPeriods", value);
  const setReportRuns = (value: SetStateAction<ReportRunVM[]>) => setField("reportRuns", value);
  const setSelectedModuleId = (value: SetStateAction<string>) => setField("selectedModuleId", value);
  const setSelectedProgramId = (value: SetStateAction<string>) => setField("selectedProgramId", value);
  const setSelectedArtifactId = (value: SetStateAction<string>) => setField("selectedArtifactId", value);
  const setBusyAction = (value: SetStateAction<string | null>) => setField("busyAction", value);
  const setProgramTitle = (value: SetStateAction<string>) => setField("programTitle", value);
  const setProgramObjective = (value: SetStateAction<string>) => setField("programObjective", value);
  const setAssertionKind = (value: SetStateAction<AssertionKindVM["kind"]>) => setField("assertionKind", value);
  const setAssertionCategory = (value: SetStateAction<string>) => setField("assertionCategory", value);
  const setAssertionStatement = (value: SetStateAction<string>) => setField("assertionStatement", value);
  const setAssertionSource = (value: SetStateAction<string>) => setField("assertionSource", value);
  const setArtifactTitle = (value: SetStateAction<string>) => setField("artifactTitle", value);
  const setArtifactContent = (value: SetStateAction<string>) => setField("artifactContent", value);
  const setEvaluationContent = (value: SetStateAction<string>) => setField("evaluationContent", value);
  const setEvaluationInputs = (value: SetStateAction<string>) => setField("evaluationInputs", value);
  const setMetricPeriodInputs = (value: SetStateAction<string>) => setField("metricPeriodInputs", value);
  const setPolicyBudget = (value: SetStateAction<string>) => setField("policyBudget", value);
  const setRevisionContent = (value: SetStateAction<string>) => setField("revisionContent", value);

  const activePack = useMemo(() => firstInstalledPack(packs, model), [model, packs]);
  const installedPackIds = useMemo(() => new Set((model?.installedPacks ?? []).map((pack) => pack.id)), [model]);
  const selectedProgram = useMemo(
    () => programs.find((program) => program.id === selectedProgramId) ?? programs[0] ?? null,
    [programs, selectedProgramId],
  );
  const primaryTemplate = activePack?.programTemplates[0] ?? null;
  const assertionKinds = activePack?.assertionKinds.length ? activePack.assertionKinds : fallbackAssertionKinds;
  const artifactSchemas = activePack?.artifactSchemas ?? [];
  const evaluationProfiles = activePack?.evaluationProfiles ?? model?.evaluationProfiles ?? [];
  const policyActions = activePack?.policyActions ?? [];
  const operationTemplates = activePack?.operationTemplates ?? [];
  const capabilityModules = useMemo(() => activePack?.modules ?? [], [activePack]);
  const toolPackages = activePack?.toolPackages ?? [];

  const setArtifactType = (value: SetStateAction<string>) => setField("artifactType", value);
  const setEvaluationProfileId = (value: SetStateAction<string>) => setField("evaluationProfileId", value);
  const setPolicyActionType = (value: SetStateAction<string>) => setField("policyActionType", value);

  const refresh = useCallback(async () => {
    if (!companyId) {
      return;
    }

    dispatchWorkspaceState({ type: "patch", patch: { loading: true, error: null } });
    try {
      const [availablePacks, operatingModel, programList, assertionList, artifactList] = await Promise.all([
        operatingModelRepository.listPacks(),
        operatingModelRepository.getCompanyOperatingModel(companyId),
        operatingModelRepository.listPrograms(companyId),
        operatingModelRepository.listAssertions({ companyId }),
        operatingModelRepository.listArtifacts({ companyId }),
      ]);
      const nextSelectedArtifactId =
        selectedArtifactId && artifactList.some((artifact) => artifact.id === selectedArtifactId)
          ? selectedArtifactId
          : (artifactList[0]?.id ?? "");
      const nextProgramId =
        selectedProgramId && programList.some((program) => program.id === selectedProgramId)
          ? selectedProgramId
          : (programList[0]?.id ?? "");
      const [projectionList, serviceHistoryList] = nextProgramId
        ? await Promise.all([
            operatingModelRepository.listStateProjections(companyId, nextProgramId),
            operatingModelRepository.listStateProjections(companyId, nextProgramId, "client_service_history"),
          ])
        : [[], []];
      const [reviewList, metricPeriodList, reportList] = await Promise.all([
        operatingModelRepository.listPeriodicReviews({
          companyId,
          programId: nextProgramId || undefined,
        }),
        operatingModelRepository.listMetricSnapshots({
          companyId,
          programId: nextProgramId || undefined,
        }),
        operatingModelRepository.listReportRuns({
          companyId,
          programId: nextProgramId || undefined,
        }),
      ]);
      dispatchWorkspaceState({
        type: "patch",
        patch: {
          packs: availablePacks,
          model: operatingModel,
          programs: programList,
          assertions: assertionList,
          artifacts: artifactList,
          selectedArtifactId: nextSelectedArtifactId,
          selectedProgramId: nextProgramId,
          projections: projectionList,
          serviceHistoryProjections: serviceHistoryList,
          periodicReviews: reviewList,
          metricPeriods: metricPeriodList,
          reportRuns: reportList,
          loading: false,
        },
      });
    } catch (loadError: unknown) {
      dispatchWorkspaceState({
        type: "patch",
        patch: { error: translateProductError(loadError, "company"), loading: false },
      });
    }
  }, [companyId, selectedArtifactId, selectedProgramId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!activePack) {
      return;
    }
    const patch: Partial<OperatingModelWorkspaceState> = {};
    if (!artifactType && activePack.artifactSchemas[0]?.id) {
      patch.artifactType = activePack.artifactSchemas[0].id;
    }
    if (!evaluationProfileId && activePack.evaluationProfiles[0]?.id) {
      patch.evaluationProfileId = activePack.evaluationProfiles[0].id;
    }
    if (!policyActionType && activePack.policyActions[0]?.actionType) {
      patch.policyActionType = activePack.policyActions[0].actionType;
    }
    if (!programTitle && activePack.programTemplates[0]) {
      patch.programTitle = titleFromTemplate(
        activePack.programTemplates[0].titleTemplate,
        companyName,
        activePack.programTemplates[0].label,
      );
    }
    if (Object.keys(patch).length) {
      dispatchWorkspaceState({ type: "patch", patch });
    }
  }, [activePack, artifactType, companyName, evaluationProfileId, policyActionType, programTitle]);

  useEffect(() => {
    if (assertionKinds.some((option) => option.kind === assertionKind)) {
      return;
    }
    setAssertionKind(assertionKinds[0]?.kind ?? "FACT");
  }, [assertionKind, assertionKinds]);

  useEffect(() => {
    if (!selectedModuleId || capabilityModules.some((module) => module.id === selectedModuleId)) {
      return;
    }
    setSelectedModuleId("");
  }, [capabilityModules, selectedModuleId]);

  const installPack = async (packId: string) => {
    setBusyAction(`install:${packId}`);
    try {
      await operatingModelRepository.installPack(companyId, packId);
      showSuccess("Operating model installed", "The company now has the selected operating model pack.");
      await refresh();
    } catch (installError: unknown) {
      showError("Install failed", translateProductError(installError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const createProgram = async () => {
    if (!primaryTemplate || !activePack) {
      showError("No program template available", "Install an operating model pack with a program template first.");
      return;
    }
    setBusyAction("program:create");
    try {
      const program = await operatingModelRepository.createProgram({
        companyId,
        packId: activePack.id,
        templateId: primaryTemplate.id,
        title: programTitle,
        objective: programObjective,
      });
      setSelectedProgramId(program.id);
      showSuccess(`${program.label} created`, "Program state is now stored in the company control plane.");
      await refresh();
    } catch (programError: unknown) {
      showError("Program creation failed", translateProductError(programError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const createAssertion = async () => {
    const statement = assertionStatement.trim();
    if (!statement) {
      showError("Assertion is empty", "Add a statement before saving it.");
      return;
    }

    const selectedKind = assertionKinds.find((option) => option.kind === assertionKind);
    setBusyAction("assertion:create");
    try {
      await operatingModelRepository.createAssertion({
        companyId,
        programId: selectedProgram?.id,
        kind: assertionKind,
        packLabel: selectedKind?.label,
        category: assertionCategory,
        statement,
        source: assertionSource,
        confidence: assertionKind === "FACT" ? 0.8 : 0.5,
      });
      setAssertionStatement("");
      setAssertionSource("");
      showSuccess("Assertion saved", "The record is stored separately from validated truth.");
      await refresh();
    } catch (assertionError: unknown) {
      showError("Assertion save failed", translateProductError(assertionError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const advanceStage = async (stageId: string, status: string) => {
    if (!selectedProgram) {
      return;
    }
    setBusyAction(`stage:${stageId}:${status}`);
    try {
      const program = await operatingModelRepository.advanceStage({
        programId: selectedProgram.id,
        stageId,
        status,
      });
      setPrograms((items) => items.map((item) => (item.id === program.id ? program : item)));
      showSuccess("Stage updated", `Status: ${status.replaceAll("_", " ")}`);
      await refresh();
    } catch (stageError: unknown) {
      showError("Stage update failed", translateProductError(stageError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const launchStageOperation = async (stageId: string, operationTemplateId: string, contextNote = "") => {
    if (!selectedProgram) {
      return;
    }
    setBusyAction(`operation:${stageId}:${operationTemplateId}`);
    try {
      const operation = await operatingModelRepository.launchStageOperation({
        programId: selectedProgram.id,
        stageId,
        operationTemplateId,
        contextNote,
      });
      setLaunchedOperation(operation);
      showSuccess("Operation launched", operation.label);
      await refresh();
    } catch (operationError: unknown) {
      showError("Operation launch failed", translateProductError(operationError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const generateStageOutputs = async (stageId: string) => {
    if (!selectedProgram) {
      return;
    }
    setBusyAction(`outputs:${stageId}`);
    try {
      const parsedEvaluationInputs = parseJsonInput(evaluationInputs);
      const result = await operatingModelRepository.generateStageOutputs({
        programId: selectedProgram.id,
        stageId,
        workflowId: `${stageId}.outputs`,
        evaluationInputs: parsedEvaluationInputs,
      });
      setStageOutput(result);
      setProjections([result.projection]);
      showSuccess(
        result.blockers.length ? "Output generation blocked" : "Outputs generated",
        result.blockers.length
          ? String(result.blockers[0]?.message ?? "Review stage requirements.")
          : `${result.createdArtifacts.length} artifacts updated.`,
      );
      await refresh();
    } catch (outputError: unknown) {
      showError("Output generation failed", translateProductError(outputError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const validateAssertion = async (
    assertion: AssertionRecordVM,
    decision: "ACCEPT" | "REJECT" | "EDIT" | "DEFER" | "NEEDS_RESEARCH",
  ) => {
    setBusyAction(`assertion:${assertion.id}:${decision}`);
    try {
      await operatingModelRepository.createValidationDecision({
        companyId,
        programId: assertion.programId ?? selectedProgram?.id,
        assertionId: assertion.id,
        decision,
        category: assertion.category,
        rationale: `${decision.toLowerCase().replaceAll("_", " ")} from operating model workspace.`,
      });
      showSuccess("Decision saved", decision.replaceAll("_", " "));
      await refresh();
    } catch (decisionError: unknown) {
      showError("Decision failed", translateProductError(decisionError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const createArtifact = async () => {
    if (!artifactType) {
      showError("Artifact type is missing", "Choose an artifact schema before saving.");
      return;
    }
    setBusyAction("artifact:create");
    try {
      await operatingModelRepository.createArtifact({
        companyId,
        programId: selectedProgram?.id,
        artifactType,
        title: artifactTitle || artifactSchemas.find((schema) => schema.id === artifactType)?.label || "Work Artifact",
        content: artifactContent || "Draft artifact content",
      });
      setArtifactTitle("");
      setArtifactContent("");
      showSuccess("Artifact saved", "The first revision is now in the company artifact ledger.");
      await refresh();
    } catch (artifactError: unknown) {
      showError("Artifact save failed", translateProductError(artifactError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const validateArtifact = async (
    artifact: WorkArtifactVM,
    decision: "ACCEPT" | "REJECT" | "EDIT" | "DEFER" | "NEEDS_RESEARCH",
  ) => {
    setBusyAction(`artifact:${artifact.id}:${decision}`);
    try {
      await operatingModelRepository.createValidationDecision({
        companyId,
        programId: artifact.programId ?? selectedProgram?.id,
        artifactId: artifact.id,
        artifactVersionId: artifact.canonicalRevisionId ?? undefined,
        decision,
        category: artifact.artifactType,
        rationale: `${decision.toLowerCase().replaceAll("_", " ")} from operating model workspace.`,
        proposedChange:
          decision === "EDIT"
            ? {
                content: revisionContent || `Revision requested for ${artifact.title}`,
                label: "v2",
                stage_id: selectedProgram?.currentStageId,
              }
            : { stage_id: selectedProgram?.currentStageId },
      });
      showSuccess("Decision saved", decision.replaceAll("_", " "));
      await refresh();
    } catch (decisionError: unknown) {
      showError("Decision failed", translateProductError(decisionError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const loadArtifactLineage = async (artifactId: string) => {
    setBusyAction(`artifact:${artifactId}:lineage`);
    try {
      const lineage = await operatingModelRepository.getArtifactLineage(artifactId);
      setArtifactLineage(lineage);
      setSelectedArtifactId(artifactId);
    } catch (lineageError: unknown) {
      showError("Lineage failed", translateProductError(lineageError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const createArtifactRevision = async () => {
    const artifact = artifacts.find((item) => item.id === selectedArtifactId);
    if (!artifact) {
      showError("No artifact selected", "Select an artifact before creating a revision.");
      return;
    }
    setBusyAction(`artifact:${artifact.id}:revision`);
    try {
      await operatingModelRepository.createArtifactRevision({
        artifactId: artifact.id,
        content: revisionContent || `Revision for ${artifact.title}`,
        parentRevisionId: artifact.canonicalRevisionId,
        label: "v2",
      });
      setRevisionContent("");
      showSuccess("Revision saved", "Artifact lineage was preserved.");
      await loadArtifactLineage(artifact.id);
      await refresh();
    } catch (revisionError: unknown) {
      showError("Revision failed", translateProductError(revisionError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const loadValidationPacket = async () => {
    if (!selectedProgram) {
      return;
    }
    setBusyAction("validation:packet");
    try {
      const packet = await operatingModelRepository.getValidationPacket(selectedProgram.id);
      setValidationPacket(packet);
      showSuccess("Validation packet ready", `${packet.artifactCount} artifacts, ${packet.assertionCount} assertions.`);
    } catch (packetError: unknown) {
      showError("Validation packet failed", translateProductError(packetError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const createReworkPlan = async () => {
    if (!selectedProgram) {
      return;
    }
    setBusyAction("rework:create");
    try {
      const plan = await operatingModelRepository.createReworkPlan({
        companyId,
        programId: selectedProgram.id,
      });
      setReworkPlan(plan);
      showSuccess("Rework plan ready", `${plan.itemCount} items.`);
      await refresh();
    } catch (reworkError: unknown) {
      showError("Rework plan failed", translateProductError(reworkError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const executeReworkPlan = async () => {
    if (!reworkPlan) {
      return;
    }
    setBusyAction(`rework:${reworkPlan.id}:execute`);
    try {
      const plan = await operatingModelRepository.executeReworkPlan(reworkPlan.id);
      setReworkPlan(plan);
      showSuccess("Rework executed", "Artifact revisions and program state were updated.");
      await refresh();
    } catch (reworkError: unknown) {
      showError("Rework failed", translateProductError(reworkError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const startEvaluation = async () => {
    if (!evaluationProfileId) {
      showError("Evaluation profile is missing", "Choose an evaluation profile first.");
      return;
    }
    setBusyAction("evaluation:evaluate");
    try {
      const parsedInputs = parseJsonInput(evaluationInputs);
      const result = await operatingModelRepository.runEvaluation({
        companyId,
        profileId: evaluationProfileId,
        content: evaluationContent,
        inputs: parsedInputs,
        programId: selectedProgram?.id,
      });
      setEvaluation(result);
      showSuccess("Evaluation complete", `Status: ${result.status}`);
    } catch (evaluationError: unknown) {
      showError("Evaluation failed", translateProductError(evaluationError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const createMetricPeriod = async () => {
    const review = periodicReviews[0];
    if (!review) {
      showError("No periodic review", "Install an operating model pack with a periodic review template first.");
      return;
    }
    setBusyAction("metric-period:create");
    try {
      const parsedInputs = parseJsonInput(metricPeriodInputs || evaluationInputs);
      const now = new Date();
      const periodEnd = now.toISOString().slice(0, 10);
      const periodStartDate = new Date(now);
      periodStartDate.setDate(1);
      const metricPeriod = await operatingModelRepository.createMetricSnapshot({
        companyId,
        programId: selectedProgram?.id,
        reviewDefinitionId: review.id,
        periodStart: periodStartDate.toISOString().slice(0, 10),
        periodEnd,
        metricValues: parsedInputs.metrics ? recordValue(parsedInputs.metrics) : parsedInputs,
        sourceType: "manual",
        notes: "Created from the operating model workspace.",
      });
      setMetricPeriods((items) => [metricPeriod, ...items]);
      showSuccess("Metric period saved", `${Object.keys(metricPeriod.metricValues).length} metrics captured.`);
      await refresh();
    } catch (metricPeriodError: unknown) {
      showError("Metric period failed", translateProductError(metricPeriodError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const startPeriodicReview = async (review: PeriodicReviewVM, metricPeriod: MetricSnapshotVM) => {
    setBusyAction(`periodic-review:${review.id}`);
    try {
      const result = await operatingModelRepository.runPeriodicReview({
        reviewId: review.id,
        metricSnapshotId: metricPeriod.id,
        notes: "Started from the operating model workspace.",
      });
      setEvaluation(result.evaluation);
      setReportRuns((items) => [result.reportRun, ...items.filter((item) => item.id !== result.reportRun.id)]);
      showSuccess("Periodic review complete", `${result.evaluation.status} · ${review.label}`);
      await refresh();
    } catch (reviewError: unknown) {
      showError("Periodic review failed", translateProductError(reviewError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const launchRecommendedOperation = async (operation: OperationTemplateVM, reason: string) => {
    const stageId = operation.stageIds[0] || selectedProgram?.currentStageId;
    if (!stageId) {
      showError("No stage available", "This recommendation is not mapped to a program stage.");
      return;
    }
    await launchStageOperation(stageId, operation.id, reason);
  };

  const evaluatePolicy = async () => {
    if (!policyActionType) {
      showError("Policy action is missing", "Choose an action before evaluating policy.");
      return;
    }
    setBusyAction("policy:evaluate");
    try {
      const result = await operatingModelRepository.evaluatePolicy({
        companyId,
        actionType: policyActionType,
        inputs: {
          budget: Number(policyBudget || 0),
          external_write_side_effect: true,
        },
      });
      setPolicyEvaluation(result);
      showSuccess("Policy evaluated", `Risk: ${result.riskLevel}`);
    } catch (policyError: unknown) {
      showError("Policy evaluation failed", translateProductError(policyError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const executeConnectorRehearsal = async () => {
    const packageOption = [...toolPackages, ...(activePack?.departmentTools ?? [])].find(
      (item) => item.sideEffects !== "none" && item.sideEffects !== "read",
    );
    if (!launchedOperation || !packageOption) {
      showError("Rehearsal unavailable", "Launch an operation and choose a governed package first.");
      return;
    }
    setBusyAction("connector:rehearsal");
    try {
      const receipt = await operatingModelRepository.executeTool({
        companyId,
        operationId: launchedOperation.id,
        toolId: packageOption.id,
        dryRun: true,
        inputs: {
          action_type: packageOption.policyActionType,
          budget: Number(policyBudget || 0),
          program_id: selectedProgram?.id,
        },
      });
      setPackageReceipt(receipt);
      showSuccess("Rehearsal receipt created", receipt.label);
    } catch (packageError: unknown) {
      showError("Package rehearsal failed", translateProductError(packageError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  if (loading && !model) {
    return (
      <Panel title="Operating Model" description="Installed packs, programs, state, evaluation, and policy.">
        <div className="flex min-h-[220px] items-center justify-center">
          <Spinner size="lg" />
        </div>
      </Panel>
    );
  }

  const currentProjection = projections[0] ?? null;
  const serviceHistoryProjection = serviceHistoryProjections[0] ?? null;

  return (
    <Panel
      title="Operating Model"
      description="Pack-driven company programs, assertions, artifacts, state, evaluation, and policy."
      className="operating-model-panel"
      action={
        <Button variant="outline" size="sm" className="rounded-full" onClick={() => void refresh()}>
          <RefreshCw className="size-4" />
          Refresh
        </Button>
      }
    >
      {error ? (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[0.92fr_1.08fr]">
        <div className="space-y-4">
          <div>
            <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
              <BookCheck className="size-4" />
              <p className="text-sm font-semibold">Packs</p>
            </div>
            <div className="mt-3 space-y-3">
              {packs.length ? (
                packs.map((pack) => (
                  <PackSummary
                    key={pack.id}
                    pack={pack}
                    installed={installedPackIds.has(pack.id)}
                    installing={busyAction === `install:${pack.id}`}
                    onInstall={() => void installPack(pack.id)}
                  />
                ))
              ) : (
                <EmptyBlock title="No packs available" description="Installable operating models will appear here." />
              )}
            </div>
          </div>

          {activePack?.dashboardPanels.length ? (
            <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
              <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Views</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {activePack.dashboardPanels.map((panel) => (
                  <span
                    key={panel.id}
                    className="rounded-full border border-zinc-900/10 bg-white/80 px-3 py-1 text-xs text-zinc-700 dark:border-white/10 dark:bg-white/6 dark:text-zinc-200"
                  >
                    {panel.label}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {activePack ? <PackServiceModelPanel pack={activePack} /> : null}

          {capabilityModules.length ? (
            <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
                  <GitBranch className="size-4" />
                  <p className="text-sm font-semibold">Capability Modules</p>
                </div>
                <StatusBadge status="available" label={`${capabilityModules.length}`} />
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {capabilityModules.slice(0, 8).map((module) => (
                  <button
                    key={module.id}
                    type="button"
                    onClick={() => setSelectedModuleId(module.id)}
                    className={`rounded-[1rem] border p-3 text-left transition-colors ${
                      selectedModuleId === module.id
                        ? "border-zinc-950 bg-zinc-950 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
                        : "border-zinc-900/8 bg-white/70 text-zinc-700 hover:bg-white dark:border-white/8 dark:bg-white/5 dark:text-zinc-200"
                    }`}
                  >
                    <p className="text-sm font-semibold">{module.label}</p>
                    <p className="mt-1 line-clamp-2 text-xs opacity-75">{module.description}</p>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {operationTemplates.length ? (
            <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
                  <ListChecks className="size-4" />
                  <p className="text-sm font-semibold">Operation Templates</p>
                </div>
                <StatusBadge status="available" label={`${operationTemplates.length}`} />
              </div>
              <div className="mt-3 space-y-2">
                {operationTemplates.slice(0, 6).map((operation) => (
                  <div
                    key={operation.id}
                    className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5"
                  >
                    <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{operation.label}</p>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-zinc-500 dark:text-zinc-400">
                      {operation.description}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {toolPackages.length ? (
            <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
              <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
                <Wrench className="size-4" />
                <p className="text-sm font-semibold">Governed Packages</p>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {toolPackages.map((tool) => (
                  <span
                    key={tool.id}
                    className="rounded-full border border-zinc-900/10 bg-white/80 px-3 py-1 text-xs text-zinc-700 dark:border-white/10 dark:bg-white/6 dark:text-zinc-200"
                  >
                    {tool.label}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className="space-y-5">
          <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
                  <ListChecks className="size-4" />
                  <p className="text-sm font-semibold">Programs</p>
                </div>
                <MicroExplanation className="mt-2">
                  {primaryTemplate ? `Template: ${primaryTemplate.label}` : "Install a pack to add program templates."}
                </MicroExplanation>
              </div>
              {programs.length ? <StatusBadge status="active" label={`${programs.length} active`} /> : null}
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto]">
              <Input
                value={programTitle}
                onChange={(event) => setProgramTitle(event.target.value)}
                placeholder={primaryTemplate?.label ?? "Program title"}
              />
              <Button
                onClick={() => void createProgram()}
                disabled={!primaryTemplate || busyAction === "program:create"}
              >
                {busyAction === "program:create" ? (
                  <Spinner size="xs" className="mr-2" />
                ) : (
                  <PackagePlus className="size-4" />
                )}
                Create
              </Button>
            </div>
            <Textarea
              className="mt-3"
              rows={2}
              value={programObjective}
              onChange={(event) => setProgramObjective(event.target.value)}
              placeholder={primaryTemplate?.objectiveTemplate || "Program objective"}
            />

            <div className="mt-4 grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
              <div className="space-y-2">
                {programs.length ? (
                  programs.map((program) => (
                    <button
                      key={program.id}
                      type="button"
                      onClick={() => setSelectedProgramId(program.id)}
                      className={`w-full rounded-[1rem] border p-3 text-left transition-colors ${
                        selectedProgram?.id === program.id
                          ? "border-zinc-950 bg-zinc-950 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
                          : "border-zinc-900/8 bg-white/70 text-zinc-700 hover:bg-white dark:border-white/8 dark:bg-white/5 dark:text-zinc-200"
                      }`}
                    >
                      <p className="text-sm font-semibold">{program.title}</p>
                      <p className="mt-1 text-xs opacity-75">{program.label}</p>
                    </button>
                  ))
                ) : (
                  <EmptyBlock title="No programs yet" description="Create the first program from an installed pack." />
                )}
              </div>
              {selectedProgram ? (
                <ProgramTimeline
                  program={selectedProgram}
                  operationTemplates={operationTemplates}
                  modules={capabilityModules}
                  selectedModuleId={selectedModuleId}
                  busyAction={busyAction}
                  stageOutput={stageOutput}
                  onSelectModule={setSelectedModuleId}
                  onAdvanceStage={(stageId, status) => void advanceStage(stageId, status)}
                  onLaunchOperation={(stageId, operationTemplateId) =>
                    void launchStageOperation(stageId, operationTemplateId)
                  }
                  onGenerateOutputs={(stageId) => void generateStageOutputs(stageId)}
                />
              ) : null}
            </div>
            {launchedOperation ? (
              <div className="mt-4 rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{launchedOperation.label}</p>
                  <StatusBadge status={launchedOperation.status} label={launchedOperation.status} />
                </div>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  Operation launched for {launchedOperation.stageId ?? "selected stage"}
                </p>
              </div>
            ) : null}
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
              <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
                <ClipboardCheck className="size-4" />
                <p className="text-sm font-semibold">Assertions</p>
              </div>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Select
                  value={assertionKind}
                  onValueChange={(value) => setAssertionKind(value as AssertionKindVM["kind"])}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Kind" />
                  </SelectTrigger>
                  <SelectContent>
                    {assertionKinds.map((kind) => (
                      <SelectItem key={kind.kind} value={kind.kind}>
                        {kind.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  value={assertionCategory}
                  onChange={(event) => setAssertionCategory(event.target.value)}
                  placeholder={activePack?.assertionCategories[0] ?? "Category"}
                />
              </div>
              <Textarea
                className="mt-3"
                rows={3}
                value={assertionStatement}
                onChange={(event) => setAssertionStatement(event.target.value)}
                placeholder="Statement"
              />
              <Input
                className="mt-3"
                value={assertionSource}
                onChange={(event) => setAssertionSource(event.target.value)}
                placeholder="Source"
              />
              <Button
                className="mt-3"
                onClick={() => void createAssertion()}
                disabled={busyAction === "assertion:create"}
              >
                {busyAction === "assertion:create" ? (
                  <Spinner size="xs" className="mr-2" />
                ) : (
                  <BookCheck className="size-4" />
                )}
                Save assertion
              </Button>
              <div className="mt-4 space-y-2">
                {assertions.slice(0, 4).map((assertion) => (
                  <div
                    key={assertion.id}
                    className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={assertion.validationStatus} label={assertion.label} />
                      {assertion.category ? <span className="text-xs text-zinc-500">{assertion.category}</span> : null}
                    </div>
                    <p className="mt-2 text-sm leading-6 text-zinc-700 dark:text-zinc-200">{assertion.statement}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 rounded-full px-3 text-xs"
                        onClick={() => void validateAssertion(assertion, "ACCEPT")}
                        disabled={busyAction === `assertion:${assertion.id}:ACCEPT`}
                      >
                        Accept
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 rounded-full px-3 text-xs"
                        onClick={() => void validateAssertion(assertion, "NEEDS_RESEARCH")}
                        disabled={busyAction === `assertion:${assertion.id}:NEEDS_RESEARCH`}
                      >
                        Research
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 rounded-full px-3 text-xs"
                        onClick={() => void validateAssertion(assertion, "REJECT")}
                        disabled={busyAction === `assertion:${assertion.id}:REJECT`}
                      >
                        Reject
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
              <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
                <FileStack className="size-4" />
                <p className="text-sm font-semibold">Work Artifacts</p>
              </div>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Select value={artifactType} onValueChange={setArtifactType}>
                  <SelectTrigger>
                    <SelectValue placeholder="Artifact type" />
                  </SelectTrigger>
                  <SelectContent>
                    {artifactSchemas.map((schema) => (
                      <SelectItem key={schema.id} value={schema.id}>
                        {schema.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  value={artifactTitle}
                  onChange={(event) => setArtifactTitle(event.target.value)}
                  placeholder="Title"
                />
              </div>
              <Textarea
                className="mt-3"
                rows={4}
                value={artifactContent}
                onChange={(event) => setArtifactContent(event.target.value)}
                placeholder="Draft content"
              />
              <Button
                className="mt-3"
                onClick={() => void createArtifact()}
                disabled={busyAction === "artifact:create"}
              >
                {busyAction === "artifact:create" ? (
                  <Spinner size="xs" className="mr-2" />
                ) : (
                  <FileStack className="size-4" />
                )}
                Save artifact
              </Button>
              <Textarea
                className="mt-3"
                rows={2}
                value={revisionContent}
                onChange={(event) => setRevisionContent(event.target.value)}
                placeholder="Revision content or requested change"
              />
              <Button
                className="mt-3"
                variant="outline"
                onClick={() => void createArtifactRevision()}
                disabled={!selectedArtifactId || busyAction?.includes(":revision")}
              >
                <GitBranch className="size-4" />
                Add revision
              </Button>
              <div className="mt-4 space-y-2">
                {artifacts.slice(0, 4).map((artifact) => (
                  <div
                    key={artifact.id}
                    className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{artifact.title}</p>
                      <StatusBadge status={artifact.status} label={`${artifact.revisionCount || 1} rev`} />
                    </div>
                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      {artifact.artifactType} · {formatDateTime(artifact.updatedAt)}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 rounded-full px-3 text-xs"
                        onClick={() => void loadArtifactLineage(artifact.id)}
                        disabled={busyAction === `artifact:${artifact.id}:lineage`}
                      >
                        Lineage
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 rounded-full px-3 text-xs"
                        onClick={() => void validateArtifact(artifact, "ACCEPT")}
                        disabled={busyAction === `artifact:${artifact.id}:ACCEPT`}
                      >
                        Accept
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 rounded-full px-3 text-xs"
                        onClick={() => void validateArtifact(artifact, "EDIT")}
                        disabled={busyAction === `artifact:${artifact.id}:EDIT`}
                      >
                        Edit
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
              {artifactLineage ? (
                <div className="mt-4 rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                      {artifactLineage.artifact.title}
                    </p>
                    <StatusBadge status="lineage" label={`${artifactLineage.dependencyCount} links`} />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {artifactLineage.artifact.revisions.map((revision) => (
                      <button
                        key={revision.id}
                        type="button"
                        onClick={() =>
                          void operatingModelRepository.setCanonicalRevision(artifactLineage.artifact.id, revision.id)
                        }
                        className={`rounded-full border px-3 py-1 text-xs ${
                          revision.isCanonical
                            ? "border-zinc-950 bg-zinc-950 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
                            : "border-zinc-900/10 bg-white text-zinc-700 dark:border-white/10 dark:bg-white/6 dark:text-zinc-200"
                        }`}
                      >
                        {revision.label}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>

          <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
                  <RotateCcw className="size-4" />
                  <p className="text-sm font-semibold">Validation & Rework</p>
                </div>
                <MicroExplanation className="mt-2">
                  Generate a review packet, record decisions, inspect impact, then execute selected rework.
                </MicroExplanation>
              </div>
              {reworkPlan ? <StatusBadge status={reworkPlan.status} label={`${reworkPlan.itemCount} items`} /> : null}
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="outline"
                onClick={() => void loadValidationPacket()}
                disabled={!selectedProgram || busyAction === "validation:packet"}
              >
                <ClipboardCheck className="size-4" />
                Build packet
              </Button>
              <Button
                variant="outline"
                onClick={() => void createReworkPlan()}
                disabled={!selectedProgram || busyAction === "rework:create"}
              >
                <RotateCcw className="size-4" />
                Plan rework
              </Button>
              <Button
                onClick={() => void executeReworkPlan()}
                disabled={!reworkPlan || reworkPlan.status === "executed" || busyAction?.includes("rework:")}
              >
                Execute rework
              </Button>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {validationPacket ? (
                <div className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
                  <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Validation packet</p>
                  <p className="mt-2 text-xs leading-5 text-zinc-500 dark:text-zinc-400">
                    {validationPacket.assertionCount} assertions · {validationPacket.artifactCount} artifacts ·{" "}
                    {validationPacket.blockingFindingCount} blockers
                  </p>
                </div>
              ) : null}
              {reworkPlan ? (
                <div className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
                  <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{reworkPlan.triggerSummary}</p>
                  <p className="mt-2 text-xs leading-5 text-zinc-500 dark:text-zinc-400">
                    Scope {String(reworkPlan.estimatedEffort.scope ?? "n/a")} ·{" "}
                    {String(reworkPlan.impact.impacted_stages ?? "[]")}
                  </p>
                </div>
              ) : null}
            </div>
          </div>

          <PeriodicReviewsPanel
            reviews={periodicReviews}
            metricPeriods={metricPeriods}
            reportRuns={reportRuns}
            onStart={(review, metricPeriod) => void startPeriodicReview(review, metricPeriod)}
          />

          <div className="grid gap-5 xl:grid-cols-3">
            <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8 xl:col-span-1">
              <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
                <BookCheck className="size-4" />
                <p className="text-sm font-semibold">{currentProjection?.label ?? "Current State"}</p>
              </div>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zinc-700 dark:text-zinc-200">
                {currentProjection?.markdownSummary || compactJson(currentProjection?.state ?? {})}
              </p>
            </div>

            <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
              <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
                <ClipboardCheck className="size-4" />
                <p className="text-sm font-semibold">Evaluation</p>
              </div>
              <Select value={evaluationProfileId} onValueChange={setEvaluationProfileId}>
                <SelectTrigger className="mt-3">
                  <SelectValue placeholder="Profile" />
                </SelectTrigger>
                <SelectContent>
                  {evaluationProfiles.map((profile) => (
                    <SelectItem key={profile.id} value={profile.id}>
                      {profile.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Textarea
                className="mt-3"
                rows={3}
                value={evaluationContent}
                onChange={(event) => setEvaluationContent(event.target.value)}
                placeholder="Content to evaluate"
              />
              <Textarea
                className="mt-3"
                rows={3}
                value={evaluationInputs}
                onChange={(event) => setEvaluationInputs(event.target.value)}
                placeholder='Structured inputs JSON, for example {"metrics":{"roas":3.5}}'
              />
              <Textarea
                className="mt-3"
                rows={3}
                value={metricPeriodInputs}
                onChange={(event) => setMetricPeriodInputs(event.target.value)}
                placeholder='Metric period JSON, for example {"roas":3.5,"email_open_rate":20}'
              />
              <div className="mt-3 flex flex-wrap gap-2">
                <Button onClick={() => void startEvaluation()} disabled={busyAction === "evaluation:evaluate"}>
                  {busyAction === "evaluation:evaluate" ? (
                    <Spinner size="xs" className="mr-2" />
                  ) : (
                    <ClipboardCheck className="size-4" />
                  )}
                  Evaluate
                </Button>
                <Button
                  variant="outline"
                  onClick={() => void createMetricPeriod()}
                  disabled={busyAction === "metric-period:create"}
                >
                  {busyAction === "metric-period:create" ? (
                    <Spinner size="xs" className="mr-2" />
                  ) : (
                    <CalendarClock className="size-4" />
                  )}
                  Save Metrics
                </Button>
              </div>
              {evaluation ? (
                <div className="mt-3 rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
                  <StatusBadge status={evaluation.status} label={evaluation.status} />
                  <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-200">
                    Score {evaluation.score ?? "n/a"} · {evaluation.blockingFindingCount} blocking
                  </p>
                </div>
              ) : null}
              <ScorecardPanel evaluation={evaluation} />
              <RecommendedOperationsPanel
                evaluation={evaluation}
                operationTemplates={operationTemplates}
                onLaunch={(operation, reason) => void launchRecommendedOperation(operation, reason)}
              />
            </div>

            <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
              <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
                <ShieldCheck className="size-4" />
                <p className="text-sm font-semibold">Policy</p>
              </div>
              <Select value={policyActionType} onValueChange={setPolicyActionType}>
                <SelectTrigger className="mt-3">
                  <SelectValue placeholder="Action" />
                </SelectTrigger>
                <SelectContent>
                  {policyActions.map((action) => (
                    <SelectItem key={action.actionType} value={action.actionType}>
                      {action.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                className="mt-3"
                value={policyBudget}
                onChange={(event) => setPolicyBudget(event.target.value)}
                inputMode="numeric"
                placeholder="Budget"
              />
              <Button
                className="mt-3"
                onClick={() => void evaluatePolicy()}
                disabled={busyAction === "policy:evaluate"}
              >
                {busyAction === "policy:evaluate" ? (
                  <Spinner size="xs" className="mr-2" />
                ) : (
                  <ShieldCheck className="size-4" />
                )}
                Evaluate
              </Button>
              <Button
                className="mt-3"
                variant="outline"
                onClick={() => void executeConnectorRehearsal()}
                disabled={!launchedOperation || busyAction === "connector:rehearsal"}
              >
                <Wrench className="size-4" />
                Rehearse package
              </Button>
              {policyEvaluation ? (
                <div className="mt-3 rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
                  <StatusBadge status={policyEvaluation.status} label={policyEvaluation.riskLevel} />
                  <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-200">
                    {policyEvaluation.actionType} · {policyEvaluation.status.replaceAll("_", " ")}
                  </p>
                </div>
              ) : null}
              {packageReceipt ? (
                <div className="mt-3 rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
                  <StatusBadge
                    status={packageReceipt.status}
                    label={packageReceipt.dryRun ? "Rehearsal" : packageReceipt.status}
                  />
                  <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-200">
                    {packageReceipt.label} · {packageReceipt.sideEffects}
                  </p>
                </div>
              ) : null}
            </div>
          </div>

          <ServiceHistoryPanel projection={serviceHistoryProjection} />
        </div>
      </div>
    </Panel>
  );
}
