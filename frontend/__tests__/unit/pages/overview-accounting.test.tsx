import fs from "fs";
import path from "path";
import type { ReactNode } from "react";
import { act, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { overviewRepository } from "@/domain/repositories";
import type { OrganizationOverviewVM } from "@/domain/repositories/overviewRepository";
import OverviewPage from "@/pages/overview";

jest.mock("@/components/DashboardLayout", () => ({
  __esModule: true,
  default: ({ children, inspector }: { children: ReactNode; inspector?: ReactNode }) => (
    <div data-testid="dashboard-layout">
      <div>{children}</div>
      {inspector ? <aside>{inspector}</aside> : null}
    </div>
  ),
}));

jest.mock("@/components/ProtectedRoute", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

jest.mock("@/domain/repositories", () => ({
  overviewRepository: {
    get: jest.fn(),
  },
}));

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: "user-1",
      email: "operator@example.com",
      default_organization_id: "org-1",
      organization_role: "owner",
    },
    isAuthenticated: true,
    loading: false,
    error: null,
    login: jest.fn(),
    register: jest.fn(),
    logout: jest.fn(),
    checkAuth: jest.fn(),
    clearError: jest.fn(),
  }),
}));

jest.mock("@/hooks/useStateFeed", () => ({
  useStateFeed: () => ({ status: "connected" }),
}));

const repoRoot = path.resolve(__dirname, "../../../..");

const flushPromises = async () => {
  await Promise.resolve();
  await Promise.resolve();
};

function makeOverview(overrides: Partial<OrganizationOverviewVM> = {}): OrganizationOverviewVM {
  const section = {
    source: "backend_projection",
    computedAt: "2026-05-04T12:00:00Z",
    lastUpdatedAt: "2026-05-04T12:00:00Z",
    freshnessMs: 0,
    status: "fresh",
    stale: false,
    degraded: false,
  };

  return {
    organization: { id: "org-1", name: "Acme Ops" },
    summary: {
      activeDepartmentCount: 0,
      activeTaskCount: 0,
      pendingApprovalCount: 0,
      operationCount24h: 0,
      knowledgeItemCount: 0,
      totalCostUsd: 42.35,
    },
    activeDepartments: [],
    activeTasks: [],
    pendingApprovals: [],
    recentOperations: [],
    memory: {
      activeKnowledgeCount: 0,
      writeCount24h: 0,
      recentTopics: [],
      section,
    },
    running: {
      ...section,
      activeAgentCount: 0,
      runningTaskCount: 0,
      operationCount24h: 0,
    },
    blocked: {
      ...section,
      blockedTaskCount: 0,
    },
    decisions: {
      ...section,
      pendingDecisionCount: 0,
    },
    costs: {
      ...section,
      source: "backend_ledger",
      totalCostUsd: 42.35,
      currency: "USD",
    },
    failures: {
      ...section,
      source: "backend_ops",
      deadLetterCount: 0,
      taskDeadLetterCount: 0,
      eventDeadLetterCount: 0,
      runtimeIntentDeadLetterCount: 0,
      runtimeIntentLagSeconds: 0,
    },
    metricProvenance: {
      totalCostUsd: {
        source: "backend_ledger",
        computedAt: "2026-05-04T12:00:00Z",
        freshnessMs: null,
        status: "available",
        value: 42.35,
        currency: "USD",
      },
      revenue: {
        source: "backend_accounting",
        computedAt: "2026-05-04T12:00:00Z",
        freshnessMs: null,
        status: "not_instrumented",
        value: null,
        reason: "Backend revenue ledger is not instrumented yet.",
      },
      profit: {
        source: "backend_accounting",
        computedAt: "2026-05-04T12:00:00Z",
        freshnessMs: null,
        status: "not_instrumented",
        value: null,
        reason: "Backend profit ledger is not instrumented yet.",
      },
    },
    costByType: [{ type: "llm", totalCostUsd: 42.35, entryCount: 1 }],
    projection: {
      computed_at: "2026-05-04T12:00:00Z",
      last_sequence: 42,
      last_event_id: "event-1",
      lag_seconds: 0,
      status: "fresh",
      projection_lag_ms: 0,
      watermark: "2026-05-04T12:00:00Z",
    },
    operations: {
      status: "fresh",
      deadLetterCount: 0,
      taskDeadLetterCount: 0,
      eventDeadLetterCount: 0,
      runtimeIntentDeadLetterCount: 0,
      projectionStatus: "fresh",
      projectionLagSeconds: 0,
      runtimeIntentLagSeconds: 0,
    },
    generatedAt: "2026-05-04T12:00:00Z",
    ...overrides,
  };
}

async function renderOverview(overview: OrganizationOverviewVM) {
  jest.mocked(overviewRepository.get).mockResolvedValue(overview);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  await act(async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <OverviewPage />
      </QueryClientProvider>,
    );
    await flushPromises();
  });
}

describe("Overview accounting metrics", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders backend cost while revenue and profit stay unavailable", async () => {
    await renderOverview(makeOverview());

    expect((await screen.findAllByText("$42.35")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Revenue").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Profit").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Not yet instrumented").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/backend_ledger/i).length).toBeGreaterThan(0);
  });

  it("does not render unavailable cost as a real value", async () => {
    await renderOverview(
      makeOverview({
        summary: {
          ...makeOverview().summary,
          totalCostUsd: 0,
        },
        metricProvenance: {
          ...makeOverview().metricProvenance,
          totalCostUsd: {
            source: "backend_ledger",
            computedAt: "2026-05-04T12:00:00Z",
            freshnessMs: null,
            status: "not_instrumented",
            value: null,
          },
        },
        costByType: [],
      }),
    );

    expect(screen.queryByText("$42.35")).not.toBeInTheDocument();
    expect((await screen.findAllByText("Not yet instrumented")).length).toBeGreaterThanOrEqual(3);
  });

  it("renders backend projection status and lag", async () => {
    await renderOverview(
      makeOverview({
        projection: {
          computed_at: "2026-05-04T12:00:00Z",
          last_sequence: 44,
          last_event_id: "event-2",
          lag_seconds: 12.4,
          status: "degraded",
          projection_lag_ms: 12400,
          watermark: "2026-05-04T12:00:00Z",
        },
      }),
    );

    expect(await screen.findByText(/Projection degraded/i)).toBeInTheDocument();
    expect(screen.getByText(/12s lag/i)).toBeInTheDocument();
  });

  it("renders all company OS cards with backend source, freshness, and status metadata", async () => {
    await renderOverview(
      makeOverview({
        running: {
          source: "backend_projection",
          computedAt: "2026-05-04T12:00:00Z",
          lastUpdatedAt: "2026-05-04T12:00:00Z",
          freshnessMs: 25,
          status: "fresh",
          stale: false,
          degraded: false,
          activeAgentCount: 3,
          runningTaskCount: 7,
          operationCount24h: 9,
        },
        decisions: {
          source: "backend_projection",
          computedAt: "2026-05-04T12:00:00Z",
          lastUpdatedAt: "2026-05-04T12:00:00Z",
          freshnessMs: 40,
          status: "stale",
          stale: true,
          degraded: false,
          pendingDecisionCount: 2,
        },
        memory: {
          activeKnowledgeCount: 5,
          writeCount24h: 4,
          recentTopics: [],
          section: {
            source: "backend_memory",
            computedAt: "2026-05-04T12:00:00Z",
            lastUpdatedAt: "2026-05-04T12:00:00Z",
            freshnessMs: 10,
            status: "fresh",
            stale: false,
            degraded: false,
          },
        },
        failures: {
          source: "backend_ops",
          computedAt: "2026-05-04T12:00:00Z",
          lastUpdatedAt: "2026-05-04T12:00:00Z",
          freshnessMs: 50,
          status: "degraded",
          stale: false,
          degraded: true,
          deadLetterCount: 1,
          taskDeadLetterCount: 1,
          eventDeadLetterCount: 0,
          runtimeIntentDeadLetterCount: 0,
          runtimeIntentLagSeconds: 3,
        },
      }),
    );

    for (const label of [
      "Active Agents",
      "Running Tasks",
      "Blocked Decisions",
      "Cost Today",
      "Memory Writes",
      "Dead Letters",
      "Projection Lag",
      "Runtime Intent Lag",
    ]) {
      expect(await screen.findByText(label)).toBeInTheDocument();
    }
    expect(screen.getAllByText(/backend_projection · fresh/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/backend_memory · fresh/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/backend_ops · degraded/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/freshness/i).length).toBeGreaterThan(0);
  });

  it("keeps local financial metric invention out of overview sources", () => {
    const combinedSource = ["frontend/pages/overview/index.tsx", "frontend/domain/repositories/overviewRepository.ts"]
      .map((relativePath) => fs.readFileSync(path.join(repoRoot, relativePath), "utf8"))
      .join("\n");

    expect(combinedSource).not.toMatch(/\b(revenueMultiplier|profitToday|revenueToday)\b/);
    expect(combinedSource).not.toMatch(/formatCurrency\([^)]*\b(revenue|profit)\b/i);
    expect(combinedSource).toMatch(/metrics/);
    expect(combinedSource).toMatch(/Not yet instrumented/);
  });
});
