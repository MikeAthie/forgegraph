import { useEffect, useRef } from "react";

import { authApi } from "@/lib/api";

type RunLiveMessage = {
  type?: string;
  event_type?: string;
  event_id?: string;
  event?: {
    type?: string;
    event_type?: string;
  };
  data?: {
    type?: string;
    event_type?: string;
  };
};

const RUN_INVALIDATION_MESSAGES = new Set([
  "connection_established",
  "resync_required",
  "run_started",
  "run_updated",
  "run_paused",
  "run_resumed",
  "run_completed",
  "run_failed",
  "run_canceled",
  "node_started",
  "node_completed",
  "node_failed",
  "node_updated",
  "decision_required",
  "decision_resolved",
  "cost_update",
  "cost_updated",
]);

function websocketBaseUrl() {
  const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
  const parsed = new URL(apiBase);
  parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
  parsed.pathname = "";
  parsed.search = "";
  parsed.hash = "";
  return parsed.toString().replace(/\/$/, "");
}

function messageType(message: RunLiveMessage) {
  return (
    message.type ||
    message.event_type ||
    message.event?.type ||
    message.event?.event_type ||
    message.data?.type ||
    message.data?.event_type ||
    ""
  );
}

export function useRunLiveUpdates(
  runId: string | null | undefined,
  onBackendStateInvalidated: () => void | Promise<void>,
  options?: { enabled?: boolean },
) {
  const callbackRef = useRef(onBackendStateInvalidated);

  useEffect(() => {
    callbackRef.current = onBackendStateInvalidated;
  }, [onBackendStateInvalidated]);

  useEffect(() => {
    if (!runId || options?.enabled === false || typeof window === "undefined") {
      return;
    }

    let closed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    const lastEventIdRef = { current: "" };

    const connect = async () => {
      try {
        const ticket = await authApi.issueWsTicket();
        if (closed) {
          return;
        }

        const params = new URLSearchParams({
          ticket: ticket.ticket,
          event_level: "default",
          event_types: Array.from(RUN_INVALIDATION_MESSAGES).join(","),
        });
        if (lastEventIdRef.current) {
          params.set("last_event_id", lastEventIdRef.current);
        }

        socket = new WebSocket(`${websocketBaseUrl()}/ws/runs/${encodeURIComponent(runId)}/?${params.toString()}`);
        socket.onmessage = (event) => {
          try {
            const parsed = JSON.parse(String(event.data ?? "{}")) as RunLiveMessage;
            const parsedType = messageType(parsed);
            if (parsed.event_id) {
              lastEventIdRef.current = parsed.event_id;
            }
            if (parsedType === "heartbeat") {
              socket?.send(JSON.stringify({ type: "pong", event_id: lastEventIdRef.current }));
              return;
            }
            if (RUN_INVALIDATION_MESSAGES.has(parsedType)) {
              void callbackRef.current();
            }
          } catch {
            // Ignore malformed transport messages; the next valid backend update will refetch state.
          }
        };
        socket.onclose = () => {
          if (!closed) {
            reconnectTimer = window.setTimeout(() => void connect(), 2000);
          }
        };
      } catch {
        if (!closed) {
          reconnectTimer = window.setTimeout(() => void connect(), 2000);
        }
      }
    };

    void connect();

    return () => {
      closed = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [options?.enabled, runId]);
}
