import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import DashboardLayout from "@/components/DashboardLayout";
import { EmptyBlock, InspectorPanel, Panel, SectionHeader, SelectionList, StatusBadge, formatDateTime } from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import { getApiErrorMessage, promptsApi, type PromptDetail, type PromptListItem } from "@/lib/api";
import { showSuccess } from "@/lib/toast";

export default function LibraryPage() {
  const router = useRouter();
  const [prompts, setPrompts] = useState<PromptListItem[]>([]);
  const [selectedPrompt, setSelectedPrompt] = useState<PromptDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await promptsApi.list({ ownership: "all" });
        if (!cancelled) {
          setPrompts(data);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(getApiErrorMessage(err, "Failed to load prompt marketplace."));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  const selectedPromptId =
    typeof router.query.prompt === "string" ? router.query.prompt : prompts.length > 0 ? prompts[0]?.id ?? null : null;

  useEffect(() => {
    if (!selectedPromptId) {
      setSelectedPrompt(null);
      return;
    }

    let cancelled = false;
    setDetailLoading(true);

    const loadDetail = async () => {
      try {
        const detail = await promptsApi.get(selectedPromptId);
        if (!cancelled) {
          setSelectedPrompt(detail);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(getApiErrorMessage(err, "Failed to load prompt details."));
        }
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
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
          content: <StatusBadge status={selectedPrompt.visibility === "public" ? "active" : "pending"} label={selectedPrompt.visibility} />,
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

    setActionLoading(true);
    try {
      const cloned = await promptsApi.clone(selectedPrompt.id);
      const data = await promptsApi.list({ ownership: "all" });
      setPrompts(data);
      setSelectedPrompt(cloned);
      showSuccess("Prompt duplicated", `"${cloned.title}" was added to your private workspace.`);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to duplicate the prompt."));
    } finally {
      setActionLoading(false);
    }
  };

  const handleShare = async () => {
    if (!selectedPrompt || selectedPrompt.visibility === "public") {
      return;
    }

    setActionLoading(true);
    try {
      const published = await promptsApi.publish(selectedPrompt.id);
      const data = await promptsApi.list({ ownership: "all" });
      setPrompts(data);
      setSelectedPrompt(published);
      showSuccess("Prompt shared", `"${published.title}" is now visible in the public marketplace.`);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to share the prompt."));
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <ProtectedRoute>
      <DashboardLayout inspector={inspector}>
        <div className="space-y-6">
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

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {loading ? (
            <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-slate-900/10 bg-white/70 dark:border-white/10 dark:bg-slate-950/50">
              <Spinner size="lg" />
            </div>
          ) : !selectedPromptId ? (
            <EmptyBlock title="No prompts available" description="The marketplace is empty for this workspace." />
          ) : (
            <div className="grid gap-6 xl:grid-cols-[0.78fr_1.22fr]">
              <Panel title="Marketplace inventory" description="Prompts available for reuse, editing, duplication, and sharing.">
                <div className="mb-4 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Private</p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">{groupedCounts.private}</p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Public</p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">{groupedCounts.public}</p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Built in</p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">{groupedCounts.builtin}</p>
                  </div>
                </div>
                <SelectionList
                  items={prompts}
                  selectedId={selectedPromptId}
                  onSelect={(prompt) => {
                    void router.replace(
                      { pathname: "/library", query: { prompt: prompt.id } },
                      undefined,
                      { shallow: true },
                    );
                  }}
                  renderTitle={(prompt) => (
                    <div className="flex items-center gap-3">
                      <span>{prompt.title}</span>
                      <StatusBadge status={prompt.visibility === "public" ? "active" : "pending"} label={prompt.visibility} />
                    </div>
                  )}
                  renderBody={(prompt) => prompt.description || "No description provided."}
                  renderMeta={(prompt) => (
                    <div className="text-right">
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                        {prompt.is_builtin ? "Built in" : prompt.category}
                      </div>
                    </div>
                  )}
                  empty={<EmptyBlock title="Marketplace is empty" description="Create or import prompts to populate this workspace." />}
                />
              </Panel>

              <div className="space-y-6">
                <Panel
                  title={selectedPrompt?.title ?? "Prompt detail"}
                  description="Visibility, content, and versioning for the selected component."
                  action={
                    <div className="flex flex-wrap items-center gap-2">
                      <Button variant="outline" className="rounded-full" disabled={actionLoading} onClick={() => void handleDuplicate()}>
                        Duplicate
                      </Button>
                      <Button className="rounded-full" disabled={actionLoading || selectedPrompt?.visibility === "public"} onClick={() => void handleShare()}>
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
                        <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Description</p>
                          <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">{selectedPrompt.description || "No description provided."}</p>
                        </div>
                      <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Visibility</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <StatusBadge status={selectedPrompt.visibility === "public" ? "active" : "pending"} label={selectedPrompt.visibility} />
                        </div>
                      </div>
                      </div>

                      <div className="mt-4 rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Content</p>
                        <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-sm leading-7 text-slate-700 dark:text-slate-200">
                          {selectedPrompt.content}
                        </pre>
                      </div>
                    </>
                  )}
                </Panel>

                <Panel title="Versioning" description="Keep version history visible, even when the current backend only exposes the active revision.">
                  {selectedPrompt ? (
                    <div className="space-y-3">
                      <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">Current version</p>
                            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Updated {formatDateTime(selectedPrompt.updated_at)}</p>
                          </div>
                          <StatusBadge status="active" label={selectedPrompt.version} />
                        </div>
                      </div>
                      <div className="rounded-[1.2rem] border border-dashed border-slate-900/12 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/12">
                        <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">Revert capability</p>
                        <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                          Full revision history is not exposed on the library route yet. Use the prompt editor for updates and treat this screen as the governed distribution surface.
                        </p>
                        <Button asChild variant="outline" className="mt-4 rounded-full">
                          <Link href="/prompts">Open prompt editor</Link>
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <EmptyBlock title="No version data" description="Select a prompt to inspect its version and sharing posture." />
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
