import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import * as api from "@/lib/api";
import LLMAnalyticsPage from "@/pages/analytics/llm";
import MemoryAnalyticsPage from "@/pages/analytics/memory";

jest.mock("@/components/DashboardLayout", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <div data-testid="dashboard-layout">{children}</div>,
}));

jest.mock("@/components/ProtectedRoute", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

describe("Analytics pages", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders LLM quota details and calls export", async () => {
    const user = userEvent.setup();
    jest.spyOn(api.analyticsApi, "getLLMUsage").mockResolvedValue({
      period: "30d",
      start_date: "2026-03-01",
      end_date: "2026-03-30",
      totals: { prompt_tokens: 100, completion_tokens: 40, total_tokens: 140, cost_usd: 4.25 },
      series: [],
      by_model: [],
      by_provider: [],
    });
    jest.spyOn(api.analyticsApi, "getLLMCosts").mockResolvedValue({
      period: "30d",
      start_date: "2026-03-01",
      end_date: "2026-03-30",
      currency: "USD",
      total_usd: 4.25,
      series: [],
    });
    jest.spyOn(api.analyticsApi, "getLLMBudget").mockResolvedValue({
      budget: { monthly_limit_usd: 25, warning_threshold_pct: 0.8 },
      usage: { month_cost_usd: 4.25 },
      warning_threshold_usd: 20,
      warning: false,
      over_budget: false,
    });
    jest.spyOn(api.analyticsApi, "getLLMQuota").mockResolvedValue({
      quota: { monthly_token_limit: 5000, monthly_cost_limit_usd: 40 },
      usage: { month_total_tokens: 140, month_cost_usd: 4.25 },
    });
    const exportSpy = jest
      .spyOn(api.analyticsApi, "exportLLMReport")
      .mockResolvedValue(new Blob(["csv"], { type: "text/csv" }));
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const createObjectURLSpy = jest.fn(() => "blob:test");
    const revokeObjectURLSpy = jest.fn();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: createObjectURLSpy,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: revokeObjectURLSpy,
    });
    const clickSpy = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<LLMAnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByText(/monthly token quota/i)).toBeInTheDocument();
    });

    expect(screen.getByText("5,000")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /export usage csv/i }));

    await waitFor(() => {
      expect(exportSpy).toHaveBeenCalledWith({
        dataset: "usage",
        format: "csv",
        period: "30d",
      });
    });

    expect(createObjectURLSpy).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();

    clickSpy.mockRestore();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: originalCreateObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: originalRevokeObjectURL,
    });
  });

  it("renders curated memory observation and indexing stats", async () => {
    jest.spyOn(api.analyticsApi, "getMemoryUsage").mockResolvedValue({
      period: "30d",
      start_date: "2026-03-01",
      end_date: "2026-03-30",
      tier1: { total_messages: 10, avg_buffer_size: 3, peak_buffer_size: 6 },
      tier2: { redis_keys: 4, storage_mb: 1.2, hit_rate: null },
      tier3: { chunks_stored: 2, embeddings_generated: 2, search_queries: 0, avg_search_latency_ms: null },
      curated_memory: {
        observations_total: 8,
        observations_created_in_period: 3,
        deleted_observations_total: 1,
        indexed_observations_total: 5,
        pending_index_total: 3,
        graph_scope_total: 5,
        run_scope_total: 2,
        session_scope_total: 1,
        retrieval_runs_in_period: 6,
      },
      retention: {
        policy_configured: true,
        runs_retention_days: 30,
        run_logs_retention_days: 14,
        audit_logs_retention_days: 90,
        usage_retention_days: 30,
        observations_retention_days: null,
        memory_chunks_retention_days: null,
        observations_retention_mode: "manual",
        memory_chunks_retention_mode: "manual",
        summary:
          "Runs, logs, audit logs, and usage follow the tenant retention policy. Curated observations and indexed chunks currently require manual cleanup.",
      },
      costs: { summarization_usd: 1.2, embedding_usd: 0, total_usd: 1.2 },
      usage_series: [],
      top_agents: [],
      totals: {
        summarization_prompt_tokens: 10,
        summarization_completion_tokens: 4,
        summarization_total_tokens: 14,
      },
    });
    jest.spyOn(api.analyticsApi, "getMemoryCosts").mockResolvedValue({
      period: "30d",
      start_date: "2026-03-01",
      end_date: "2026-03-30",
      currency: "USD",
      summarization_total_usd: 1.2,
      embedding_total_usd: 0,
      series: [],
    });
    jest.spyOn(api.analyticsApi, "getMemoryPerformance").mockResolvedValue({
      period: "30d",
      start_date: "2026-03-01",
      end_date: "2026-03-30",
      vector: { search_queries: 0, avg_search_latency_ms: null, chunks_indexed: 2 },
      summarization: { runs: 1, avg_latency_ms: null },
      grpc: { requests_total: 4, errors_total: 1 },
      maintenance: { memory_gc_last_run_at: null, memory_gc_last_reindex: null },
      indexing: {
        jobs_total: 9,
        success_total: 5,
        delete_total: 1,
        enqueue_errors_total: 2,
        delete_enqueue_errors_total: 0,
        pending_observations_total: 3,
        indexed_observations_total: 5,
      },
    });

    render(<MemoryAnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByText(/curated memory/i)).toBeInTheDocument();
    });

    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
    expect(screen.getByText(/retrieval runs this period: 6/i)).toBeInTheDocument();
    expect(screen.getByText(/search queries this period: 0/i)).toBeInTheDocument();
    expect(screen.getByText(/index queue errors/i)).toBeInTheDocument();
    expect(screen.getByText(/retention posture/i)).toBeInTheDocument();
    expect(screen.getByText(/manual cleanup/i)).toBeInTheDocument();
  });
});
