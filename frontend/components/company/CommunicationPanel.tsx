import { useCallback, useEffect, useMemo, useReducer } from "react";
import { LockKeyhole, MessageSquare, Paperclip, Send } from "lucide-react";

import { StatusBadge, formatDateTime } from "@/components/os/operations-ui";
import {
  Button,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
  Textarea,
} from "@/components/ui";
import { communicationRepository } from "@/domain/repositories";
import { translateProductError } from "@/domain/errors";
import type { CommunicationMessageDTO, CommunicationThreadDTO, CommunicationVisibility } from "@/lib/api";
import { showError } from "@/lib/toast";

type CommunicationPanelProps = {
  companyId: string;
  companyName: string;
};

type CommunicationPanelState = {
  threads: CommunicationThreadDTO[];
  messages: CommunicationMessageDTO[];
  selectedThreadId: string;
  body: string;
  visibility: CommunicationVisibility;
  loading: boolean;
  sending: boolean;
  error: string | null;
};

type CommunicationPanelAction =
  | { type: "load-threads-start" }
  | { type: "load-threads-success"; threads: CommunicationThreadDTO[] }
  | { type: "load-threads-error"; error: string }
  | { type: "load-messages-clear" }
  | { type: "load-messages-success"; messages: CommunicationMessageDTO[] }
  | { type: "load-messages-error"; error: string }
  | { type: "select-thread"; selectedThreadId: string }
  | { type: "set-body"; body: string }
  | { type: "set-visibility"; visibility: CommunicationVisibility }
  | { type: "send-start" }
  | { type: "send-thread-created"; thread: CommunicationThreadDTO }
  | { type: "send-success" }
  | { type: "send-error"; error: string }
  | { type: "send-finish" };

const initialCommunicationPanelState: CommunicationPanelState = {
  threads: [],
  messages: [],
  selectedThreadId: "",
  body: "",
  visibility: "customer",
  loading: true,
  sending: false,
  error: null,
};

function communicationPanelReducer(
  state: CommunicationPanelState,
  action: CommunicationPanelAction,
): CommunicationPanelState {
  switch (action.type) {
    case "load-threads-start":
      return { ...state, loading: true, error: null };
    case "load-threads-success": {
      const selectedThreadId =
        state.selectedThreadId && action.threads.some((thread) => thread.id === state.selectedThreadId)
          ? state.selectedThreadId
          : (action.threads[0]?.id ?? "");
      return { ...state, threads: action.threads, selectedThreadId, loading: false };
    }
    case "load-threads-error":
      return { ...state, error: action.error, loading: false };
    case "load-messages-clear":
      return { ...state, messages: [] };
    case "load-messages-success":
      return { ...state, messages: action.messages };
    case "load-messages-error":
      return { ...state, error: action.error };
    case "select-thread":
      return { ...state, selectedThreadId: action.selectedThreadId };
    case "set-body":
      return { ...state, body: action.body };
    case "set-visibility":
      return { ...state, visibility: action.visibility };
    case "send-start":
      return { ...state, sending: true, error: null };
    case "send-thread-created":
      return { ...state, threads: [action.thread], selectedThreadId: action.thread.id };
    case "send-success":
      return { ...state, body: "" };
    case "send-error":
      return { ...state, error: action.error };
    case "send-finish":
      return { ...state, sending: false };
    default:
      return state;
  }
}

function visibilityLabel(value: string): string {
  if (value === "internal") {
    return "Internal";
  }
  if (value === "operator") {
    return "Operator";
  }
  return "Customer-visible";
}

function attachmentLabel(type: string): string {
  return type.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function CommunicationPanel({ companyId, companyName }: CommunicationPanelProps) {
  const [state, dispatch] = useReducer(communicationPanelReducer, initialCommunicationPanelState);
  const { threads, messages, selectedThreadId, body, visibility, loading, sending, error } = state;

  const selectedThread = useMemo(
    () => threads.find((thread) => thread.id === selectedThreadId) ?? threads[0] ?? null,
    [selectedThreadId, threads],
  );

  const canSendInternal = Boolean(selectedThread?.can_send_internal);

  const loadThreads = useCallback(async () => {
    dispatch({ type: "load-threads-start" });
    try {
      const threadList = await communicationRepository.listThreads({ companyId });
      dispatch({ type: "load-threads-success", threads: threadList });
    } catch (loadError: unknown) {
      const message = translateProductError(loadError, "company");
      dispatch({ type: "load-threads-error", error: message });
    }
  }, [companyId]);

  const loadMessages = useCallback(async (threadId: string) => {
    if (!threadId) {
      dispatch({ type: "load-messages-clear" });
      return;
    }
    try {
      const messageList = await communicationRepository.listMessages(threadId);
      dispatch({ type: "load-messages-success", messages: messageList });
    } catch (loadError: unknown) {
      const message = translateProductError(loadError, "company");
      dispatch({ type: "load-messages-error", error: message });
    }
  }, []);

  useEffect(() => {
    void loadThreads();
  }, [loadThreads]);

  useEffect(() => {
    void loadMessages(selectedThread?.id ?? "");
  }, [loadMessages, selectedThread?.id]);

  useEffect(() => {
    if (!canSendInternal && visibility !== "customer") {
      dispatch({ type: "set-visibility", visibility: "customer" });
    }
  }, [canSendInternal, visibility]);

  const handleSend = async () => {
    const trimmed = body.trim();
    if (!trimmed || sending) {
      return;
    }
    dispatch({ type: "send-start" });
    try {
      let thread = selectedThread;
      if (!thread) {
        thread = await communicationRepository.createThread({
          company_id: companyId,
          title: `${companyName} Communication`,
          thread_type: "support",
          visibility_mode: "mixed",
          source_key: `company:${companyId}:primary_communication`,
          metadata: {},
        });
        dispatch({ type: "send-thread-created", thread });
      }
      await communicationRepository.createMessage(thread.id, {
        message_kind: trimmed.endsWith("?") ? "request" : "note",
        body_format: "markdown",
        body: trimmed,
        visibility,
        metadata: {},
        attachments: [],
      });
      dispatch({ type: "send-success" });
      await Promise.all([loadThreads(), loadMessages(thread.id)]);
    } catch (sendError: unknown) {
      const message = translateProductError(sendError, "company");
      dispatch({ type: "send-error", error: message });
      showError("Message not sent", message);
    } finally {
      dispatch({ type: "send-finish" });
    }
  };

  return (
    <div
      data-testid="communication-panel"
      className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
          <MessageSquare className="size-4" />
          <p className="text-sm font-semibold">Communication</p>
        </div>
        <StatusBadge status={selectedThread?.status ?? "open"} label={`${messages.length} messages`} />
      </div>

      {loading ? (
        <div className="mt-4 flex min-h-[92px] items-center justify-center">
          <Spinner size="sm" />
        </div>
      ) : (
        <>
          {threads.length > 1 ? (
            <div className="mt-3" data-testid="communication-thread-list">
              <Select
                value={selectedThread?.id ?? ""}
                onValueChange={(value) => dispatch({ type: "select-thread", selectedThreadId: value })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Thread" />
                </SelectTrigger>
                <SelectContent>
                  {threads.map((thread) => (
                    <SelectItem key={thread.id} value={thread.id}>
                      {thread.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}

          <div data-testid="communication-message-list" className="mt-4 space-y-3">
            {messages.length ? (
              messages.map((message) => (
                <div
                  key={message.id}
                  data-testid={`communication-message-${message.id}`}
                  className="rounded-[1rem] border border-zinc-900/8 bg-white/75 p-3 dark:border-white/8 dark:bg-white/5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold uppercase text-zinc-500 dark:text-zinc-400">
                        {message.sender_kind}
                      </span>
                      <span className="text-xs text-zinc-400 dark:text-zinc-500">
                        {formatDateTime(message.created_at)}
                      </span>
                    </div>
                    <span data-testid="communication-message-visibility">
                      <StatusBadge status={message.visibility} label={visibilityLabel(message.visibility)} />
                    </span>
                    {message.visibility === "internal" ? (
                      <span data-testid="communication-internal-badge" title="Internal">
                        <LockKeyhole className="size-3.5 text-amber-600 dark:text-amber-300" />
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-zinc-800 dark:text-zinc-100">
                    {message.redacted ? "Message redacted" : message.body}
                  </p>
                  {message.attachments.length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {message.attachments.map((attachment) => (
                        <span
                          key={attachment.id}
                          data-testid={`communication-attachment-${attachment.type}-${attachment.target_id}`}
                          className="inline-flex items-center gap-1.5 rounded-full border border-zinc-900/10 bg-white px-2.5 py-1 text-xs text-zinc-600 dark:border-white/10 dark:bg-white/6 dark:text-zinc-300"
                        >
                          <Paperclip className="size-3" />
                          {attachmentLabel(attachment.type)}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            ) : (
              <div className="rounded-[1rem] border border-dashed border-zinc-900/12 bg-white/50 p-4 text-sm text-zinc-500 dark:border-white/10 dark:bg-white/5 dark:text-zinc-400">
                No messages yet.
              </div>
            )}
          </div>

          <div className="mt-4 grid gap-2 sm:grid-cols-[1fr_auto]">
            <Textarea
              data-testid="communication-composer"
              value={body}
              onChange={(event) => dispatch({ type: "set-body", body: event.target.value })}
              placeholder="Write a message"
              rows={3}
            />
            <div className="flex flex-row gap-2 sm:flex-col">
              {canSendInternal ? (
                <Select
                  value={visibility}
                  onValueChange={(value) =>
                    dispatch({ type: "set-visibility", visibility: value as CommunicationVisibility })
                  }
                >
                  <SelectTrigger data-testid="communication-visibility-select" className="min-w-[150px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="customer">Customer</SelectItem>
                    <SelectItem value="internal">Internal</SelectItem>
                  </SelectContent>
                </Select>
              ) : null}
              <Button
                data-testid="communication-send-button"
                type="button"
                onClick={() => void handleSend()}
                disabled={!body.trim() || sending}
              >
                {sending ? <Spinner size="xs" /> : <Send className="size-4" />}
                Send
              </Button>
            </div>
          </div>
          {error ? <p className="mt-3 text-sm text-red-600 dark:text-red-300">{error}</p> : null}
        </>
      )}
    </div>
  );
}
