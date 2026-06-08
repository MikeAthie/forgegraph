import { useCallback, useEffect, useMemo, useReducer, type ReactNode, type SetStateAction } from "react";
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

const OPERATE_NEXT_ITEMS = [
  {
    title: "Operations",
    icon: Layers3,
    body: "See departments working and handing the task forward.",
  },
  {
    title: "Approvals",
    icon: ShieldCheck,
    body: "Step in only when the company needs a real decision.",
  },
  {
    title: "Deliverable",
    icon: CheckCircle2,
    body: "Review one concrete output you can act on or share.",
  },
  {
    title: "Next move",
    icon: Sparkles,
    body: "Launch again, refine the objective, retry, or change AI mode.",
  },
] as const;

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

const ROUTING_DEPARTMENT_ID = "routing-department";

function ToggleChip({
  active,
  disabled = false,
  onClick,
  children,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-full border px-3 py-2 text-sm transition-colors ${
        active
          ? "border-zinc-950 bg-zinc-950 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
          : "border-zinc-900/10 bg-white/80 text-zinc-700 hover:border-zinc-950 dark:border-white/10 dark:bg-white/5 dark:text-zinc-200 dark:hover:border-white/30"
      } ${disabled ? "cursor-default opacity-90" : ""}`}
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
  if (department.id === ROUTING_DEPARTMENT_ID) {
    return "Shows up first to recommend the operation and identify which departments should participate.";
  }
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
    case ROUTING_DEPARTMENT_ID:
      return "Turns the request into an operation recommendation without executing the work itself.";
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
    <div className="relative overflow-hidden rounded-[1.75rem] border border-zinc-900/8 bg-[linear-gradient(180deg,rgba(248,250,252,0.96),rgba(241,245,249,0.92))] p-5 dark:border-white/8 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.96),rgba(15,23,42,0.9))]">
      <div className="pointer-events-none absolute inset-0 opacity-60">
        <div className="absolute left-[18%] top-[18%] size-2 rounded-full bg-sky-400/70" />
        <div className="absolute left-[48%] top-[26%] size-2 rounded-full bg-sky-400/60" />
        <div className="absolute right-[18%] top-[18%] size-2 rounded-full bg-sky-400/70" />
        <div className="absolute left-[28%] top-[44%] size-2 rounded-full bg-sky-400/60" />
        <div className="absolute right-[28%] top-[44%] size-2 rounded-full bg-sky-400/60" />
        <div className="absolute bottom-[22%] left-1/2 size-2 -tranzinc-x-1/2 rounded-full bg-emerald-400/70" />
        <div className="absolute left-[19%] top-[19%] h-px w-[30%] rotate-[12deg] bg-sky-400/35" />
        <div className="absolute right-[19%] top-[19%] h-px w-[30%] -rotate-[12deg] bg-sky-400/35" />
        <div className="absolute left-[29%] top-[44%] h-[24%] w-px bg-sky-400/28" />
        <div className="absolute right-[29%] top-[44%] h-[24%] w-px bg-sky-400/28" />
        <div className="absolute left-1/2 top-[26%] h-[42%] w-px -tranzinc-x-1/2 bg-sky-400/28" />
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

        <div className="mt-4 rounded-[1.35rem] border border-zinc-900/8 bg-white/80 p-4 shadow-[0_18px_40px_-32px_rgba(15,23,42,0.45)] dark:border-white/8 dark:bg-white/8">
          <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Company</p>
          <p className="mt-2 text-lg font-semibold text-zinc-950 dark:text-zinc-50">{companyName}</p>
          <MicroExplanation className="mt-2">
            {objective || "Add an objective to see the company take shape."}
          </MicroExplanation>
        </div>

        <div className="mt-5 grid gap-3">
          {departments.slice(0, 4).map((department, index) => (
            <div
              key={department.id}
              className={`rounded-[1.2rem] border p-4 backdrop-blur ${
                index === 0
                  ? "border-sky-800/14 bg-sky-50/90 dark:border-sky-200/14 dark:bg-sky-500/12"
                  : "border-zinc-900/8 bg-white/76 dark:border-white/8 dark:bg-white/6"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{department.label}</p>
                <span className="rounded-full border border-zinc-900/8 px-2.5 py-1 text-[11px] uppercase tracking-[0.16em] text-zinc-500 dark:border-white/10 dark:text-zinc-300">
                  {index === 0 ? "Starts" : index === departments.slice(0, 4).length - 1 ? "Finishes" : "Handoff"}
                </span>
              </div>
              <MicroExplanation className="mt-2">{department.responsibility}</MicroExplanation>
            </div>
          ))}
        </div>

        <div className="mt-5 rounded-[1.35rem] border border-emerald-800/12 bg-emerald-50/85 p-4 dark:border-emerald-200/15 dark:bg-emerald-500/10">
          <p className="text-[11px] uppercase tracking-[0.18em] text-emerald-900/70 dark:text-emerald-100/75">
            Expected first deliverable
          </p>
          <ul className="mt-3 space-y-2">
            {deliverablePreview.map((line) => (
              <li key={line} className="flex gap-2 text-sm leading-6 text-emerald-950/85 dark:text-emerald-50/85">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-emerald-500" />
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

type ObjectiveStepPanelProps = {
  companyName: string;
  objective: string;
  onCompanyNameChange: (value: string) => void;
  onObjectiveChange: (value: string) => void;
};

function ObjectiveStepPanel({
  companyName,
  objective,
  onCompanyNameChange,
  onObjectiveChange,
}: ObjectiveStepPanelProps) {
  return (
    <div data-guide-id="builder-objective-step">
      <Panel
        title="1. Objective"
        description="Tell ForgeGraph what the company should do. The system will suggest the rest."
        action={<StatusBadge status="active" label="Start here" />}
      >
        <div className="space-y-5">
          <div className="space-y-2">
            <label
              htmlFor="components-company-companybuilderform-661"
              className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400"
            >
              Company name
            </label>
            <Input
              id="components-company-companybuilderform-661"
              data-testid="company-name-input"
              value={companyName}
              onChange={(event) => onCompanyNameChange(event.target.value)}
              placeholder="Northstar Company"
            />
            <MicroExplanation>Name the company the way you would refer to it in the real world.</MicroExplanation>
          </div>

          <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-5 dark:border-white/8">
            <div className="flex items-center gap-3">
              <Sparkles className="size-4 text-zinc-500 dark:text-zinc-300" />
              <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                What do you want this company to accomplish?
              </p>
            </div>
            <p className="mt-3 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
              Start with the result, not the system structure. You can describe the work in your own words.
            </p>
          </div>

          <div className="space-y-2">
            <label
              htmlFor="components-company-companybuilderform-686"
              className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400"
            >
              Business objective
            </label>
            <Textarea
              id="components-company-companybuilderform-686"
              data-testid="company-objective-input"
              value={objective}
              onChange={(event) => onObjectiveChange(event.target.value)}
              rows={6}
              placeholder="Coordinate weekly client delivery updates and send a clear action summary by Friday."
            />
            <MicroExplanation>
              One sentence is enough. Write the outcome you want, not the system you think you need.
            </MicroExplanation>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
              Need a starting idea?
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {objectiveHintExamples.map((hint) => (
                <ToggleChip
                  key={hint}
                  active={objective.trim().toLowerCase() === hint.toLowerCase()}
                  onClick={() => onObjectiveChange(hint)}
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
}

type SuggestedSetupStepPanelProps = {
  objective: string;
  selectedPreset: CompanyPreset;
  selectedPresetId: string;
  deliverablePreview: string[];
  selectedDepartments: CompanyDepartment[];
  selectedSkillHighlights: string[];
  onPresetOverride: (presetId: string) => void;
};

function SuggestedSetupStepPanel({
  objective,
  selectedPreset,
  selectedPresetId,
  deliverablePreview,
  selectedDepartments,
  selectedSkillHighlights,
  onPresetOverride,
}: SuggestedSetupStepPanelProps) {
  return (
    <div data-guide-id="builder-suggested-setup-step">
      <Panel
        title="2. Suggested setup"
        description="ForgeGraph suggested this company structure from the objective. You can keep it or change it."
        action={<StatusBadge status="active" label="Auto-suggested" />}
      >
        <div className="space-y-5">
          <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-5 dark:border-white/8">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
              Suggested category
            </p>
            <p className="mt-3 text-xl font-semibold text-zinc-950 dark:text-zinc-50">{selectedPreset.label}</p>
            <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{selectedPreset.description}</p>
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

          <div className="rounded-[1.35rem] border border-emerald-800/12 bg-emerald-50/80 p-4 dark:border-emerald-200/15 dark:bg-emerald-500/10">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-900/75 dark:text-emerald-100/75">
              Why this is a safe first launch
            </p>
            <p className="mt-3 text-sm leading-6 text-emerald-950/85 dark:text-emerald-50/85">
              This starting setup is designed to get you to a useful first deliverable quickly. You can keep it if it
              feels roughly right and refine it after the first result.
            </p>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
              Change the fit if needed
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {companyPresets.map((preset) => (
                <ToggleChip
                  key={preset.id}
                  active={selectedPresetId === preset.id}
                  onClick={() => onPresetOverride(preset.id)}
                >
                  {preset.label}
                </ToggleChip>
              ))}
            </div>
            <MicroExplanation className="mt-3">
              Changing the category only updates the starting team and skills. The company objective stays the same.
            </MicroExplanation>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
              <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Suggested departments</p>
              <div className="mt-3 space-y-3">
                {selectedDepartments.slice(0, 3).map((department) => (
                  <div
                    key={department.id}
                    className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5"
                  >
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{department.label}</p>
                    <MicroExplanation className="mt-1">{getDepartmentBenefitSummary(department)}</MicroExplanation>
                  </div>
                ))}
              </div>
              <MicroExplanation className="mt-3">
                These are the parts of the company most likely to help you reach a usable first result.
              </MicroExplanation>
            </div>
            <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
              <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Suggested skills</p>
              <div className="mt-3 space-y-3">
                {selectedSkillHighlights.map((skill) => (
                  <div
                    key={skill}
                    className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5"
                  >
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{skill}</p>
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
}

type TeamStepPanelProps = {
  selectedDepartments: CompanyDepartment[];
  teamReasons: string[];
  availableDepartments: CompanyDepartment[];
  selectedDepartmentIds: string[];
  selectedSkills: string[];
  selectedSkillHighlights: string[];
  onDepartmentToggle: (department: CompanyDepartment) => void;
  onSkillToggle: (skill: string) => void;
};

function TeamStepPanel({
  selectedDepartments,
  teamReasons,
  availableDepartments,
  selectedDepartmentIds,
  selectedSkills,
  selectedSkillHighlights,
  onDepartmentToggle,
  onSkillToggle,
}: TeamStepPanelProps) {
  return (
    <div data-guide-id="builder-team-step">
      <Panel
        title="3. Adjust the team"
        description="Fine-tune the company structure before launch."
        action={<StatusBadge status="active" label={`${selectedDepartments.length} departments`} />}
      >
        <div className="space-y-5">
          <WhyBlock title="These departments will work together because" reasons={teamReasons} />

          <div className="rounded-[1.35rem] border border-sky-800/12 bg-sky-50/80 p-4 dark:border-sky-200/15 dark:bg-sky-500/10">
            <p className="text-sm font-semibold text-sky-950 dark:text-sky-50">This team will work together to:</p>
            <ul className="mt-3 space-y-2">
              {["understand your business", "create a plan", "produce usable output", "tell you what to do next"].map(
                (item) => (
                  <li key={item} className="flex gap-2 text-sm leading-6 text-sky-950/85 dark:text-sky-50/85">
                    <span className="mt-2 size-1.5 shrink-0 rounded-full bg-sky-500" />
                    <span>{item}</span>
                  </li>
                ),
              )}
            </ul>
          </div>

          <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
            <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Quick decision rule</p>
            <MicroExplanation className="mt-2">
              If this team feels roughly right, leave it alone for the first launch. The first deliverable will tell you
              more than extra setup time will.
            </MicroExplanation>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
              Departments
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {availableDepartments.map((department) => {
                const isRoutingDepartment = department.id === ROUTING_DEPARTMENT_ID;
                return (
                  <ToggleChip
                    key={department.id}
                    active={selectedDepartmentIds.includes(department.id)}
                    disabled={isRoutingDepartment}
                    onClick={() => onDepartmentToggle(department)}
                  >
                    <span data-testid={`department-chip-${department.id}`}>
                      {department.label}
                      {isRoutingDepartment ? " (default)" : ""}
                    </span>
                  </ToggleChip>
                );
              })}
            </div>
            <MicroExplanation className="mt-3">
              Routing is included in every company. Departments think and propose; operations execute the work.
            </MicroExplanation>
          </div>

          <div className="grid gap-3">
            {selectedDepartments.map((department, index) => (
              <div
                key={department.id}
                className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
              >
                <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{department.label}</p>
                <MicroExplanation className="mt-2">{getDepartmentBenefitSummary(department)}</MicroExplanation>
                <MicroExplanation className="mt-2">
                  {getDepartmentStageSummary(department, index, selectedDepartments.length)}
                </MicroExplanation>
              </div>
            ))}
          </div>

          <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
            <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Optional skills</p>
            <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
              Add extra skills only if they matter for the first operation.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {companySkillCatalog.map((skill) => (
                <ToggleChip key={skill} active={selectedSkills.includes(skill)} onClick={() => onSkillToggle(skill)}>
                  <span data-testid={`skill-chip-${skill.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>{skill}</span>
                </ToggleChip>
              ))}
            </div>
            <div className="mt-4 grid gap-2">
              {selectedSkillHighlights.map((skill) => (
                <div
                  key={skill}
                  className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5"
                >
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{skill}</p>
                  <MicroExplanation className="mt-1">{getSkillExplanation(skill)}</MicroExplanation>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Panel>
    </div>
  );
}

type PolicyStepPanelProps = {
  autonomyMode: CompanyAutonomyMode;
  aiAccessMode: CompanyAIAccessMode;
  byokApiKey: string;
  onAutonomyModeChange: (value: CompanyAutonomyMode) => void;
  onAIAccessModeChange: (value: CompanyAIAccessMode) => void;
  onByokApiKeyChange: (value: string) => void;
};

function PolicyStepPanel({
  autonomyMode,
  aiAccessMode,
  byokApiKey,
  onAutonomyModeChange,
  onAIAccessModeChange,
  onByokApiKeyChange,
}: PolicyStepPanelProps) {
  return (
    <Panel
      title="4. Policy"
      description="Decide what happens after launch."
      action={<StatusBadge status="paused" label="Assisted recommended" />}
    >
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
            How should this company operate?
          </p>
          <div className="mt-3 space-y-3">
            {autonomyOptions.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => onAutonomyModeChange(option.id)}
                className={`w-full rounded-[1.35rem] border p-4 text-left transition-colors ${
                  autonomyMode === option.id
                    ? "border-zinc-950 bg-zinc-950 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
                    : "border-zinc-900/8 bg-[var(--panel-muted)] hover:border-zinc-950 dark:border-white/8 dark:hover:border-white/30"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold">{option.label}</p>
                    <p
                      className={`mt-2 text-sm leading-6 ${
                        autonomyMode === option.id
                          ? "text-white/75 dark:text-zinc-700"
                          : "text-zinc-600 dark:text-zinc-300"
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
          <div className="mt-4 rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
            <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">If you launch with this mode</p>
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
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
            AI access mode
          </p>
          <div className="mt-3 space-y-3">
            {aiAccessOptions.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => onAIAccessModeChange(option.id)}
                className={`w-full rounded-[1.35rem] border p-4 text-left transition-colors ${
                  aiAccessMode === option.id
                    ? "border-zinc-950 bg-zinc-950 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
                    : "border-zinc-900/8 bg-[var(--panel-muted)] hover:border-zinc-950 dark:border-white/8 dark:hover:border-white/30"
                }`}
              >
                <p className="text-sm font-semibold">{option.label}</p>
                <p
                  className={`mt-2 text-sm leading-6 ${
                    aiAccessMode === option.id ? "text-white/75 dark:text-zinc-700" : "text-zinc-600 dark:text-zinc-300"
                  }`}
                >
                  {option.description}
                </p>
              </button>
            ))}
          </div>
          <MicroExplanation className="mt-3">{getAiAccessModeSummary(aiAccessMode)}</MicroExplanation>
          <div className="mt-4 rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
            <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">If you launch with this AI mode</p>
            <MicroExplanation className="mt-2">
              {aiAccessMode === "managed"
                ? "ForgeGraph will use its built-in AI access so you can launch now without more setup."
                : "ForgeGraph will use your key for the company's work, so launch depends on your AI access being ready."}
            </MicroExplanation>
          </div>

          {aiAccessMode === "byok" ? (
            <div className="mt-4 rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
              <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Bring your own key</p>
              <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
                Enter one API key if you want the company to operate on your own AI access.
              </p>
              <Input
                data-testid="company-byok-api-key-input"
                className="mt-4"
                type="password"
                value={byokApiKey}
                onChange={(event) => onByokApiKeyChange(event.target.value)}
                placeholder="sk-proj-example"
              />
            </div>
          ) : null}
        </div>
      </div>
    </Panel>
  );
}

type LaunchStepPanelProps = {
  reviewProfile: ReturnType<typeof buildCompanyProfile>;
  selectedPreset: CompanyPreset;
  operationBrief: string;
  autonomyMode: CompanyAutonomyMode;
  aiAccessMode: CompanyAIAccessMode;
  saving: boolean;
  onOperationBriefChange: (value: string) => void;
  onCreateCompany: (launchFirstOperation: boolean) => void;
};

function LaunchStepPanel({
  reviewProfile,
  selectedPreset,
  operationBrief,
  autonomyMode,
  aiAccessMode,
  saving,
  onOperationBriefChange,
  onCreateCompany,
}: LaunchStepPanelProps) {
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
            {
              label: "Operating model",
              value: selectedPreset.operatingModelPackId ? selectedPreset.label : "Generic",
            },
            { label: "Departments", value: `${reviewProfile.departments.length} selected` },
          ]}
        />

        <div className="mt-4 rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
            Objective
          </p>
          <p className="mt-3 text-sm leading-6 text-zinc-700 dark:text-zinc-200">{reviewProfile.objective}</p>
        </div>

        <div className="mt-4 rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
            Launch first operation
          </p>
          <p className="mt-3 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
            ForgeGraph will open the company workspace and immediately start the first operation.
          </p>
          <div className="mt-4 space-y-2">
            <label
              htmlFor="components-company-companybuilderform-1094"
              className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400"
            >
              First assignment
            </label>
            <Textarea
              id="components-company-companybuilderform-1094"
              data-testid="company-operation-brief-input"
              value={operationBrief}
              onChange={(event) => onOperationBriefChange(event.target.value)}
              rows={4}
            />
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              Keep it short. One clear first assignment is enough to reach the first deliverable quickly.
            </p>
          </div>
        </div>

        <div className="mt-4 rounded-[1.35rem] border border-emerald-800/12 bg-emerald-50/80 p-4 dark:border-emerald-200/15 dark:bg-emerald-500/10">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-900/75 dark:text-emerald-100/75">
            Preview outcome
          </p>
          <p className="mt-3 text-sm font-semibold text-emerald-950 dark:text-emerald-50">
            When you launch, this company will produce:
          </p>
          <ul className="mt-3 space-y-2">
            {["A clear plan", "Concrete actions", "A result you can use immediately"].map((item) => (
              <li key={item} className="flex gap-2 text-sm leading-6 text-emerald-950/85 dark:text-emerald-50/85">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-emerald-500" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <div className="mt-4 rounded-[1rem] border border-emerald-800/10 bg-white/75 p-3 text-sm leading-6 text-emerald-950/85 dark:border-emerald-200/12 dark:bg-white/6 dark:text-emerald-50/85">
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

        <div className="mt-4 rounded-[1.5rem] border border-dashed border-zinc-900/12 p-4 text-sm leading-6 text-zinc-600 dark:border-white/12 dark:text-zinc-300">
          After you click launch: ForgeGraph creates the company, applies{" "}
          <span className="font-medium">{autonomyMode}</span> control, uses{" "}
          <span className="font-medium">{aiAccessMode === "managed" ? "Managed" : "BYOK"}</span> AI mode, and starts the
          first operation.
        </div>

        <div className="mt-5 flex flex-wrap gap-3">
          <Button data-testid="company-create-submit" onClick={() => onCreateCompany(true)} disabled={saving}>
            {saving ? <Spinner size="xs" className="mr-2" /> : <CheckCircle2 className="size-4" />}
            Create company and launch first operation
          </Button>
          <Button variant="outline" onClick={() => onCreateCompany(false)} disabled={saving}>
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

type CompanyBuilderState = {
  currentStepIndex: number;
  selectedPresetId: string;
  companyName: string;
  objective: string;
  selectedDepartmentIds: string[];
  selectedSkills: string[];
  autonomyMode: CompanyAutonomyMode;
  aiAccessMode: CompanyAIAccessMode;
  byokApiKey: string;
  operationBrief: string;
  saving: boolean;
  error: string | null;
  questModeEnabled: boolean;
  guidePromptVisible: boolean;
};

type CompanyBuilderAction = {
  patch: Partial<CompanyBuilderState> | ((state: CompanyBuilderState) => Partial<CompanyBuilderState>);
};

const initialCompanyBuilderState: CompanyBuilderState = {
  currentStepIndex: 0,
  selectedPresetId: companyPresets[0].id,
  companyName: "Northstar Company",
  objective: "",
  selectedDepartmentIds: companyPresets[0].departments.map((department) => department.id),
  selectedSkills: companyPresets[0].skills,
  autonomyMode: "assisted",
  aiAccessMode: "managed",
  byokApiKey: "",
  operationBrief: "Launch the first operating cycle and produce a useful deliverable.",
  saving: false,
  error: null,
  questModeEnabled: false,
  guidePromptVisible: false,
};

function companyBuilderReducer(state: CompanyBuilderState, action: CompanyBuilderAction): CompanyBuilderState {
  const patch = typeof action.patch === "function" ? action.patch(state) : action.patch;
  return { ...state, ...patch };
}

function resolveStateAction<T>(value: SetStateAction<T>, current: T): T {
  return typeof value === "function" ? (value as (current: T) => T)(current) : value;
}

function useCompanyBuilderFormController() {
  const router = useRouter();
  const { push } = router;
  const [builderState, dispatchBuilderState] = useReducer(companyBuilderReducer, initialCompanyBuilderState);
  const {
    currentStepIndex,
    selectedPresetId,
    companyName,
    objective,
    selectedDepartmentIds,
    selectedSkills,
    autonomyMode,
    aiAccessMode,
    byokApiKey,
    operationBrief,
    saving,
    error,
    questModeEnabled,
    guidePromptVisible,
  } = builderState;
  const setBuilderField = useCallback(
    <K extends keyof CompanyBuilderState>(key: K, value: SetStateAction<CompanyBuilderState[K]>) => {
      dispatchBuilderState({
        patch: (current) => ({ [key]: resolveStateAction(value, current[key]) }) as Partial<CompanyBuilderState>,
      });
    },
    [],
  );
  const setCurrentStepIndex = (value: SetStateAction<number>) => setBuilderField("currentStepIndex", value);
  const setSelectedPresetId = (value: SetStateAction<string>) => setBuilderField("selectedPresetId", value);
  const setCompanyName = (value: SetStateAction<string>) => setBuilderField("companyName", value);
  const setObjective = (value: SetStateAction<string>) => setBuilderField("objective", value);
  const setSelectedDepartmentIds = (value: SetStateAction<string[]>) => setBuilderField("selectedDepartmentIds", value);
  const setSelectedSkills = (value: SetStateAction<string[]>) => setBuilderField("selectedSkills", value);
  const setAutonomyMode = (value: SetStateAction<CompanyAutonomyMode>) => setBuilderField("autonomyMode", value);
  const setAiAccessMode = (value: SetStateAction<CompanyAIAccessMode>) => setBuilderField("aiAccessMode", value);
  const setByokApiKey = (value: SetStateAction<string>) => setBuilderField("byokApiKey", value);
  const setOperationBrief = (value: SetStateAction<string>) => setBuilderField("operationBrief", value);
  const setSaving = (value: SetStateAction<boolean>) => setBuilderField("saving", value);
  const setError = (value: SetStateAction<string | null>) => setBuilderField("error", value);
  const setQuestModeEnabled = useCallback(
    (value: SetStateAction<boolean>) => setBuilderField("questModeEnabled", value),
    [setBuilderField],
  );
  const setGuidePromptVisible = useCallback(
    (value: SetStateAction<boolean>) => setBuilderField("guidePromptVisible", value),
    [setBuilderField],
  );

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
  }, [setGuidePromptVisible]);

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
  }, [router.isReady, router.query.guide, setGuidePromptVisible, setQuestModeEnabled]);

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
    if (department.id === ROUTING_DEPARTMENT_ID) {
      return;
    }
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
        operatingModelPackId: selectedPreset.operatingModelPackId,
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
        void push(commandOpsHref);
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

      await push(commandOpsHref);
    } catch (saveError: unknown) {
      setError(translateProductError(saveError, "company"));
    } finally {
      setSaving(false);
    }
  };

  return {
    currentStepIndex,
    selectedPresetId,
    companyName,
    objective,
    selectedDepartmentIds,
    selectedSkills,
    autonomyMode,
    aiAccessMode,
    byokApiKey,
    operationBrief,
    saving,
    error,
    questModeEnabled,
    guidePromptVisible,
    currentStep,
    selectedPreset,
    availableDepartments,
    selectedDepartments,
    selectedSkillHighlights,
    teamReasons,
    deliverablePreview,
    questSteps,
    reviewProfile,
    setCurrentStepIndex,
    setCompanyName,
    setObjective,
    setAutonomyMode,
    setAiAccessMode,
    setByokApiKey,
    setOperationBrief,
    setGuidePromptVisible,
    setQuestModeEnabled,
    handlePresetOverride,
    toggleDepartment,
    toggleSkill,
    moveStep,
    dismissQuestMode,
    handleCreateCompany,
  };
}

type CompanyBuilderController = ReturnType<typeof useCompanyBuilderFormController>;

export function CompanyBuilderForm() {
  const controller = useCompanyBuilderFormController();
  const inspector = useMemo(() => <CompanyBuilderInspector controller={controller} />, [controller]);

  return (
    <ProtectedRoute>
      <DashboardLayout inspector={inspector}>
        <CompanyBuilderContent controller={controller} />
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function CompanyBuilderInspector({ controller }: { controller: CompanyBuilderController }) {
  const { reviewProfile } = controller;

  return (
    <div className="space-y-4 2xl:sticky 2xl:top-[6.5rem]">
      <Surface className="overflow-hidden">
        <div className="border-b border-zinc-900/8 p-6 dark:border-white/8">
          <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-400">Operating preview</p>
          <h3 className="mt-3 text-xl font-semibold text-zinc-950 dark:text-zinc-50">Company shape</h3>
          <p className="mt-3 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
            See the company as a working system, not a form. The visual below previews the team, flow, and likely
            deliverable.
          </p>
        </div>
        <div className="p-6">
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
  );
}

function CompanyBuilderContent({ controller }: { controller: CompanyBuilderController }) {
  return (
    <div className="space-y-6">
      <QuestGuide
        active={controller.questModeEnabled}
        title="Guided first operation"
        steps={controller.questSteps}
        onSkip={() => {
          void controller.dismissQuestMode("skip");
        }}
        onComplete={() => {
          void controller.dismissQuestMode("complete");
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
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        }
      />
      {controller.guidePromptVisible ? <CompanyBuilderGuidePrompt controller={controller} /> : null}
      {controller.error ? (
        <Alert variant="destructive">
          <AlertDescription>{controller.error}</AlertDescription>
        </Alert>
      ) : null}
      <BuilderStepsProgress controller={controller} />
      <div className="grid gap-6 2xl:grid-cols-[1.18fr_0.82fr]">
        <div className="space-y-6">
          <CompanyBuilderStepPanel controller={controller} />
          <CompanyBuilderNavigation controller={controller} />
        </div>
        <div className="space-y-6">
          <LaunchSummaryPanel controller={controller} />
          <OperateNextPanel />
        </div>
      </div>
    </div>
  );
}

function CompanyBuilderGuidePrompt({ controller }: { controller: CompanyBuilderController }) {
  return (
    <Surface
      data-testid="company-guide-prompt"
      className="border-sky-900/10 bg-sky-50/80 px-5 py-4 dark:border-sky-200/15 dark:bg-sky-500/10"
    >
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex min-w-0 gap-3">
          <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-white text-sky-700 shadow-sm dark:bg-white/10 dark:text-sky-100">
            <Sparkles className="size-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Guided setup is available</p>
            <p className="mt-1 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
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
              controller.setGuidePromptVisible(false);
              controller.setQuestModeEnabled(true);
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
              void controller.dismissQuestMode("skip");
            }}
          >
            Dismiss
          </Button>
        </div>
      </div>
    </Surface>
  );
}

function BuilderStepsProgress({ controller }: { controller: CompanyBuilderController }) {
  return (
    <Panel
      title={`Step ${controller.currentStepIndex + 1} of ${builderSteps.length}`}
      description={controller.currentStep.description}
    >
      <div className="grid gap-3 lg:grid-cols-5">
        {builderSteps.map((step, index) => {
          const active = index === controller.currentStepIndex;
          const completed = index < controller.currentStepIndex;
          return (
            <button
              key={step.id}
              type="button"
              onClick={() => controller.setCurrentStepIndex(index)}
              className={`rounded-[1.25rem] border p-4 text-left transition-colors ${
                active
                  ? "border-zinc-950 bg-zinc-950 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
                  : "border-zinc-900/8 bg-[var(--panel-muted)] hover:border-zinc-950 dark:border-white/8 dark:hover:border-white/30"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold">{step.label}</p>
                {completed ? <StatusBadge status="active" label="Done" /> : null}
              </div>
              <p
                className={`mt-2 text-sm leading-6 ${active ? "text-white/75 dark:text-zinc-700" : "text-zinc-600 dark:text-zinc-300"}`}
              >
                {step.title}
              </p>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

function CompanyBuilderStepPanel({ controller }: { controller: CompanyBuilderController }) {
  if (controller.currentStep.id === "objective") {
    return (
      <ObjectiveStepPanel
        companyName={controller.companyName}
        objective={controller.objective}
        onCompanyNameChange={controller.setCompanyName}
        onObjectiveChange={controller.setObjective}
      />
    );
  }

  if (controller.currentStep.id === "suggestion") {
    return (
      <SuggestedSetupStepPanel
        objective={controller.objective}
        selectedPreset={controller.selectedPreset}
        selectedPresetId={controller.selectedPresetId}
        deliverablePreview={controller.deliverablePreview}
        selectedDepartments={controller.selectedDepartments}
        selectedSkillHighlights={controller.selectedSkillHighlights}
        onPresetOverride={controller.handlePresetOverride}
      />
    );
  }

  if (controller.currentStep.id === "team") {
    return (
      <TeamStepPanel
        selectedDepartments={controller.selectedDepartments}
        teamReasons={controller.teamReasons}
        availableDepartments={controller.availableDepartments}
        selectedDepartmentIds={controller.selectedDepartmentIds}
        selectedSkills={controller.selectedSkills}
        selectedSkillHighlights={controller.selectedSkillHighlights}
        onDepartmentToggle={controller.toggleDepartment}
        onSkillToggle={controller.toggleSkill}
      />
    );
  }

  if (controller.currentStep.id === "policy") {
    return (
      <PolicyStepPanel
        autonomyMode={controller.autonomyMode}
        aiAccessMode={controller.aiAccessMode}
        byokApiKey={controller.byokApiKey}
        onAutonomyModeChange={controller.setAutonomyMode}
        onAIAccessModeChange={controller.setAiAccessMode}
        onByokApiKeyChange={controller.setByokApiKey}
      />
    );
  }

  if (controller.currentStep.id === "launch") {
    return (
      <LaunchStepPanel
        reviewProfile={controller.reviewProfile}
        selectedPreset={controller.selectedPreset}
        operationBrief={controller.operationBrief}
        autonomyMode={controller.autonomyMode}
        aiAccessMode={controller.aiAccessMode}
        saving={controller.saving}
        onOperationBriefChange={controller.setOperationBrief}
        onCreateCompany={(launchFirstOperation) => {
          void controller.handleCreateCompany(launchFirstOperation);
        }}
      />
    );
  }

  return null;
}

function CompanyBuilderNavigation({ controller }: { controller: CompanyBuilderController }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Button
        variant="outline"
        onClick={() => controller.moveStep("back")}
        disabled={controller.currentStepIndex === 0 || controller.saving}
      >
        <ArrowLeft className="size-4" />
        Back
      </Button>
      {controller.currentStep.id !== "launch" ? (
        <Button onClick={() => controller.moveStep("next")}>
          {getNextStepLabel(controller.currentStep.id)}
          <ArrowRight className="size-4" />
        </Button>
      ) : null}
    </div>
  );
}

function LaunchSummaryPanel({ controller }: { controller: CompanyBuilderController }) {
  const { reviewProfile, selectedSkills } = controller;

  return (
    <Panel title="Launch summary" description="The essentials you are about to launch.">
      <div className="grid gap-3 sm:grid-cols-2">
        <LaunchSummaryItem label="Company" value={reviewProfile.companyName} detail={reviewProfile.companyType} />
        <LaunchSummaryItem
          label="Team size"
          value={`${reviewProfile.departments.length} departments`}
          detail={
            selectedSkills.length ? `${selectedSkills.length} supporting skills included` : "No extra skills selected"
          }
        />
        <LaunchSummaryItem
          label="Autonomy"
          value={reviewProfile.autonomyMode}
          status={reviewProfile.autonomyMode}
          detail={
            reviewProfile.autonomyMode === "assisted"
              ? "Starts work and pauses only when a human decision matters."
              : reviewProfile.autonomyMode === "manual"
                ? "Waits for you before meaningful work continues."
                : "Keeps moving until a limit, approval, or failure stops it."
          }
        />
        <LaunchSummaryItem
          label="AI mode"
          value={reviewProfile.aiAccessMode === "managed" ? "Managed" : "BYOK"}
          status={reviewProfile.aiAccessMode === "managed" ? "active" : "paused"}
          detail={
            reviewProfile.aiAccessMode === "managed"
              ? "Launches immediately on ForgeGraph-managed AI access."
              : "Launches on your own AI access once your key is ready."
          }
        />
      </div>
    </Panel>
  );
}

function LaunchSummaryItem({
  detail,
  label,
  status,
  value,
}: {
  detail: string;
  label: string;
  status?: string;
  value: string;
}) {
  return (
    <div className="rounded-[1.25rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">{label}</p>
      {status ? (
        <StatusBadge status={status} label={value} />
      ) : (
        <p className="mt-2 text-sm font-semibold text-zinc-950 dark:text-zinc-50">{value}</p>
      )}
      <MicroExplanation className="mt-2">{detail}</MicroExplanation>
    </div>
  );
}

function OperateNextPanel() {
  return (
    <Panel title="What you will operate next" description="The workspace opens around work, results, and decisions.">
      <div className="grid gap-3">
        {OPERATE_NEXT_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.title}
              className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
            >
              <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
                <Icon className="size-4" />
                <p className="text-sm font-semibold">{item.title}</p>
              </div>
              <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{item.body}</p>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
