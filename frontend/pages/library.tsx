import { useEffect, useMemo, useReducer } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import DashboardLayout from "@/components/DashboardLayout";
import {
  EmptyBlock,
  InspectorPanel,
  Panel,
  SectionHeader,
  SelectionList,
  StatusBadge,
  formatDateTime,
} from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import { getApiErrorMessage, promptsApi, type PromptDetail, type PromptListItem } from "@/lib/api";
import { showSuccess } from "@/lib/toast";

type LibraryState = {
  prompts: PromptListItem[];
  selectedPrompt: PromptDetail | null;
  loading: boolean;
  detailLoading: boolean;
  actionLoading: boolean;
  error: string | null;
};

type LibraryAction =
  | { type: "list-success"; prompts: PromptListItem[] }
  | { type: "list-error"; error: string }
  | { type: "detail-start" }
  | { type: "detail-empty" }
  | { type: "detail-success"; selectedPrompt: PromptDetail }
  | { type: "detail-error"; error: string }
  | { type: "action-start" }
  | { type: "action-success"; prompts: PromptListItem[]; selectedPrompt: PromptDetail }
  | { type: "action-error"; error: string };

const initialLibraryState: LibraryState = {
  prompts: [],
  selectedPrompt: null,
  loading: true,
  detailLoading: false,
  actionLoading: false,
  error: null,
};

function libraryReducer(state: LibraryState, action: LibraryAction): LibraryState {
  switch (action.type) {
    case "list-success":
      return { ...state, prompts: action.prompts, loading: false, error: null };
    case "list-error":
      return { ...state, loading: false, error: action.error };
    case "detail-start":
      return { ...state, detailLoading: true };
    case "detail-empty":
      return { ...state, selectedPrompt: null, detailLoading: false };
    case "detail-success":
      return { ...state, selectedPrompt: action.selectedPrompt, detailLoading: false, error: null };
    case "detail-error":
      return { ...state, detailLoading: false, error: action.error };
    case "action-start":
      return { ...state, actionLoading: true, error: null };
    case "action-success":
      return {
        ...state,
        prompts: action.prompts,
        selectedPrompt: action.selectedPrompt,
        actionLoading: false,
        error: null,
      };
    case "action-error":
      return { ...state, actionLoading: false, error: action.error };
    default:
      return state;
  }
}

function PromptDetailPanel({
  selectedPrompt,
  detailLoading,
  actionLoading,
  onDuplicate,
  onShare,
}: {
  selectedPrompt: PromptDetail | null;
  detailLoading: boolean;
  actionLoading: boolean;
  onDuplicate: () => void;
  onShare: () => void;
}) {
  return (
    <Panel
      title={selectedPrompt?.title ?? "Prompt detail"}
      description="Visibility, content, and versioning for the selected component."
      action={
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" className="rounded-full" disabled={actionLoading} onClick={onDuplicate}>
            Duplicate
          </Button>
          <Button
            className="rounded-full"
            disabled={actionLoading || selectedPrompt?.visibility === "public"}
            onClick={onShare}
          >
            Share
          </Button>
        </div>
      }
    >
      {detailLoading || !selectedPrompt ? (
        <div className="flex min-h-[220px] items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
              <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Description</p>
              <p className="mt-2 text-sm leading-7 text-zinc-700 dark:text-zinc-200">
                {selectedPrompt.description || "No description provided."}
              </p>
            </div>
            <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
              <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Visibility</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <StatusBadge
                  status={selectedPrompt.visibility === "public" ? "active" : "pending"}
                  label={selectedPrompt.visibility}
                />
              </div>
            </div>
          </div>

          <div className="mt-4 rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
            <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Content</p>
            <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-sm leading-7 text-zinc-700 dark:text-zinc-200">
              {selectedPrompt.content}
            </pre>
          </div>
        </>
      )}
    </Panel>
  );
}

function LibraryHeader() {
  return (
    <SectionHeader
      eyebrow="Prompt marketplace"
      title="Reusable prompts and governed components"
      description="The marketplace is treated like a developer tool: ownership, privacy, versions, duplication, and controlled sharing."
      action={
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild className="rounded-full">
            <Link href="/prompts">Create new</Link>
          </Button>
          <Button asChild variant="outline" className="rounded-full">
            <Link href="/prompts">Open prompt editor</Link>
          </Button>
        </div>
      }
    />
  );
}

export default function LibraryPage() {
  const router = useRouter();
  const { replace } = router;
  const [{ prompts, selectedPrompt, loading, detailLoading, actionLoading, error }, dispatchLibrary] = useReducer(
    libraryReducer,
    initialLibraryState,
  );

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await promptsApi.list({ ownership: "all" });
        if (!cancelled) {
          dispatchLibrary({ type: "list-success", prompts: data });
        }
      } catch (err: unknown) {
        if (!cancelled) {
          dispatchLibrary({
            type: "list-error",
            error: getApiErrorMessage(err, "Failed to load prompt marketplace."),
          });
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  const selectedPromptId =
    typeof router.query.prompt === "string"
      ? router.query.prompt
      : prompts.length > 0
        ? (prompts[0]?.id ?? null)
        : null;

  useEffect(() => {
    if (!selectedPromptId) {
      dispatchLibrary({ type: "detail-empty" });
      return;
    }

    let cancelled = false;
    dispatchLibrary({ type: "detail-start" });

    const loadDetail = async () => {
      try {
        const detail = await promptsApi.get(selectedPromptId);
        if (!cancelled) {
          dispatchLibrary({ type: "detail-success", selectedPrompt: detail });
        }
      } catch (err: unknown) {
        if (!cancelled) {
          dispatchLibrary({
            type: "detail-error",
            error: getApiErrorMessage(err, "Failed to load prompt details."),
          });
        }
      }
    };

    void loadDetail();

    return () => {
      cancelled = true;
    };
  }, [selectedPromptId]);

  const groupedCounts = useMemo(
    () => ({
      private: prompts.filter((prompt) => prompt.visibility === "private").length,
      public: prompts.filter((prompt) => prompt.visibility === "public").length,
      builtin: prompts.filter((prompt) => prompt.is_builtin).length,
    }),
    [prompts],
  );

  const inspector = selectedPrompt ? (
    <InspectorPanel
      title="Visibility controls"
      subtitle="Privacy should behave like a governed developer tool. Public and private are available now; organization scope is the next control to land."
      sections={[
        {
          title: "Current visibility",
          content: (
            <StatusBadge
              status={selectedPrompt.visibility === "public" ? "active" : "pending"}
              label={selectedPrompt.visibility}
            />
          ),
        },
        {
          title: "Owner",
          content: selectedPrompt.owner_id ?? "ForgeGraph built-in",
        },
        {
          title: "Version",
          content: selectedPrompt.version,
        },
        {
          title: "Organization scope",
          content: "Planned next: internal repository visibility and team-level ownership.",
        },
      ]}
    />
  ) : null;

  const handleDuplicate = async () => {
    if (!selectedPrompt) {
      return;
    }

    dispatchLibrary({ type: "action-start" });
    try {
      const cloned = await promptsApi.clone(selectedPrompt.id);
      const data = await promptsApi.list({ ownership: "all" });
      dispatchLibrary({ type: "action-success", prompts: data, selectedPrompt: cloned });
      showSuccess("Prompt duplicated", `"${cloned.title}" was added to your private workspace.`);
    } catch (err: unknown) {
      dispatchLibrary({
        type: "action-error",
        error: getApiErrorMessage(err, "Failed to duplicate the prompt."),
      });
    }
  };

  const handleShare = async () => {
    if (!selectedPrompt || selectedPrompt.visibility === "public") {
      return;
    }

    dispatchLibrary({ type: "action-start" });
    try {
      const published = await promptsApi.publish(selectedPrompt.id);
      const data = await promptsApi.list({ ownership: "all" });
      dispatchLibrary({ type: "action-success", prompts: data, selectedPrompt: published });
      showSuccess("Prompt shared", `"${published.title}" is now visible in the public marketplace.`);
    } catch (err: unknown) {
      dispatchLibrary({
        type: "action-error",
        error: getApiErrorMessage(err, "Failed to share the prompt."),
      });
    }
  };

  return (
    <ProtectedRoute>
      <DashboardLayout inspector={inspector}>
        <div className="space-y-6">
          <LibraryHeader />

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {loading ? (
            <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-zinc-900/10 bg-white/70 dark:border-white/10 dark:bg-zinc-950/50">
              <Spinner size="lg" />
            </div>
          ) : !selectedPromptId ? (
            <EmptyBlock title="No prompts available" description="The marketplace is empty for this workspace." />
          ) : (
            <div className="grid gap-6 xl:grid-cols-[0.78fr_1.22fr]">
              <Panel
                title="Marketplace inventory"
                description="Prompts available for reuse, editing, duplication, and sharing."
              >
                <div className="mb-4 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Private</p>
                    <p className="mt-2 text-2xl font-semibold text-zinc-950 dark:text-zinc-50">
                      {groupedCounts.private}
                    </p>
                  </div>
                  <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Public</p>
                    <p className="mt-2 text-2xl font-semibold text-zinc-950 dark:text-zinc-50">
                      {groupedCounts.public}
                    </p>
                  </div>
                  <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Built in</p>
                    <p className="mt-2 text-2xl font-semibold text-zinc-950 dark:text-zinc-50">
                      {groupedCounts.builtin}
                    </p>
                  </div>
                </div>
                <SelectionList
                  items={prompts}
                  selectedId={selectedPromptId}
                  onSelect={(prompt) => {
                    void replace({ pathname: "/library", query: { prompt: prompt.id } }, undefined, {
                      shallow: true,
                    });
                  }}
                  empty={
                    <EmptyBlock
                      title="Marketplace is empty"
                      description="Create or import prompts to populate this workspace."
                    />
                  }
                >
                  {(prompt, { selected }) => (
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-3 text-sm font-semibold">
                          <span>{prompt.title}</span>
                          <StatusBadge
                            status={prompt.visibility === "public" ? "active" : "pending"}
                            label={prompt.visibility}
                          />
                        </div>
                        <div
                          className={
                            selected
                              ? "mt-2 text-sm leading-6 text-white/78 dark:text-zinc-700"
                              : "mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300"
                          }
                        >
                          {prompt.description || "No description provided."}
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <div className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">
                          {prompt.is_builtin ? "Built in" : prompt.category}
                        </div>
                      </div>
                    </div>
                  )}
                </SelectionList>
              </Panel>

              <div className="space-y-6">
                <PromptDetailPanel
                  selectedPrompt={selectedPrompt}
                  detailLoading={detailLoading}
                  actionLoading={actionLoading}
                  onDuplicate={() => {
                    void handleDuplicate();
                  }}
                  onShare={() => {
                    void handleShare();
                  }}
                />
                <Panel
                  title="Versioning"
                  description="Keep version history visible, even when the current backend only exposes the active revision."
                >
                  {selectedPrompt ? (
                    <div className="space-y-3">
                      <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Current version</p>
                            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                              Updated {formatDateTime(selectedPrompt.updated_at)}
                            </p>
                          </div>
                          <StatusBadge status="active" label={selectedPrompt.version} />
                        </div>
                      </div>
                      <div className="rounded-[1.2rem] border border-dashed border-zinc-900/12 bg-[var(--panel-muted)] p-4 dark:border-white/12">
                        <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Revert capability</p>
                        <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
                          Full revision history is not exposed on the library route yet. Use the prompt editor for
                          updates and treat this screen as the governed distribution surface.
                        </p>
                        <Button asChild variant="outline" className="mt-4 rounded-full">
                          <Link href="/prompts">Open prompt editor</Link>
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <EmptyBlock
                      title="No version data"
                      description="Select a prompt to inspect its version and sharing posture."
                    />
                  )}
                </Panel>
              </div>
            </div>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
