import { useCallback, useEffect, useMemo, useReducer, useState, type SetStateAction } from "react";
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

import { CommunicationPanel } from "@/components/company/CommunicationPanel";
import { WhiteboardPanel } from "@/components/company/WhiteboardPanel";
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
  installedPacks: OperatingModelPackVM[];
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
  installedPacks: [],
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
  installedPacks: OperatingModelPackVM[],
): OperatingModelPackVM | null {
  const installation =
    installedPacks.find((pack) => pack.status === "active" && pack.role === "primary") ??
    installedPacks.find((pack) => pack.status === "active") ??
    installedPacks.find((pack) => pack.status !== "archived") ??
    null;
  if (!installation) {
    return packs[0] ?? null;
  }
  const definition = packs.find((pack) => pack.id === installation.id);
  if (!definition) {
    return installation;
  }
  return {
    ...definition,
    installationId: installation.installationId,
    basePackId: installation.basePackId,
    role: installation.role,
    status: installation.status,
    namespace: installation.namespace,
    activeSince: installation.activeSince,
    archivedAt: installation.archivedAt,
    configRevisionCount: installation.configRevisionCount,
    namespaceClaimCount: installation.namespaceClaimCount,
    config: installation.config,
    publicConfig: installation.publicConfig,
  };
}

function labelForIdentifier(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function connectorCandidatesFromPack(pack: OperatingModelPackVM | null): string[] {
  const connectors = new Set<string>();
  collectRequiredConnectors(pack?.files ?? {}, connectors);
  return Array.from(connectors).sort();
}

function collectRequiredConnectors(value: unknown, connectors: Set<string>): void {
  if (Array.isArray(value)) {
    for (const item of value) {
      collectRequiredConnectors(item, connectors);
    }
    return;
  }
  if (!value || typeof value !== "object") {
    return;
  }
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    if (key === "required_connector" && typeof item === "string" && item.trim()) {
      connectors.add(item.trim());
    }
    collectRequiredConnectors(item, connectors);
  }
}

function availableConnectorsFromPack(pack: OperatingModelPackVM | null): string[] {
  const value = (pack?.publicConfig ?? pack?.config ?? {}).available_connectors;
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
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
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const text = String(item);
        return text ? [text] : [];
      })
    : [];
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
    <div
      data-testid="service-history-panel"
      className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
    >
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
  installation,
  installed,
  installing,
  onInstall,
}: {
  pack: OperatingModelPackVM;
  installation: OperatingModelPackVM | null;
  installed: boolean;
  installing: boolean;
  onInstall: () => void;
}) {
  const namespace = installation?.namespace ?? pack.namespace ?? pack.id;
  const status = installation?.status ?? (installed ? "active" : "available");
  const role = installation?.role ?? "available";
  return (
    <div
      data-testid={`operating-model-pack-card-${pack.id}`}
      className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{pack.name}</p>
            <StatusBadge status={status} label={installed ? status : "Available"} />
            {installed ? (
              <span data-testid="installed-pack-role">
                <StatusBadge status={role} label={role} />
              </span>
            ) : null}
          </div>
          <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{pack.description}</p>
          <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
            {pack.companyTypeLabel} · v{pack.version}
            {installed ? ` · ${namespace}` : ""}
          </p>
          {installed ? (
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              {(installation?.namespaceClaimCount ?? 0).toLocaleString()} namespace claims ·{" "}
              {(installation?.configRevisionCount ?? 0).toLocaleString()} config revisions
            </p>
          ) : null}
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

function useOperatingModelWorkspaceController({ companyId, companyName }: OperatingModelWorkspaceProps) {
  const [workspaceState, dispatchWorkspaceState] = useReducer(
    operatingModelWorkspaceReducer,
    initialOperatingModelWorkspaceState,
  );
  const {
    packs,
    installedPacks,
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
  const setPackageReceipt = (value: SetStateAction<ToolExecutionReceiptVM | null>) => setField("packageReceipt", value);
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

  const activePack = useMemo(() => firstInstalledPack(packs, installedPacks), [installedPacks, packs]);
  const installedPackIds = useMemo(() => {
    const ids = new Set<string>();
    for (const pack of installedPacks) {
      if (pack.status !== "archived") {
        ids.add(pack.id);
      }
    }
    return ids;
  }, [installedPacks]);
  const installedPackById = useMemo(() => new Map(installedPacks.map((pack) => [pack.id, pack])), [installedPacks]);
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
      const [availablePacks, installedPackList, operatingModel, programList, assertionList, artifactList] =
        await Promise.all([
          operatingModelRepository.listPacks(),
          operatingModelRepository.listInstalledPacks(companyId),
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
          installedPacks: installedPackList,
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
    dispatchWorkspaceState({
      type: "setField",
      key: "assertionKind",
      value: assertionKinds[0]?.kind ?? "FACT",
    });
  }, [assertionKind, assertionKinds]);

  useEffect(() => {
    if (!selectedModuleId || capabilityModules.some((module) => module.id === selectedModuleId)) {
      return;
    }
    dispatchWorkspaceState({ type: "setField", key: "selectedModuleId", value: "" });
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

  const updateAvailableConnectors = async (availableConnectors: string[]) => {
    if (!activePack?.installationId) {
      showError("Connector setup unavailable", "Install an operating model pack before configuring connectors.");
      return;
    }
    setBusyAction("connectors:update");
    try {
      await operatingModelRepository.updateAvailableConnectors({
        companyId,
        installationId: activePack.installationId,
        currentConfig: activePack.config ?? activePack.publicConfig ?? {},
        availableConnectors,
      });
      showSuccess("Connector availability saved", `${availableConnectors.length} connector signals configured.`);
      await refresh();
    } catch (connectorError: unknown) {
      showError("Connector setup failed", translateProductError(connectorError, "company"));
    } finally {
      setBusyAction(null);
    }
  };

  const currentProjection = projections[0] ?? null;
  const serviceHistoryProjection = serviceHistoryProjections[0] ?? null;

  return {
    companyId,
    companyName,
    packs,
    model,
    programs,
    assertions,
    artifacts,
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
    activePack,
    installedPacks,
    installedPackById,
    installedPackIds,
    selectedProgram,
    primaryTemplate,
    assertionKinds,
    artifactSchemas,
    evaluationProfiles,
    policyActions,
    operationTemplates,
    capabilityModules,
    toolPackages,
    currentProjection,
    serviceHistoryProjection,
    refresh,
    installPack,
    createProgram,
    createAssertion,
    advanceStage,
    launchStageOperation,
    generateStageOutputs,
    validateAssertion,
    createArtifact,
    validateArtifact,
    loadArtifactLineage,
    createArtifactRevision,
    loadValidationPacket,
    createReworkPlan,
    executeReworkPlan,
    startEvaluation,
    createMetricPeriod,
    startPeriodicReview,
    launchRecommendedOperation,
    evaluatePolicy,
    executeConnectorRehearsal,
    updateAvailableConnectors,
    setSelectedModuleId,
    setSelectedProgramId,
    setAssertionKind,
    setAssertionCategory,
    setAssertionStatement,
    setAssertionSource,
    setArtifactType,
    setArtifactTitle,
    setArtifactContent,
    setEvaluationProfileId,
    setEvaluationContent,
    setEvaluationInputs,
    setMetricPeriodInputs,
    setPolicyActionType,
    setPolicyBudget,
    setRevisionContent,
    setProgramTitle,
    setProgramObjective,
  };
}

type OperatingModelController = ReturnType<typeof useOperatingModelWorkspaceController>;

export function OperatingModelWorkspace(props: OperatingModelWorkspaceProps) {
  const controller = useOperatingModelWorkspaceController(props);

  if (controller.loading && !controller.model) {
    return (
      <Panel title="Operating Model" description="Installed packs, programs, state, evaluation, and policy.">
        <div className="flex min-h-[220px] items-center justify-center">
          <Spinner size="lg" />
        </div>
      </Panel>
    );
  }

  return <OperatingModelPanel controller={controller} />;
}

function OperatingModelPanel({ controller }: { controller: OperatingModelController }) {
  return (
    <Panel
      title="Operating Model"
      description="Pack-driven company programs, assertions, artifacts, state, evaluation, and policy."
      className="operating-model-panel"
      action={
        <Button variant="outline" size="sm" className="rounded-full" onClick={() => void controller.refresh()}>
          <RefreshCw className="size-4" />
          Refresh
        </Button>
      }
    >
      {controller.error ? (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{controller.error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="grid gap-5 xl:grid-cols-[0.92fr_1.08fr]">
        <OperatingModelPackColumn controller={controller} />
        <OperatingModelWorkColumn controller={controller} />
      </div>
    </Panel>
  );
}

function OperatingModelPackColumn({ controller }: { controller: OperatingModelController }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
          <BookCheck className="size-4" />
          <p className="text-sm font-semibold">Packs</p>
        </div>
        <div className="mt-3 space-y-3">
          {controller.packs.length ? (
            controller.packs.map((pack) => (
              <PackSummary
                key={pack.id}
                pack={pack}
                installation={controller.installedPackById.get(pack.id) ?? null}
                installed={controller.installedPackIds.has(pack.id)}
                installing={controller.busyAction === `install:${pack.id}`}
                onInstall={() => void controller.installPack(pack.id)}
              />
            ))
          ) : (
            <EmptyBlock title="No packs available" description="Installable operating models will appear here." />
          )}
        </div>
      </div>
      <PackDashboardPanel controller={controller} />
      <ConnectorAvailabilityPanel controller={controller} />
      {controller.activePack ? <PackServiceModelPanel pack={controller.activePack} /> : null}
      <CapabilityModulesPanel controller={controller} />
      <OperationTemplatesPanel controller={controller} />
      <ToolPackagesPanel controller={controller} />
    </div>
  );
}

function PackDashboardPanel({ controller }: { controller: OperatingModelController }) {
  if (!controller.activePack?.dashboardPanels.length) {
    return null;
  }

  return (
    <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Views</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {controller.activePack.dashboardPanels.map((panel) => (
          <span
            key={panel.id}
            className="rounded-full border border-zinc-900/10 bg-white/80 px-3 py-1 text-xs text-zinc-700 dark:border-white/10 dark:bg-white/6 dark:text-zinc-200"
          >
            {panel.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function ConnectorAvailabilityPanel({ controller }: { controller: OperatingModelController }) {
  const candidates = useMemo(() => connectorCandidatesFromPack(controller.activePack), [controller.activePack]);
  const persistedAvailable = useMemo(() => availableConnectorsFromPack(controller.activePack), [controller.activePack]);
  const [selected, setSelected] = useState<string[]>(persistedAvailable);

  useEffect(() => {
    setSelected(persistedAvailable);
  }, [persistedAvailable]);

  if (!controller.activePack?.installationId || !candidates.length) {
    return null;
  }

  const selectedSet = new Set(selected);
  const toggleConnector = (connectorId: string) => {
    setSelected((items) =>
      items.includes(connectorId) ? items.filter((item) => item !== connectorId) : [...items, connectorId].sort(),
    );
  };
  const applySandboxCore = () => {
    const core = ["email_connector", "social_connector", "analytics_connector"];
    setSelected(candidates.filter((connectorId) => core.includes(connectorId)));
  };
  const saving = controller.busyAction === "connectors:update";

  return (
    <div
      data-testid="connector-management-panel"
      className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
          <Wrench className="size-4" />
          <p className="text-sm font-semibold">Connector Availability</p>
        </div>
        <StatusBadge status="configured" label={`${selected.length}/${candidates.length}`} />
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {candidates.map((connectorId) => (
          <label
            key={connectorId}
            data-testid={`connector-option-${connectorId}`}
            className="flex min-w-0 cursor-pointer items-center gap-2 rounded-[0.85rem] border border-zinc-900/8 bg-white/70 px-3 py-2 text-xs text-zinc-700 dark:border-white/8 dark:bg-white/5 dark:text-zinc-200"
          >
            <input
              data-testid={`connector-toggle-${connectorId}`}
              type="checkbox"
              className="size-4 accent-zinc-950 dark:accent-zinc-100"
              checked={selectedSet.has(connectorId)}
              onChange={() => toggleConnector(connectorId)}
            />
            <span className="min-w-0 truncate">{labelForIdentifier(connectorId)}</span>
          </label>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          data-testid="connector-sandbox-core-preset"
          variant="outline"
          size="sm"
          onClick={applySandboxCore}
          disabled={saving}
        >
          <ShieldCheck className="size-4" />
          Sandbox core
        </Button>
        <Button
          data-testid="connector-save-button"
          size="sm"
          onClick={() => void controller.updateAvailableConnectors(selected)}
          disabled={saving}
        >
          {saving ? <Spinner size="xs" className="mr-2" /> : <ClipboardCheck className="size-4" />}
          Save availability
        </Button>
      </div>
    </div>
  );
}

function CapabilityModulesPanel({ controller }: { controller: OperatingModelController }) {
  if (!controller.capabilityModules.length) {
    return null;
  }

  return (
    <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
          <GitBranch className="size-4" />
          <p className="text-sm font-semibold">Capability Modules</p>
        </div>
        <StatusBadge status="available" label={`${controller.capabilityModules.length}`} />
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {controller.capabilityModules.slice(0, 8).map((module) => (
          <button
            key={module.id}
            type="button"
            onClick={() => controller.setSelectedModuleId(module.id)}
            className={`rounded-[1rem] border p-3 text-left transition-colors ${
              controller.selectedModuleId === module.id
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
  );
}

function OperationTemplatesPanel({ controller }: { controller: OperatingModelController }) {
  if (!controller.operationTemplates.length) {
    return null;
  }

  return (
    <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
          <ListChecks className="size-4" />
          <p className="text-sm font-semibold">Operation Templates</p>
        </div>
        <StatusBadge status="available" label={`${controller.operationTemplates.length}`} />
      </div>
      <div className="mt-3 space-y-2">
        {controller.operationTemplates.slice(0, 6).map((operation) => (
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
  );
}

function ToolPackagesPanel({ controller }: { controller: OperatingModelController }) {
  if (!controller.toolPackages.length) {
    return null;
  }

  return (
    <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
        <Wrench className="size-4" />
        <p className="text-sm font-semibold">Governed Packages</p>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {controller.toolPackages.map((tool) => (
          <span
            key={tool.id}
            className="rounded-full border border-zinc-900/10 bg-white/80 px-3 py-1 text-xs text-zinc-700 dark:border-white/10 dark:bg-white/6 dark:text-zinc-200"
          >
            {tool.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function OperatingModelWorkColumn({ controller }: { controller: OperatingModelController }) {
  const communicationEnabled = process.env.NEXT_PUBLIC_COMMUNICATION_ENABLED !== "false";

  return (
    <div className="space-y-5">
      <ProgramsPanel controller={controller} />
      <div className="grid gap-5 xl:grid-cols-2">
        <AssertionsPanel controller={controller} />
        <ArtifactsPanel controller={controller} />
      </div>
      <ValidationReworkPanel controller={controller} />
      <PeriodicReviewsPanel
        reviews={controller.periodicReviews}
        metricPeriods={controller.metricPeriods}
        reportRuns={controller.reportRuns}
        onStart={(review, metricPeriod) => void controller.startPeriodicReview(review, metricPeriod)}
      />
      <div className="grid gap-5 xl:grid-cols-3">
        <CurrentStatePanel controller={controller} />
        <EvaluationPanel controller={controller} />
        <PolicyPanel controller={controller} />
      </div>
      <ServiceHistoryPanel projection={controller.serviceHistoryProjection} />
      <WhiteboardPanel companyId={controller.companyId} />
      {communicationEnabled ? (
        <CommunicationPanel companyId={controller.companyId} companyName={controller.companyName} />
      ) : null}
    </div>
  );
}

function ProgramsPanel({ controller }: { controller: OperatingModelController }) {
  return (
    <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
            <ListChecks className="size-4" />
            <p className="text-sm font-semibold">Programs</p>
          </div>
          <MicroExplanation className="mt-2">
            {controller.primaryTemplate
              ? `Template: ${controller.primaryTemplate.label}`
              : "Install a pack to add program templates."}
          </MicroExplanation>
        </div>
        {controller.programs.length ? (
          <StatusBadge status="active" label={`${controller.programs.length} active`} />
        ) : null}
      </div>
      <ProgramCreateForm controller={controller} />
      <div className="mt-4 grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
        <ProgramSelector controller={controller} />
        {controller.selectedProgram ? (
          <ProgramTimeline
            program={controller.selectedProgram}
            operationTemplates={controller.operationTemplates}
            modules={controller.capabilityModules}
            selectedModuleId={controller.selectedModuleId}
            busyAction={controller.busyAction}
            stageOutput={controller.stageOutput}
            onSelectModule={controller.setSelectedModuleId}
            onAdvanceStage={(stageId, status) => void controller.advanceStage(stageId, status)}
            onLaunchOperation={(stageId, operationTemplateId) =>
              void controller.launchStageOperation(stageId, operationTemplateId)
            }
            onGenerateOutputs={(stageId) => void controller.generateStageOutputs(stageId)}
          />
        ) : null}
      </div>
      {controller.launchedOperation ? <LaunchedOperationNotice controller={controller} /> : null}
    </div>
  );
}

function ProgramCreateForm({ controller }: { controller: OperatingModelController }) {
  return (
    <>
      <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto]">
        <Input
          value={controller.programTitle}
          onChange={(event) => controller.setProgramTitle(event.target.value)}
          placeholder={controller.primaryTemplate?.label ?? "Program title"}
        />
        <Button
          onClick={() => void controller.createProgram()}
          disabled={!controller.primaryTemplate || controller.busyAction === "program:create"}
        >
          {controller.busyAction === "program:create" ? (
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
        value={controller.programObjective}
        onChange={(event) => controller.setProgramObjective(event.target.value)}
        placeholder={controller.primaryTemplate?.objectiveTemplate || "Program objective"}
      />
    </>
  );
}

function ProgramSelector({ controller }: { controller: OperatingModelController }) {
  if (!controller.programs.length) {
    return <EmptyBlock title="No programs yet" description="Create the first program from an installed pack." />;
  }

  return (
    <div className="space-y-2">
      {controller.programs.map((program) => (
        <button
          key={program.id}
          type="button"
          onClick={() => controller.setSelectedProgramId(program.id)}
          className={`w-full rounded-[1rem] border p-3 text-left transition-colors ${
            controller.selectedProgram?.id === program.id
              ? "border-zinc-950 bg-zinc-950 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
              : "border-zinc-900/8 bg-white/70 text-zinc-700 hover:bg-white dark:border-white/8 dark:bg-white/5 dark:text-zinc-200"
          }`}
        >
          <p className="text-sm font-semibold">{program.title}</p>
          <p className="mt-1 text-xs opacity-75">{program.label}</p>
        </button>
      ))}
    </div>
  );
}

function LaunchedOperationNotice({ controller }: { controller: OperatingModelController }) {
  const operation = controller.launchedOperation;
  if (!operation) {
    return null;
  }

  return (
    <div className="mt-4 rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{operation.label}</p>
        <StatusBadge status={operation.status} label={operation.status} />
      </div>
      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
        Operation launched for {operation.stageId ?? "selected stage"}
      </p>
    </div>
  );
}

function AssertionsPanel({ controller }: { controller: OperatingModelController }) {
  return (
    <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
        <ClipboardCheck className="size-4" />
        <p className="text-sm font-semibold">Assertions</p>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Select
          value={controller.assertionKind}
          onValueChange={(value) => controller.setAssertionKind(value as AssertionKindVM["kind"])}
        >
          <SelectTrigger>
            <SelectValue placeholder="Kind" />
          </SelectTrigger>
          <SelectContent>
            {controller.assertionKinds.map((kind) => (
              <SelectItem key={kind.kind} value={kind.kind}>
                {kind.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          value={controller.assertionCategory}
          onChange={(event) => controller.setAssertionCategory(event.target.value)}
          placeholder={controller.activePack?.assertionCategories[0] ?? "Category"}
        />
      </div>
      <Textarea
        className="mt-3"
        rows={3}
        value={controller.assertionStatement}
        onChange={(event) => controller.setAssertionStatement(event.target.value)}
        placeholder="Statement"
      />
      <Input
        className="mt-3"
        value={controller.assertionSource}
        onChange={(event) => controller.setAssertionSource(event.target.value)}
        placeholder="Source"
      />
      <Button
        className="mt-3"
        onClick={() => void controller.createAssertion()}
        disabled={controller.busyAction === "assertion:create"}
      >
        {controller.busyAction === "assertion:create" ? (
          <Spinner size="xs" className="mr-2" />
        ) : (
          <BookCheck className="size-4" />
        )}
        Save assertion
      </Button>
      <div className="mt-4 space-y-2">
        {controller.assertions.slice(0, 4).map((assertion) => (
          <AssertionCard key={assertion.id} assertion={assertion} controller={controller} />
        ))}
      </div>
    </div>
  );
}

function AssertionCard({
  assertion,
  controller,
}: {
  assertion: AssertionRecordVM;
  controller: OperatingModelController;
}) {
  return (
    <div className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={assertion.validationStatus} label={assertion.label} />
        {assertion.category ? <span className="text-xs text-zinc-500">{assertion.category}</span> : null}
      </div>
      <p className="mt-2 text-sm leading-6 text-zinc-700 dark:text-zinc-200">{assertion.statement}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {(["ACCEPT", "NEEDS_RESEARCH", "REJECT"] as const).map((decision) => (
          <Button
            key={decision}
            size="sm"
            variant="outline"
            className="h-8 rounded-full px-3 text-xs"
            onClick={() => void controller.validateAssertion(assertion, decision)}
            disabled={controller.busyAction === `assertion:${assertion.id}:${decision}`}
          >
            {decision === "NEEDS_RESEARCH" ? "Research" : decision.toLowerCase()}
          </Button>
        ))}
      </div>
    </div>
  );
}

function ArtifactsPanel({ controller }: { controller: OperatingModelController }) {
  return (
    <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
        <FileStack className="size-4" />
        <p className="text-sm font-semibold">Work Artifacts</p>
      </div>
      <ArtifactForm controller={controller} />
      <div className="mt-4 space-y-2">
        {controller.artifacts.slice(0, 4).map((artifact) => (
          <ArtifactCard key={artifact.id} artifact={artifact} controller={controller} />
        ))}
      </div>
      <ArtifactLineagePanel controller={controller} />
    </div>
  );
}

function ArtifactForm({ controller }: { controller: OperatingModelController }) {
  return (
    <>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Select value={controller.artifactType} onValueChange={controller.setArtifactType}>
          <SelectTrigger>
            <SelectValue placeholder="Artifact type" />
          </SelectTrigger>
          <SelectContent>
            {controller.artifactSchemas.map((schema) => (
              <SelectItem key={schema.id} value={schema.id}>
                {schema.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          value={controller.artifactTitle}
          onChange={(event) => controller.setArtifactTitle(event.target.value)}
          placeholder="Title"
        />
      </div>
      <Textarea
        className="mt-3"
        rows={4}
        value={controller.artifactContent}
        onChange={(event) => controller.setArtifactContent(event.target.value)}
        placeholder="Draft content"
      />
      <Button
        className="mt-3"
        onClick={() => void controller.createArtifact()}
        disabled={controller.busyAction === "artifact:create"}
      >
        {controller.busyAction === "artifact:create" ? (
          <Spinner size="xs" className="mr-2" />
        ) : (
          <FileStack className="size-4" />
        )}
        Save artifact
      </Button>
      <Textarea
        className="mt-3"
        rows={2}
        value={controller.revisionContent}
        onChange={(event) => controller.setRevisionContent(event.target.value)}
        placeholder="Revision content or requested change"
      />
      <Button
        className="mt-3"
        variant="outline"
        onClick={() => void controller.createArtifactRevision()}
        disabled={!controller.selectedArtifactId || controller.busyAction?.includes(":revision")}
      >
        <GitBranch className="size-4" />
        Add revision
      </Button>
    </>
  );
}

function ArtifactCard({ artifact, controller }: { artifact: WorkArtifactVM; controller: OperatingModelController }) {
  return (
    <div
      data-testid={`artifact-card-${artifact.id}`}
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
          onClick={() => void controller.loadArtifactLineage(artifact.id)}
          disabled={controller.busyAction === `artifact:${artifact.id}:lineage`}
        >
          Lineage
        </Button>
        {(["ACCEPT", "EDIT"] as const).map((decision) => (
          <Button
            key={decision}
            size="sm"
            variant="outline"
            className="h-8 rounded-full px-3 text-xs"
            onClick={() => void controller.validateArtifact(artifact, decision)}
            disabled={controller.busyAction === `artifact:${artifact.id}:${decision}`}
          >
            {decision.toLowerCase()}
          </Button>
        ))}
      </div>
    </div>
  );
}

function ArtifactLineagePanel({ controller }: { controller: OperatingModelController }) {
  if (!controller.artifactLineage) {
    return null;
  }

  return (
    <div className="mt-4 rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          {controller.artifactLineage.artifact.title}
        </p>
        <StatusBadge status="lineage" label={`${controller.artifactLineage.dependencyCount} links`} />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {controller.artifactLineage.artifact.revisions.map((revision) => (
          <span
            key={revision.id}
            className={`rounded-full border px-3 py-1 text-xs ${
              revision.isCanonical
                ? "border-zinc-950 bg-zinc-950 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
                : "border-zinc-900/10 bg-white text-zinc-700 dark:border-white/10 dark:bg-white/6 dark:text-zinc-200"
            }`}
          >
            {revision.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function ValidationReworkPanel({ controller }: { controller: OperatingModelController }) {
  return (
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
        {controller.reworkPlan ? (
          <StatusBadge status={controller.reworkPlan.status} label={`${controller.reworkPlan.itemCount} items`} />
        ) : null}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          variant="outline"
          onClick={() => void controller.loadValidationPacket()}
          disabled={!controller.selectedProgram || controller.busyAction === "validation:packet"}
        >
          <ClipboardCheck className="size-4" />
          Build packet
        </Button>
        <Button
          variant="outline"
          onClick={() => void controller.createReworkPlan()}
          disabled={!controller.selectedProgram || controller.busyAction === "rework:create"}
        >
          <RotateCcw className="size-4" />
          Plan rework
        </Button>
        <Button
          onClick={() => void controller.executeReworkPlan()}
          disabled={
            !controller.reworkPlan ||
            controller.reworkPlan.status === "executed" ||
            controller.busyAction?.includes("rework:")
          }
        >
          Execute rework
        </Button>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {controller.validationPacket ? (
          <div className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
            <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Validation packet</p>
            <p className="mt-2 text-xs leading-5 text-zinc-500 dark:text-zinc-400">
              {controller.validationPacket.assertionCount} assertions · {controller.validationPacket.artifactCount}{" "}
              artifacts · {controller.validationPacket.blockingFindingCount} blockers
            </p>
          </div>
        ) : null}
        {controller.reworkPlan ? (
          <div className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
            <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              {controller.reworkPlan.triggerSummary}
            </p>
            <p className="mt-2 text-xs leading-5 text-zinc-500 dark:text-zinc-400">
              Scope {String(controller.reworkPlan.estimatedEffort.scope ?? "n/a")} ·{" "}
              {String(controller.reworkPlan.impact.impacted_stages ?? "[]")}
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function CurrentStatePanel({ controller }: { controller: OperatingModelController }) {
  return (
    <div
      data-testid={
        controller.currentProjection
          ? `state-projection-card-${controller.currentProjection.id}`
          : "state-projection-card-empty"
      }
      className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8 xl:col-span-1"
    >
      <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
        <BookCheck className="size-4" />
        <p className="text-sm font-semibold">{controller.currentProjection?.label ?? "Current State"}</p>
      </div>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zinc-700 dark:text-zinc-200">
        {controller.currentProjection?.markdownSummary || compactJson(controller.currentProjection?.state ?? {})}
      </p>
    </div>
  );
}

function EvaluationPanel({ controller }: { controller: OperatingModelController }) {
  return (
    <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
        <ClipboardCheck className="size-4" />
        <p className="text-sm font-semibold">Evaluation</p>
      </div>
      <Select value={controller.evaluationProfileId} onValueChange={controller.setEvaluationProfileId}>
        <SelectTrigger className="mt-3">
          <SelectValue placeholder="Profile" />
        </SelectTrigger>
        <SelectContent>
          {controller.evaluationProfiles.map((profile) => (
            <SelectItem key={profile.id} value={profile.id}>
              {profile.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Textarea
        className="mt-3"
        rows={3}
        value={controller.evaluationContent}
        onChange={(event) => controller.setEvaluationContent(event.target.value)}
        placeholder="Content to evaluate"
      />
      <Textarea
        className="mt-3"
        rows={3}
        value={controller.evaluationInputs}
        onChange={(event) => controller.setEvaluationInputs(event.target.value)}
        placeholder='Structured inputs JSON, for example {"metrics":{"roas":3.5}}'
      />
      <Textarea
        className="mt-3"
        rows={3}
        value={controller.metricPeriodInputs}
        onChange={(event) => controller.setMetricPeriodInputs(event.target.value)}
        placeholder='Metric period JSON, for example {"roas":3.5,"email_open_rate":20}'
      />
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          onClick={() => void controller.startEvaluation()}
          disabled={controller.busyAction === "evaluation:evaluate"}
        >
          {controller.busyAction === "evaluation:evaluate" ? (
            <Spinner size="xs" className="mr-2" />
          ) : (
            <ClipboardCheck className="size-4" />
          )}
          Evaluate
        </Button>
        <Button
          variant="outline"
          onClick={() => void controller.createMetricPeriod()}
          disabled={controller.busyAction === "metric-period:create"}
        >
          {controller.busyAction === "metric-period:create" ? (
            <Spinner size="xs" className="mr-2" />
          ) : (
            <CalendarClock className="size-4" />
          )}
          Save Metrics
        </Button>
      </div>
      {controller.evaluation ? (
        <div className="mt-3 rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
          <StatusBadge status={controller.evaluation.status} label={controller.evaluation.status} />
          <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-200">
            Score {controller.evaluation.score ?? "n/a"} · {controller.evaluation.blockingFindingCount} blocking
          </p>
        </div>
      ) : null}
      <ScorecardPanel evaluation={controller.evaluation} />
      <RecommendedOperationsPanel
        evaluation={controller.evaluation}
        operationTemplates={controller.operationTemplates}
        onLaunch={(operation, reason) => void controller.launchRecommendedOperation(operation, reason)}
      />
    </div>
  );
}

function PolicyPanel({ controller }: { controller: OperatingModelController }) {
  return (
    <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
        <ShieldCheck className="size-4" />
        <p className="text-sm font-semibold">Policy</p>
      </div>
      <Select value={controller.policyActionType} onValueChange={controller.setPolicyActionType}>
        <SelectTrigger className="mt-3">
          <SelectValue placeholder="Action" />
        </SelectTrigger>
        <SelectContent>
          {controller.policyActions.map((action) => (
            <SelectItem key={action.actionType} value={action.actionType}>
              {action.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Input
        className="mt-3"
        value={controller.policyBudget}
        onChange={(event) => controller.setPolicyBudget(event.target.value)}
        inputMode="numeric"
        placeholder="Budget"
      />
      <Button
        className="mt-3"
        onClick={() => void controller.evaluatePolicy()}
        disabled={controller.busyAction === "policy:evaluate"}
      >
        {controller.busyAction === "policy:evaluate" ? (
          <Spinner size="xs" className="mr-2" />
        ) : (
          <ShieldCheck className="size-4" />
        )}
        Evaluate
      </Button>
      <Button
        className="mt-3"
        variant="outline"
        onClick={() => void controller.executeConnectorRehearsal()}
        disabled={!controller.launchedOperation || controller.busyAction === "connector:rehearsal"}
      >
        <Wrench className="size-4" />
        Rehearse package
      </Button>
      {controller.policyEvaluation ? (
        <div className="mt-3 rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
          <StatusBadge status={controller.policyEvaluation.status} label={controller.policyEvaluation.riskLevel} />
          <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-200">
            {controller.policyEvaluation.actionType} · {controller.policyEvaluation.status.replaceAll("_", " ")}
          </p>
        </div>
      ) : null}
      {controller.packageReceipt ? (
        <div className="mt-3 rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
          <StatusBadge
            status={controller.packageReceipt.status}
            label={controller.packageReceipt.dryRun ? "Rehearsal" : controller.packageReceipt.status}
          />
          <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-200">
            {controller.packageReceipt.label} · {controller.packageReceipt.sideEffects}
          </p>
        </div>
      ) : null}
    </div>
  );
}
