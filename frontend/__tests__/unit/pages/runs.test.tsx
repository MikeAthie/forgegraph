import type { ReactNode } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/router";

import * as api from "@/lib/api";
import RunsPage from "@/pages/runs";
import RunDetailPage from "@/pages/runs/[runId]";

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
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
}));

jest.mock("next/router");

const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  url: string;

  private listeners: Record<string, Array<(event?: any) => void>> = {
    open: [],
    message: [],
    error: [],
    close: [],
  };

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  addEventListener(type: string, listener: (event?: any) => void) {
    this.listeners[type] ??= [];
    this.listeners[type].push(listener);
  }

  removeEventListener(type: string, listener: (event?: any) => void) {
    this.listeners[type] = (this.listeners[type] ?? []).filter((candidate) => candidate !== listener);
  }

  close() {
    this.emit("close");
  }

  emit(type: string, event?: any) {
    for (const listener of this.listeners[type] ?? []) {
      listener(event);
    }
  }

  static reset() {
    MockWebSocket.instances = [];
  }
}

const runId = "11111111-1111-1111-1111-111111111111";

const makeRunListItem = (overrides: Partial<api.RunListItem> = {}): api.RunListItem => ({
  id: "run-1",
  graph_id: "graph-1",
  graph_name: "Revenue triage",
  graph_version_id: "version-1",
  graph_version: 3,
  status: "running",
  queue_status: "processing",
  queue_attempts: 1,
  queue_available_at: null,
  started_at: "2026-04-05T10:00:00Z",
  ended_at: null,
  duration_ms: null,
  memory_activity: {
    has_activity: true,
    save_node_count: 1,
    saved_observation_count: 2,
    retrieval_node_count: 1,
    retrieved_observation_count: 4,
    influenced_node_count: 1,
    influenced_observation_count: 2,
    degraded: false,
    operations: [],
  },
  ...overrides,
});

const makeNodeRun = (overrides: Partial<api.NodeRunItem> = {}): api.NodeRunItem => ({
  id: "node-run-1",
  node_id: "fetch_customer",
  node_type: "tool",
  status: "succeeded",
  attempt: 1,
  started_at: "2026-04-05T10:00:00Z",
  ended_at: "2026-04-05T10:00:01Z",
  duration_ms: 1000,
  input_json: { customer_id: "cust_123" },
  output_json: { customer_name: "Jackie" },
  error_json: null,
  agent_trace: null,
  memory_activity: null,
  ...overrides,
});

const makeRunDetail = (overrides: Partial<api.RunDetail> = {}): api.RunDetail => ({
  id: runId,
  owner_id: "owner-1",
  graph_id: "graph-1",
  graph_name: "Revenue triage",
  graph_version_id: "version-1",
  graph_version: 3,
  status: "running",
  queue_status: "processing",
  queue_attempts: 1,
  queue_available_at: null,
  started_at: "2026-04-05T10:00:00Z",
  ended_at: null,
  input_json: { ticket_id: "ticket-1" },
  output_json: null,
  error_message: "",
  duration_ms: 1000,
  node_runs: [makeNodeRun()],
  agent_events: [],
  memory_activity: null,
  paused_node_id: null,
  pause_payload: null,
  ...overrides,
});

const flushPromises = async () => {
  await Promise.resolve();
  await Promise.resolve();
};

const renderRunsPage = async () => {
  await act(async () => {
    render(<RunsPage />);
    await flushPromises();
  });
};

const renderRunDetailPage = async () => {
  await act(async () => {
    render(<RunDetailPage />);
    await flushPromises();
  });
};

describe("Runs pages", () => {
  beforeAll(() => {
    Object.defineProperty(global, "WebSocket", {
      writable: true,
      value: MockWebSocket,
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
    MockWebSocket.reset();
    api.clearTokens();
    jest.spyOn(api.authApi, "issueWsTicket").mockResolvedValue({
      ticket: "ws-ticket-123",
      expires_in_seconds: 45,
    });
    mockUseRouter.mockReturnValue({
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      pathname: "/runs",
      query: {},
      asPath: "/runs",
    } as any);
  });

  describe("RunsPage", () => {
    it("shows the loading shell while executions are still loading", () => {
      jest.spyOn(api.runsApi, "list").mockImplementation(() => new Promise(() => {}));

      render(<RunsPage />);

      expect(screen.getByText("Distributed trace for humans")).toBeInTheDocument();
      expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
    });

    it("renders an empty state when no executions exist", async () => {
      jest.spyOn(api.runsApi, "list").mockResolvedValue([]);

      await renderRunsPage();

      expect(screen.getByText(/no executions available/i)).toBeInTheDocument();
    });

    it("renders executions and selects the most recent one by default", async () => {
      jest.spyOn(api.runsApi, "list").mockResolvedValue([
        makeRunListItem({
          id: "run-old",
          graph_name: "Nightly digest",
          graph_version: 1,
          started_at: "2026-04-05T08:00:00Z",
          status: "succeeded",
          duration_ms: 62_000,
        }),
        makeRunListItem({
          id: "run-new",
          graph_name: "Revenue triage",
          graph_version: 4,
          started_at: "2026-04-05T12:00:00Z",
          status: "running",
          duration_ms: 90_000,
        }),
      ]);

      await renderRunsPage();

      expect(screen.getAllByText("Revenue triage").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Nightly digest").length).toBeGreaterThan(0);
      expect(screen.getByText(/workflow revision/i)).toBeInTheDocument();
      expect(screen.getByText("v4")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /open execution detail/i })).toHaveAttribute(
        "href",
        "/executions/run-new",
      );
    });

    it("updates the selected execution through the router when the operator switches rows", async () => {
      const replace = jest.fn();
      mockUseRouter.mockReturnValue({
        push: jest.fn(),
        replace,
        prefetch: jest.fn(),
        pathname: "/runs",
        query: {},
        asPath: "/runs",
      } as any);

      jest.spyOn(api.runsApi, "list").mockResolvedValue([
        makeRunListItem({ id: "run-1", graph_name: "Revenue triage" }),
        makeRunListItem({
          id: "run-2",
          graph_name: "Inbox sweep",
          started_at: "2026-04-05T11:00:00Z",
        }),
      ]);

      await renderRunsPage();
      await userEvent.click(screen.getByRole("button", { name: /inbox sweep/i }));

      expect(replace).toHaveBeenCalledWith({ pathname: "/executions", query: { execution: "run-2" } }, undefined, {
        shallow: true,
      });
    });

    it("renders an error banner when executions fail to load", async () => {
      jest.spyOn(api.runsApi, "list").mockRejectedValue(new Error("API Error"));

      await renderRunsPage();

      expect(screen.getByText("API Error")).toBeInTheDocument();
    });
  });

  describe("RunDetailPage", () => {
    beforeEach(() => {
      mockUseRouter.mockReturnValue({
        push: jest.fn(),
        replace: jest.fn(),
        prefetch: jest.fn(),
        pathname: `/runs/${runId}`,
        query: { runId },
        asPath: `/runs/${runId}`,
      } as any);
    });

    it("shows the loading shell while the execution detail request is pending", () => {
      jest.spyOn(api.runsApi, "get").mockImplementation(() => new Promise(() => {}));

      render(<RunDetailPage />);

      expect(screen.getByText("Structured execution trace")).toBeInTheDocument();
      expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
    });

    it("renders the execution summary, step flow, and inspector content", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue(
        makeRunDetail({
          status: "failed",
          duration_ms: 95_000,
          node_runs: [
            makeNodeRun({
              id: "node-run-1",
              node_id: "fetch_customer",
              output_json: { customer_name: "Jackie" },
            }),
            makeNodeRun({
              id: "node-run-2",
              node_id: "draft_reply",
              node_type: "prompt",
              status: "failed",
              duration_ms: 2000,
              input_json: { prompt: "Draft the message" },
              output_json: null,
              error_json: { code: "MODEL_TIMEOUT", message: "Provider timed out" },
            }),
          ],
        }),
      );

      await renderRunDetailPage();

      expect(api.runsApi.get).toHaveBeenCalledWith(runId);
      expect(screen.getByText("Structured execution trace")).toBeInTheDocument();
      expect(screen.getByText("Execution flow")).toBeInTheDocument();
      expect(screen.getByText("Human gate")).toBeInTheDocument();
      expect(screen.getAllByText("Revenue triage").length).toBeGreaterThan(0);
      expect(screen.getAllByText("draft_reply").length).toBeGreaterThan(0);
      expect(screen.getAllByText("fetch_customer").length).toBeGreaterThan(0);
      expect(screen.getByText(/execution requires intervention here/i)).toBeInTheDocument();
      expect(screen.getByText(/model_timeout/i)).toBeInTheDocument();
      expect(screen.getByText(/provider timed out/i)).toBeInTheDocument();
      expect(screen.getByText(/failure point/i)).toBeInTheDocument();
    });

    it("renders paused runs in the human gate panel", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue(
        makeRunDetail({
          status: "paused",
          paused_node_id: "approval_1",
          pause_payload: {
            node_id: "approval_1",
            node_name: "Finance approval",
            prompt_message: "Approve the outbound refund before execution resumes.",
          },
        }),
      );

      await renderRunDetailPage();

      expect(screen.getByText("Finance approval")).toBeInTheDocument();
      expect(screen.getByText(/approve the outbound refund before execution resumes/i)).toBeInTheDocument();
    });

    it("connects to run websocket updates and applies canonical backend updates", async () => {
      api.setAccessToken("test-token");
      jest.spyOn(api.runsApi, "get").mockResolvedValue(
        makeRunDetail({
          status: "running",
          node_runs: [makeNodeRun({ id: "node-run-1", node_id: "fetch_customer" })],
        }),
      );

      await renderRunDetailPage();

      expect(MockWebSocket.instances).toHaveLength(1);
<<<<<<< Updated upstream
      expect(MockWebSocket.instances[0]?.url).toContain(`/ws/runs/${runId}/?token=test-token`);
=======
      expect(MockWebSocket.instances[0]?.url).toContain(`/ws/runs/${runId}/?ticket=ws-ticket-123&event_level=default`);
>>>>>>> Stashed changes

      await act(async () => {
        MockWebSocket.instances[0]?.emit("open");
        MockWebSocket.instances[0]?.emit("message", {
          data: JSON.stringify({
            type: "connection_established",
            timestamp: "2026-04-05T10:00:00Z",
            trace_id: "trace-1",
            run_id: runId,
            payload: {
              event_level: "default",
            },
          }),
        });
      });

      expect(screen.getByText(/live updates/i)).toBeInTheDocument();

      await act(async () => {
        MockWebSocket.instances[0]?.emit("message", {
          data: JSON.stringify({
            type: "run_started",
            timestamp: "2026-04-05T10:00:05Z",
            trace_id: "trace-1",
            run_id: runId,
            payload: {
              status: "running",
              run: {
                status: "running",
                duration_ms: 5000,
              },
            },
          }),
        });
        MockWebSocket.instances[0]?.emit("message", {
          data: JSON.stringify({
            type: "node_completed",
            timestamp: "2026-04-05T10:00:03Z",
            trace_id: "trace-1",
            run_id: runId,
            payload: {
              status: "succeeded",
              node_run: {
                id: "node-run-2",
                node_id: "send_summary",
                node_type: "tool",
                status: "succeeded",
                attempt: 1,
                started_at: "2026-04-05T10:00:02Z",
                ended_at: "2026-04-05T10:00:03Z",
                duration_ms: 1000,
                input_json: { channel: "slack" },
                output_json: { ok: true },
              },
            },
          }),
        });
      });

      await waitFor(() => {
        expect(screen.getByText("send_summary")).toBeInTheDocument();
        expect(screen.getAllByText(/succeeded/i).length).toBeGreaterThan(0);
      });
    });

    it("falls back to offline realtime status when no access token is available", async () => {
      api.clearTokens();
      jest.spyOn(api.runsApi, "get").mockResolvedValue(makeRunDetail());

      await renderRunDetailPage();

      expect(screen.getByText(/offline/i)).toBeInTheDocument();
      expect(MockWebSocket.instances).toHaveLength(0);
    });

    it("renders an error banner when the execution detail request fails", async () => {
      jest.spyOn(api.runsApi, "get").mockRejectedValue(new Error("API Error"));

      await renderRunDetailPage();

      expect(screen.getByText("API Error")).toBeInTheDocument();
    });
  });
});
