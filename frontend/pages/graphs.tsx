import { useCallback, useEffect, useMemo, useReducer, type FormEvent, type SetStateAction } from "react";
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

type GraphsPageState = {
  graphs: GraphListItem[];
  loading: boolean;
  error: string | null;
  isCreateOpen: boolean;
  createForm: GraphFormState;
  isCreating: boolean;
  createError: string | null;
  editingGraph: GraphListItem | null;
  editForm: GraphFormState;
  isSavingEdit: boolean;
  editError: string | null;
  versionsGraph: GraphListItem | null;
  versions: GraphVersionSummary[];
  versionsLoading: boolean;
  versionsError: string | null;
};

type GraphsPageAction = {
  patch: Partial<GraphsPageState> | ((state: GraphsPageState) => Partial<GraphsPageState>);
};

const emptyGraphForm: GraphFormState = { name: "", description: "" };

const initialGraphsPageState: GraphsPageState = {
  graphs: [],
  loading: true,
  error: null,
  isCreateOpen: false,
  createForm: emptyGraphForm,
  isCreating: false,
  createError: null,
  editingGraph: null,
  editForm: emptyGraphForm,
  isSavingEdit: false,
  editError: null,
  versionsGraph: null,
  versions: [],
  versionsLoading: false,
  versionsError: null,
};

function graphsPageReducer(state: GraphsPageState, action: GraphsPageAction): GraphsPageState {
  const patch = typeof action.patch === "function" ? action.patch(state) : action.patch;
  return { ...state, ...patch };
}

function resolveStateAction<T>(value: SetStateAction<T>, current: T): T {
  return typeof value === "function" ? (value as (current: T) => T)(current) : value;
}

function useGraphsPageController() {
  const router = useRouter();
  const { push } = router;
  const [pageState, dispatchPageState] = useReducer(graphsPageReducer, initialGraphsPageState);
  const {
    graphs,
    loading,
    error,
    isCreateOpen,
    createForm,
    isCreating,
    createError,
    editingGraph,
    editForm,
    isSavingEdit,
    editError,
    versionsGraph,
    versions,
    versionsLoading,
    versionsError,
  } = pageState;
  const setPageField = useCallback(
    <K extends keyof GraphsPageState>(key: K, value: SetStateAction<GraphsPageState[K]>) => {
      dispatchPageState({
        patch: (current) => ({ [key]: resolveStateAction(value, current[key]) }) as Partial<GraphsPageState>,
      });
    },
    [],
  );
  const setGraphs = useCallback((value: SetStateAction<GraphListItem[]>) => setPageField("graphs", value), [setPageField]);
  const setLoading = useCallback((value: SetStateAction<boolean>) => setPageField("loading", value), [setPageField]);
  const setError = useCallback((value: SetStateAction<string | null>) => setPageField("error", value), [setPageField]);
  const setIsCreateOpen = useCallback((value: SetStateAction<boolean>) => setPageField("isCreateOpen", value), [setPageField]);
  const setCreateForm = useCallback((value: SetStateAction<GraphFormState>) => setPageField("createForm", value), [setPageField]);
  const setIsCreating = useCallback((value: SetStateAction<boolean>) => setPageField("isCreating", value), [setPageField]);
  const setCreateError = useCallback((value: SetStateAction<string | null>) => setPageField("createError", value), [setPageField]);
  const setEditingGraph = useCallback((value: SetStateAction<GraphListItem | null>) => setPageField("editingGraph", value), [setPageField]);
  const setEditForm = useCallback((value: SetStateAction<GraphFormState>) => setPageField("editForm", value), [setPageField]);
  const setIsSavingEdit = useCallback((value: SetStateAction<boolean>) => setPageField("isSavingEdit", value), [setPageField]);
  const setEditError = useCallback((value: SetStateAction<string | null>) => setPageField("editError", value), [setPageField]);
  const setVersionsGraph = useCallback((value: SetStateAction<GraphListItem | null>) => setPageField("versionsGraph", value), [setPageField]);
  const setVersions = useCallback((value: SetStateAction<GraphVersionSummary[]>) => setPageField("versions", value), [setPageField]);
  const setVersionsLoading = useCallback((value: SetStateAction<boolean>) => setPageField("versionsLoading", value), [setPageField]);
  const setVersionsError = useCallback((value: SetStateAction<string | null>) => setPageField("versionsError", value), [setPageField]);

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
  }, [setError, setGraphs, setLoading]);

  useEffect(() => {
    void refreshGraphs();
  }, [refreshGraphs]);

  const sortedGraphs = useMemo(() => {
    return graphs.toSorted((a, b) => b.updated_at.localeCompare(a.updated_at));
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
      await push(`/workflows/${created.id}`);
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

  return {
    graphs,
    loading,
    error,
    isCreateOpen,
    createForm,
    isCreating,
    createError,
    editingGraph,
    editForm,
    isSavingEdit,
    editError,
    versionsGraph,
    versions,
    versionsLoading,
    versionsError,
    sortedGraphs,
    refreshGraphs,
    openCreate,
    closeCreate,
    submitCreate,
    setIsCreateOpen,
    setCreateForm,
    setEditingGraph,
    setEditForm,
    setVersionsGraph,
    openEdit,
    closeEdit,
    submitEdit,
    openVersions,
    closeVersions,
    handleDelete,
  };
}

type GraphsPageController = ReturnType<typeof useGraphsPageController>;

function GraphsInspector() {
  return (
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
  );
}

function GraphsHeader({
  loading,
  onRefresh,
  onCreate,
}: {
  loading: boolean;
  onRefresh: () => void;
  onCreate: () => void;
}) {
  return (
    <SectionHeader
      eyebrow="Advanced Mode"
      title="Manage operating models and saved versions"
      description="Edit the underlying operating model here. The company workspace remains the primary customer-facing experience."
      action={
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" className="rounded-full" onClick={onRefresh} disabled={loading}>
            <RefreshCw aria-hidden="true" />
            Refresh
          </Button>
          <Button variant="outline" className="rounded-full" asChild>
            <Link href="/companies/new">Company builder</Link>
          </Button>
          <Button className="rounded-full" onClick={onCreate}>
            <Plus aria-hidden="true" />
            New operating model
          </Button>
        </div>
      }
    />
  );
}

function GraphsContent({ controller }: { controller: GraphsPageController }) {
  return (
    <div className="flex flex-col gap-6">
      <GraphsHeader
        loading={controller.loading}
        onRefresh={() => void controller.refreshGraphs()}
        onCreate={controller.openCreate}
      />

      {controller.error ? (
        <Alert variant="destructive">
          <AlertDescription>{controller.error}</AlertDescription>
        </Alert>
      ) : null}

      <GraphsListPanel
        loading={controller.loading}
        graphs={controller.sortedGraphs}
        onCreate={controller.openCreate}
        onEdit={controller.openEdit}
        onVersions={(graph) => void controller.openVersions(graph)}
        onDelete={(graph) => void controller.handleDelete(graph)}
      />
    </div>
  );
}

function GraphsListPanel({
  loading,
  graphs,
  onCreate,
  onEdit,
  onVersions,
  onDelete,
}: {
  loading: boolean;
  graphs: GraphListItem[];
  onCreate: () => void;
  onEdit: (graph: GraphListItem) => void;
  onVersions: (graph: GraphListItem) => void;
  onDelete: (graph: GraphListItem) => void;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="flex items-center gap-x-3 text-muted-foreground">
          <Spinner size="md" />
          <span className="text-sm">Loading operating models</span>
        </div>
      </div>
    );
  }

  if (graphs.length === 0) {
    return (
      <Panel title="Operating models" description="No advanced operating models exist yet.">
        <EmptyState
          className="py-16"
          title="No operating models yet"
          description="Create a company first, or start an advanced operating model directly if you need low-level control."
          action={
            <div className="flex flex-wrap gap-2">
              <Button onClick={onCreate}>Create operating model</Button>
              <Button variant="outline" asChild>
                <Link href="/companies/new">Use company builder</Link>
              </Button>
            </div>
          }
        />
      </Panel>
    );
  }

  return (
    <Panel title="Operating models" description="Current advanced operating models and saved version counts.">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {graphs.map((graph) => (
          <GraphCard
            key={graph.id}
            graph={graph}
            onEdit={() => onEdit(graph)}
            onVersions={() => onVersions(graph)}
            onDelete={() => onDelete(graph)}
          />
        ))}
      </div>
    </Panel>
  );
}

function GraphCard({
  graph,
  onEdit,
  onVersions,
  onDelete,
}: {
  graph: GraphListItem;
  onEdit: () => void;
  onVersions: () => void;
  onDelete: () => void;
}) {
  return (
    <Card className="group rounded-[1.5rem] border-zinc-900/8 bg-white/75 shadow-none transition-colors hover:bg-[var(--panel-muted)] dark:border-white/8 dark:bg-white/4">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <Link href={`/workflows/${graph.id}`} className="transition-colors hover:text-zinc-700 dark:hover:text-zinc-200">
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
          <Button variant="outline" size="sm" className="flex-1 min-w-[6rem] rounded-full" onClick={onEdit}>
            Edit
          </Button>
          <Button variant="outline" size="sm" className="flex-1 min-w-[6rem] rounded-full" onClick={onVersions}>
            Saved versions
          </Button>
          <ConfirmButton
            variant="destructive"
            size="sm"
            title={`Delete "${graph.name}"`}
            description="This will permanently delete the operating model and all saved versions. This action cannot be undone."
            confirmText="Delete"
            onConfirm={onDelete}
          >
            Delete
          </ConfirmButton>
        </div>
      </CardContent>
    </Card>
  );
}

function GraphFormDialog({
  open,
  title,
  description,
  formId,
  nameId,
  descriptionId,
  form,
  error,
  submitting,
  submitLabel,
  submittingLabel,
  namePlaceholder,
  descriptionPlaceholder,
  onOpenChange,
  onClose,
  onSubmit,
  onFormChange,
}: {
  open: boolean;
  title: string;
  description: string;
  formId: string;
  nameId: string;
  descriptionId: string;
  form: GraphFormState;
  error: string | null;
  submitting: boolean;
  submitLabel: string;
  submittingLabel: string;
  namePlaceholder?: string;
  descriptionPlaceholder?: string;
  onOpenChange: (open: boolean) => void;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onFormChange: (value: SetStateAction<GraphFormState>) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <form id={formId} className="space-y-4" onSubmit={onSubmit}>
          <FormField label="Name" required htmlFor={nameId}>
            <Input
              id={nameId}
              value={form.name}
              onChange={(e) => onFormChange((prev) => ({ ...prev, name: e.target.value }))}
              disabled={submitting}
              placeholder={namePlaceholder}
            />
          </FormField>

          <FormField label="Description" htmlFor={descriptionId}>
            <Textarea
              id={descriptionId}
              value={form.description}
              onChange={(e) => onFormChange((prev) => ({ ...prev, description: e.target.value }))}
              disabled={submitting}
              placeholder={descriptionPlaceholder}
              rows={3}
            />
          </FormField>
        </form>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" form={formId} disabled={submitting}>
            {submitting ? (
              <>
                <Spinner size="xs" className="mr-2" />
                {submittingLabel}
              </>
            ) : (
              submitLabel
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function GraphVersionsDialog({
  graph,
  versions,
  loading,
  error,
  onOpenChange,
  onClose,
}: {
  graph: GraphListItem | null;
  versions: GraphVersionSummary[];
  loading: boolean;
  error: string | null;
  onOpenChange: (open: boolean) => void;
  onClose: () => void;
}) {
  const sortedVersions = useMemo(() => versions.toSorted((a, b) => b.version - a.version), [versions]);

  return (
    <Dialog open={Boolean(graph)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Saved versions {graph ? `- ${graph.name}` : ""}</DialogTitle>
          <DialogDescription>View saved versions for this advanced operating model.</DialogDescription>
        </DialogHeader>

        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <GraphVersionsContent versions={sortedVersions} loading={loading} />

        <DialogFooter>
          {graph ? (
            <Button variant="outline" asChild>
              <Link href={`/workflows/${graph.id}`}>Open advanced editor</Link>
            </Button>
          ) : null}
          <Button onClick={onClose} disabled={loading}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function GraphVersionsContent({
  versions,
  loading,
}: {
  versions: GraphVersionSummary[];
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Spinner size="md" />
        <span className="ml-3 text-sm text-muted-foreground">Loading saved versions</span>
      </div>
    );
  }

  if (versions.length === 0) {
    return <div className="py-6 text-center text-sm text-muted-foreground">No saved versions yet.</div>;
  }

  return (
    <div className="overflow-x-auto max-h-64">
      <table className="min-w-full divide-y divide-border">
        <thead className="bg-muted/40">
          <tr>
            <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">Version</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">Created</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase">Checksum</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {versions.map((version) => (
            <tr key={version.id}>
              <td className="px-4 py-2 text-sm font-medium">
                <Badge variant="outline">v{version.version}</Badge>
              </td>
              <td className="px-4 py-2 text-sm text-muted-foreground">{formatDateTime(version.created_at)}</td>
              <td className="px-4 py-2 text-sm text-muted-foreground font-mono">
                {version.checksum.slice(0, 10)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GraphDialogs({ controller }: { controller: GraphsPageController }) {
  return (
    <>
      <GraphFormDialog
        open={controller.isCreateOpen}
        title="Create advanced operating model"
        description="Give the operating model a name and optional description."
        formId="create-graph-form"
        nameId="create-graph-name"
        descriptionId="create-graph-description"
        form={controller.createForm}
        error={controller.createError}
        submitting={controller.isCreating}
        submitLabel="Create"
        submittingLabel="Creating"
        namePlaceholder="Customer support operating loop"
        descriptionPlaceholder="What company work is this operating model responsible for?"
        onOpenChange={(open) => !controller.isCreating && controller.setIsCreateOpen(open)}
        onClose={controller.closeCreate}
        onSubmit={controller.submitCreate}
        onFormChange={controller.setCreateForm}
      />

      <GraphFormDialog
        open={Boolean(controller.editingGraph)}
        title="Edit advanced operating model"
        description="Update the operating model name and description."
        formId="edit-graph-form"
        nameId="edit-graph-name"
        descriptionId="edit-graph-description"
        form={controller.editForm}
        error={controller.editError}
        submitting={controller.isSavingEdit}
        submitLabel="Save"
        submittingLabel="Saving"
        onOpenChange={(open) => !controller.isSavingEdit && !open && controller.setEditingGraph(null)}
        onClose={controller.closeEdit}
        onSubmit={controller.submitEdit}
        onFormChange={controller.setEditForm}
      />

      <GraphVersionsDialog
        graph={controller.versionsGraph}
        versions={controller.versions}
        loading={controller.versionsLoading}
        error={controller.versionsError}
        onOpenChange={(open) => !controller.versionsLoading && !open && controller.setVersionsGraph(null)}
        onClose={controller.closeVersions}
      />
    </>
  );
}

export default function GraphsPage() {
  const controller = useGraphsPageController();

  return (
    <ProtectedRoute>
      <DashboardLayout inspector={<GraphsInspector />}>
        <GraphsContent controller={controller} />
        <GraphDialogs controller={controller} />
      </DashboardLayout>
    </ProtectedRoute>
  );
}
