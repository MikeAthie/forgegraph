import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, CheckCircle2, Layers3, ShieldCheck, Sparkles } from "lucide-react";
import { useRouter } from "next/router";

import { QuestGuide } from "@/components/company/QuestGuide";
import DashboardLayout from "@/components/DashboardLayout";
import ProtectedRoute from "@/components/ProtectedRoute";
import {
  KeyValueGrid,
  MicroExplanation,
  Panel,
  SectionHeader,
  StatusBadge,
  Surface,
  WhyBlock,
} from "@/components/os/operations-ui";
import { Alert, AlertDescription, Button, Input, Spinner, Textarea } from "@/components/ui";
import { onboardingApi } from "@/lib/api";
import { companyRepository } from "@/domain/repositories";
import { translateProductError } from "@/domain/errors";
import {
  buildSuggestedSetupReasons,
  buildTeamCompositionReasons,
  buildCompanyProfile,
  companyPresets,
  companySkillCatalog,
  getSkillExplanation,
  inferCompanyPresetFromObjective,
  type CompanyAIAccessMode,
  type CompanyAutonomyMode,
  type CompanyDepartment,
  type CompanyPreset,
} from "@/lib/company-workspace";
import { showError, showSuccess } from "@/lib/toast";

const autonomyOptions: Array<{
  id: CompanyAutonomyMode;
  label: string;
  description: string;
}> = [
  { id: "manual", label: "Manual", description: "Nothing moves forward without explicit approval." },
  { id: "assisted", label: "Assisted", description: "Recommended for alpha. The company pauses at key review points." },
  { id: "autonomous", label: "Autonomous", description: "Keeps operating within budget and safety limits." },
];

const aiAccessOptions: Array<{
  id: CompanyAIAccessMode;
  label: string;
  description: string;
}> = [
  { id: "managed", label: "Managed", description: "Use ForgeGraph-managed model access with simple limits." },
  { id: "byok", label: "BYOK", description: "Use your own AI access when you want ForgeGraph to operate on your key." },
];

const objectiveHintExamples = [
  "Launch a marketing campaign",
  "Analyze business performance",
  "Generate legal documents",
  "Manage operations",
  "Something else",
];

const builderSteps = [
  {
    id: "objective",
    label: "Objective",
    title: "What should this company accomplish?",
    description: "Start with the business result. ForgeGraph will suggest the company setup after this step.",
  },
  {
    id: "suggestion",
    label: "Suggested Setup",
    title: "Review the suggested structure",
    description: "ForgeGraph suggests a category, team, and skills from the objective. You can accept it or adjust it.",
  },
  {
    id: "team",
    label: "Adjust",
    title: "Adjust the team",
    description: "Add or remove departments and skills until the setup matches how this company should really operate.",
  },
  {
    id: "policy",
    label: "Policy",
    title: "Choose operating rules",
    description: "Decide how independently the company should operate and how it will access AI.",
  },
  {
    id: "launch",
    label: "Launch",
    title: "Review and launch",
    description: "Sanity-check the company setup, then start the first operation when you are ready.",
  },
] as const;

type BuilderStepId = (typeof builderSteps)[number]["id"];

function ToggleChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-2 text-sm transition-colors ${
        active
          ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
          : "border-slate-900/10 bg-white/80 text-slate-700 hover:border-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:border-white/30"
      }`}
    >
      {children}
    </button>
  );
}

function getAutonomyModeSummary(mode: CompanyAutonomyMode): string {
  switch (mode) {
    case "manual":
      return "Manual means every meaningful step waits for you before work continues.";
    case "autonomous":
      return "Autonomous keeps work moving on its own until a budget or safety limit is reached.";
    default:
      return "Assisted starts work automatically and pauses only when a decision is worth your time.";
  }
}

function getAiAccessModeSummary(mode: CompanyAIAccessMode): string {
  return mode === "managed"
    ? "Managed uses ForgeGraph's AI access so you can launch immediately."
    : "BYOK uses your own API key so the company operates on your AI access.";
}

function getStepError(
  stepId: BuilderStepId,
  values: {
    companyName: string;
    objective: string;
    selectedDepartments: CompanyDepartment[];
  },
) {
  switch (stepId) {
    case "objective":
      if (!values.companyName.trim()) {
        return "Add a company name before continuing.";
      }
      return values.objective.trim() ? null : "Add a company objective before continuing.";
    case "team":
      return values.selectedDepartments.length ? null : "Select at least one department before continuing.";
    default:
      return null;
  }
}

function getNextStepLabel(stepId: BuilderStepId): string {
  switch (stepId) {
    case "objective":
      return "Review Suggested Setup";
    case "suggestion":
      return "Adjust Team";
    case "team":
      return "Choose Policy";
    case "policy":
      return "Review Launch";
    default:
      return "Continue";
  }
}

function getUniqueDepartments(presets: CompanyPreset[]) {
  const departmentMap = new Map<string, CompanyDepartment>();
  for (const preset of presets) {
    for (const department of preset.departments) {
      if (!departmentMap.has(department.id)) {
        departmentMap.set(department.id, department);
      }
    }
  }
  return Array.from(departmentMap.values());
}

function getDepartmentStageSummary(department: CompanyDepartment, index: number, total: number): string {
  if (index === 0) {
    return "Shows up early to set direction from the objective.";
  }
  if (index === total - 1) {
    return "Shows up near the end to help shape the final deliverable.";
  }
  return "Shows up in the middle to keep the work moving between handoffs.";
}

function getDepartmentBenefitSummary(department: CompanyDepartment): string {
  switch (department.id) {
    case "strategy-department":
      return "Helps you decide what to do and where the company should focus next.";
    case "operations-desk":
      return "Keeps work moving so you get an answer faster instead of losing time in handoffs.";
    case "delivery-management":
      return "Turns the plan into something usable and keeps delivery from slipping.";
    case "client-success":
      return "Packages the result so you can share it, use it, or follow through on it immediately.";
    case "research-analysis":
      return "Helps you understand what is happening, what matters, and what to change.";
    case "business-development":
      return "Turns opportunities into concrete next actions and follow-up.";
    case "finance-admin":
      return "Keeps budgets, approvals, and operating constraints visible before they become problems.";
    case "compliance-review":
      return "Reduces risk before the result reaches you or your customer.";
    case "document-drafting":
      return "Produces the written output you will actually review, send, or use.";
    case "creative-production":
      return "Produces the assets and materials you need to act on the plan.";
    default:
      return department.responsibility;
  }
}

function getCompanyOutcomeSummary(objective: string): string {
  return objective.trim() ? `"${objective.trim()}"` : "your business goal";
}

function getExpectedDeliverablePreview(objective: string) {
  const normalized = objective.trim().toLowerCase();

  if (normalized.includes("understand") || normalized.includes("performance") || normalized.includes("improve")) {
    return [
      "What changed in the business this cycle",
      "Where attention should go next",
      "A short owner-by-owner action list",
    ];
  }

  if (normalized.includes("legal") || normalized.includes("contract") || normalized.includes("document")) {
    return ["A draft document or brief", "Key risks or gaps to review", "Recommended next edits or approvals"];
  }

  if (normalized.includes("launch") || normalized.includes("campaign") || normalized.includes("marketing")) {
    return [
      "A launch-ready plan or message set",
      "The next production or outreach actions",
      "A short performance or readiness summary",
    ];
  }

  return [
    "A concise summary of what the company found or completed",
    "Recommended next actions with clear owners",
    "One deliverable you can review, share, or act on immediately",
  ];
}

function getCommandOpsHref(companyId: string, startQuest: boolean) {
  return `/companies/${companyId}${startQuest ? "?quest=1" : ""}#command-ops`;
}

function focusCommandOpsInput() {
  if (typeof document === "undefined") {
    return false;
  }

  const target = document.getElementById("command-ops");
  const input = document.querySelector<HTMLTextAreaElement>('[data-testid="operating-brief-input"]');
  if (!target || !input) {
    return false;
  }

  target.scrollIntoView({ block: "start", inline: "nearest", behavior: "smooth" });
  window.setTimeout(() => {
    input.focus({ preventScroll: true });
  }, 80);
  return true;
}

function BuilderCompanyMap({
  companyName,
  companyType,
  objective,
  departments,
  autonomyMode,
  aiAccessMode,
}: {
  companyName: string;
  companyType: string;
  objective: string;
  departments: CompanyDepartment[];
  autonomyMode: CompanyAutonomyMode;
  aiAccessMode: CompanyAIAccessMode;
}) {
  const deliverablePreview = getExpectedDeliverablePreview(objective);

  return (
    <div className="relative overflow-hidden rounded-[1.75rem] border border-slate-900/8 bg-[linear-gradient(180deg,rgba(248,250,252,0.96),rgba(241,245,249,0.92))] p-5 dark:border-white/8 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.96),rgba(15,23,42,0.9))]">
      <div className="pointer-events-none absolute inset-0 opacity-60">
        <div className="absolute left-[18%] top-[18%] h-2 w-2 rounded-full bg-sky-400/70" />
        <div className="absolute left-[48%] top-[26%] h-2 w-2 rounded-full bg-sky-400/60" />
        <div className="absolute right-[18%] top-[18%] h-2 w-2 rounded-full bg-sky-400/70" />
        <div className="absolute left-[28%] top-[44%] h-2 w-2 rounded-full bg-sky-400/60" />
        <div className="absolute right-[28%] top-[44%] h-2 w-2 rounded-full bg-sky-400/60" />
        <div className="absolute bottom-[22%] left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-emerald-400/70" />
        <div className="absolute left-[19%] top-[19%] h-px w-[30%] rotate-[12deg] bg-sky-400/35" />
        <div className="absolute right-[19%] top-[19%] h-px w-[30%] -rotate-[12deg] bg-sky-400/35" />
        <div className="absolute left-[29%] top-[44%] h-[24%] w-px bg-sky-400/28" />
        <div className="absolute right-[29%] top-[44%] h-[24%] w-px bg-sky-400/28" />
        <div className="absolute left-1/2 top-[26%] h-[42%] w-px -translate-x-1/2 bg-sky-400/28" />
      </div>

      <div className="relative">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status="active" label={companyType} />
          <StatusBadge status={autonomyMode} label={autonomyMode} />
          <StatusBadge
            status={aiAccessMode === "managed" ? "active" : "paused"}
            label={aiAccessMode === "managed" ? "Managed" : "BYOK"}
          />
        </div>

        <div className="mt-4 rounded-[1.35rem] border border-slate-900/8 bg-white/80 px-4 py-4 shadow-[0_18px_40px_-32px_rgba(15,23,42,0.45)] dark:border-white/8 dark:bg-white/8">
          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Company</p>
          <p className="mt-2 text-lg font-semibold text-slate-950 dark:text-slate-50">{companyName}</p>
          <MicroExplanation className="mt-2">
            {objective || "Add an objective to see the company take shape."}
          </MicroExplanation>
        </div>

        <div className="mt-5 grid gap-3">
          {departments.slice(0, 4).map((department, index) => (
            <div
              key={department.id}
              className={`rounded-[1.2rem] border px-4 py-4 backdrop-blur ${
                index === 0
                  ? "border-sky-800/14 bg-sky-50/90 dark:border-sky-200/14 dark:bg-sky-500/12"
                  : "border-slate-900/8 bg-white/76 dark:border-white/8 dark:bg-white/6"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">{department.label}</p>
                <span className="rounded-full border border-slate-900/8 px-2.5 py-1 text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:border-white/10 dark:text-slate-300">
                  {index === 0 ? "Starts" : index === departments.slice(0, 4).length - 1 ? "Finishes" : "Handoff"}
                </span>
              </div>
              <MicroExplanation className="mt-2">{department.responsibility}</MicroExplanation>
            </div>
          ))}
        </div>

        <div className="mt-5 rounded-[1.35rem] border border-emerald-800/12 bg-emerald-50/85 px-4 py-4 dark:border-emerald-200/15 dark:bg-emerald-500/10">
          <p className="text-[11px] uppercase tracking-[0.18em] text-emerald-900/70 dark:text-emerald-100/75">
            Expected first deliverable
          </p>
          <ul className="mt-3 space-y-2">
            {deliverablePreview.map((line) => (
              <li key={line} className="flex gap-2 text-sm leading-6 text-emerald-950/85 dark:text-emerald-50/85">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </div>

        <MicroExplanation className="mt-4">
          ForgeGraph connects these departments as one operating flow under the hood, so the company can move work from
          objective to deliverable without exposing technical internals.
        </MicroExplanation>
      </div>
    </div>
  );
}

export function CompanyBuilderForm() {
  const router = useRouter();
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [selectedPresetId, setSelectedPresetId] = useState(companyPresets[0].id);
  const [companyName, setCompanyName] = useState("Northstar Company");
  const [objective, setObjective] = useState("");
  const [selectedDepartmentIds, setSelectedDepartmentIds] = useState<string[]>(
    companyPresets[0].departments.map((department) => department.id),
  );
  const [selectedSkills, setSelectedSkills] = useState<string[]>(companyPresets[0].skills);
  const [autonomyMode, setAutonomyMode] = useState<CompanyAutonomyMode>("assisted");
  const [aiAccessMode, setAiAccessMode] = useState<CompanyAIAccessMode>("managed");
  const [byokApiKey, setByokApiKey] = useState("");
  const [operationBrief, setOperationBrief] = useState(
    "Launch the first operating cycle and produce a useful deliverable.",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [questModeEnabled, setQuestModeEnabled] = useState(false);
  const [guidePromptVisible, setGuidePromptVisible] = useState(false);

  const currentStep = builderSteps[currentStepIndex] ?? builderSteps[0];
  const selectedPreset = useMemo(
    () => companyPresets.find((preset) => preset.id === selectedPresetId) ?? companyPresets[0],
    [selectedPresetId],
  );
  const availableDepartments = useMemo(() => getUniqueDepartments(companyPresets), []);
  const selectedDepartments = availableDepartments.filter((department) =>
    selectedDepartmentIds.includes(department.id),
  );
  const selectedSkillHighlights = selectedSkills.slice(0, 4);
  const suggestionReasons = useMemo(
    () => buildSuggestedSetupReasons(objective, selectedPreset, selectedDepartments),
    [objective, selectedDepartments, selectedPreset],
  );
  const teamReasons = useMemo(() => buildTeamCompositionReasons(selectedDepartments), [selectedDepartments]);
  const deliverablePreview = useMemo(() => getExpectedDeliverablePreview(objective), [objective]);
  const questSteps = useMemo(
    () => [
      {
        id: "objective",
        targetId: "builder-objective-step",
        title: "Tell ForgeGraph what you want this company to accomplish.",
        description:
          "Start with the outcome. ForgeGraph will shape the company around the goal instead of making you design a system first.",
        placement: "right" as const,
      },
      {
        id: "suggested-setup",
        targetId: "builder-suggested-setup-step",
        title: "We suggest this structure based on your goal.",
        description:
          "You are seeing the first operating model ForgeGraph inferred from the objective, plus a short explanation of why it picked it.",
        placement: "right" as const,
      },
      {
        id: "team",
        targetId: "builder-team-step",
        title: "These departments will work together to complete the task.",
        description:
          "Each department has a visible job, so you can decide quickly whether the team matches the business need.",
        placement: "left" as const,
      },
      {
        id: "launch",
        targetId: "builder-launch-step",
        title: "Start your first operation.",
        description:
          "This turns the company from a setup into active work and opens the workspace where you can watch it operate.",
        placement: "left" as const,
      },
    ],
    [],
  );

  const reviewProfile = useMemo(
    () =>
      buildCompanyProfile({
        companyName,
        companyType: selectedPreset.label,
        objective,
        departments: selectedDepartments,
        skills: selectedSkills,
        autonomyMode,
        aiAccessMode,
      }),
    [aiAccessMode, autonomyMode, companyName, objective, selectedDepartments, selectedPreset.label, selectedSkills],
  );

  useEffect(() => {
    let mounted = true;

    void onboardingApi
      .list()
      .then((milestones) => {
        if (!mounted) {
          return;
        }
        const guidedMilestone = milestones.find((item) => item.key === "company_first_run_explained");
        setGuidePromptVisible(!guidedMilestone?.completed);
      })
      .catch(() => {
        if (mounted) {
          setGuidePromptVisible(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!router.isReady) {
      return;
    }
    const guideParam = router.query.guide;
    const shouldOpenGuide =
      guideParam === "1" ||
      guideParam === "true" ||
      (Array.isArray(guideParam) && (guideParam.includes("1") || guideParam.includes("true")));
    if (shouldOpenGuide) {
      setGuidePromptVisible(false);
      setQuestModeEnabled(true);
    }
  }, [router.isReady, router.query.guide]);

  const applyPresetSuggestion = (preset: CompanyPreset) => {
    setSelectedPresetId(preset.id);
    setSelectedDepartmentIds(preset.departments.map((department) => department.id));
    setSelectedSkills(preset.skills);
  };

  const handlePresetOverride = (presetId: string) => {
    const nextPreset = companyPresets.find((preset) => preset.id === presetId) ?? companyPresets[0];
    applyPresetSuggestion(nextPreset);
  };

  const toggleDepartment = (department: CompanyDepartment) => {
    setSelectedDepartmentIds((current) =>
      current.includes(department.id)
        ? current.filter((departmentId) => departmentId !== department.id)
        : [...current, department.id],
    );
  };

  const toggleSkill = (skill: string) => {
    setSelectedSkills((current) =>
      current.includes(skill) ? current.filter((item) => item !== skill) : [...current, skill],
    );
  };

  const moveStep = (direction: "next" | "back") => {
    if (direction === "back") {
      setError(null);
      setCurrentStepIndex((index) => Math.max(index - 1, 0));
      return;
    }

    const stepError = getStepError(currentStep.id, {
      companyName,
      objective,
      selectedDepartments,
    });
    if (stepError) {
      setError(stepError);
      return;
    }

    if (currentStep.id === "objective") {
      applyPresetSuggestion(inferCompanyPresetFromObjective(objective));
    }

    setError(null);
    setCurrentStepIndex((index) => Math.min(index + 1, builderSteps.length - 1));
  };

  const dismissQuestMode = async (reason: "skip" | "complete") => {
    setQuestModeEnabled(false);
    setGuidePromptVisible(false);
    try {
      await onboardingApi.complete("company_first_run_explained", {
        source: "builder",
        reason: reason === "skip" ? "skipped" : "complete",
      });
    } catch {
      // Ignore onboarding guide persistence failures to keep the builder moving.
    }
  };

  const handleCreateCompany = async (launchFirstOperation: boolean) => {
    if (!companyName.trim()) {
      setError("Add a company name before continuing.");
      return;
    }
    if (!objective.trim()) {
      setError("Add a company objective before continuing.");
      return;
    }
    if (selectedDepartments.length === 0) {
      setError("Select at least one department or skill for the company.");
      return;
    }
    if (aiAccessMode === "byok" && launchFirstOperation && !byokApiKey.trim()) {
      setError("Add an API key or switch AI access mode before launching the first operation.");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const profile = buildCompanyProfile(reviewProfile);
      const created = await companyRepository.create({
        profile,
        operationBrief,
        launchFirstOperation,
        byokApiKey,
      });
      const startQuest = launchFirstOperation && questModeEnabled;
      const commandOpsHref = getCommandOpsHref(created.companyId, startQuest);
      const openCommandOps = () => {
        if (typeof window !== "undefined" && window.location.pathname === `/companies/${created.companyId}`) {
          if (window.location.hash !== "#command-ops") {
            window.history.replaceState(null, "", commandOpsHref);
          }
          if (focusCommandOpsInput()) {
            return;
          }
        }
        void router.push(commandOpsHref);
      };

      if (launchFirstOperation && created.firstOperation) {
        showSuccess("Company launched", "We opened Command Ops. Use the Operating Brief there to steer the company.", {
          action: {
            label: "Open Command Ops",
            onClick: openCommandOps,
          },
          duration: 12000,
        });
      } else {
        showSuccess("Company created", "We opened Command Ops. Start the first operation from that panel.", {
          action: {
            label: "Open Command Ops",
            onClick: openCommandOps,
          },
          duration: 12000,
        });
      }

      await router.push(commandOpsHref);
    } catch (saveError: unknown) {
      setError(translateProductError(saveError, "company"));
    } finally {
      setSaving(false);
    }
  };

  const renderStepPanel = () => {
    switch (currentStep.id) {
      case "objective":
        return (
          <div data-guide-id="builder-objective-step">
            <Panel
              title="1. Objective"
              description="Tell ForgeGraph what the company should do. The system will suggest the rest."
              action={<StatusBadge status="active" label="Start here" />}
            >
              <div className="space-y-5">
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                    Company name
                  </label>
                  <Input
                    data-testid="company-name-input"
                    value={companyName}
                    onChange={(event) => setCompanyName(event.target.value)}
                    placeholder="Northstar Company"
                  />
                  <MicroExplanation>Name the company the way you would refer to it in the real world.</MicroExplanation>
                </div>

                <div className="rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] p-5 dark:border-white/8">
                  <div className="flex items-center gap-3">
                    <Sparkles className="h-4 w-4 text-slate-500 dark:text-slate-300" />
                    <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                      What do you want this company to accomplish?
                    </p>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
                    Start with the result, not the system structure. You can describe the work in your own words.
                  </p>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                    Business objective
                  </label>
                  <Textarea
                    data-testid="company-objective-input"
                    value={objective}
                    onChange={(event) => setObjective(event.target.value)}
                    rows={6}
                    placeholder="Coordinate weekly client delivery updates and send a clear action summary by Friday."
                  />
                  <MicroExplanation>
                    One sentence is enough. Write the outcome you want, not the system you think you need.
                  </MicroExplanation>
                </div>

                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                    Need a starting idea?
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {objectiveHintExamples.map((hint) => (
                      <ToggleChip
                        key={hint}
                        active={objective.trim().toLowerCase() === hint.toLowerCase()}
                        onClick={() => setObjective(hint)}
                      >
                        {hint}
                      </ToggleChip>
                    ))}
                  </div>
                </div>
              </div>
            </Panel>
          </div>
        );
      case "suggestion":
        return (
          <div data-guide-id="builder-suggested-setup-step">
            <Panel
              title="2. Suggested setup"
              description="ForgeGraph suggested this company structure from the objective. You can keep it or change it."
              action={<StatusBadge status="active" label="Auto-suggested" />}
            >
              <div className="space-y-5">
                <div className="rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] p-5 dark:border-white/8">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                    Suggested category
                  </p>
                  <p className="mt-3 text-xl font-semibold text-slate-950 dark:text-slate-50">{selectedPreset.label}</p>
                  <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                    {selectedPreset.description}
                  </p>
                  <MicroExplanation className="mt-3">
                    This is a starting shape for the company, not a fixed type you are locked into.
                  </MicroExplanation>
                </div>

                <WhyBlock
                  title={`Because your goal is ${getCompanyOutcomeSummary(objective)}, this company will`}
                  reasons={[
                    "do the first round of thinking and coordination for you instead of making you design the whole system yourself.",
                    `produce ${deliverablePreview[0]?.toLowerCase() ?? "a useful first result"} so you can judge the company by output, not setup.`,
                    `help you achieve ${deliverablePreview[2]?.toLowerCase() ?? "a result you can use immediately"} after the first launch.`,
                  ]}
                />

                <div className="rounded-[1.35rem] border border-emerald-800/12 bg-emerald-50/80 px-4 py-4 dark:border-emerald-200/15 dark:bg-emerald-500/10">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-900/75 dark:text-emerald-100/75">
                    Why this is a safe first launch
                  </p>
                  <p className="mt-3 text-sm leading-6 text-emerald-950/85 dark:text-emerald-50/85">
                    This starting setup is designed to get you to a useful first deliverable quickly. You can keep it if
                    it feels roughly right and refine it after the first result.
                  </p>
                </div>

                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                    Change the fit if needed
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {companyPresets.map((preset) => (
                      <ToggleChip
                        key={preset.id}
                        active={selectedPresetId === preset.id}
                        onClick={() => handlePresetOverride(preset.id)}
                      >
                        {preset.label}
                      </ToggleChip>
                    ))}
                  </div>
                  <MicroExplanation className="mt-3">
                    Changing the category only updates the starting team and skills. The company objective stays the
                    same.
                  </MicroExplanation>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
                    <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">Suggested departments</p>
                    <div className="mt-3 space-y-3">
                      {selectedDepartments.slice(0, 3).map((department) => (
                        <div
                          key={department.id}
                          className="rounded-[1rem] border border-slate-900/8 bg-white/70 px-3 py-3 dark:border-white/8 dark:bg-white/5"
                        >
                          <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{department.label}</p>
                          <MicroExplanation className="mt-1">
                            {getDepartmentBenefitSummary(department)}
                          </MicroExplanation>
                        </div>
                      ))}
                    </div>
                    <MicroExplanation className="mt-3">
                      These are the parts of the company most likely to help you reach a usable first result.
                    </MicroExplanation>
                  </div>
                  <div className="rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
                    <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">Suggested skills</p>
                    <div className="mt-3 space-y-3">
                      {selectedSkillHighlights.map((skill) => (
                        <div
                          key={skill}
                          className="rounded-[1rem] border border-slate-900/8 bg-white/70 px-3 py-3 dark:border-white/8 dark:bg-white/5"
                        >
                          <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{skill}</p>
                          <MicroExplanation className="mt-1">{getSkillExplanation(skill)}</MicroExplanation>
                        </div>
                      ))}
                    </div>
                    <MicroExplanation className="mt-3">
                      Skills are optional capabilities the company can lean on during the first operation.
                    </MicroExplanation>
                  </div>
                </div>
              </div>
            </Panel>
          </div>
        );
      case "team":
        return (
          <div data-guide-id="builder-team-step">
            <Panel
              title="3. Adjust the team"
              description="Fine-tune the company structure before launch."
              action={<StatusBadge status="active" label={`${selectedDepartments.length} departments`} />}
            >
              <div className="space-y-5">
                <WhyBlock title="These departments will work together because" reasons={teamReasons} />

                <div className="rounded-[1.35rem] border border-sky-800/12 bg-sky-50/80 px-4 py-4 dark:border-sky-200/15 dark:bg-sky-500/10">
                  <p className="text-sm font-semibold text-sky-950 dark:text-sky-50">
                    This team will work together to:
                  </p>
                  <ul className="mt-3 space-y-2">
                    {[
                      "understand your business",
                      "create a plan",
                      "produce usable output",
                      "tell you what to do next",
                    ].map((item) => (
                      <li key={item} className="flex gap-2 text-sm leading-6 text-sky-950/85 dark:text-sky-50/85">
                        <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-500" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                  <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">Quick decision rule</p>
                  <MicroExplanation className="mt-2">
                    If this team feels roughly right, leave it alone for the first launch. The first deliverable will
                    tell you more than extra setup time will.
                  </MicroExplanation>
                </div>

                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                    Departments
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {availableDepartments.map((department) => (
                      <ToggleChip
                        key={department.id}
                        active={selectedDepartmentIds.includes(department.id)}
                        onClick={() => toggleDepartment(department)}
                      >
                        <span data-testid={`department-chip-${department.id}`}>{department.label}</span>
                      </ToggleChip>
                    ))}
                  </div>
                  <MicroExplanation className="mt-3">
                    Departments are the actors that take the work from goal to deliverable.
                  </MicroExplanation>
                </div>

                <div className="grid gap-3">
                  {selectedDepartments.map((department, index) => (
                    <div
                      key={department.id}
                      className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8"
                    >
                      <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">{department.label}</p>
                      <MicroExplanation className="mt-2">{getDepartmentBenefitSummary(department)}</MicroExplanation>
                      <MicroExplanation className="mt-2">
                        {getDepartmentStageSummary(department, index, selectedDepartments.length)}
                      </MicroExplanation>
                    </div>
                  ))}
                </div>

                <div className="rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
                  <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">Optional skills</p>
                  <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                    Add extra skills only if they matter for the first operation.
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {companySkillCatalog.map((skill) => (
                      <ToggleChip
                        key={skill}
                        active={selectedSkills.includes(skill)}
                        onClick={() => toggleSkill(skill)}
                      >
                        <span data-testid={`skill-chip-${skill.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
                          {skill}
                        </span>
                      </ToggleChip>
                    ))}
                  </div>
                  <div className="mt-4 grid gap-2">
                    {selectedSkillHighlights.map((skill) => (
                      <div
                        key={skill}
                        className="rounded-[1rem] border border-slate-900/8 bg-white/70 px-3 py-3 dark:border-white/8 dark:bg-white/5"
                      >
                        <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{skill}</p>
                        <MicroExplanation className="mt-1">{getSkillExplanation(skill)}</MicroExplanation>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </Panel>
          </div>
        );
      case "policy":
        return (
          <Panel
            title="4. Policy"
            description="Decide what happens after launch."
            action={<StatusBadge status="paused" label="Assisted recommended" />}
          >
            <div className="grid gap-6 lg:grid-cols-2">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                  How should this company operate?
                </p>
                <div className="mt-3 space-y-3">
                  {autonomyOptions.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => setAutonomyMode(option.id)}
                      className={`w-full rounded-[1.35rem] border p-4 text-left transition-colors ${
                        autonomyMode === option.id
                          ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                          : "border-slate-900/8 bg-[var(--panel-muted)] hover:border-slate-950 dark:border-white/8 dark:hover:border-white/30"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold">{option.label}</p>
                          <p
                            className={`mt-2 text-sm leading-6 ${
                              autonomyMode === option.id
                                ? "text-white/75 dark:text-slate-700"
                                : "text-slate-600 dark:text-slate-300"
                            }`}
                          >
                            {option.description}
                          </p>
                        </div>
                        {option.id === "assisted" ? <StatusBadge status="paused" label="Recommended" /> : null}
                      </div>
                    </button>
                  ))}
                </div>
                <MicroExplanation className="mt-3">{getAutonomyModeSummary(autonomyMode)}</MicroExplanation>
                <div className="mt-4 rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                  <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                    If you launch with this mode
                  </p>
                  <MicroExplanation className="mt-2">
                    {autonomyMode === "manual"
                      ? "ForgeGraph will wait for you before meaningful work moves forward."
                      : autonomyMode === "autonomous"
                        ? "ForgeGraph will keep the company moving on its own until a limit, approval, or failure stops it."
                        : "ForgeGraph will start the work immediately and pause only when your judgment is worth using."}
                  </MicroExplanation>
                </div>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                  AI access mode
                </p>
                <div className="mt-3 space-y-3">
                  {aiAccessOptions.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => setAiAccessMode(option.id)}
                      className={`w-full rounded-[1.35rem] border p-4 text-left transition-colors ${
                        aiAccessMode === option.id
                          ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                          : "border-slate-900/8 bg-[var(--panel-muted)] hover:border-slate-950 dark:border-white/8 dark:hover:border-white/30"
                      }`}
                    >
                      <p className="text-sm font-semibold">{option.label}</p>
                      <p
                        className={`mt-2 text-sm leading-6 ${
                          aiAccessMode === option.id
                            ? "text-white/75 dark:text-slate-700"
                            : "text-slate-600 dark:text-slate-300"
                        }`}
                      >
                        {option.description}
                      </p>
                    </button>
                  ))}
                </div>
                <MicroExplanation className="mt-3">{getAiAccessModeSummary(aiAccessMode)}</MicroExplanation>
                <div className="mt-4 rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                  <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                    If you launch with this AI mode
                  </p>
                  <MicroExplanation className="mt-2">
                    {aiAccessMode === "managed"
                      ? "ForgeGraph will use its built-in AI access so you can launch now without more setup."
                      : "ForgeGraph will use your key for the company’s work, so launch depends on your AI access being ready."}
                  </MicroExplanation>
                </div>

                {aiAccessMode === "byok" ? (
                  <div className="mt-4 rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
                    <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">Bring your own key</p>
                    <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                      Enter one API key if you want the company to operate on your own AI access.
                    </p>
                    <Input
                      data-testid="company-byok-api-key-input"
                      className="mt-4"
                      type="password"
                      value={byokApiKey}
                      onChange={(event) => setByokApiKey(event.target.value)}
                      placeholder="sk-proj-example"
                    />
                  </div>
                ) : null}
              </div>
            </div>
          </Panel>
        );
      case "launch":
        return (
          <div data-guide-id="builder-launch-step">
            <Panel
              title="5. Launch"
              description="Review the setup, then launch the first operation."
              action={<StatusBadge status="active" label="Ready to launch" />}
            >
              <KeyValueGrid
                columns={1}
                items={[
                  { label: "Suggested category", value: reviewProfile.companyType },
                  { label: "Autonomy mode", value: reviewProfile.autonomyMode },
                  { label: "AI access mode", value: reviewProfile.aiAccessMode === "managed" ? "Managed" : "BYOK" },
                  { label: "Departments", value: `${reviewProfile.departments.length} selected` },
                ]}
              />

              <div className="mt-4 rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                  Objective
                </p>
                <p className="mt-3 text-sm leading-6 text-slate-700 dark:text-slate-200">{reviewProfile.objective}</p>
              </div>

              <div className="mt-4 rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                  Launch first operation
                </p>
                <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
                  ForgeGraph will open the company workspace and immediately start the first operation.
                </p>
                <div className="mt-4 space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                    First assignment
                  </label>
                  <Textarea
                    data-testid="company-operation-brief-input"
                    value={operationBrief}
                    onChange={(event) => setOperationBrief(event.target.value)}
                    rows={4}
                  />
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    Keep it short. One clear first assignment is enough to reach the first deliverable quickly.
                  </p>
                </div>
              </div>

              <div className="mt-4 rounded-[1.35rem] border border-emerald-800/12 bg-emerald-50/80 px-4 py-4 dark:border-emerald-200/15 dark:bg-emerald-500/10">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-900/75 dark:text-emerald-100/75">
                  Preview outcome
                </p>
                <p className="mt-3 text-sm font-semibold text-emerald-950 dark:text-emerald-50">
                  When you launch, this company will produce:
                </p>
                <ul className="mt-3 space-y-2">
                  {["A clear plan", "Concrete actions", "A result you can use immediately"].map((item) => (
                    <li key={item} className="flex gap-2 text-sm leading-6 text-emerald-950/85 dark:text-emerald-50/85">
                      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
                <div className="mt-4 rounded-[1rem] border border-emerald-800/10 bg-white/75 px-3 py-3 text-sm leading-6 text-emerald-950/85 dark:border-emerald-200/12 dark:bg-white/6 dark:text-emerald-50/85">
                  Example: &ldquo;Next week, focus on X, do Y first, and assign Z to keep the business moving.&rdquo;
                </div>
              </div>

              <WhyBlock
                title="Why launch from here"
                reasons={[
                  "The company setup is ready, so the next useful thing is to start real work.",
                  "Your first operation becomes the clearest test of whether the objective, team, and policies make sense.",
                ]}
                className="mt-4"
              />

              <div className="mt-4 rounded-[1.5rem] border border-dashed border-slate-900/12 px-4 py-4 text-sm leading-6 text-slate-600 dark:border-white/12 dark:text-slate-300">
                After you click launch: ForgeGraph creates the company, applies{" "}
                <span className="font-medium">{autonomyMode}</span> control, uses{" "}
                <span className="font-medium">{aiAccessMode === "managed" ? "Managed" : "BYOK"}</span> AI mode, and
                starts the first operation.
              </div>

              <div className="mt-5 flex flex-wrap gap-3">
                <Button
                  data-testid="company-create-submit"
                  onClick={() => void handleCreateCompany(true)}
                  disabled={saving}
                >
                  {saving ? <Spinner size="xs" className="mr-2" /> : <CheckCircle2 className="h-4 w-4" />}
                  Create company and launch first operation
                </Button>
                <Button variant="outline" onClick={() => void handleCreateCompany(false)} disabled={saving}>
                  Create company without launch
                </Button>
                <Button asChild variant="outline">
                  <Link href="/companies">View companies</Link>
                </Button>
              </div>
            </Panel>
          </div>
        );
    }
  };

  return (
    <ProtectedRoute>
      <DashboardLayout
        inspector={
          <div className="space-y-4 2xl:sticky 2xl:top-[6.5rem]">
            <Surface className="overflow-hidden">
              <div className="border-b border-slate-900/8 px-6 py-6 dark:border-white/8">
                <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">
                  Operating preview
                </p>
                <h3 className="mt-3 text-xl font-semibold text-slate-950 dark:text-slate-50">Company shape</h3>
                <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
                  See the company as a working system, not a form. The visual below previews the team, flow, and likely
                  deliverable.
                </p>
              </div>
              <div className="px-6 py-6">
                <BuilderCompanyMap
                  companyName={reviewProfile.companyName}
                  companyType={reviewProfile.companyType}
                  objective={reviewProfile.objective}
                  departments={reviewProfile.departments}
                  autonomyMode={reviewProfile.autonomyMode}
                  aiAccessMode={reviewProfile.aiAccessMode}
                />
              </div>
            </Surface>
          </div>
        }
      >
        <div className="space-y-6">
          <QuestGuide
            active={questModeEnabled}
            title="Guided first operation"
            steps={questSteps}
            onSkip={() => {
              void dismissQuestMode("skip");
            }}
            onComplete={() => {
              void dismissQuestMode("complete");
            }}
          />

          <SectionHeader
            eyebrow="Create Company"
            title="Define the objective first"
            description="ForgeGraph should adapt to the business, not force the business into system terms. Start with the goal, then review the suggested setup."
            action={
              <Button asChild variant="outline" className="rounded-full">
                <Link href="/workflows">
                  Advanced editor
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            }
          />

          {guidePromptVisible ? (
            <Surface
              data-testid="company-guide-prompt"
              className="border-sky-900/10 bg-sky-50/80 px-5 py-4 dark:border-sky-200/15 dark:bg-sky-500/10"
            >
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div className="flex min-w-0 gap-3">
                  <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-sky-700 shadow-sm dark:bg-white/10 dark:text-sky-100">
                    <Sparkles className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">Guided setup is available</p>
                    <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">
                      Start the focused walkthrough when useful. The builder stays ready for direct setup.
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    className="rounded-full"
                    onClick={() => {
                      setGuidePromptVisible(false);
                      setQuestModeEnabled(true);
                    }}
                  >
                    Start guided setup
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="rounded-full"
                    onClick={() => {
                      void dismissQuestMode("skip");
                    }}
                  >
                    Dismiss
                  </Button>
                </div>
              </div>
            </Surface>
          ) : null}

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <Panel title={`Step ${currentStepIndex + 1} of ${builderSteps.length}`} description={currentStep.description}>
            <div className="grid gap-3 lg:grid-cols-5">
              {builderSteps.map((step, index) => {
                const active = index === currentStepIndex;
                const completed = index < currentStepIndex;
                return (
                  <button
                    key={step.id}
                    type="button"
                    onClick={() => setCurrentStepIndex(index)}
                    className={`rounded-[1.25rem] border px-4 py-4 text-left transition-colors ${
                      active
                        ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                        : "border-slate-900/8 bg-[var(--panel-muted)] hover:border-slate-950 dark:border-white/8 dark:hover:border-white/30"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold">{step.label}</p>
                      {completed ? <StatusBadge status="active" label="Done" /> : null}
                    </div>
                    <p
                      className={`mt-2 text-sm leading-6 ${active ? "text-white/75 dark:text-slate-700" : "text-slate-600 dark:text-slate-300"}`}
                    >
                      {step.title}
                    </p>
                  </button>
                );
              })}
            </div>
          </Panel>

          <div className="grid gap-6 2xl:grid-cols-[1.18fr_0.82fr]">
            <div className="space-y-6">
              {renderStepPanel()}

              <div className="flex flex-wrap items-center justify-between gap-3">
                <Button variant="outline" onClick={() => moveStep("back")} disabled={currentStepIndex === 0 || saving}>
                  <ArrowLeft className="h-4 w-4" />
                  Back
                </Button>
                {currentStep.id !== "launch" ? (
                  <Button onClick={() => moveStep("next")}>
                    {getNextStepLabel(currentStep.id)}
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                ) : null}
              </div>
            </div>

            <div className="space-y-6">
              <Panel title="Launch summary" description="The essentials you are about to launch.">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-[1.25rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Company
                    </p>
                    <p className="mt-2 text-sm font-semibold text-slate-950 dark:text-slate-50">
                      {reviewProfile.companyName}
                    </p>
                    <MicroExplanation className="mt-2">{reviewProfile.companyType}</MicroExplanation>
                  </div>
                  <div className="rounded-[1.25rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Team size
                    </p>
                    <p className="mt-2 text-sm font-semibold text-slate-950 dark:text-slate-50">
                      {reviewProfile.departments.length} departments
                    </p>
                    <MicroExplanation className="mt-2">
                      {selectedSkills.length
                        ? `${selectedSkills.length} supporting skills included`
                        : "No extra skills selected"}
                    </MicroExplanation>
                  </div>
                  <div className="rounded-[1.25rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Autonomy
                    </p>
                    <StatusBadge status={reviewProfile.autonomyMode} label={reviewProfile.autonomyMode} />
                    <MicroExplanation className="mt-2">
                      {reviewProfile.autonomyMode === "assisted"
                        ? "Starts work and pauses only when a human decision matters."
                        : reviewProfile.autonomyMode === "manual"
                          ? "Waits for you before meaningful work continues."
                          : "Keeps moving until a limit, approval, or failure stops it."}
                    </MicroExplanation>
                  </div>
                  <div className="rounded-[1.25rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      AI mode
                    </p>
                    <StatusBadge
                      status={reviewProfile.aiAccessMode === "managed" ? "active" : "paused"}
                      label={reviewProfile.aiAccessMode === "managed" ? "Managed" : "BYOK"}
                    />
                    <MicroExplanation className="mt-2">
                      {reviewProfile.aiAccessMode === "managed"
                        ? "Launches immediately on ForgeGraph-managed AI access."
                        : "Launches on your own AI access once your key is ready."}
                    </MicroExplanation>
                  </div>
                </div>
              </Panel>

              <Panel
                title="What you will operate next"
                description="The workspace opens around work, results, and decisions."
              >
                <div className="grid gap-3">
                  {[
                    {
                      title: "Operations",
                      icon: <Layers3 className="h-4 w-4" />,
                      body: "See departments working and handing the task forward.",
                    },
                    {
                      title: "Approvals",
                      icon: <ShieldCheck className="h-4 w-4" />,
                      body: "Step in only when the company needs a real decision.",
                    },
                    {
                      title: "Deliverable",
                      icon: <CheckCircle2 className="h-4 w-4" />,
                      body: "Review one concrete output you can act on or share.",
                    },
                    {
                      title: "Next move",
                      icon: <Sparkles className="h-4 w-4" />,
                      body: "Launch again, refine the objective, retry, or change AI mode.",
                    },
                  ].map((item) => (
                    <div
                      key={item.title}
                      className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8"
                    >
                      <div className="flex items-center gap-2 text-slate-950 dark:text-slate-50">
                        {item.icon}
                        <p className="text-sm font-semibold">{item.title}</p>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{item.body}</p>
                    </div>
                  ))}
                </div>
              </Panel>
            </div>
          </div>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
