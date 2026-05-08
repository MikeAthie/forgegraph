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
      setError(getApiErrorMessage(err, "Failed to load advanced operating models."));
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
      showSuccess("Operating model created");
      await router.push(`/workflows/${created.id}`);
    } catch (err: unknown) {
      setCreateError(getApiErrorMessage(err, "Failed to create the operating model."));
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
      showSuccess("Operating model updated", `"${updated.name}" has been saved.`);
    } catch (err: unknown) {
      setEditError(getApiErrorMessage(err, "Failed to update the operating model."));
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
      setVersionsError(getApiErrorMessage(err, "Failed to load saved versions."));
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
      showSuccess("Operating model deleted", `"${graph.name}" has been removed.`);
    } catch (err: unknown) {
      showError("Delete failed", getApiErrorMessage(err, ERROR_FALLBACKS.graph.delete));
    }
  };

  return (
    <ProtectedRoute>
      <DashboardLayout
        inspector={
          <InspectorPanel
            title="Advanced operating models"
            subtitle="Company workspaces remain primary. This area is for editing the underlying operating model."
            sections={[
              {
                title: "What lives here",
                content: "Operating model definitions, saved versions, and the advanced editor.",
              },
              {
                title: "What does not",
                content: "Company launch, command ops, approvals, and deliverables stay outside this advanced area.",
              },
            ]}
          />
        }
      >
        <div className="flex flex-col gap-6">
          <SectionHeader
            eyebrow="Advanced Mode"
            title="Manage operating models and saved versions"
            description="Edit the underlying operating model here. The company workspace remains the primary customer-facing experience."
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
                  <Link href="/companies/new">Company builder</Link>
                </Button>
                <Button className="rounded-full" onClick={openCreate}>
                  <Plus aria-hidden="true" />
                  New operating model
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
                <span className="text-sm">Loading operating models</span>
              </div>
            </div>
          ) : sortedGraphs.length === 0 ? (
            <Panel title="Operating models" description="No advanced operating models exist yet.">
              <EmptyState
                className="py-16"
                title="No operating models yet"
                description="Create a company first, or start an advanced operating model directly if you need low-level control."
                action={
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={openCreate}>Create operating model</Button>
                    <Button variant="outline" asChild>
                      <Link href="/companies/new">Use company builder</Link>
                    </Button>
                  </div>
                }
              />
            </Panel>
          ) : (
            <Panel title="Operating models" description="Current advanced operating models and saved version counts.">
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
                          Saved versions
                        </Button>
                        <ConfirmButton
                          variant="destructive"
                          size="sm"
                          title={`Delete "${graph.name}"`}
                          description="This will permanently delete the operating model and all saved versions. This action cannot be undone."
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
              <DialogTitle>Create advanced operating model</DialogTitle>
              <DialogDescription>Give the operating model a name and optional description.</DialogDescription>
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
                  placeholder="What company work is this operating model responsible for?"
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
                    Creating
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
              <DialogTitle>Edit advanced operating model</DialogTitle>
              <DialogDescription>Update the operating model name and description.</DialogDescription>
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
                    Saving
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
              <DialogTitle>Saved versions {versionsGraph && `— ${versionsGraph.name}`}</DialogTitle>
              <DialogDescription>View saved versions for this advanced operating model.</DialogDescription>
            </DialogHeader>

            {versionsError && (
              <Alert variant="destructive">
                <AlertDescription>{versionsError}</AlertDescription>
              </Alert>
            )}

            {versionsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Spinner size="md" />
                <span className="ml-3 text-sm text-muted-foreground">Loading saved versions</span>
              </div>
            ) : versions.length === 0 ? (
              <div className="py-6 text-center text-sm text-muted-foreground">No saved versions yet.</div>
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
                  <Link href={`/workflows/${versionsGraph.id}`}>Open advanced editor</Link>
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
