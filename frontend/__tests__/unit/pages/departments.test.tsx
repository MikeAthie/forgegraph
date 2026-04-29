import fs from "node:fs";
import path from "node:path";
import type { ReactNode } from "react";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/router";

import { departmentRepository } from "@/domain/repositories";
import type { DepartmentActivityVM } from "@/domain/translation";
import DepartmentsPage from "@/pages/departments";

jest.mock("@/components/DashboardLayout", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <div data-testid="dashboard-layout">{children}</div>,
}));

jest.mock("@/components/ProtectedRoute", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
}));

jest.mock("next/router");

jest.mock("@/domain/repositories", () => ({
  departmentRepository: {
    listActivity: jest.fn(),
  },
}));

const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
const mockDepartmentRepository = departmentRepository as jest.Mocked<typeof departmentRepository>;

const operationRef = {
  id: "operation-1",
  name: "Weekly retention strategy",
  status: "running",
  role: "Currently shaping the operation",
  currentStage: "Retention Strategy is participating",
  startedAt: "2026-04-05T10:00:00Z",
} as const;

const activities: DepartmentActivityVM[] = [
  {
    department: {
      id: "retention",
      label: "Retention Strategy",
      name: "Retention Strategy",
      role: "Owns retention planning",
      responsibility: "Turns churn signals into retention recommendations.",
      purpose: "Turns churn signals into retention recommendations.",
      tools: [],
      category: "department",
      activityStatus: "waiting",
      currentFocus: "Analyzing customer churn signals to propose retention strategies.",
      activeTaskCount: 1,
      pendingDecisionCount: 1,
      totalCostUsd: 1.24,
    },
    focus: {
      objective: "Analyzing customer churn signals to propose retention strategies.",
      reasoning: "Comparing renewal risk, recent support issues, and margin before recommending outreach.",
    },
    proposals: [
      {
        id: "proposal-1",
        description: "Deploy a retention campaign for accounts with declining weekly usage.",
        status: "awaiting approval",
        operation: operationRef,
        createdAt: "2026-04-05T10:04:00Z",
      },
    ],
    tasks: [
      {
        id: "task-1",
        operationId: "operation-1",
        departmentId: "retention",
        departmentName: "Retention Strategy",
        title: "Score at-risk accounts",
        status: "running",
        summary: "Derived from the retention proposal and used to prepare the outreach plan.",
        startedAt: "2026-04-05T10:01:00Z",
        endedAt: null,
        durationMs: null,
      },
    ],
    operations: [operationRef],
    blockers: [
      {
        id: "blocker-1",
        description: "Waiting for approval to deploy the retention campaign.",
        status: "waiting",
        operation: operationRef,
      },
    ],
    approvals: [
      {
        id: "approval-1",
        operationId: "operation-1",
        operationName: "Weekly retention strategy",
        companyName: "Operadora Horizonte",
        departmentId: "retention",
        departmentName: "Retention Strategy",
        status: "pending",
        promptMessage: "Approve the retention campaign before customer outreach starts.",
        requiredFields: [],
        result: null,
        createdAt: "2026-04-05T10:04:00Z",
        resolvedAt: null,
        estimatedCost: 0.12,
        risk: "medium",
        consequence: "This approval affects customer-facing behavior.",
        blastRadius: "The operation will continue after approval.",
      },
    ],
  },
  {
    department: {
      id: "finance",
      label: "Finance Review",
      name: "Finance Review",
      role: "Owns budget judgment",
      responsibility: "Checks spend and margin before commitments.",
      purpose: "Checks spend and margin before commitments.",
      tools: [],
      category: "department",
      activityStatus: "idle",
      currentFocus: "Ready to evaluate spend when a proposal needs financial judgment.",
      activeTaskCount: 0,
      pendingDecisionCount: 0,
      totalCostUsd: 0,
    },
    focus: {
      objective: "Ready to evaluate spend when a proposal needs financial judgment.",
      reasoning: "No approval or task currently requires finance input.",
    },
    proposals: [],
    tasks: [],
    operations: [],
    blockers: [],
    approvals: [],
  },
];

const flushPromises = async () => {
  await Promise.resolve();
  await Promise.resolve();
};

const renderPage = async () => {
  await act(async () => {
    render(<DepartmentsPage />);
    await flushPromises();
  });
};

describe("Departments page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseRouter.mockReturnValue({
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      pathname: "/departments",
      query: {},
      asPath: "/departments",
    } as any);
    mockDepartmentRepository.listActivity.mockResolvedValue(activities);
  });

  it("renders departments as a thinking and proposal surface", async () => {
    await renderPage();

    expect(mockDepartmentRepository.listActivity).toHaveBeenCalledTimes(1);
    expect(screen.getByText("How the company thinks")).toBeInTheDocument();
    expect(screen.getAllByText("Retention Strategy").length).toBeGreaterThan(0);
    expect(screen.getByText("Owns retention planning")).toBeInTheDocument();
    expect(screen.getAllByText(/analyzing customer churn signals/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Current focus")).toBeInTheDocument();
    expect(screen.getByText("Active proposals")).toBeInTheDocument();
    expect(screen.getByText("Operation participation")).toBeInTheDocument();
    expect(screen.getByText("Blockers and approvals")).toBeInTheDocument();
  });

  it("shows proposals before task work and links operations through canonical routes", async () => {
    await renderPage();

    expect(screen.getByText(/deploy a retention campaign/i)).toBeInTheDocument();
    expect(screen.getByText("Tasks from operations")).toBeInTheDocument();
    expect(screen.getByText("Score at-risk accounts")).toBeInTheDocument();
    expect(screen.getByText(/derived from the retention proposal/i)).toBeInTheDocument();

    const operationLinks = screen.getAllByRole("link", { name: /open operation/i });
    expect(operationLinks.length).toBeGreaterThan(0);
    expect(operationLinks[0]).toHaveAttribute("href", "/runs/operation-1");
  });

  it("renders blockers and allows selecting another department", async () => {
    const replace = jest.fn();
    mockUseRouter.mockReturnValue({
      push: jest.fn(),
      replace,
      prefetch: jest.fn(),
      pathname: "/departments",
      query: {},
      asPath: "/departments",
    } as any);

    await renderPage();

    expect(screen.getByText(/waiting for approval to deploy the retention campaign/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /finance review/i }));

    expect(replace).toHaveBeenCalledWith({ pathname: "/departments", query: { department: "finance" } }, undefined, {
      shallow: true,
    });
  });

  it("does not render internal terminology in the product page", async () => {
    await renderPage();

    const visibleText = document.body.textContent ?? "";
    expect(visibleText).not.toMatch(/\bgraph\b/i);
    expect(visibleText).not.toMatch(/\bnode\b/i);
    expect(visibleText).not.toMatch(/\brun\b/i);
    expect(visibleText).not.toMatch(/\bruns\b/i);
    expect(visibleText).not.toMatch(/\bexecution\b/i);
    expect(visibleText).not.toMatch(/\bworkflow\b/i);
  });

  it("uses department ViewModels rather than raw backend DTOs", () => {
    const source = fs.readFileSync(path.join(process.cwd(), "pages", "departments", "index.tsx"), "utf8");

    expect(source).toContain("DepartmentActivityVM");
    expect(source).toContain("DepartmentVM");
    expect(source).not.toMatch(/tasksApi|TaskRecord|RunDetail|RunListItem|GraphDetail|GraphListItem|NodeRunItem/);
    expect(source).not.toMatch(/execution_id|graph_id|node_id|node_runs|output_json/);
  });

  it("renders all required department detail sections", async () => {
    await renderPage();

    expect(screen.getByText("Current focus")).toBeInTheDocument();
    expect(screen.getByText("Active proposals")).toBeInTheDocument();
    expect(screen.getByText("Tasks from operations")).toBeInTheDocument();
    expect(screen.getByText("Operation participation")).toBeInTheDocument();
    expect(screen.getByText("Blockers and approvals")).toBeInTheDocument();
  });
});
