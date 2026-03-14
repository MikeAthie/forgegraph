import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import * as api from "@/lib/api";
import MemoryBrowserPage from "@/pages/memory";

jest.mock("@/components/DashboardLayout", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <div data-testid="dashboard-layout">{children}</div>,
}));

jest.mock("@/components/ProtectedRoute", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

const observationOne: api.MemoryObservation = {
  id: "obs-1",
  tenant_id: "tenant-1",
  graph_id: "graph-1",
  run_id: "run-1",
  session_id: "session-1",
  agent_id: "agent-1",
  memory_chunk_id: "chunk-1",
  type: "fact",
  title: "Jackie prefers concise follow-ups",
  content: "Jackie prefers concise follow-ups and wants action items grouped by owner.",
  scope: "graph",
  topic_key: "jackie-style",
  tool_name: "slack",
  revision_count: 2,
  duplicate_count: 1,
  last_seen_at: "2026-03-10T18:35:00Z",
  created_at: "2026-03-08T10:00:00Z",
  updated_at: "2026-03-09T09:15:00Z",
  deleted_at: null,
  is_deleted: false,
};

const observationTwo: api.MemoryObservation = {
  ...observationOne,
  id: "obs-2",
  graph_id: null,
  run_id: "run-2",
  session_id: "session-2",
  memory_chunk_id: null,
  type: "summary",
  title: "Weekly launch summary",
  content: "Launch blockers were reduced from four to one after the Tuesday review.",
  scope: "run",
  topic_key: "launch-week",
  tool_name: "notion",
};

describe("Memory Browser Page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders the loading state while the timeline is pending", () => {
    jest.spyOn(api.memoryApi, "timeline").mockImplementation(() => new Promise(() => {}));

    render(<MemoryBrowserPage />);

    expect(screen.getByText(/loading curated memory/i)).toBeInTheDocument();
  });

  it("loads the default timeline and observation detail", async () => {
    jest.spyOn(api.memoryApi, "timeline").mockResolvedValue([observationOne, observationTwo]);
    jest.spyOn(api.memoryApi, "get").mockResolvedValue(observationOne);

    render(<MemoryBrowserPage />);

    await waitFor(() => {
      expect(api.memoryApi.timeline).toHaveBeenCalledWith({ scope: undefined, limit: 24 });
    });

    await waitFor(() => {
      expect(api.memoryApi.get).toHaveBeenCalledWith("obs-1");
    });

    expect(screen.getAllByText("Jackie prefers concise follow-ups").length).toBeGreaterThan(0);
    expect(screen.getByText(/weekly launch summary/i)).toBeInTheDocument();
    expect(screen.getByText(/captured content/i)).toBeInTheDocument();
    expect(screen.getAllByText(/linked scope/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/timeline/i).length).toBeGreaterThan(0);
  });

  it("switches to search mode and shows a no-results state", async () => {
    const user = userEvent.setup();

    jest.spyOn(api.memoryApi, "timeline").mockResolvedValue([observationOne, observationTwo]);
    jest.spyOn(api.memoryApi, "get").mockResolvedValue(observationOne);
    jest.spyOn(api.memoryApi, "search").mockResolvedValue([]);

    render(<MemoryBrowserPage />);

    await waitFor(() => {
      expect(screen.getAllByText(/jackie prefers concise follow-ups/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getAllByRole("button", { name: /summary/i })[0]);

    await waitFor(() => {
      expect(api.memoryApi.search).toHaveBeenCalledWith({
        query: undefined,
        scope: undefined,
        type: "summary",
        limit: 24,
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/no observations matched/i)).toBeInTheDocument();
    });
  });

  it("applies the scope filter to the timeline request", async () => {
    const timelineSpy = jest
      .spyOn(api.memoryApi, "timeline")
      .mockResolvedValue([observationOne]);
    jest.spyOn(api.memoryApi, "get").mockResolvedValue(observationOne);

    const user = userEvent.setup();
    render(<MemoryBrowserPage />);

    await waitFor(() => {
      expect(timelineSpy).toHaveBeenCalledWith({ scope: undefined, limit: 24 });
    });

    await user.click(screen.getByRole("button", { name: /^graph$/i }));

    await waitFor(() => {
      expect(timelineSpy).toHaveBeenLastCalledWith({ scope: "graph", limit: 24 });
    });
  });

  it("renders an error banner when the API request fails", async () => {
    jest.spyOn(api.memoryApi, "timeline").mockRejectedValue(new Error("Timeline exploded"));

    render(<MemoryBrowserPage />);

    await waitFor(() => {
      expect(screen.getByText("Timeline exploded")).toBeInTheDocument();
    });
  });
});
