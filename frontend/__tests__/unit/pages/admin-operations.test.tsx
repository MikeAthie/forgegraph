import type { ReactNode } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { useAuth } from "@/contexts/AuthContext";
import * as api from "@/lib/api";
import AdminOperationsPage from "@/pages/admin/operations";

jest.mock("@/contexts/AuthContext");
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
  default: ({ href, children, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;

describe("AdminOperationsPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuth.mockReturnValue({
      user: {
        id: "u1",
        email: "owner@example.com",
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
    });
  });

  it("renders policy, retention, and health summaries for operators", async () => {
    jest.spyOn(api.policiesApi, "getGuardrails").mockResolvedValue({
      http_allowlist: ["api.openai.com"],
      http_denylist: ["example.com"],
      http_default_deny: true,
      allowed_providers: ["openai"],
      allowed_models: ["gpt-5"],
      summary: {
        runtime_mode: "cloud",
        http_access_mode: "default_deny",
        egress_allowlist_count: 1,
        egress_denylist_count: 1,
        provider_allowlist_count: 1,
        model_allowlist_count: 1,
        exec_tools_policy: "restricted_in_cloud",
        curated_memory_enabled: true,
        curated_memory_vector_indexing_enabled: true,
      },
    });
    jest.spyOn(api.retentionApi, "getPolicy").mockResolvedValue({
      runs_retention_days: 30,
      run_logs_retention_days: 14,
      audit_logs_retention_days: 90,
      usage_retention_days: 60,
    });
    jest.spyOn(api.analyticsApi, "getMemoryUsage").mockResolvedValue({
      period: "30d",
      start_date: "2026-02-12",
      end_date: "2026-03-13",
      tier1: { total_messages: 0, avg_buffer_size: 0, peak_buffer_size: 0 },
      tier2: { redis_keys: 10, storage_mb: 4, hit_rate: 0.9 },
      tier3: { chunks_stored: 5, embeddings_generated: 5, search_queries: 12, avg_search_latency_ms: 42 },
      curated_memory: {
        observations_total: 18,
        observations_created_in_period: 6,
        deleted_observations_total: 1,
        indexed_observations_total: 16,
        pending_index_total: 2,
        graph_scope_total: 8,
        run_scope_total: 7,
        session_scope_total: 3,
        retrieval_runs_in_period: 4,
      },
      retention: {
        policy_configured: true,
        runs_retention_days: 30,
        run_logs_retention_days: 14,
        audit_logs_retention_days: 90,
        usage_retention_days: 60,
        observations_retention_days: null,
        memory_chunks_retention_days: null,
        observations_retention_mode: "manual",
        memory_chunks_retention_mode: "manual",
        summary: "Runs, logs, audit logs, and usage follow the tenant retention policy.",
      },
      costs: { summarization_usd: 1.2, embedding_usd: 0.8, total_usd: 2.0 },
      usage_series: [],
      top_agents: [],
      totals: {
        summarization_prompt_tokens: 120,
        summarization_completion_tokens: 80,
        summarization_total_tokens: 200,
      },
    });
    jest.spyOn(api.analyticsApi, "getMemoryPerformance").mockResolvedValue({
      period: "30d",
      start_date: "2026-02-12",
      end_date: "2026-03-13",
      vector: { search_queries: 12, avg_search_latency_ms: 42, chunks_indexed: 16 },
      summarization: { runs: 3, avg_latency_ms: 85 },
      grpc: { requests_total: 22, errors_total: 1 },
      maintenance: {
        memory_gc_last_run_at: "2026-03-12T10:00:00Z",
        memory_gc_last_reindex: "2026-03-12T12:00:00Z",
      },
      indexing: {
        jobs_total: 18,
        success_total: 16,
        delete_total: 1,
        enqueue_errors_total: 0,
        delete_enqueue_errors_total: 0,
        pending_observations_total: 2,
        indexed_observations_total: 16,
      },
    });
    jest.spyOn(api.healthApi, "getMemory").mockResolvedValue({
      redis: { healthy: true, latency_ms: 8 },
      grpc: { configured: true, healthy: true },
      metrics: {
        memory_gc_deleted_retention_total: 0,
        memory_gc_deleted_tenant_total: 0,
        memory_gc_deleted_missing_users_total: 0,
        memory_gc_last_run_at: "2026-03-12T10:00:00Z",
        memory_gc_last_reindex: "2026-03-12T12:00:00Z",
        memory_grpc_requests_total: 22,
        memory_grpc_errors_total: 1,
        memory_observation_index_jobs_total: 18,
        memory_observation_index_success_total: 16,
        memory_observation_index_delete_total: 1,
        memory_observation_index_enqueue_errors_total: 0,
        memory_observation_delete_enqueue_errors_total: 0,
      },
    });
    jest.spyOn(api.metricsApi, "getSummary").mockResolvedValue({
      runs: {
        started_total: 40,
        completed_total: 38,
        failed_total: 2,
        canceled_total: 0,
        success_rate: 0.95,
        failure_rate: 0.05,
        latency_ms_p50: 1200,
        latency_ms_p95: 4000,
        window_size: 50,
        active_total: 2,
      },
      queue: {
        pending: 3,
        processing: 1,
        total_depth: 4,
        oldest_pending_age_seconds: 12,
        by_tenant: [],
      },
      slo: {
        run_success_rate_target: 0.99,
        run_p95_latency_ms_target: 60000,
        queue_max_depth_target: 500,
      },
      guardrails: {
        run_max_active_per_tenant: 5,
        run_input_max_bytes: 65536,
        queue_max_concurrency_per_tenant: 2,
      },
      violations: {
        run_success_rate: true,
        run_p95_latency: false,
        queue_depth: false,
      },
      sre: {
        catalog_version: 1,
        catalog_path: "docs/ops/production-slos.yaml",
        release_tier: "beta",
        window_seconds: 3600,
        objectives: [
          {
            id: "api_availability",
            title: "API availability",
            target: 0.995,
            actual: 0.998,
            unit: "ratio",
            comparison: "gte",
            status: "passing",
            source: "durable_metric_samples",
            observed_count: 20,
            missing_data: false,
          },
          {
            id: "runtime_intent_processing_p95",
            title: "Runtime intent processing p95",
            target: 1000,
            actual: null,
            unit: "ms",
            comparison: "lte",
            status: "no_data",
            source: "durable_metric_samples",
            observed_count: 0,
            missing_data: true,
          },
        ],
        dashboard_panels: [
          {
            id: "runtime_intent_backlog",
            title: "Runtime intent backlog",
            value: 3,
            unit: "count",
            missing_data: false,
          },
          {
            id: "llm_queue_depth",
            title: "LLM queue depth",
            value: null,
            unit: "count",
            missing_data: true,
          },
        ],
        alerts: {
          active_total: 1,
          items: [
            {
              id: "intent_backlog_growing",
              title: "Intent Backlog Growing",
              state: "active",
              severity: "warning",
              evidence: { backlog: 3 },
              runbook: "docs/ops/runbooks/intent_backlog_growing.md",
            },
          ],
        },
        catalog_validation: {
          missing_slos: [],
          missing_dashboard_panels: [],
          missing_alerts: [],
        },
        generated_at: "2026-03-13T10:00:00Z",
      },
      generated_at: "2026-03-13T10:00:00Z",
    });
    const previewSpy = jest.spyOn(api.retentionApi, "previewCleanup").mockResolvedValue({
      tenant_id: "org-1",
      dry_run: true,
      retention_days: { runs: 30, run_logs: 14, audit_logs: 90, usage: 60 },
      runs_deleted: 2,
      run_logs_deleted: 4,
      run_events_deleted: 1,
      node_runs_deleted: 1,
      run_checkpoints_deleted: 1,
      approval_tasks_deleted: 1,
      audit_logs_deleted: 3,
      llm_usage_deleted: 2,
      memory_usage_deleted: 1,
      total_deleted: 12,
      errors: [],
    });
    jest.spyOn(api.operatorApi, "getRuntimeIntentBacklog").mockResolvedValue({
      stream: "runtime:intents",
      dead_letter_stream: "runtime:intents:dead",
      stream_length: 3,
      pending: 1,
      lag: 2,
      backlog: 3,
      dead_letter_count: 1,
      recent_dead_letters: [],
    });
    jest.spyOn(api.operatorApi, "getDeadLetters").mockResolvedValue({
      task_dead_letters: [],
      runtime_intent_outcomes: [],
    });
    jest.spyOn(api.operatorApi, "getOrgLoad").mockResolvedValue({
      organization_id: "org-1",
      runs: { running: 1, paused: 1, failed: 0 },
      tasks: [{ status: "running", count: 1 }],
      retry_operations: [{ status: "scheduled", count: 2 }],
      dead_letters: 1,
    });
    jest.spyOn(api.operatorApi, "getWebSocketSubscribers").mockResolvedValue({
      total: 2,
      by_org: { "org-1": 2 },
      by_run: {},
      by_user: {},
      subscribers: [],
    });

    render(<AdminOperationsPage />);

    await waitFor(() => {
      expect(screen.getByText(/guardrail summary/i)).toBeInTheDocument();
    });

    expect(screen.getAllByText(/default deny/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/production slos and sre alerts/i)).toBeInTheDocument();
    expect(screen.getByText(/api availability/i)).toBeInTheDocument();
    expect(screen.getByText(/intent backlog growing/i)).toBeInTheDocument();
    expect(screen.getByText(/recovery controls/i)).toBeInTheDocument();
    expect(screen.getByText(/support-safe exports/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /operator help/i })).toHaveAttribute("href", "/admin/help");

    const user = userEvent.setup();
    await act(async () => {
      await user.click(screen.getByRole("button", { name: /preview cleanup impact/i }));
    });

    await waitFor(() => {
      expect(previewSpy).toHaveBeenCalled();
    });

    expect(screen.getByText(/would delete/i)).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });
});
