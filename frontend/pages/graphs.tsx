import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { Plus, RefreshCw } from "lucide-react";

import DashboardLayout from "../components/DashboardLayout";
import ProtectedRoute from "../components/ProtectedRoute";
import { getApiErrorMessage, graphsApi, type GraphListItem, type GraphVersionSummary } from "../lib/api";
import { showSuccess, showError } from "../lib/toast";
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

const formatDateTime = (isoString: string) => {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return isoString;
  }
  return date.toLocaleString();
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
      setError(getApiErrorMessage(err, "Failed to load graphs."));
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
      showSuccess("Graph created");
      await router.push(`/graphs/${created.id}`);
    } catch (err: unknown) {
      setCreateError(getApiErrorMessage(err, "Failed to create graph."));
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
      showSuccess("Graph updated", `"${updated.name}" has been saved.`);
    } catch (err: unknown) {
      setEditError(getApiErrorMessage(err, "Failed to update graph."));
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
      setVersionsError(getApiErrorMessage(err, "Failed to load versions."));
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
      showSuccess("Graph deleted", `"${graph.name}" has been removed.`);
    } catch (err: unknown) {
      showError("Delete failed", getApiErrorMessage(err, "Could not delete graph."));
    }
  };

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <div className="relative overflow-hidden rounded-2xl border border-border/50 bg-card/60 backdrop-blur-sm p-6">
            <div className="pointer-events-none absolute inset-0 bg-linear-to-br from-primary/12 via-violet-500/8 to-fuchsia-500/8" />
            <div className="relative flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight bg-linear-to-r from-primary via-violet-500 to-fuchsia-500 bg-clip-text text-transparent">
                  Graphs
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Manage your workflow graphs and their versions.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline" onClick={() => void refreshGraphs()} disabled={loading}>
                  <RefreshCw aria-hidden="true" />
                  Refresh
                </Button>
                <Button onClick={openCreate}>
                  <Plus aria-hidden="true" />
                  New graph
                </Button>
              </div>
            </div>
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="flex items-center space-x-3 text-muted-foreground">
                <Spinner size="md" />
                <span className="text-sm">Loading graphs...</span>
              </div>
            </div>
          ) : sortedGraphs.length === 0 ? (
            <EmptyState
              className="py-16"
              title="No graphs yet"
              description="Create your first graph to start building workflows."
              action={<Button onClick={openCreate}>Create a graph</Button>}
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {sortedGraphs.map((graph) => (
                <Card
                  key={graph.id}
                  className="group relative overflow-hidden border-border/50 bg-card/60 backdrop-blur-sm transition-all hover:border-primary/30 hover:shadow-lg"
                >
                  <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-linear-to-r from-primary/60 via-violet-500/50 to-fuchsia-500/50 opacity-0 transition-opacity group-hover:opacity-100" />

                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between gap-2">
                      <Link
                        href={`/graphs/${graph.id}`}
                        className="hover:text-primary transition-colors"
                      >
                        <CardTitle className="text-lg">{graph.name}</CardTitle>
                      </Link>
                      {graph.latest_version != null && (
                        <Badge variant="secondary">v{graph.latest_version}</Badge>
                      )}
                    </div>
                    <CardDescription className="line-clamp-2">
                      {graph.description || <span className="italic">No description</span>}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center justify-between text-sm text-muted-foreground mb-4">
                      <span>{formatDateTime(graph.updated_at)}</span>
                      <span>
                        {graph.version_count} {graph.version_count === 1 ? "version" : "versions"}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Button size="sm" className="flex-1 min-w-[6rem]" asChild>
                        <Link href={`/graphs/${graph.id}`}>Open</Link>
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="flex-1 min-w-[6rem]"
                        onClick={() => openEdit(graph)}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="flex-1 min-w-[6rem]"
                        onClick={() => void openVersions(graph)}
                      >
                        Versions
                      </Button>
                      <ConfirmButton
                        variant="destructive"
                        size="sm"
                        title={`Delete "${graph.name}"`}
                        description="This will permanently delete the graph and all its versions. This action cannot be undone."
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
          )}
        </div>

        {/* Create Dialog */}
        <Dialog open={isCreateOpen} onOpenChange={(open) => !isCreating && setIsCreateOpen(open)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create new graph</DialogTitle>
              <DialogDescription>
                Give your graph a name and optional description.
              </DialogDescription>
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
                  placeholder="My first graph"
                />
              </FormField>

              <FormField label="Description" htmlFor="create-graph-description">
                <Textarea
                  id="create-graph-description"
                  value={createForm.description}
                  onChange={(e) => setCreateForm((prev) => ({ ...prev, description: e.target.value }))}
                  disabled={isCreating}
                  placeholder="What is this graph for?"
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
              <DialogTitle>Edit graph</DialogTitle>
              <DialogDescription>
                Update the graph name and description.
              </DialogDescription>
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
        <Dialog open={Boolean(versionsGraph)} onOpenChange={(open) => !versionsLoading && !open && setVersionsGraph(null)}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Versions {versionsGraph && `— ${versionsGraph.name}`}</DialogTitle>
              <DialogDescription>
                View all saved versions of this graph.
              </DialogDescription>
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
              <div className="py-6 text-center text-sm text-muted-foreground">
                No versions yet.
              </div>
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
                          <td className="px-4 py-2 text-sm text-muted-foreground">
                            {formatDateTime(v.created_at)}
                          </td>
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
                  <Link href={`/graphs/${versionsGraph.id}`}>Open graph</Link>
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
