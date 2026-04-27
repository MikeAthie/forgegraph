import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { AlertTriangle, ArrowRight, Bot, Building2, PauseCircle, PlayCircle, RotateCcw, Settings2 } from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import { QuestGuide } from "@/components/company/QuestGuide";
import ProtectedRoute from "@/components/ProtectedRoute";
import {
  EmptyBlock,
  InspectorPanel,
  MicroExplanation,
  Panel,
  SectionHeader,
  StatusBadge,
  WhyBlock,
  formatCompactNumber,
  formatDateTime,
} from "@/components/os/operations-ui";
import { Alert, AlertDescription, Button, Input, Spinner, Textarea } from "@/components/ui";
import {
  approvalsApi,
  getApiErrorMessage,
  graphsApi,
  onboardingApi,
  runsApi,
  type GraphDetail,
  type RunDetail,
  type RunListItem,
} from "@/lib/api";
import {
  buildCompanyGraphJson,
  buildCompanyProfile,
  buildOperationInput,
  getDepartmentExplanation,
  getCompanyProfileFromGraph,
  getCompanyStatus,
  getCurrentDepartmentLabel,
  getDepartmentProgress,
  summarizeDeliverable,
  translateFailure,
  translateRunStatus,
  type CompanyAIAccessMode,
  type CompanyAutonomyMode,
  type CompanyProfile,
} from "@/lib/company-workspace";
import type { GraphVersion } from "@/lib/graph-types";
import { showError, showSuccess } from "@/lib/toast";

type CompanyWorkspaceShellProps = {
  companyId: string;
  company: GraphDetail | null;
  latestVersion: GraphVersion | null;
  operations: RunListItem[];
  operationDetails: RunDetail[];
  pendingApprovalCount: number;
  loading: boolean;
  error: string | null;
  onRefresh: () => Promise<void>;
  questMode?: boolean;
};

function getProgressTone(status: "pending" | "running" | "completed" | "failed") {
  switch (status) {
    case "completed":
      return { dot: "bg-emerald-500", line: "bg-emerald-300/70 dark:bg-emerald-500/30", title: "Handed off" };
    case "running":
      return { dot: "bg-sky-500 ring-4 ring-sky-500/15", line: "bg-slate-300 dark:bg-white/15", title: "Working now" };
    case "failed":
      return {
        dot: "bg-rose-500 ring-4 ring-rose-500/15",
        line: "bg-slate-300 dark:bg-white/15",
        title: "Needs attention",
      };
    default:
      return { dot: "bg-slate-300 dark:bg-white/15", line: "bg-slate-300 dark:bg-white/15", title: "Queued next" };
  }
}

function describeOperationMomentum(
  progress: Array<{ label: string; status: "pending" | "running" | "completed" | "failed" }>,
  currentDepartment: string,
  userStatus: "queued" | "running" | "completed" | "failed" | "paused",
) {
  const activeStep = progress.find((step) => step.status === "running");
  const failedStep = progress.find((step) => step.status === "failed");
  const nextStep = progress.find((step) => step.status === "pending");

  if (failedStep) {
    return `${failedStep.label} needs attention before the operation can continue.`;
  }
  if (activeStep) {
    return nextStep
      ? `${activeStep.label} is working now. ${nextStep.label} is next.`
      : `${activeStep.label} is finishing the final part of this operation.`;
  }
  if (userStatus === "completed") {
    return `${currentDepartment} completed the last handoff and the deliverable is ready to review.`;
  }
  if (userStatus === "paused") {
    return `${currentDepartment} is waiting for a decision before work can continue.`;
  }
  return "The company is preparing this operation to begin.";
}

function OperationsList({
  runs,
  runDetails,
  latestVersion,
}: {
  runs: RunListItem[];
  runDetails: RunDetail[];
  latestVersion: GraphVersion | null;
}) {
  const detailMap = new Map(runDetails.map((run) => [run.id, run]));

  if (!runs.length) {
    return (
      <EmptyBlock
        title="No operations yet"
        description="Launch the first operation to see company work move through departments, tasks, and deliverables."
      />
    );
  }

  return (
    <div className="space-y-4">
      {runs.map((run) => {
        const detail = detailMap.get(run.id);
        const progress = detail ? getDepartmentProgress(detail, latestVersion?.graph_json ?? null) : [];
        const currentDepartment = detail
          ? getCurrentDepartmentLabel(detail, latestVersion?.graph_json ?? null)
          : "Queued";
        const currentDepartmentExplanation = getDepartmentExplanation(
          currentDepartment,
          latestVersion?.graph_json ?? null,
        );
        const deliverablePreview = detail
          ? summarizeDeliverable(detail)
          : "Deliverable will appear once this operation finishes.";
        const userStatus = translateRunStatus(String(run.status));
        const momentum = describeOperationMomentum(progress, currentDepartment, userStatus);

        return (
          <div
            key={run.id}
            className="rounded-[1.4rem] border border-slate-900/8 bg-[var(--panel-muted)] px-5 py-5 dark:border-white/8"
          >
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-3">
                  <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                    Operation {run.id.slice(0, 8)}
                  </p>
                  <StatusBadge status={userStatus} label={userStatus} />
                  <p className="text-xs text-slate-500 dark:text-slate-400">Started {formatDateTime(run.started_at)}</p>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
                  Current department:{" "}
                  <span className="font-medium text-slate-900 dark:text-slate-100">{currentDepartment}</span>
                </p>
                <MicroExplanation className="mt-2">{currentDepartmentExplanation}</MicroExplanation>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">{momentum}</p>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <Button asChild size="sm" className="rounded-full">
                  <Link href={`/executions/${run.id}`}>Inspect operation</Link>
                </Button>
              </div>
            </div>

            <div className="mt-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                Progress through departments
              </p>
              <div className="mt-4 space-y-3">
                {progress.length ? (
                  progress.map((step, index) => {
                    const tone = getProgressTone(step.status);
                    return (
                      <div key={`${run.id}-${step.label}`} className="grid grid-cols-[1rem_1fr] gap-3">
                        <div className="flex flex-col items-center pt-1">
                          <span className={`h-3 w-3 rounded-full ${tone.dot}`} />
                          {index < progress.length - 1 ? <span className={`mt-2 h-full w-px ${tone.line}`} /> : null}
                        </div>
                        <div className="rounded-[1rem] border border-slate-900/8 bg-white/70 px-3 py-3 dark:border-white/8 dark:bg-white/5">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{step.label}</p>
                            <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                              {tone.title}
                            </p>
                          </div>
                          <MicroExplanation className="mt-2">
                            {getDepartmentExplanation(step.label, latestVersion?.graph_json ?? null)}
                          </MicroExplanation>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <StatusBadge status="pending" label="Preparing operation" />
                )}
              </div>
            </div>

            <div className="mt-4 rounded-[1.2rem] border border-slate-900/8 bg-white/70 px-4 py-4 dark:border-white/8 dark:bg-white/5">
              <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                Latest deliverable preview
              </p>
              <p className="mt-3 text-sm leading-6 text-slate-700 dark:text-slate-200">{deliverablePreview}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FailureCard({
  failure,
  onRetry,
}: {
  failure: NonNullable<ReturnType<typeof translateFailure>>;
  onRetry: () => Promise<void>;
}) {
  return (
    <div className="rounded-[1.3rem] border border-rose-800/12 bg-rose-50/80 px-4 py-4 dark:border-rose-200/15 dark:bg-rose-500/10">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-rose-600 dark:text-rose-300" />
            <p className="text-sm font-semibold text-rose-900 dark:text-rose-100">{failure.title}</p>
          </div>
          <p className="mt-2 text-xs font-semibold uppercase tracking-[0.16em] text-rose-700/80 dark:text-rose-100/70">
            What happened
          </p>
          <p className="mt-2 text-sm leading-6 text-rose-900/85 dark:text-rose-100/85">{failure.summary}</p>
          <p className="mt-4 text-xs font-semibold uppercase tracking-[0.16em] text-rose-700/80 dark:text-rose-100/70">
            What you can do next
          </p>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-rose-900/80 dark:text-rose-100/80">
            {failure.nextSteps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button size="sm" className="rounded-full" onClick={() => void onRetry()}>
            Retry
          </Button>
          <Button asChild size="sm" variant="outline" className="rounded-full">
            <a href="#company-controls">Switch AI access mode</a>
          </Button>
          <Button asChild size="sm" variant="outline" className="rounded-full">
            <a href="#company-controls">Edit objective</a>
          </Button>
        </div>
      </div>
      {failure.technicalDetails ? (
        <details className="mt-4 rounded-2xl border border-rose-800/12 bg-white/80 px-4 py-3 text-sm dark:border-rose-200/15 dark:bg-white/5">
          <summary className="cursor-pointer font-medium text-rose-900 dark:text-rose-100">Technical details</summary>
          <pre className="mt-3 whitespace-pre-wrap text-xs leading-6 text-rose-900/80 dark:text-rose-100/80">
            {failure.technicalDetails}
          </pre>
        </details>
      ) : null}
    </div>
  );
}

export function CompanyWorkspaceShell({
  companyId,
  company,
  latestVersion,
  operations,
  operationDetails,
  pendingApprovalCount,
  loading,
  error,
  onRefresh,
  questMode = false,
}: CompanyWorkspaceShellProps) {
  const router = useRouter();
  const profile = useMemo(
    () =>
      getCompanyProfileFromGraph(company ?? { name: "Company", description: "" }, latestVersion?.graph_json ?? null),
    [company, latestVersion?.graph_json],
  );
  const [launching, setLaunching] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [savingObjective, setSavingObjective] = useState(false);
  const [savingCompanyState, setSavingCompanyState] = useState(false);
  const [companyPaused, setCompanyPaused] = useState(profile.companyStatus === "Paused by operator");
  const [operationBrief, setOperationBrief] = useState(
    "Run the next operating cycle and produce a useful deliverable.",
  );
  const companyStatus = useMemo(
    () => getCompanyStatus(operationDetails.length ? operationDetails : operations, pendingApprovalCount),
    [operationDetails, operations, pendingApprovalCount],
  );
  const [editableObjective, setEditableObjective] = useState(profile.objective);
  const [editableAutonomyMode, setEditableAutonomyMode] = useState<CompanyAutonomyMode>(profile.autonomyMode);
  const [editableAIAccessMode, setEditableAIAccessMode] = useState<CompanyAIAccessMode>(profile.aiAccessMode);
  const [questMilestoneComplete, setQuestMilestoneComplete] = useState(false);
  const [questPhase, setQuestPhase] = useState<"workspace" | "deliverable" | "done">("workspace");

  useEffect(() => {
    setEditableObjective(profile.objective);
    setEditableAutonomyMode(profile.autonomyMode);
    setEditableAIAccessMode(profile.aiAccessMode);
    setCompanyPaused(profile.companyStatus === "Paused by operator");
  }, [profile.aiAccessMode, profile.autonomyMode, profile.companyStatus, profile.objective]);

  useEffect(() => {
    if (!questMode) {
      setQuestMilestoneComplete(true);
      setQuestPhase("done");
      return;
    }

    let mounted = true;
    void onboardingApi
      .list()
      .then((milestones) => {
        if (!mounted) {
          return;
        }
        const guideMilestone = milestones.find((item) => item.key === "company_first_run_explained");
        const completed = Boolean(guideMilestone?.completed);
        setQuestMilestoneComplete(completed);
        if (completed) {
          setQuestPhase("done");
          return;
        }

        if (typeof window !== "undefined") {
          const storedPhase = window.sessionStorage.getItem(`forgegraph:first-run-quest:${companyId}`);
          if (storedPhase === "deliverable" || storedPhase === "done") {
            setQuestPhase(storedPhase);
          }
        }
      })
      .catch(() => {
        if (mounted) {
          setQuestMilestoneComplete(true);
          setQuestPhase("done");
        }
      });

    return () => {
      mounted = false;
    };
  }, [companyId, questMode]);

  const displayedCompanyStatus = companyPaused ? "Paused by operator" : companyStatus;

  const latestFailedRun = useMemo(
    () => operationDetails.find((run) => translateRunStatus(String(run.status)) === "failed") ?? null,
    [operationDetails],
  );
  const failure = useMemo(
    () => (latestFailedRun ? translateFailure(latestFailedRun, latestVersion?.graph_json ?? null) : null),
    [latestFailedRun, latestVersion?.graph_json],
  );
  const latestCompletedOutputs = useMemo(
    () =>
      operationDetails
        .filter((run) => translateRunStatus(String(run.status)) === "completed")
        .slice(0, 3)
        .map((run) => ({
          id: run.id,
          preview: summarizeDeliverable(run),
        })),
    [operationDetails],
  );
  const workspaceGuideActive = questMode && !questMilestoneComplete && questPhase === "workspace";
  const deliverableGuideActive =
    questMode && !questMilestoneComplete && questPhase === "deliverable" && latestCompletedOutputs.length > 0;
  const workspaceQuestSteps = useMemo(
    () => [
      {
        id: "workspace",
        targetId: "company-operations-panel",
        title: "Watch your company operate.",
        description:
          "This area shows the work moving through departments so you can see what is happening right now and what comes next.",
        placement: "left" as const,
      },
    ],
    [],
  );
  const deliverableQuestSteps = useMemo(
    () => [
      {
        id: "deliverable",
        targetId: "company-latest-outputs",
        title: "This is the result your company produced.",
        description:
          "Completed operations leave readable deliverables here so you can decide whether to launch the next cycle, retry, or tighten the objective.",
        placement: "left" as const,
      },
    ],
    [],
  );
  const runningOperation = useMemo(
    () => operationDetails.find((run) => translateRunStatus(String(run.status)) === "running") ?? null,
    [operationDetails],
  );
  const nextAction = useMemo(() => {
    if (failure) {
      return {
        title: "Needs attention now",
        body: "A department failed. Retry the work first if the request is still valid, or tighten the objective before launching again.",
        tone: "rose" as const,
      };
    }
    if (pendingApprovalCount > 0) {
      return {
        title: "Review approvals next",
        body: `${pendingApprovalCount} operation${pendingApprovalCount === 1 ? "" : "s"} are waiting on a human decision before the company can continue.`,
        tone: "amber" as const,
      };
    }
    if (companyPaused) {
      return {
        title: "Resume the company when you are ready",
        body: "New work is paused. Resume the company to let the next operation start.",
        tone: "slate" as const,
      };
    }
    if (!operations.length) {
      return {
        title: "Launch the first operation",
        body: "The company shell is ready. Start one focused assignment to reach the first deliverable quickly.",
        tone: "emerald" as const,
      };
    }
    if (runningOperation) {
      return {
        title: "Work is already in motion",
        body: `${getCurrentDepartmentLabel(runningOperation, latestVersion?.graph_json ?? null)} is actively working right now. Review progress or let the company finish this cycle.`,
        tone: "sky" as const,
      };
    }
    return {
      title: "Start the next operating cycle",
      body: "The last deliverable is ready. Launch the next operation when you want the company to keep moving.",
      tone: "emerald" as const,
    };
  }, [companyPaused, failure, latestVersion?.graph_json, operations.length, pendingApprovalCount, runningOperation]);

  const finishQuest = async (reason: "skip" | "complete") => {
    setQuestMilestoneComplete(true);
    setQuestPhase("done");
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(`forgegraph:first-run-quest:${companyId}`, "done");
    }
    try {
      await onboardingApi.complete("company_first_run_explained", {
        source: "workspace",
        reason,
        company_id: companyId,
      });
    } catch {
      // Ignore guide persistence errors to keep the workspace responsive.
    }
    if (router.query.quest) {
      void router.replace({ pathname: `/companies/${companyId}` }, undefined, { shallow: true });
    }
  };

  const advanceWorkspaceQuest = () => {
    setQuestPhase("deliverable");
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(`forgegraph:first-run-quest:${companyId}`, "deliverable");
    }
  };

  const handleLaunchOperation = async () => {
    if (!latestVersion) {
      showError("Company setup is incomplete", "Finish creating the company before launching an operation.");
      return;
    }
    if (companyPaused) {
      showError("Company is paused", "Resume the company before launching another operation.");
      return;
    }

    setLaunching(true);
    try {
      await runsApi.start({
        graph_version_id: latestVersion.id,
        llm_mode: editableAIAccessMode,
        provider: profile.intelligenceProvider,
        credential_id: profile.byokCredentialId ?? undefined,
        input_json: buildOperationInput(
          buildCompanyProfile({
            ...profile,
            objective: editableObjective,
            autonomyMode: editableAutonomyMode,
            aiAccessMode: editableAIAccessMode,
          }),
          operationBrief,
        ),
      });
      showSuccess("Operation launched", "The company is now running the next operation.");
      await onRefresh();
    } catch (launchError: unknown) {
      showError("Operation failed to launch", getApiErrorMessage(launchError, "Unable to start the operation."));
    } finally {
      setLaunching(false);
    }
  };

  const handleRetryFailedOperation = async () => {
    if (!latestFailedRun) {
      showError("Nothing to retry", "No failed operation is currently available.");
      return;
    }

    setRetrying(true);
    try {
      await runsApi.replay(latestFailedRun.id, {
        llm_mode: editableAIAccessMode,
        provider: profile.intelligenceProvider,
        credential_id: profile.byokCredentialId ?? undefined,
      });
      showSuccess("Retry started", "The failed operation has been requeued.");
      await onRefresh();
    } catch (retryError: unknown) {
      showError("Retry failed", getApiErrorMessage(retryError, "Unable to retry the failed operation."));
    } finally {
      setRetrying(false);
    }
  };

  const handleSaveObjective = async () => {
    if (!company) {
      return;
    }

    setSavingObjective(true);
    try {
      await graphsApi.update(company.id, {
        name: profile.companyName,
        description: editableObjective,
      });

      if (latestVersion) {
        const nextProfile: CompanyProfile = buildCompanyProfile({
          ...profile,
          objective: editableObjective,
          autonomyMode: editableAutonomyMode,
          aiAccessMode: editableAIAccessMode,
          companyStatus: companyPaused ? "Paused by operator" : companyStatus,
        });
        const nextGraphJson = buildCompanyGraphJson(nextProfile);
        await graphsApi.createVersion(company.id, { graph_json: nextGraphJson });
      }

      showSuccess("Company updated", "The objective and operating settings were saved.");
      await onRefresh();
    } catch (saveError: unknown) {
      showError("Update failed", getApiErrorMessage(saveError, "Unable to update the company objective."));
    } finally {
      setSavingObjective(false);
    }
  };

  const handleToggleCompanyPause = async () => {
    if (!company || !latestVersion) {
      showError("No operating model available", "Save a company operating model before changing company state.");
      return;
    }

    const nextPaused = !companyPaused;
    setSavingCompanyState(true);
    try {
      const nextProfile = buildCompanyProfile({
        ...profile,
        objective: editableObjective,
        autonomyMode: editableAutonomyMode,
        aiAccessMode: editableAIAccessMode,
        companyStatus: nextPaused ? "Paused by operator" : "Ready to launch",
      });
      const nextGraphJson = buildCompanyGraphJson(nextProfile);
      await graphsApi.createVersion(company.id, { graph_json: nextGraphJson });
      setCompanyPaused(nextPaused);
      showSuccess(
        nextPaused ? "Company paused" : "Company resumed",
        nextPaused
          ? "New operations are paused until you resume the company."
          : "The company can launch operations again.",
      );
      await onRefresh();
    } catch (saveError: unknown) {
      showError(
        nextPaused ? "Pause failed" : "Resume failed",
        getApiErrorMessage(saveError, "Unable to update the company operating state."),
      );
    } finally {
      setSavingCompanyState(false);
    }
  };

  return (
    <ProtectedRoute>
      <DashboardLayout
        inspector={
          <InspectorPanel
            title={profile.companyName}
            subtitle="Debug details stay collapsed here so the main shell can stay in company language."
            sections={[
              {
                title: "Company status",
                content: (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span>Status</span>
                      <StatusBadge
                        status={
                          displayedCompanyStatus === "Needs attention"
                            ? "failed"
                            : displayedCompanyStatus === "Operating"
                              ? "running"
                              : displayedCompanyStatus === "Paused by operator"
                                ? "paused"
                                : "pending"
                        }
                        label={displayedCompanyStatus}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Pending approvals</span>
                      <span>{pendingApprovalCount}</span>
                    </div>
                  </div>
                ),
              },
              {
                title: "Debug",
                content: (
                  <details className="text-sm">
                    <summary className="cursor-pointer font-medium">Show internal identifiers</summary>
                    <div className="mt-3 space-y-2 text-xs leading-6">
                      <div>Graph ID: {companyId}</div>
                      <div>Version ID: {latestVersion?.id ?? "None"}</div>
                      <div>Latest run ID: {operations[0]?.id ?? "None"}</div>
                    </div>
                  </details>
                ),
              },
            ]}
          />
        }
      >
        <div className="space-y-6">
          <QuestGuide
            active={workspaceGuideActive}
            title="Guided first run"
            steps={workspaceQuestSteps}
            onSkip={() => {
              void finishQuest("skip");
            }}
            onComplete={advanceWorkspaceQuest}
          />
          <QuestGuide
            active={deliverableGuideActive}
            title="Guided first run"
            steps={deliverableQuestSteps}
            onSkip={() => {
              void finishQuest("skip");
            }}
            onComplete={() => {
              void finishQuest("complete");
            }}
          />

          <SectionHeader
            eyebrow="Company Workspace"
            title={profile.companyName}
            description="Operate the company from one shell: see what it is doing, what it produced, and what needs your decision next."
            action={
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="outline" className="rounded-full">
                  <Link href={`/graphs/${companyId}`}>Advanced mode</Link>
                </Button>
                <Button asChild className="rounded-full">
                  <Link href="/companies/new">
                    Create another company
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
              </div>
            }
          />

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {loading || !company ? (
            <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-slate-900/10 bg-white/70 dark:border-white/10 dark:bg-slate-950/50">
              <Spinner size="lg" />
            </div>
          ) : (
            <>
              <Panel
                title="Company Header"
                description="Primary company information translated from the current operating model and runtime state."
                className="company-header-panel"
              >
                <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
                  <div>
                    <div className="flex flex-wrap items-center gap-3">
                      <StatusBadge
                        status={
                          companyStatus === "Needs attention"
                            ? "failed"
                            : companyStatus === "Operating"
                              ? "running"
                              : "pending"
                        }
                        label={companyStatus}
                      />
                      <StatusBadge status={editableAutonomyMode} label={editableAutonomyMode} />
                      <StatusBadge
                        status={editableAIAccessMode === "managed" ? "active" : "paused"}
                        label={editableAIAccessMode === "managed" ? "Managed" : "BYOK"}
                      />
                    </div>
                    <p
                      className="mt-4 text-3xl font-semibold tracking-tight text-slate-950 dark:text-slate-50"
                      style={{ fontFamily: "var(--font-serif)" }}
                    >
                      {profile.companyName}
                    </p>
                    <p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-300">{profile.objective}</p>
                    <MicroExplanation className="mt-3">
                      The objective is the company-wide result ForgeGraph is trying to produce right now.
                    </MicroExplanation>
                  </div>

                  <div className="space-y-3">
                    <div className="rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Company Category
                      </p>
                      <p className="mt-2 text-sm font-medium text-slate-900 dark:text-slate-100">
                        {profile.companyType}
                      </p>
                      <MicroExplanation className="mt-2">
                        A starting shape that tells ForgeGraph how to organize the first team.
                      </MicroExplanation>
                    </div>
                    <div className="rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Status
                      </p>
                      <p className="mt-2 text-sm font-medium text-slate-900 dark:text-slate-100">
                        {displayedCompanyStatus}
                      </p>
                      <MicroExplanation className="mt-2">
                        Tells you whether the company is working, waiting, paused, or needs attention.
                      </MicroExplanation>
                    </div>
                    <div className="rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Autonomy Mode
                      </p>
                      <p className="mt-2 text-sm font-medium text-slate-900 dark:text-slate-100">
                        {editableAutonomyMode}
                      </p>
                      <MicroExplanation className="mt-2">
                        {editableAutonomyMode === "manual"
                          ? "Manual waits for you before work moves forward."
                          : editableAutonomyMode === "autonomous"
                            ? "Autonomous keeps the company moving until a limit or failure stops it."
                            : "Assisted keeps the company moving and pauses only when a decision matters."}
                      </MicroExplanation>
                    </div>
                    <div className="rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        AI Access Mode
                      </p>
                      <p className="mt-2 text-sm font-medium text-slate-900 dark:text-slate-100">
                        {editableAIAccessMode === "managed" ? "Managed" : "BYOK"}
                      </p>
                      <MicroExplanation className="mt-2">
                        {editableAIAccessMode === "managed"
                          ? "Managed means ForgeGraph handles the AI access so you can operate immediately."
                          : "BYOK means the company runs on your own AI access."}
                      </MicroExplanation>
                    </div>
                  </div>
                </div>
              </Panel>

              <div className="grid gap-6 2xl:grid-cols-[1.06fr_0.94fr]">
                <div data-guide-id="company-operations-panel">
                  <Panel
                    title="Operations"
                    description="Current and recent operations translated from runs into company language."
                    className="operations-panel"
                  >
                    <OperationsList runs={operations} runDetails={operationDetails} latestVersion={latestVersion} />
                  </Panel>
                </div>

                <Panel
                  title="Command Ops"
                  description="Company health, controls, and operational decisions from one command surface."
                  className="command-ops-panel"
                >
                  <div
                    className={`rounded-[1.35rem] border px-4 py-4 ${
                      nextAction.tone === "rose"
                        ? "border-rose-800/12 bg-rose-50/80 dark:border-rose-200/15 dark:bg-rose-500/10"
                        : nextAction.tone === "amber"
                          ? "border-amber-800/12 bg-amber-50/80 dark:border-amber-200/15 dark:bg-amber-500/10"
                          : nextAction.tone === "sky"
                            ? "border-sky-800/12 bg-sky-50/80 dark:border-sky-200/15 dark:bg-sky-500/10"
                            : "border-emerald-800/12 bg-emerald-50/80 dark:border-emerald-200/15 dark:bg-emerald-500/10"
                    }`}
                  >
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-300">
                      Next best action
                    </p>
                    <div className="mt-3 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">{nextAction.title}</p>
                        <p className="mt-2 text-sm leading-6 text-slate-700 dark:text-slate-200">{nextAction.body}</p>
                      </div>
                      <div className="flex shrink-0 flex-wrap gap-2">
                        {failure ? (
                          <Button size="sm" className="rounded-full" onClick={() => void handleRetryFailedOperation()}>
                            Retry now
                          </Button>
                        ) : pendingApprovalCount > 0 ? (
                          <Button asChild size="sm" className="rounded-full">
                            <Link href="/inbox">Review approvals</Link>
                          </Button>
                        ) : companyPaused ? (
                          <Button size="sm" className="rounded-full" onClick={() => void handleToggleCompanyPause()}>
                            Resume company
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            className="rounded-full"
                            onClick={() => void handleLaunchOperation()}
                            disabled={launching}
                          >
                            Launch operation
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Active operations
                      </p>
                      <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                        {formatCompactNumber(
                          operations.filter((run) => translateRunStatus(String(run.status)) === "running").length,
                        )}
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Failed operations
                      </p>
                      <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                        {formatCompactNumber(
                          operations.filter((run) => translateRunStatus(String(run.status)) === "failed").length,
                        )}
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Pending approvals
                      </p>
                      <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                        {formatCompactNumber(pendingApprovalCount)}
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        AI mode and usage
                      </p>
                      <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                        {editableAIAccessMode === "managed" ? "Managed" : "BYOK"}
                      </p>
                      <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                        {operations.length} total operation{operations.length === 1 ? "" : "s"} recorded in this company
                        workspace.
                      </p>
                    </div>
                  </div>

                  <WhyBlock
                    title="Why you are seeing this"
                    reasons={
                      failure
                        ? [
                            "A department could not finish its part of the operation.",
                            "Retrying is the fastest way to check whether the issue was temporary or whether the objective needs to change.",
                          ]
                        : pendingApprovalCount > 0
                          ? [
                              "The company reached a point where a human decision is required.",
                              "Approvals are shown first because the operation cannot continue until you respond.",
                            ]
                          : runningOperation
                            ? [
                                `${getCurrentDepartmentLabel(runningOperation, latestVersion?.graph_json ?? null)} is actively working right now.`,
                                "The command surface shifts toward monitoring until the operation finishes or something needs your intervention.",
                              ]
                            : [
                                "There is no blocked work right now, so the best next move is to launch another operation.",
                                "This area keeps the next decision visible instead of making you hunt through metrics.",
                              ]
                    }
                    className="mt-5"
                  />

                  {failure ? (
                    <div className="mt-5">
                      <FailureCard failure={failure} onRetry={handleRetryFailedOperation} />
                    </div>
                  ) : null}

                  <div
                    id="company-controls"
                    className="mt-5 rounded-[1.5rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8"
                  >
                    <div className="flex items-center gap-2 text-slate-950 dark:text-slate-50">
                      <Settings2 className="h-4 w-4" />
                      <p className="text-sm font-semibold">Controls</p>
                    </div>

                    <div className="mt-4 space-y-4">
                      <div>
                        <label className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                          Objective
                        </label>
                        <Textarea
                          className="mt-2"
                          rows={4}
                          value={editableObjective}
                          onChange={(event) => setEditableObjective(event.target.value)}
                        />
                      </div>

                      <div className="grid gap-4 md:grid-cols-2">
                        <div>
                          <label className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                            Autonomy mode
                          </label>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {(["manual", "assisted", "autonomous"] as CompanyAutonomyMode[]).map((mode) => (
                              <button
                                key={mode}
                                type="button"
                                onClick={() => setEditableAutonomyMode(mode)}
                                className={`rounded-full border px-3 py-2 text-sm transition-colors ${
                                  editableAutonomyMode === mode
                                    ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                                    : "border-slate-900/10 bg-white/80 text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"
                                }`}
                              >
                                {mode}
                              </button>
                            ))}
                          </div>
                          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                            {editableAutonomyMode === "manual"
                              ? "Nothing meaningful runs forward without you."
                              : editableAutonomyMode === "autonomous"
                                ? "The company keeps moving on its own until a limit or failure stops it."
                                : "The company works on its own and pauses only at key decision points."}
                          </p>
                        </div>

                        <div>
                          <label className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                            AI access mode
                          </label>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {(["managed", "byok"] as CompanyAIAccessMode[]).map((mode) => (
                              <button
                                key={mode}
                                type="button"
                                onClick={() => setEditableAIAccessMode(mode)}
                                className={`rounded-full border px-3 py-2 text-sm transition-colors ${
                                  editableAIAccessMode === mode
                                    ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                                    : "border-slate-900/10 bg-white/80 text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"
                                }`}
                              >
                                {mode === "managed" ? "Managed" : "BYOK"}
                              </button>
                            ))}
                          </div>
                          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                            {editableAIAccessMode === "managed"
                              ? "Managed uses ForgeGraph's AI access so you can keep operating immediately."
                              : "BYOK uses your own API key and is best when you want the company to run on your AI access."}
                          </p>
                        </div>
                      </div>

                      <div>
                        <label className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                          Launch operation
                        </label>
                        <Input
                          data-testid="company-launch-operation-input"
                          className="mt-2"
                          value={operationBrief}
                          onChange={(event) => setOperationBrief(event.target.value)}
                          placeholder="Run the next company operation..."
                        />
                        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                          Use one clear instruction. The company will turn it into work across the selected departments.
                        </p>
                      </div>

                      <div className="flex flex-wrap gap-3">
                        <Button
                          data-testid="company-launch-operation-button"
                          onClick={() => void handleLaunchOperation()}
                          disabled={launching || companyPaused}
                        >
                          {launching ? <Spinner size="xs" className="mr-2" /> : <PlayCircle className="h-4 w-4" />}
                          Launch operation
                        </Button>
                        <Button
                          data-testid="company-retry-operation-button"
                          variant="outline"
                          onClick={() => void handleRetryFailedOperation()}
                          disabled={retrying || !latestFailedRun}
                        >
                          {retrying ? <Spinner size="xs" className="mr-2" /> : <RotateCcw className="h-4 w-4" />}
                          Retry failed operation
                        </Button>
                        <Button
                          data-testid="company-update-objective-button"
                          variant="outline"
                          onClick={() => void handleSaveObjective()}
                          disabled={savingObjective}
                        >
                          {savingObjective ? <Spinner size="xs" className="mr-2" /> : <Bot className="h-4 w-4" />}
                          Update objective
                        </Button>
                        <Button
                          variant="outline"
                          onClick={() => void handleToggleCompanyPause()}
                          disabled={savingCompanyState}
                        >
                          {savingCompanyState ? (
                            <Spinner size="xs" className="mr-2" />
                          ) : companyPaused ? (
                            <PlayCircle className="h-4 w-4" />
                          ) : (
                            <PauseCircle className="h-4 w-4" />
                          )}
                          {companyPaused ? "Resume company" : "Pause company"}
                        </Button>
                      </div>
                    </div>
                  </div>

                  <div data-guide-id="company-latest-outputs" className="mt-5">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Latest outputs
                    </p>
                    <MicroExplanation className="mt-2">
                      Completed operations leave readable deliverables here so you can quickly decide whether to launch,
                      refine, or retry.
                    </MicroExplanation>
                    <div className="mt-3 space-y-3">
                      {latestCompletedOutputs.length ? (
                        latestCompletedOutputs.map((item) => (
                          <div
                            key={item.id}
                            className="rounded-[1.2rem] border border-slate-900/8 bg-white/70 px-4 py-4 dark:border-white/8 dark:bg-white/5"
                          >
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                                Deliverable from operation {item.id.slice(0, 8)}
                              </p>
                              <Button asChild size="sm" variant="outline" className="rounded-full">
                                <Link href={`/executions/${item.id}`}>Open</Link>
                              </Button>
                            </div>
                            <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">{item.preview}</p>
                          </div>
                        ))
                      ) : (
                        <EmptyBlock
                          title="No deliverables yet"
                          description="Completed operations will surface their latest outputs here."
                        />
                      )}
                    </div>
                  </div>
                </Panel>
              </div>
            </>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
