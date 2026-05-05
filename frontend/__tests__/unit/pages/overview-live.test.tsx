import type { ReactNode } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { overviewRepository } from "@/domain/repositories";
import type { OrganizationOverviewVM } from "@/domain/repositories/overviewRepository";
import OverviewPage from "@/pages/overview";

jest.mock("@/components/DashboardLayout", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
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

let mockLatestStateFeedOptions: any;

jest.mock("@/hooks/useStateFeed", () => ({
  useStateFeed: (options: any) => {
    mockLatestStateFeedOptions = options;
    return { status: "connected" };
  },
}));

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
      totalCostUsd: 12,
    },
    activeDepartments: [],
    activeTasks: [],
    pendingApprovals: [],
    recentOperations: [],
    memory: { activeKnowledgeCount: 0, writeCount24h: 0, recentTopics: [], section },
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
      totalCostUsd: 12,
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
        value: 12,
        currency: "USD",
      },
      revenue: {
        source: "backend_accounting",
        computedAt: "2026-05-04T12:00:00Z",
        freshnessMs: null,
        status: "not_instrumented",
        value: null,
      },
      profit: {
        source: "backend_accounting",
        computedAt: "2026-05-04T12:00:00Z",
        freshnessMs: null,
        status: "not_instrumented",
        value: null,
      },
    },
    costByType: [{ type: "llm", totalCostUsd: 12, entryCount: 1 }],
    projection: {
      computed_at: "2026-05-04T12:00:00Z",
      last_sequence: 1,
      state_feed_version: 1,
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

function renderOverview() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <OverviewPage />
    </QueryClientProvider>,
  );
}

describe("Overview live state feed", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockLatestStateFeedOptions = null;
  });

  it("invalidates overview from backend organization feed events", async () => {
    jest
      .mocked(overviewRepository.get)
      .mockResolvedValueOnce(makeOverview())
      .mockResolvedValueOnce(
        makeOverview({
          summary: {
            ...makeOverview().summary,
            pendingApprovalCount: 2,
          },
          pendingApprovals: [
            {
              id: "decision-1",
              operationId: null,
              taskId: null,
              departmentId: null,
              status: "pending",
              label: "budget approval",
              promptMessage: "Approve budget?",
              requestedAt: "2026-05-04T12:01:00Z",
            },
            {
              id: "decision-2",
              operationId: null,
              taskId: null,
              departmentId: null,
              status: "pending",
              label: "vendor approval",
              promptMessage: "Approve vendor?",
              requestedAt: "2026-05-04T12:02:00Z",
            },
          ],
          projection: {
            ...makeOverview().projection!,
            state_feed_version: 2,
          },
        }),
      );

    await act(async () => {
      renderOverview();
      await flushPromises();
    });

    await waitFor(() => expect(mockLatestStateFeedOptions?.organizationId).toBe("org-1"));

    await act(async () => {
      mockLatestStateFeedOptions.onEvent({
        type: "decision.created",
        event_id: "evt-2",
        state_version: 2,
        requires_refetch: true,
      });
      await flushPromises();
    });

    await waitFor(() => expect(overviewRepository.get).toHaveBeenCalledTimes(2));
    expect(screen.getAllByText(/2 pending/i).length).toBeGreaterThan(0);
  });

  it.each(["fresh", "stale", "rebuilding", "degraded"] as const)(
    "renders %s projection state from backend metadata",
    async (status) => {
      jest.mocked(overviewRepository.get).mockResolvedValue(
        makeOverview({
          projection: {
            ...makeOverview().projection!,
            status,
            lag_seconds: status === "fresh" ? 0 : 9,
          },
        }),
      );

      await act(async () => {
        renderOverview();
        await flushPromises();
      });

      expect(await screen.findByText(new RegExp(`Projection ${status}`, "i"))).toBeInTheDocument();
    },
  );
});
