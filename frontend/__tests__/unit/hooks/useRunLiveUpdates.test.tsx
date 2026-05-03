import { act, render, waitFor } from "@testing-library/react";

import { useRunLiveUpdates } from "@/hooks/useRunLiveUpdates";
import { authApi } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  authApi: {
    issueWsTicket: jest.fn(),
  },
}));

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  send = jest.fn();

  constructor(public readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  close() {
    this.onclose?.();
  }

  receive(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
}

function Probe({ runId, onInvalidate }: { runId: string | null; onInvalidate: () => void | Promise<void> }) {
  useRunLiveUpdates(runId, onInvalidate);
  return null;
}

describe("useRunLiveUpdates", () => {
  const originalWebSocket = global.WebSocket;

  beforeEach(() => {
    jest.clearAllMocks();
    FakeWebSocket.instances = [];
    (authApi.issueWsTicket as jest.Mock).mockResolvedValue({ ticket: "ws-ticket-1" });
    global.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    process.env.NEXT_PUBLIC_API_URL = "http://backend.test";
  });

  afterEach(() => {
    global.WebSocket = originalWebSocket;
  });

  it("opens a backend-ticketed run websocket and invalidates through the caller refetch callback", async () => {
    const onInvalidate = jest.fn();

    render(<Probe runId="run-123" onInvalidate={onInvalidate} />);

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    expect(authApi.issueWsTicket).toHaveBeenCalledTimes(1);
    const openedUrl = new URL(FakeWebSocket.instances[0].url);
    expect(`${openedUrl.origin}${openedUrl.pathname}`).toBe("ws://backend.test/ws/runs/run-123/");
    expect(openedUrl.searchParams.get("ticket")).toBe("ws-ticket-1");
    expect(openedUrl.searchParams.get("event_level")).toBe("default");
    expect(openedUrl.searchParams.get("event_types")).toContain("run_completed");

    act(() => {
      FakeWebSocket.instances[0].receive({ type: "run_completed", status: "succeeded" });
    });

    expect(onInvalidate).toHaveBeenCalledTimes(1);
  });

  it("uses backend resync messages and heartbeats without inventing state", async () => {
    const onInvalidate = jest.fn();

    render(<Probe runId="run-789" onInvalidate={onInvalidate} />);

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));

    act(() => {
      FakeWebSocket.instances[0].receive({ type: "connection_established", event_id: "evt-1" });
      FakeWebSocket.instances[0].receive({ type: "heartbeat" });
    });

    expect(onInvalidate).toHaveBeenCalledTimes(1);
    expect(FakeWebSocket.instances[0].send).toHaveBeenCalledWith(
      JSON.stringify({ type: "pong", event_id: "evt-1" }),
    );
  });

  it("ignores transport-only messages instead of inventing final backend state locally", async () => {
    const onInvalidate = jest.fn();

    render(<Probe runId="run-456" onInvalidate={onInvalidate} />);

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));

    act(() => {
      FakeWebSocket.instances[0].receive({ type: "socket.connected", status: "approved" });
      FakeWebSocket.instances[0].receive({ data: { event_type: "decision_resolved" } });
    });

    expect(onInvalidate).toHaveBeenCalledTimes(1);
  });
});
