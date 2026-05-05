import { act, render, waitFor } from "@testing-library/react";

import { useRunLiveUpdates } from "@/hooks/useRunLiveUpdates";
import { useStateFeed, type StateFeedMessage } from "@/hooks/useStateFeed";
import { authApi } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  authApi: {
    issueWsTicket: jest.fn(),
  },
}));

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  send = jest.fn();

  constructor(public readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  open() {
    this.onopen?.();
  }

  close() {
    this.onclose?.();
  }

  receive(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
}

function OrganizationProbe({
  organizationId,
  lastSeenStateVersion,
  onEvent,
  onFullResync = jest.fn(),
}: {
  organizationId: string | null;
  lastSeenStateVersion?: number;
  onEvent: (event: StateFeedMessage) => void;
  onFullResync?: (event: StateFeedMessage) => void;
}) {
  useStateFeed({
    scope: "organization",
    organizationId,
    lastSeenStateVersion,
    eventTypes: ["overview.updated", "decision.created"],
    onEvent,
    onFullResync,
  });
  return null;
}

function RunProbe({ runId, onInvalidate }: { runId: string | null; onInvalidate: () => void }) {
  useRunLiveUpdates(runId, onInvalidate);
  return null;
}

describe("useStateFeed", () => {
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

  it("opens an organization websocket and resumes from the backend state version", async () => {
    const onEvent = jest.fn();

    render(<OrganizationProbe organizationId="org-123" lastSeenStateVersion={42} onEvent={onEvent} />);

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const openedUrl = new URL(FakeWebSocket.instances[0].url);
    expect(`${openedUrl.origin}${openedUrl.pathname}`).toBe("ws://backend.test/ws/organizations/org-123/state/");
    expect(openedUrl.searchParams.get("ticket")).toBe("ws-ticket-1");
    expect(openedUrl.searchParams.get("last_seen_state_version")).toBe("42");
    expect(openedUrl.searchParams.get("event_types")).toBe("overview.updated,decision.created");

    act(() => {
      FakeWebSocket.instances[0].open();
    });

    expect(FakeWebSocket.instances[0].send).toHaveBeenCalledWith(
      JSON.stringify({ type: "resume", event_id: "", last_seen_state_version: 42 }),
    );

    act(() => {
      FakeWebSocket.instances[0].receive({
        type: "overview.updated",
        event_id: "evt-1",
        state_version: 43,
        requires_refetch: true,
      });
    });

    expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ type: "overview.updated" }));
  });

  it("handles heartbeats and full resync without local state invention", async () => {
    const onEvent = jest.fn();
    const onFullResync = jest.fn();

    render(<OrganizationProbe organizationId="org-789" onEvent={onEvent} onFullResync={onFullResync} />);

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));

    act(() => {
      FakeWebSocket.instances[0].receive({
        type: "connection_established",
        event_id: "evt-1",
        payload: { replay_supported: true, resync_required: false, latest_state_version: 7 },
      });
      FakeWebSocket.instances[0].receive({ type: "heartbeat" });
      FakeWebSocket.instances[0].receive({ type: "full_resync_required", reason: "replay_window_expired" });
    });

    expect(onEvent).not.toHaveBeenCalled();
    expect(onFullResync).toHaveBeenCalledTimes(1);
    expect(FakeWebSocket.instances[0].send).toHaveBeenCalledWith(
      JSON.stringify({ type: "pong", event_id: "evt-1", last_seen_state_version: 7 }),
    );
  });

  it("reconnects with the last backend state version", async () => {
    const onEvent = jest.fn();

    render(<OrganizationProbe organizationId="org-999" onEvent={onEvent} />);

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));

    jest.useFakeTimers();
    try {
      act(() => {
        FakeWebSocket.instances[0].receive({ type: "decision.created", event_id: "evt-9", state_version: 9 });
        FakeWebSocket.instances[0].onclose?.();
      });

      await act(async () => {
        jest.advanceTimersByTime(2000);
        await Promise.resolve();
      });

      expect(FakeWebSocket.instances).toHaveLength(2);
      const reconnectUrl = new URL(FakeWebSocket.instances[1].url);
      expect(reconnectUrl.searchParams.get("last_event_id")).toBe("evt-9");
      expect(reconnectUrl.searchParams.get("last_seen_state_version")).toBe("9");
    } finally {
      jest.useRealTimers();
    }
  });

  it("keeps the run live update wrapper compatible", async () => {
    const onInvalidate = jest.fn();

    render(<RunProbe runId="run-123" onInvalidate={onInvalidate} />);

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const openedUrl = new URL(FakeWebSocket.instances[0].url);
    expect(`${openedUrl.origin}${openedUrl.pathname}`).toBe("ws://backend.test/ws/runs/run-123/");

    act(() => {
      FakeWebSocket.instances[0].receive({ type: "run_completed", state_version: 1 });
    });

    expect(onInvalidate).toHaveBeenCalledTimes(1);
  });
});
