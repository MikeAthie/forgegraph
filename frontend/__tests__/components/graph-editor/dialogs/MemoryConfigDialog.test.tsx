import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryConfigDialog } from "@/components/graph-editor/dialogs/MemoryConfigDialog";
import type { MemoryConfig } from "@/lib/api";

jest.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children, open }: any) => <div data-testid="dialog">{open ? children : null}</div>,
  DialogContent: ({ children }: any) => <div data-testid="dialog-content">{children}</div>,
  DialogHeader: ({ children }: any) => <div data-testid="dialog-header">{children}</div>,
  DialogTitle: ({ children }: any) => <h2 data-testid="dialog-title">{children}</h2>,
  DialogDescription: ({ children }: any) => <p data-testid="dialog-description">{children}</p>,
  DialogFooter: ({ children }: any) => <div data-testid="dialog-footer">{children}</div>,
}));

jest.mock("@/lib/api", () => {
  const actual = jest.requireActual("@/lib/api");

  return {
    ...actual,
    graphsApi: {
      ...actual.graphsApi,
      getMemoryConfig: jest.fn(),
      updateMemoryConfig: jest.fn(),
    },
    getApiErrorMessage: jest.fn((_, fallback) => fallback as string),
  };
});

const showError = jest.fn();
const showSuccess = jest.fn();

jest.mock("@/lib/toast", () => ({
  showError: (...args: unknown[]) => showError(...args),
  showSuccess: (...args: unknown[]) => showSuccess(...args),
}));

const baseConfig: MemoryConfig = {
  id: "config-1",
  graph: "graph-1",
  user: null,
  buffer_enabled: true,
  buffer_size: 50,
  auto_prepend: true,
  redis_enabled: true,
  redis_summary_ttl: 7200,
  redis_facts_ttl: 86400,
  vector_enabled: false,
  vector_top_k: 5,
  vector_threshold: 0.7,
  vector_recency_weight: undefined,
  embedding_model: "text-embedding-ada-002",
  summarization_enabled: false,
  summarization_threshold: 30,
  summarization_keep_recent: 10,
  summarization_model: "gpt-4",
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

describe("MemoryConfigDialog", () => {
  const setupUser = () => {
    const user = userEvent.setup();
    return {
      click: (element: HTMLElement) => act(async () => user.click(element)),
      type: (element: HTMLElement, text: string) => act(async () => user.type(element, text)),
      clear: (element: HTMLElement) => act(async () => user.clear(element)),
      select: (element: HTMLElement, value: string) =>
        act(async () => user.selectOptions(element, value)),
    };
  };

  const getMocks = () => {
    const api = jest.requireMock("@/lib/api") as typeof import("@/lib/api");
    return {
      mockGetMemoryConfig: api.graphsApi.getMemoryConfig as jest.Mock,
      mockUpdateMemoryConfig: api.graphsApi.updateMemoryConfig as jest.Mock,
      mockGetApiErrorMessage: api.getApiErrorMessage as jest.Mock,
    };
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("loads and displays current config", async () => {
    const { mockGetMemoryConfig } = getMocks();
    mockGetMemoryConfig.mockResolvedValue(baseConfig);

    render(<MemoryConfigDialog graphId="graph-1" open={true} onOpenChange={jest.fn()} />);

    expect(screen.getByText(/loading memory configuration/i)).toBeInTheDocument();

    const memoryDepth = await screen.findByLabelText(/memory depth/i);
    expect(memoryDepth).toHaveValue("long");

    const persistenceSwitch = screen.getByRole("switch", { name: /enable persistence/i });
    expect(persistenceSwitch).toHaveAttribute("aria-checked", "true");
  });

  it("shows custom buffer size input when custom depth is selected", async () => {
    const { mockGetMemoryConfig } = getMocks();
    mockGetMemoryConfig.mockResolvedValue(baseConfig);
    const { select } = setupUser();

    render(<MemoryConfigDialog graphId="graph-1" open={true} onOpenChange={jest.fn()} />);

    const memoryDepth = await screen.findByLabelText(/memory depth/i);
    await select(memoryDepth, "custom");

    expect(await screen.findByLabelText(/custom buffer size/i)).toBeInTheDocument();
  });

  it("saves updated configuration", async () => {
    const { mockGetMemoryConfig, mockUpdateMemoryConfig } = getMocks();
    mockGetMemoryConfig.mockResolvedValue(baseConfig);
    mockUpdateMemoryConfig.mockResolvedValue({
      ...baseConfig,
      buffer_size: 42,
      redis_enabled: false,
    });
    const onOpenChange = jest.fn();
    const { click, clear, select, type } = setupUser();

    render(<MemoryConfigDialog graphId="graph-1" open={true} onOpenChange={onOpenChange} />);

    const memoryDepth = await screen.findByLabelText(/memory depth/i);
    await select(memoryDepth, "custom");

    const customSizeInput = await screen.findByLabelText(/custom buffer size/i);
    await clear(customSizeInput);
    await type(customSizeInput, "42");

    const persistenceSwitch = screen.getByRole("switch", { name: /enable persistence/i });
    await click(persistenceSwitch);

    const advancedButton = screen.getByRole("button", { name: /show advanced settings/i });
    await click(advancedButton);

    const summaryInput = await screen.findByLabelText(/summary ttl/i);
    await clear(summaryInput);
    await type(summaryInput, "48");

    const factsInput = await screen.findByLabelText(/facts ttl/i);
    await clear(factsInput);
    await type(factsInput, "10");

    await click(screen.getByRole("button", { name: /save settings/i }));

    await waitFor(() => {
      expect(mockUpdateMemoryConfig).toHaveBeenCalledWith("graph-1", {
        buffer_enabled: true,
        buffer_size: 42,
        auto_prepend: true,
        redis_enabled: false,
        redis_summary_ttl: 48 * 3600,
        redis_facts_ttl: 10 * 86400,
        vector_enabled: baseConfig.vector_enabled,
        vector_top_k: baseConfig.vector_top_k,
        vector_threshold: baseConfig.vector_threshold,
        vector_recency_weight: baseConfig.vector_recency_weight,
        embedding_model: baseConfig.embedding_model,
        summarization_enabled: baseConfig.summarization_enabled,
        summarization_threshold: baseConfig.summarization_threshold,
        summarization_keep_recent: baseConfig.summarization_keep_recent,
        summarization_model: baseConfig.summarization_model,
      });
    });

    expect(showSuccess).toHaveBeenCalledWith("Memory settings saved.");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("blocks save when buffer size is invalid", async () => {
    const { mockGetMemoryConfig, mockUpdateMemoryConfig } = getMocks();
    mockGetMemoryConfig.mockResolvedValue(baseConfig);
    const { click, clear, select, type } = setupUser();

    render(<MemoryConfigDialog graphId="graph-1" open={true} onOpenChange={jest.fn()} />);

    const memoryDepth = await screen.findByLabelText(/memory depth/i);
    await select(memoryDepth, "custom");

    const customSizeInput = await screen.findByLabelText(/custom buffer size/i);
    await clear(customSizeInput);
    await type(customSizeInput, "0");

    await click(screen.getByRole("button", { name: /save settings/i }));

    await waitFor(() => {
      expect(showError).toHaveBeenCalledWith("Buffer size must be between 1 and 200.");
    });
    expect(mockUpdateMemoryConfig).not.toHaveBeenCalled();
  });
});
