import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { Plus, RefreshCw } from "lucide-react";

import DashboardLayout from "../components/DashboardLayout";
import { InspectorPanel, Panel, SectionHeader, StatusBadge, formatDateTime } from "@/components/os/operations-ui";
import ProtectedRoute from "../components/ProtectedRoute";
import { getApiErrorMessage, graphsApi, type GraphListItem, type GraphVersionSummary } from "../lib/api";
import { showSuccess, showError } from "../lib/toast";
import { ERROR_FALLBACKS } from "../lib/error-messages";
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  ConfirmButton,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  EmptyState,
  FormField,
  Input,
  Spinner,
  Textarea,
} from "@/components/ui";

type GraphFormState = {
  name: string;
  description: string;
};

export default function GraphsPage() {
  const router = useRouter();
  const [graphs, setGraphs] = useState<GraphListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<GraphFormState>({ name: "", description: "" });
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [editingGraph, setEditingGraph] = useState<GraphListItem | null>(null);
  const [editForm, setEditForm] = useState<GraphFormState>({ name: "", description: "" });
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [versionsGraph, setVersionsGraph] = useState<GraphListItem | null>(null);
  const [versions, setVersions] = useState<GraphVersionSummary[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsError, setVersionsError] = useState<string | null>(null);

  const refreshGraphs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await graphsApi.list();
      setGraphs(data);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to load workflows."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshGraphs();
  }, [refreshGraphs]);

  const sortedGraphs = useMemo(() => {
    return [...graphs].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  }, [graphs]);

  const openCreate = () => {
    setCreateForm({ name: "", description: "" });
    setCreateError(null);
    setIsCreateOpen(true);
  };

  const closeCreate = () => {
    if (isCreating) return;
    setIsCreateOpen(false);
  };

  const submitCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCreateError(null);

    if (!createForm.name.trim()) {
      setCreateError("Name is required.");
      return;
    }

    setIsCreating(true);
    try {
      const created = await graphsApi.create({
        name: createForm.name.trim(),
        description: createForm.description.trim(),
      });
      showSuccess("Workflow created");
      await router.push(`/workflows/${created.id}`);
    } catch (err: unknown) {
      setCreateError(getApiErrorMessage(err, "Failed to create workflow."));
    } finally {
      setIsCreating(false);
    }
  };

  const openEdit = (graph: GraphListItem) => {
    setEditingGraph(graph);
    setEditForm({ name: graph.name, description: graph.description ?? "" });
    setEditError(null);
  };

  const closeEdit = () => {
    if (isSavingEdit) return;
    setEditingGraph(null);
  };

  const submitEdit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editingGraph) return;
    setEditError(null);

    if (!editForm.name.trim()) {
      setEditError("Name is required.");
      return;
    }

    setIsSavingEdit(true);
    try {
      const updated = await graphsApi.update(editingGraph.id, {
        name: editForm.name.trim(),
        description: editForm.description.trim(),
      });
      setGraphs((prev) => prev.map((g) => (g.id === updated.id ? updated : g)));
      setEditingGraph(null);
      showSuccess("Workflow updated", `"${updated.name}" has been saved.`);
    } catch (err: unknown) {
      setEditError(getApiErrorMessage(err, "Failed to update workflow."));
    } finally {
      setIsSavingEdit(false);
    }
  };

  const openVersions = async (graph: GraphListItem) => {
    setVersionsGraph(graph);
    setVersions([]);
    setVersionsError(null);
    setVersionsLoading(true);

    try {
      const data = await graphsApi.listVersions(graph.id);
      setVersions(data);
    } catch (err: unknown) {
      setVersionsError(getApiErrorMessage(err, "Failed to load revisions."));
    } finally {
      setVersionsLoading(false);
    }
  };

  const closeVersions = () => {
    if (versionsLoading) return;
    setVersionsGraph(null);
  };

  const handleDelete = async (graph: GraphListItem) => {
    try {
      await graphsApi.delete(graph.id);
      setGraphs((prev) => prev.filter((g) => g.id !== graph.id));
      showSuccess("Workflow deleted", `"${graph.name}" has been removed.`);
    } catch (err: unknown) {
      showError("Delete failed", getApiErrorMessage(err, ERROR_FALLBACKS.graph.delete));
    }
  };

  return (
    <ProtectedRoute>
      <DashboardLayout
        inspector={
          <InspectorPanel
            title="Builder workspace"
            subtitle="Workflow definitions remain fully supported, but they are intentionally secondary to the operating surfaces."
            sections={[
              {
                title: "What lives here",
                content: "Definitions, revisions, and editor entry points.",
              },
              {
                title: "What does not",
                content:
                  "Runtime supervision, cost posture, approval handling, and memory inspection stay outside the builder workspace.",
              },
            ]}
          />
        }
      >
        <div className="flex flex-col gap-6">
          <SectionHeader
            eyebrow="Workflow definitions"
            title="Manage definitions and revisions"
            description="The builder workspace remains available for authoring and versioning, but it no longer defines the top-level product mental model."
            action={
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  className="rounded-full"
                  onClick={() => void refreshGraphs()}
                  disabled={loading}
                >
                  <RefreshCw aria-hidden="true" />
                  Refresh
                </Button>
                <Button variant="outline" className="rounded-full" asChild>
                  <Link href="/onboarding">Use template</Link>
                </Button>
                <Button className="rounded-full" onClick={openCreate}>
                  <Plus aria-hidden="true" />
                  New workflow
                </Button>
              </div>
            }
          />

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="flex items-center space-x-3 text-muted-foreground">
                <Spinner size="md" />
                <span className="text-sm">Loading workflows...</span>
              </div>
            </div>
          ) : sortedGraphs.length === 0 ? (
            <Panel title="Definitions" description="No workflow definitions exist yet.">
              <EmptyState
                className="py-16"
                title="No workflows yet"
                description="Create your first workflow definition to start building supervised automations."
                action={
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={openCreate}>Create a workflow</Button>
                    <Button variant="outline" asChild>
                      <Link href="/onboarding">Use template</Link>
                    </Button>
                  </div>
                }
              />
            </Panel>
          ) : (
            <Panel title="Definitions" description="Current workflow definitions and revision counts.">
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {sortedGraphs.map((graph) => (
                  <Card
                    key={graph.id}
                    className="group rounded-[1.5rem] border-slate-900/8 bg-white/75 shadow-none transition-colors hover:bg-[var(--panel-muted)] dark:border-white/8 dark:bg-white/4"
                  >
                    <CardHeader className="pb-2">
                      <div className="flex items-start justify-between gap-2">
                        <Link
                          href={`/workflows/${graph.id}`}
                          className="transition-colors hover:text-slate-700 dark:hover:text-slate-200"
                        >
                          <CardTitle className="text-lg">{graph.name}</CardTitle>
                        </Link>
                        {graph.latest_version != null ? (
                          <StatusBadge status="pending" label={`v${graph.latest_version}`} />
                        ) : (
                          <StatusBadge status="pending" label="draft" />
                        )}
                      </div>
                      <CardDescription className="line-clamp-2">
                        {graph.description || <span className="italic">No description</span>}
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="mb-4 flex items-center justify-between text-sm text-muted-foreground">
                        <span>{formatDateTime(graph.updated_at)}</span>
                        <span>
                          {graph.version_count} {graph.version_count === 1 ? "revision" : "revisions"}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Button size="sm" className="flex-1 min-w-[6rem] rounded-full" asChild>
                          <Link href={`/workflows/${graph.id}`}>Open</Link>
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="flex-1 min-w-[6rem] rounded-full"
                          onClick={() => openEdit(graph)}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="flex-1 min-w-[6rem] rounded-full"
                          onClick={() => void openVersions(graph)}
                        >
                          Versions
                        </Button>
                        <ConfirmButton
                          variant="destructive"
                          size="sm"
                          title={`Delete "${graph.name}"`}
                          description="This will permanently delete the workflow definition and all its revisions. This action cannot be undone."
                          confirmText="Delete"
                          onConfirm={() => handleDelete(graph)}
                        >
                          Delete
                        </ConfirmButton>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </Panel>
          )}
        </div>

        {/* Create Dialog */}
        <Dialog open={isCreateOpen} onOpenChange={(open) => !isCreating && setIsCreateOpen(open)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create workflow definition</DialogTitle>
              <DialogDescription>Give the workflow a name and optional description.</DialogDescription>
            </DialogHeader>

            {createError && (
              <Alert variant="destructive">
                <AlertDescription>{createError}</AlertDescription>
              </Alert>
            )}

            <form id="create-graph-form" className="space-y-4" onSubmit={submitCreate}>
              <FormField label="Name" required htmlFor="create-graph-name">
                <Input
                  id="create-graph-name"
                  value={createForm.name}
                  onChange={(e) => setCreateForm((prev) => ({ ...prev, name: e.target.value }))}
                  disabled={isCreating}
                  placeholder="Customer support operating loop"
                />
              </FormField>

              <FormField label="Description" htmlFor="create-graph-description">
                <Textarea
                  id="create-graph-description"
                  value={createForm.description}
                  onChange={(e) => setCreateForm((prev) => ({ ...prev, description: e.target.value }))}
                  disabled={isCreating}
                  placeholder="What is this workflow responsible for?"
                  rows={3}
                />
              </FormField>
            </form>

            <DialogFooter>
              <Button variant="outline" onClick={closeCreate} disabled={isCreating}>
                Cancel
              </Button>
              <Button type="submit" form="create-graph-form" disabled={isCreating}>
                {isCreating ? (
                  <>
                    <Spinner size="xs" className="mr-2" />
                    Creating...
                  </>
                ) : (
                  "Create"
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Edit Dialog */}
        <Dialog open={Boolean(editingGraph)} onOpenChange={(open) => !isSavingEdit && !open && setEditingGraph(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Edit workflow definition</DialogTitle>
              <DialogDescription>Update the workflow name and description.</DialogDescription>
            </DialogHeader>

            {editError && (
              <Alert variant="destructive">
                <AlertDescription>{editError}</AlertDescription>
              </Alert>
            )}

            <form id="edit-graph-form" className="space-y-4" onSubmit={submitEdit}>
              <FormField label="Name" required htmlFor="edit-graph-name">
                <Input
                  id="edit-graph-name"
                  value={editForm.name}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, name: e.target.value }))}
                  disabled={isSavingEdit}
                />
              </FormField>

              <FormField label="Description" htmlFor="edit-graph-description">
                <Textarea
                  id="edit-graph-description"
                  value={editForm.description}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, description: e.target.value }))}
                  disabled={isSavingEdit}
                  rows={3}
                />
              </FormField>
            </form>

            <DialogFooter>
              <Button variant="outline" onClick={closeEdit} disabled={isSavingEdit}>
                Cancel
              </Button>
              <Button type="submit" form="edit-graph-form" disabled={isSavingEdit}>
                {isSavingEdit ? (
                  <>
                    <Spinner size="xs" className="mr-2" />
                    Saving...
                  </>
                ) : (
                  "Save"
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Versions Dialog */}
        <Dialog
          open={Boolean(versionsGraph)}
          onOpenChange={(open) => !versionsLoading && !open && setVersionsGraph(null)}
        >
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Revisions {versionsGraph && `— ${versionsGraph.name}`}</DialogTitle>
              <DialogDescription>View saved revisions for this workflow definition.</DialogDescription>
            </DialogHeader>

            {versionsError && (
              <Alert variant="destructive">
                <AlertDescription>{versionsError}</AlertDescription>
              </Alert>
            )}

            {versionsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Spinner size="md" />
                <span className="ml-3 text-sm text-muted-foreground">Loading versions...</span>
              </div>
            ) : versions.length === 0 ? (
              <div className="py-6 text-center text-sm text-muted-foreground">No versions yet.</div>
            ) : (
              <div className="overflow-x-auto max-h-64">
                <table className="min-w-full divide-y divide-border">
                  <thead className="bg-muted/40">
                    <tr>
                      <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">
                        Version
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">
                        Created
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">
                        Checksum
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {versions
                      .slice()
                      .sort((a, b) => b.version - a.version)
                      .map((v) => (
                        <tr key={v.id}>
                          <td className="px-4 py-2 text-sm font-medium">
                            <Badge variant="outline">v{v.version}</Badge>
                          </td>
                          <td className="px-4 py-2 text-sm text-muted-foreground">{formatDateTime(v.created_at)}</td>
                          <td className="px-4 py-2 text-sm text-muted-foreground font-mono">
                            {v.checksum.slice(0, 10)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}

            <DialogFooter>
              {versionsGraph && (
                <Button variant="outline" asChild>
                  <Link href={`/workflows/${versionsGraph.id}`}>Open workflow</Link>
                </Button>
              )}
              <Button onClick={closeVersions} disabled={versionsLoading}>
                Close
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
