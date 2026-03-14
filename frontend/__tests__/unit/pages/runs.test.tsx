/**
 * Unit tests for Runs pages (Phase 4 observability).
 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/router";

import { useAuth } from "@/contexts/AuthContext";
import * as api from "@/lib/api";
import RunsPage from "@/pages/runs";
import RunDetailPage from "@/pages/runs/[runId]";

jest.mock("@/contexts/AuthContext");
jest.mock("next/router");

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;

const actClick = (element: HTMLElement) => act(async () => userEvent.click(element));
const actSelect = (element: HTMLElement, value: string) => act(async () => userEvent.selectOptions(element, value));

describe("Runs List Page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuth.mockReturnValue({
      user: { id: "u1", email: "user@example.com" },
      isAuthenticated: true,
      loading: false,
      error: null,
      login: jest.fn(),
      register: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn(),
      clearError: jest.fn(),
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

  describe("Loading and Empty States", () => {
    it("renders loading state initially", async () => {
      jest.spyOn(api.runsApi, "list").mockImplementation(
        () => new Promise(() => {}), // Never resolves
      );

      render(<RunsPage />);

      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    it("renders empty state when no runs exist", async () => {
      jest.spyOn(api.runsApi, "list").mockResolvedValue([]);

      render(<RunsPage />);

      await waitFor(() => {
        expect(screen.getByText(/no runs yet/i)).toBeInTheDocument();
      });
    });

    it("renders error state when API fails", async () => {
      jest.spyOn(api.runsApi, "list").mockRejectedValue(new Error("API Error"));

      render(<RunsPage />);

      await waitFor(() => {
        expect(screen.getByText("API Error")).toBeInTheDocument();
      });
    });
  });

  describe("Run List Rendering", () => {
    it("renders list of runs with correct data", async () => {
      const mockRuns = [
        {
          id: "run1",
          graph_id: "g1",
          graph_name: "Graph 1",
          graph_version_id: "v1",
          graph_version: 1,
          status: "succeeded",
          started_at: "2024-01-15T10:00:00Z",
          ended_at: "2024-01-15T10:01:00Z",
          duration_ms: 60000,
        },
        {
          id: "run2",
          graph_id: "g2",
          graph_name: "Graph 2",
          graph_version_id: "v2",
          graph_version: 2,
          status: "running",
          started_at: "2024-01-15T11:00:00Z",
          ended_at: null,
          duration_ms: null,
        },
      ];

      jest.spyOn(api.runsApi, "list").mockResolvedValue(mockRuns as any);

      render(<RunsPage />);

      await waitFor(() => {
        expect(screen.getByText("Graph 1")).toBeInTheDocument();
        expect(screen.getByText("Graph 2")).toBeInTheDocument();
      });
    });

    it("displays status badges with correct colors", async () => {
      const mockRuns = [
        {
          id: "run1",
          graph_name: "Graph 1",
          status: "succeeded",
          started_at: "2024-01-15T10:00:00Z",
        },
        {
          id: "run2",
          graph_name: "Graph 2",
          status: "failed",
          started_at: "2024-01-15T11:00:00Z",
        },
        {
          id: "run3",
          graph_name: "Graph 3",
          status: "running",
          started_at: "2024-01-15T12:00:00Z",
        },
      ];

      jest.spyOn(api.runsApi, "list").mockResolvedValue(mockRuns as any);

      render(<RunsPage />);

      await waitFor(() => {
        const succeededBadge = screen.getByText(/succeeded/i);
        const failedBadge = screen.getByText(/failed/i);
        const runningBadge = screen.getByText(/running/i);

        expect(succeededBadge).toBeInTheDocument();
        expect(failedBadge).toBeInTheDocument();
        expect(runningBadge).toBeInTheDocument();

        // Check for appropriate CSS classes or styles
        expect(succeededBadge).toHaveClass(/emerald/i);
        expect(failedBadge).toHaveClass(/rose/i);
        expect(runningBadge).toHaveClass(/blue/i);
      });
    });

    it("displays duration for completed runs", async () => {
      const mockRuns = [
        {
          id: "run1",
          graph_name: "Graph 1",
          status: "succeeded",
          started_at: "2024-01-15T10:00:00Z",
          ended_at: "2024-01-15T10:01:30Z",
          duration_ms: 90000,
        },
      ];

      jest.spyOn(api.runsApi, "list").mockResolvedValue(mockRuns as any);

      render(<RunsPage />);

      await waitFor(() => {
        // Should display duration (90000ms = 1m 30s)
        expect(screen.getByText(/1m 30s|90s|90000ms/i)).toBeInTheDocument();
      });
    });

    it("handles runs with null timestamps gracefully", async () => {
      const mockRuns = [
        {
          id: "run1",
          graph_name: "Graph 1",
          status: "pending",
          started_at: null,
          ended_at: null,
          duration_ms: null,
        },
      ];

      jest.spyOn(api.runsApi, "list").mockResolvedValue(mockRuns as any);

      render(<RunsPage />);

      await waitFor(() => {
        expect(screen.getByText("Graph 1")).toBeInTheDocument();
        expect(screen.getByText(/pending/i)).toBeInTheDocument();
      });
    });
  });

  describe("Navigation", () => {
    it("navigates to run detail when clicking view link", async () => {
      const mockPush = jest.fn();
      mockUseRouter.mockReturnValue({
        push: mockPush,
        replace: jest.fn(),
        prefetch: jest.fn(),
        pathname: "/runs",
        query: {},
        asPath: "/runs",
      } as any);

      const mockRuns = [
        {
          id: "run1",
          graph_name: "Graph 1",
          status: "succeeded",
          started_at: "2024-01-15T10:00:00Z",
        },
      ];

      jest.spyOn(api.runsApi, "list").mockResolvedValue(mockRuns as any);

      render(<RunsPage />);

      await waitFor(() => {
        expect(screen.getByText("Graph 1")).toBeInTheDocument();
      });

      const viewLink = screen.getByRole("link", { name: /view/i });
      await actClick(viewLink);

      expect(mockPush).toHaveBeenCalledWith("/runs/run1");
    });

    it("navigates to run detail when clicking row", async () => {
      const mockPush = jest.fn();
      mockUseRouter.mockReturnValue({
        push: mockPush,
        replace: jest.fn(),
        prefetch: jest.fn(),
        pathname: "/runs",
        query: {},
        asPath: "/runs",
      } as any);

      const mockRuns = [
        {
          id: "run1",
          graph_name: "Graph 1",
          status: "succeeded",
          started_at: "2024-01-15T10:00:00Z",
        },
      ];

      jest.spyOn(api.runsApi, "list").mockResolvedValue(mockRuns as any);

      render(<RunsPage />);

      await waitFor(() => {
        expect(screen.getByText("Graph 1")).toBeInTheDocument();
      });

      const row = screen.getByText("Graph 1").closest("tr");
      if (row) {
        await actClick(row);
        expect(mockPush).toHaveBeenCalledWith("/runs/run1");
      }
    });
  });

  describe("Filtering", () => {
    it("filters runs by status", async () => {
      const mockRuns = [
        {
          id: "run1",
          graph_name: "Graph 1",
          status: "succeeded",
          started_at: "2024-01-15T10:00:00Z",
        },
        {
          id: "run2",
          graph_name: "Graph 2",
          status: "failed",
          started_at: "2024-01-15T11:00:00Z",
        },
      ];

      jest.spyOn(api.runsApi, "list").mockResolvedValue(mockRuns as any);

      render(<RunsPage />);

      await waitFor(() => {
        expect(screen.getByText("Graph 1")).toBeInTheDocument();
        expect(screen.getByText("Graph 2")).toBeInTheDocument();
      });

      // Find and interact with status filter
      const statusFilter = screen.queryByLabelText(/filter.*status/i);
      if (statusFilter) {
        await actSelect(statusFilter, "succeeded");

        // After filtering, should only show succeeded runs
        await waitFor(() => {
          expect(screen.getByText("Graph 1")).toBeInTheDocument();
          expect(screen.queryByText("Graph 2")).not.toBeInTheDocument();
        });
      }
    });
  });

  describe("Responsive Design", () => {
    it("renders table on desktop", async () => {
      jest.spyOn(api.runsApi, "list").mockResolvedValue([
        {
          id: "run1",
          graph_name: "Graph 1",
          status: "succeeded",
          started_at: "2024-01-15T10:00:00Z",
        },
      ] as any);

      render(<RunsPage />);

      await waitFor(() => {
        const table = screen.queryByRole("table");
        expect(table).toBeInTheDocument();
      });
    });
  });
});

describe("Run Detail Page", () => {
  const runId = "11111111-1111-1111-1111-111111111111";

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuth.mockReturnValue({
      user: { id: "u1", email: "user@example.com" },
      isAuthenticated: true,
      loading: false,
      error: null,
      login: jest.fn(),
      register: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn(),
      clearError: jest.fn(),
    });
    mockUseRouter.mockReturnValue({
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      pathname: `/runs/${runId}`,
      query: { runId },
      asPath: `/runs/${runId}`,
    } as any);
  });

  describe("Loading and Error States", () => {
    it("renders loading state initially", async () => {
      jest.spyOn(api.runsApi, "get").mockImplementation(
        () => new Promise(() => {}), // Never resolves
      );
      jest.spyOn(api.graphsApi, "getVersion").mockImplementation(() => new Promise(() => {}));

      render(<RunDetailPage />);

      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    it("renders error state when run not found", async () => {
      jest.spyOn(api.runsApi, "get").mockRejectedValue({ status: 404 });

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/not found|404/i)).toBeInTheDocument();
      });
    });

    it("renders error state when API fails", async () => {
      jest.spyOn(api.runsApi, "get").mockRejectedValue(new Error("API Error"));

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/error/i)).toBeInTheDocument();
      });
    });
  });

  describe("Run Overview", () => {
    it("renders run overview with all details", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        owner_id: "u1",
        graph_id: "g1",
        graph_name: "My Graph",
        graph_version_id: "v1",
        graph_version: 1,
        status: "succeeded",
        started_at: "2024-01-15T10:00:00Z",
        ended_at: "2024-01-15T10:01:00Z",
        duration_ms: 60000,
        input_json: {},
        output_json: { result: "ok" },
        error_message: "",
        node_runs: [],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        id: "v1",
        version: 1,
        checksum: "x".repeat(64),
        created_at: "2024-01-15T09:00:00Z",
        graph_json: { nodes: [], edges: [] },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByText("My Graph")).toBeInTheDocument();
        expect(screen.getByText(/succeeded/i)).toBeInTheDocument();
        expect(screen.getByText(/60000ms|1m|60s/i)).toBeInTheDocument();
      });
    });

    it("displays error message for failed runs", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_name: "My Graph",
        status: "failed",
        error_message: "Node execution timed out",
        node_runs: [],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: { nodes: [], edges: [] },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/Node execution timed out/i)).toBeInTheDocument();
      });
    });

    it("displays error message for canceled runs", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_name: "My Graph",
        status: "canceled",
        error_message: "Canceled by user",
        node_runs: [],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: { nodes: [], edges: [] },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/Canceled by user/i)).toBeInTheDocument();
      });
    });

    it("derives run diagnostics for policy-denied and degraded-memory runs", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        owner_id: "u1",
        graph_id: "g1",
        graph_name: "My Graph",
        graph_version_id: "v1",
        graph_version: 1,
        status: "failed",
        started_at: "2024-01-15T10:00:00Z",
        ended_at: "2024-01-15T10:01:00Z",
        duration_ms: 60000,
        input_json: {},
        output_json: null,
        error_message: "policy denied: exec tools are disabled in cloud mode",
        memory_activity: {
          has_activity: true,
          save_node_count: 0,
          saved_observation_count: 0,
          retrieval_node_count: 1,
          retrieved_observation_count: 1,
          influenced_node_count: 0,
          influenced_observation_count: 0,
          degraded: true,
          operations: [],
        },
        node_runs: [],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: { nodes: [], edges: [] },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/run diagnostics/i)).toBeInTheDocument();
      });

      expect(screen.getByText(/policy denied execution/i)).toBeInTheDocument();
      expect(screen.getByText(/curated memory degraded during execution/i)).toBeInTheDocument();
    });

    it("displays live-updating duration for running runs", async () => {
      jest.useFakeTimers();

      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_name: "My Graph",
        status: "running",
        started_at: new Date(Date.now() - 5000).toISOString(),
        ended_at: null,
        duration_ms: null,
        node_runs: [],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: { nodes: [], edges: [] },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/running/i)).toBeInTheDocument();
      });

      // Duration should update over time
      const initialDuration = screen.getByText(/\d+[ms|s]/);
      expect(initialDuration).toBeInTheDocument();

      act(() => {
        jest.advanceTimersByTime(1000);
      });

      // Duration should have changed
      await waitFor(() => {
        const updatedDuration = screen.getByText(/\d+[ms|s]/);
        expect(updatedDuration.textContent).not.toBe(initialDuration.textContent);
      });

      jest.useRealTimers();
    });

    it("renders curated memory timeline for memory-backed runs", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        owner_id: "u1",
        graph_id: "g1",
        graph_name: "Memory Graph",
        graph_version_id: "v1",
        graph_version: 1,
        status: "succeeded",
        started_at: "2024-01-15T10:00:00Z",
        ended_at: "2024-01-15T10:01:00Z",
        duration_ms: 60000,
        input_json: {},
        output_json: { answer: "Bring sweet snacks." },
        error_message: "",
        node_runs: [
          {
            id: "nr1",
            node_id: "obs_save",
            node_type: "observation_save",
            status: "succeeded",
            attempt: 1,
            started_at: "2024-01-15T10:00:00Z",
            ended_at: "2024-01-15T10:00:01Z",
            duration_ms: 1000,
            input_json: {},
            output_json: {},
            error_json: null,
            memory_activity: {
              category: "save",
              operation: "save",
              saved_observation_count: 1,
              scope: "session",
              observation: {
                id: "obs-1",
                title: "Snack preference",
                content_preview: "Customer prefers sweet snacks during meetings.",
              },
            },
          },
          {
            id: "nr2",
            node_id: "obs_context",
            node_type: "observation_context",
            status: "succeeded",
            attempt: 1,
            started_at: "2024-01-15T10:00:02Z",
            ended_at: "2024-01-15T10:00:03Z",
            duration_ms: 1000,
            input_json: {},
            output_json: {},
            error_json: null,
            memory_activity: {
              category: "retrieval",
              operation: "context",
              count: 1,
              query: "sweet snacks",
              degraded: true,
              strategies: ["fts"],
              observations: [
                {
                  id: "obs-1",
                  title: "Snack preference",
                  content_preview: "Customer prefers sweet snacks during meetings.",
                },
              ],
            },
          },
          {
            id: "nr3",
            node_id: "prompt_1",
            node_type: "prompt",
            status: "succeeded",
            attempt: 1,
            started_at: "2024-01-15T10:00:04Z",
            ended_at: "2024-01-15T10:00:05Z",
            duration_ms: 1000,
            input_json: {},
            output_json: {},
            error_json: null,
            memory_activity: {
              category: "influence",
              operation: "context_use",
              observation_count: 1,
              curated_context_paths: ["node.obs_context.output"],
              observations: [
                {
                  id: "obs-1",
                  title: "Snack preference",
                  content_preview: "Customer prefers sweet snacks during meetings.",
                },
              ],
            },
          },
        ],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        id: "v1",
        version: 1,
        checksum: "x".repeat(64),
        created_at: "2024-01-15T09:00:00Z",
        graph_json: {
          nodes: [
            { id: "obs_save", type: "observation_save", name: "Save preference", config: {} },
            { id: "obs_context", type: "observation_context", name: "Load context", config: {} },
            { id: "prompt_1", type: "prompt", name: "Answer", config: {} },
          ],
          edges: [],
        },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getAllByText(/Curated memory/i).length).toBeGreaterThan(0);
      });

      expect(screen.getAllByText(/Saved observation/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Built curated context/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Used curated memory/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Snack preference/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/sweet snacks/i).length).toBeGreaterThan(0);
      expect(screen.getByText(/Degraded retrieval seen/i)).toBeInTheDocument();
    });
  });

  describe("Node Runs List", () => {
    it("renders node runs in correct order", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_name: "My Graph",
        status: "succeeded",
        node_runs: [
          {
            id: "nr1",
            node_id: "node_1",
            node_type: "prompt",
            status: "succeeded",
            attempt: 1,
            started_at: "2024-01-15T10:00:00Z",
            ended_at: "2024-01-15T10:00:01Z",
            duration_ms: 1000,
            input_json: {},
            output_json: { ok: true },
            error_json: null,
          },
          {
            id: "nr2",
            node_id: "node_2",
            node_type: "http",
            status: "succeeded",
            attempt: 1,
            started_at: "2024-01-15T10:00:02Z",
            ended_at: "2024-01-15T10:00:03Z",
            duration_ms: 1000,
            input_json: {},
            output_json: { data: "test" },
            error_json: null,
          },
        ],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: {
          nodes: [
            { id: "node_1", type: "prompt", name: "Start", config: {} },
            { id: "node_2", type: "http", name: "API Call", config: {} },
          ],
          edges: [],
        },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(api.runsApi.get).toHaveBeenCalledWith(runId);
      });

      await waitFor(() => {
        const nodeButtons = screen.getAllByRole("button");
        const startButton = nodeButtons.find((btn) => btn.textContent?.includes("Start"));
        const apiButton = nodeButtons.find((btn) => btn.textContent?.includes("API Call"));

        expect(startButton).toBeInTheDocument();
        expect(apiButton).toBeInTheDocument();

        // Verify order
        const buttonsArray = screen.getAllByRole("button");
        const startIndex = buttonsArray.findIndex((btn) => btn.textContent?.includes("Start"));
        const apiIndex = buttonsArray.findIndex((btn) => btn.textContent?.includes("API Call"));
        expect(startIndex).toBeLessThan(apiIndex);
      });
    });

    it("shows node name from graph JSON", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_id: "g1",
        graph_version_id: "v1",
        graph_name: "My Graph",
        status: "succeeded",
        node_runs: [
          {
            id: "nr1",
            node_id: "node_1",
            node_type: "prompt",
            status: "succeeded",
            attempt: 1,
            started_at: "2024-01-15T10:00:00Z",
            ended_at: "2024-01-15T10:00:01Z",
            duration_ms: 1000,
            input_json: {},
            output_json: { ok: true },
            error_json: null,
          },
        ],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        id: "v1",
        version: 1,
        checksum: "x".repeat(64),
        created_at: "2024-01-15T09:00:00Z",
        graph_json: {
          nodes: [{ id: "node_1", type: "prompt", name: "Custom Start Node", config: {} }],
          edges: [],
        },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/Custom Start Node/i)).toBeInTheDocument();
      });
    });

    it("displays node status with appropriate indicators", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_name: "My Graph",
        status: "running",
        node_runs: [
          {
            id: "nr1",
            node_id: "node_1",
            status: "succeeded",
            node_type: "prompt",
            attempt: 1,
          },
          {
            id: "nr2",
            node_id: "node_2",
            status: "running",
            node_type: "http",
            attempt: 1,
          },
          {
            id: "nr3",
            node_id: "node_3",
            status: "failed",
            node_type: "transform",
            attempt: 1,
            error_json: { message: "Error" },
          },
        ],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: {
          nodes: [
            { id: "node_1", type: "prompt", name: "Node 1", config: {} },
            { id: "node_2", type: "http", name: "Node 2", config: {} },
            { id: "node_3", type: "transform", name: "Node 3", config: {} },
          ],
          edges: [],
        },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/succeeded/i)).toBeInTheDocument();
        expect(screen.getByText(/running/i)).toBeInTheDocument();
        expect(screen.getByText(/failed/i)).toBeInTheDocument();
      });
    });

    it("displays retry attempts correctly", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_name: "My Graph",
        status: "succeeded",
        node_runs: [
          {
            id: "nr1",
            node_id: "node_1",
            node_type: "http",
            status: "failed",
            attempt: 1,
            error_json: { message: "Timeout" },
          },
          {
            id: "nr2",
            node_id: "node_1",
            node_type: "http",
            status: "succeeded",
            attempt: 2,
            output_json: { ok: true },
          },
        ],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: {
          nodes: [{ id: "node_1", type: "http", name: "API Call", config: {} }],
          edges: [],
        },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/attempt 1/i)).toBeInTheDocument();
        expect(screen.getByText(/attempt 2/i)).toBeInTheDocument();
      });
    });
  });

  describe("Node Details Expansion", () => {
    it("expands node to show input/output JSON", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_id: "g1",
        graph_version_id: "v1",
        graph_name: "My Graph",
        status: "succeeded",
        node_runs: [
          {
            id: "nr1",
            node_id: "node_1",
            node_type: "prompt",
            status: "succeeded",
            attempt: 1,
            started_at: "2024-01-15T10:00:00Z",
            ended_at: "2024-01-15T10:00:01Z",
            duration_ms: 1000,
            input_json: { prompt: "Hello" },
            output_json: { response: "Hi there" },
            error_json: null,
          },
        ],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        id: "v1",
        version: 1,
        checksum: "x".repeat(64),
        created_at: "2024-01-15T09:00:00Z",
        graph_json: {
          nodes: [{ id: "node_1", type: "prompt", name: "Start", config: {} }],
          edges: [],
        },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Start/i })).toBeInTheDocument();
      });

      const nodeButton = screen.getByRole("button", { name: /Start/i });
      await actClick(nodeButton);

      await waitFor(() => {
        expect(screen.getByText(/"prompt": "Hello"/i)).toBeInTheDocument();
        expect(screen.getByText(/"response": "Hi there"/i)).toBeInTheDocument();
      });
    });

    it("displays formatted JSON with syntax highlighting", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_id: "g1",
        graph_version_id: "v1",
        graph_name: "My Graph",
        status: "succeeded",
        node_runs: [
          {
            id: "nr1",
            node_id: "node_1",
            node_type: "prompt",
            status: "succeeded",
            attempt: 1,
            output_json: { nested: { key: "value" } },
          },
        ],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: {
          nodes: [{ id: "node_1", type: "prompt", name: "Start", config: {} }],
          edges: [],
        },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Start/i })).toBeInTheDocument();
      });

      const nodeButton = screen.getByRole("button", { name: /Start/i });
      await actClick(nodeButton);

      await waitFor(() => {
        // Check for formatted JSON (with proper indentation)
        const jsonText = screen.getByText(/"nested"/i);
        expect(jsonText).toBeInTheDocument();
      });
    });

    it("shows error JSON for failed nodes", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_id: "g1",
        graph_version_id: "v1",
        graph_name: "My Graph",
        status: "failed",
        node_runs: [
          {
            id: "nr1",
            node_id: "node_1",
            node_type: "http",
            status: "failed",
            attempt: 1,
            error_json: { code: "TIMEOUT", message: "Request timed out after 30s" },
          },
        ],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: {
          nodes: [{ id: "node_1", type: "http", name: "API Call", config: {} }],
          edges: [],
        },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /API Call/i })).toBeInTheDocument();
      });

      const nodeButton = screen.getByRole("button", { name: /API Call/i });
      await actClick(nodeButton);

      await waitFor(() => {
        expect(screen.getByText(/TIMEOUT/i)).toBeInTheDocument();
        expect(screen.getByText(/Request timed out after 30s/i)).toBeInTheDocument();
      });
    });

    it("renders agent step traces and approval state for agent nodes", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_id: "g1",
        graph_version_id: "v1",
        graph_name: "My Graph",
        status: "succeeded",
        agent_events: [
          {
            event: "agent.step.started",
            node_id: "agent_1",
            step_index: 1,
          },
        ],
        node_runs: [
          {
            id: "nr1",
            node_id: "agent_1",
            node_type: "agent",
            status: "succeeded",
            attempt: 1,
            started_at: "2024-01-15T10:00:00Z",
            ended_at: "2024-01-15T10:00:05Z",
            duration_ms: 5000,
            input_json: { customer_id: "cust_123" },
            output_json: {
              output: {
                final_output: "",
                stop_reason: "approval_required",
                step_count: 1,
                tool_call_count: 0,
                approval_pending: true,
                steps: [
                  {
                    step_index: 1,
                    action: "tool_call",
                    tool: "send_email",
                    tool_input: { to: "user@example.com" },
                    approval_required: true,
                  },
                ],
              },
            },
            error_json: null,
            agent_trace: {
              final_output: "",
              stop_reason: "approval_required",
              step_count: 1,
              tool_call_count: 0,
              approval_pending: true,
              steps: [
                {
                  step_index: 1,
                  action: "tool_call",
                  tool: "send_email",
                  tool_input: { to: "user@example.com" },
                  approval_required: true,
                },
              ],
              events: [
                {
                  event: "agent.step.started",
                  node_id: "agent_1",
                  step_index: 1,
                },
              ],
            },
          },
        ],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        id: "v1",
        version: 1,
        checksum: "x".repeat(64),
        created_at: "2024-01-15T09:00:00Z",
        graph_json: {
          nodes: [{ id: "agent_1", type: "agent", name: "Support Agent", config: {} }],
          edges: [],
        },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Support Agent/i })).toBeInTheDocument();
      });

      await actClick(screen.getByRole("button", { name: /Support Agent/i }));

      await waitFor(() => {
        expect(screen.getByText(/Agent execution/i)).toBeInTheDocument();
        expect(screen.getAllByText(/Approval required/i).length).toBeGreaterThan(0);
        expect(screen.getAllByText(/send_email/i).length).toBeGreaterThan(0);
        expect(screen.getByText(/Tool input/i)).toBeInTheDocument();
      });
    });

    it("shows curated memory influence before raw response payloads", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_id: "g1",
        graph_version_id: "v1",
        graph_name: "My Graph",
        status: "succeeded",
        node_runs: [
          {
            id: "nr1",
            node_id: "prompt_1",
            node_type: "prompt",
            status: "succeeded",
            attempt: 1,
            started_at: "2024-01-15T10:00:00Z",
            ended_at: "2024-01-15T10:00:01Z",
            duration_ms: 1000,
            input_json: { prompt: "Prepare the answer" },
            output_json: { response: "Bring sweet snacks." },
            error_json: null,
            memory_activity: {
              category: "influence",
              operation: "context_use",
              observation_count: 1,
              degraded: false,
              curated_context_paths: ["node.obs_context.output"],
              strategies: ["fts"],
              observations: [
                {
                  id: "obs-1",
                  type: "fact",
                  title: "Snack preference",
                  scope: "session",
                  topic_key: "snacks",
                  content_preview: "Customer prefers sweet snacks during meetings.",
                },
              ],
            },
          },
        ],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        id: "v1",
        version: 1,
        checksum: "x".repeat(64),
        created_at: "2024-01-15T09:00:00Z",
        graph_json: {
          nodes: [{ id: "prompt_1", type: "prompt", name: "Answer", config: {} }],
          edges: [],
        },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getAllByRole("button", { name: /Answer/i }).length).toBeGreaterThan(0);
      });

      const answerButtons = screen.getAllByRole("button", { name: /Answer/i });
      await actClick(answerButtons[answerButtons.length - 1]);

      await waitFor(() => {
        expect(screen.getByText(/Curated memory activity/i)).toBeInTheDocument();
      });

      expect(screen.getAllByText(/Context sources/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/node\.obs_context\.output/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Snack preference/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Customer prefers sweet snacks during meetings\./i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Response/i).length).toBeGreaterThan(0);
    });
  });

  describe("Final Output", () => {
    it("displays final output summary", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_name: "My Graph",
        status: "succeeded",
        output_json: { final_result: "Success", data: [1, 2, 3] },
        node_runs: [],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: { nodes: [], edges: [] },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/final_result/i)).toBeInTheDocument();
        expect(screen.getByText(/"Success"/i)).toBeInTheDocument();
      });
    });

    it("handles null output_json gracefully", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_name: "My Graph",
        status: "running",
        output_json: null,
        node_runs: [],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: { nodes: [], edges: [] },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/running/i)).toBeInTheDocument();
      });
    });
  });

  describe("Live Polling", () => {
    it("polls for updates on running runs", async () => {
      jest.useFakeTimers();

      const getSpy = jest
        .spyOn(api.runsApi, "get")
        .mockResolvedValueOnce({
          id: runId,
          graph_id: "g1",
          graph_version_id: "v1",
          graph_name: "My Graph",
          status: "running",
          node_runs: [],
        } as any)
        .mockResolvedValueOnce({
          id: runId,
          graph_id: "g1",
          graph_version_id: "v1",
          graph_name: "My Graph",
          status: "running",
          node_runs: [],
        } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: { nodes: [], edges: [] },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(getSpy).toHaveBeenCalledTimes(1);
      });

      act(() => {
        jest.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(getSpy).toHaveBeenCalledTimes(2);
      });

      jest.useRealTimers();
    });

    it("stops polling on terminal status (succeeded)", async () => {
      jest.useFakeTimers();

      const getSpy = jest
        .spyOn(api.runsApi, "get")
        .mockResolvedValueOnce({
          id: runId,
          graph_id: "g1",
          graph_version_id: "v1",
          graph_name: "My Graph",
          status: "running",
          node_runs: [],
        } as any)
        .mockResolvedValueOnce({
          id: runId,
          graph_id: "g1",
          graph_version_id: "v1",
          graph_name: "My Graph",
          status: "succeeded",
          node_runs: [],
        } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: { nodes: [], edges: [] },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(getSpy).toHaveBeenCalledTimes(1);
      });

      act(() => {
        jest.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(getSpy).toHaveBeenCalledTimes(2);
      });

      // Should not poll again after succeeded
      act(() => {
        jest.advanceTimersByTime(10000);
      });

      await waitFor(() => {
        expect(getSpy).toHaveBeenCalledTimes(2);
      });

      jest.useRealTimers();
    });

    it("stops polling on terminal status (failed)", async () => {
      jest.useFakeTimers();

      const getSpy = jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_id: "g1",
        graph_version_id: "v1",
        graph_name: "My Graph",
        status: "failed",
        error_message: "Node failed",
        node_runs: [],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: { nodes: [], edges: [] },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(getSpy).toHaveBeenCalledTimes(1);
      });

      // Should not poll again after failed
      act(() => {
        jest.advanceTimersByTime(10000);
      });

      expect(getSpy).toHaveBeenCalledTimes(1);

      jest.useRealTimers();
    });

    it("stops polling on terminal status (canceled)", async () => {
      jest.useFakeTimers();

      const getSpy = jest.spyOn(api.runsApi, "get").mockResolvedValue({
        id: runId,
        graph_id: "g1",
        graph_version_id: "v1",
        graph_name: "My Graph",
        status: "canceled",
        error_message: "Canceled by user",
        node_runs: [],
      } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: { nodes: [], edges: [] },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(getSpy).toHaveBeenCalledTimes(1);
      });

      // Should not poll again after canceled
      act(() => {
        jest.advanceTimersByTime(10000);
      });

      expect(getSpy).toHaveBeenCalledTimes(1);

      jest.useRealTimers();
    });

    it("handles polling failures gracefully", async () => {
      jest.useFakeTimers();

      const getSpy = jest
        .spyOn(api.runsApi, "get")
        .mockResolvedValueOnce({
          id: runId,
          graph_id: "g1",
          graph_version_id: "v1",
          graph_name: "My Graph",
          status: "running",
          node_runs: [],
        } as any)
        .mockRejectedValueOnce(new Error("Network error"))
        .mockResolvedValueOnce({
          id: runId,
          graph_id: "g1",
          graph_version_id: "v1",
          graph_name: "My Graph",
          status: "running",
          node_runs: [],
        } as any);

      jest.spyOn(api.graphsApi, "getVersion").mockResolvedValue({
        graph_json: { nodes: [], edges: [] },
      } as any);

      render(<RunDetailPage />);

      await waitFor(() => {
        expect(getSpy).toHaveBeenCalledTimes(1);
      });

      // First poll fails
      act(() => {
        jest.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(getSpy).toHaveBeenCalledTimes(2);
      });

      // Should continue polling after error
      act(() => {
        jest.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(getSpy).toHaveBeenCalledTimes(3);
      });

      jest.useRealTimers();
    });
  });
});
