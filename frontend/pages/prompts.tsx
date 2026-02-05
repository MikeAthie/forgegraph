import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Plus, RefreshCw } from "lucide-react";

import DashboardLayout from "../components/DashboardLayout";
import ProtectedRoute from "../components/ProtectedRoute";
import { useAuth } from "../contexts/AuthContext";
import {
  getApiErrorMessage,
  promptsApi,
  type PromptCategory,
  type PromptDetail,
  type PromptListItem,
  type PromptOwnershipFilter,
} from "../lib/api";
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
  SearchInput,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Spinner,
  Textarea,
} from "@/components/ui";

type PromptFormState = {
  title: string;
  description: string;
  category: PromptCategory;
  content: string;
  variablesSchemaText: string;
};

const CATEGORIES: { value: PromptCategory; label: string }[] = [
  { value: "research", label: "Research" },
  { value: "summarization", label: "Summarization" },
  { value: "email", label: "Email" },
  { value: "extraction", label: "Extraction" },
  { value: "reasoning", label: "Reasoning" },
  { value: "other", label: "Other" },
];

const OWNERSHIP_OPTIONS: { value: PromptOwnershipFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "builtin", label: "Built-in" },
  { value: "mine", label: "My prompts" },
];

const formatDateTime = (isoString: string) => {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return isoString;
  }
  return date.toLocaleString();
};

const formatCategory = (category: string) => {
  const match = CATEGORIES.find((c) => c.value === category);
  return match?.label ?? category;
};

const parseVariablesSchema = (
  variablesSchemaText: string,
): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } => {
  const trimmed = variablesSchemaText.trim();
  if (!trimmed) {
    return { ok: true, value: {} };
  }

  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { ok: false, error: "Variables schema must be a JSON object." };
    }
    return { ok: true, value: parsed as Record<string, unknown> };
  } catch {
    return { ok: false, error: "Variables schema must be valid JSON." };
  }
};

export default function PromptsPage() {
  const { user } = useAuth();

  const [ownership, setOwnership] = useState<PromptOwnershipFilter>("all");
  const [category, setCategory] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");

  const [prompts, setPrompts] = useState<PromptListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createForm, setCreateForm] = useState<PromptFormState>({
    title: "",
    description: "",
    category: "other",
    content: "",
    variablesSchemaText: "",
  });

  const [selectedPromptId, setSelectedPromptId] = useState<string | null>(null);
  const [selectedPrompt, setSelectedPrompt] = useState<PromptDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [isCloning, setIsCloning] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<{
    title: string;
    description: string;
    content: string;
    variablesSchemaText: string;
  }>({
    title: "",
    description: "",
    content: "",
    variablesSchemaText: "",
  });
  const [isPublishing, setIsPublishing] = useState(false);

  const filters = useMemo(
    () => ({
      ownership,
      category: category || undefined,
      search: searchQuery || undefined,
    }),
    [ownership, category, searchQuery],
  );

  const refreshPrompts = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await promptsApi.list(filters);
      setPrompts(data);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to load prompts."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let isActive = true;
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await promptsApi.list(filters);
        if (!isActive) return;
        setPrompts(data);
      } catch (err: unknown) {
        if (!isActive) return;
        setError(getApiErrorMessage(err, "Failed to load prompts."));
      } finally {
        if (!isActive) return;
        setLoading(false);
      }
    };

    void run();
    return () => {
      isActive = false;
    };
  }, [filters]);

  const openCreate = () => {
    setCreateError(null);
    setCreateForm({
      title: "",
      description: "",
      category: "other",
      content: "",
      variablesSchemaText: "",
    });
    setIsCreateOpen(true);
  };

  const closeCreate = () => {
    if (isCreating) return;
    setIsCreateOpen(false);
  };

  const submitCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCreateError(null);

    if (!createForm.title.trim()) {
      setCreateError("Title is required.");
      return;
    }
    if (!createForm.content.trim()) {
      setCreateError("Content is required.");
      return;
    }

    const parsed = parseVariablesSchema(createForm.variablesSchemaText);
    if (!parsed.ok) {
      setCreateError(parsed.error);
      return;
    }

    setIsCreating(true);
    try {
      const created = await promptsApi.create({
        title: createForm.title.trim(),
        description: createForm.description.trim(),
        category: createForm.category,
        content: createForm.content,
        variables_schema: parsed.value,
      });

      setIsCreateOpen(false);
      showSuccess("Prompt created", `"${created.title}" is ready to use.`);
      await refreshPrompts();
    } catch (err: unknown) {
      setCreateError(getApiErrorMessage(err, "Failed to create prompt."));
    } finally {
      setIsCreating(false);
    }
  };

  const openDetail = async (promptId: string) => {
    setSelectedPromptId(promptId);
    setSelectedPrompt(null);
    setDetailError(null);
    setIsEditing(false);
    setEditError(null);
    setDetailLoading(true);

    try {
      const detail = await promptsApi.get(promptId);
      setSelectedPrompt(detail);
    } catch (err: unknown) {
      setDetailError(getApiErrorMessage(err, "Failed to load prompt."));
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    if (detailLoading || isCloning || isSaving || isPublishing) return;
    setSelectedPromptId(null);
    setSelectedPrompt(null);
    setDetailError(null);
    setIsEditing(false);
    setEditError(null);
  };

  const canCloneSelected = Boolean(
    selectedPrompt && selectedPrompt.visibility === "public" && selectedPrompt.owner_id !== user?.id,
  );

  const isOrgAdmin = user?.organization_role === "owner" || user?.organization_role === "admin";

  const canEditSelected = Boolean(
    selectedPrompt &&
      user?.id &&
      selectedPrompt.owner_id &&
      (selectedPrompt.owner_id === user.id || isOrgAdmin),
  );

  const canPublishSelected = Boolean(
    selectedPrompt &&
      canEditSelected &&
      selectedPrompt.visibility !== "public" &&
      isOrgAdmin,
  );

  const cloneSelected = async () => {
    if (!selectedPrompt) return;
    setIsCloning(true);
    setDetailError(null);

    try {
      const cloned = await promptsApi.clone(selectedPrompt.id);
      showSuccess("Prompt cloned", `"${cloned.title}" has been added to your library.`);
      await refreshPrompts();
      setSelectedPromptId(cloned.id);
      setSelectedPrompt(cloned);
    } catch (err: unknown) {
      setDetailError(getApiErrorMessage(err, "Failed to clone prompt."));
    } finally {
      setIsCloning(false);
    }
  };

  const startEditing = () => {
    if (!selectedPrompt) return;
    setIsEditing(true);
    setEditError(null);
    setEditForm({
      title: selectedPrompt.title,
      description: selectedPrompt.description ?? "",
      content: selectedPrompt.content,
      variablesSchemaText: JSON.stringify(selectedPrompt.variables_schema ?? {}, null, 2),
    });
  };

  const cancelEditing = () => {
    if (isSaving) return;
    setIsEditing(false);
    setEditError(null);
  };

  const submitEdit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedPrompt) return;

    setEditError(null);

    if (!editForm.title.trim()) {
      setEditError("Title is required.");
      return;
    }
    if (!editForm.content.trim()) {
      setEditError("Content is required.");
      return;
    }

    const parsed = parseVariablesSchema(editForm.variablesSchemaText);
    if (!parsed.ok) {
      setEditError(parsed.error);
      return;
    }

    setIsSaving(true);
    try {
      const updated = await promptsApi.update(selectedPrompt.id, {
        title: editForm.title.trim(),
        description: editForm.description.trim(),
        content: editForm.content,
        variables_schema: parsed.value,
      });

      setSelectedPrompt(updated);
      setPrompts((prev) =>
        prev.map((p) =>
          p.id === updated.id
            ? { ...p, title: updated.title, description: updated.description, visibility: updated.visibility }
            : p,
        ),
      );
      setIsEditing(false);
      showSuccess("Prompt updated", `"${updated.title}" has been saved.`);
    } catch (err: unknown) {
      setEditError(getApiErrorMessage(err, "Failed to update prompt."));
    } finally {
      setIsSaving(false);
    }
  };

  const publishSelected = async () => {
    if (!selectedPrompt) return;
    setIsPublishing(true);
    setDetailError(null);
    try {
      const updated = await promptsApi.publish(selectedPrompt.id);
      setSelectedPrompt(updated);
      setPrompts((prev) =>
        prev.map((p) => (p.id === updated.id ? { ...p, visibility: updated.visibility } : p)),
      );
      showSuccess("Prompt published", `"${updated.title}" is now public.`);
    } catch (err: unknown) {
      setDetailError(getApiErrorMessage(err, "Failed to publish prompt."));
    } finally {
      setIsPublishing(false);
    }
  };

  const handleDelete = async (prompt: PromptDetail) => {
    try {
      await promptsApi.delete(prompt.id);
      setPrompts((prev) => prev.filter((p) => p.id !== prompt.id));
      setSelectedPromptId(null);
      setSelectedPrompt(null);
      showSuccess("Prompt deleted", `"${prompt.title}" has been removed.`);
    } catch (err: unknown) {
      showError("Delete failed", getApiErrorMessage(err, "Could not delete prompt."));
    }
  };

  const emptyStateTitle =
    ownership === "mine"
      ? "No prompts yet"
      : ownership === "builtin"
        ? "No built-in prompts found"
        : "No prompts found";

  const emptyStateDescription =
    ownership === "mine"
      ? "Create a prompt or clone a built-in one to get started."
      : ownership === "builtin"
        ? "Seed data may not be loaded yet."
        : "Try adjusting your filters.";

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <div className="relative overflow-hidden rounded-2xl border border-border/50 bg-card/60 backdrop-blur-sm p-6">
            <div className="pointer-events-none absolute inset-0 bg-linear-to-br from-primary/12 via-violet-500/8 to-fuchsia-500/8" />
            <div className="relative flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight bg-linear-to-r from-primary via-violet-500 to-fuchsia-500 bg-clip-text text-transparent">
                  Prompts
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Browse built-in prompts and manage your own prompt library.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline" onClick={() => void refreshPrompts()} disabled={loading}>
                  <RefreshCw aria-hidden="true" />
                  Refresh
                </Button>
                <Button onClick={openCreate}>
                  <Plus aria-hidden="true" />
                  New prompt
                </Button>
              </div>
            </div>
          </div>

          {/* Filters */}
          <Card className="border-border/50 bg-card/60 backdrop-blur-sm">
            <CardContent className="pt-6">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div className="flex flex-wrap items-center gap-2">
                  {OWNERSHIP_OPTIONS.map((o) => (
                    <Button
                      key={o.value}
                      variant={ownership === o.value ? "default" : "outline"}
                      size="sm"
                      onClick={() => setOwnership(o.value)}
                    >
                      {o.label}
                    </Button>
                  ))}
                </div>

                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end">
                  <Select value={category || "all"} onValueChange={(v) => setCategory(v === "all" ? "" : v)}>
                    <SelectTrigger className="w-full sm:w-48">
                      <SelectValue placeholder="All categories" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All categories</SelectItem>
                      {CATEGORIES.map((c) => (
                        <SelectItem key={c.value} value={c.value}>
                          {c.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <SearchInput
                    placeholder="Search prompts..."
                    className="w-full sm:w-64"
                    onSearch={setSearchQuery}
                    debounceMs={300}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-10">
              <Spinner size="md" />
              <span className="ml-3 text-sm text-muted-foreground">Loading prompts...</span>
            </div>
          ) : prompts.length === 0 ? (
            <EmptyState
              className="py-10"
              title={emptyStateTitle}
              description={emptyStateDescription}
              action={
                ownership !== "builtin" ? (
                  <Button onClick={openCreate}>Create a prompt</Button>
                ) : undefined
              }
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {prompts.map((prompt) => (
                <Card
                  key={prompt.id}
                  className={prompt.is_builtin ? "border-primary/30 bg-primary/5" : ""}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between gap-2">
                      <CardTitle className="text-base line-clamp-2">{prompt.title}</CardTitle>
                      <div className="flex flex-col items-end gap-1">
                        <Badge variant={prompt.is_builtin ? "default" : "secondary"}>
                          {prompt.is_builtin ? "Built-in" : "Custom"}
                        </Badge>
                        <Badge variant={prompt.visibility === "public" ? "outline" : "secondary"}>
                          {prompt.visibility === "public" ? "Public" : "Private"}
                        </Badge>
                      </div>
                    </div>
                    <CardDescription className="line-clamp-2">
                      {prompt.description || "No description"}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center justify-between text-xs text-muted-foreground mb-3">
                      <span>{formatCategory(prompt.category)}</span>
                      <span>{formatDateTime(prompt.created_at)}</span>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full"
                      onClick={() => void openDetail(prompt.id)}
                    >
                      View
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

        {/* Create Dialog */}
        <Dialog open={isCreateOpen} onOpenChange={(open) => !isCreating && setIsCreateOpen(open)}>
          <DialogContent className="max-w-3xl">
            <DialogHeader>
              <DialogTitle>Create new prompt</DialogTitle>
              <DialogDescription>Create a reusable prompt template.</DialogDescription>
            </DialogHeader>

            {createError && (
              <Alert variant="destructive">
                <AlertDescription>{createError}</AlertDescription>
              </Alert>
            )}

            <form id="create-prompt-form" className="space-y-4" onSubmit={submitCreate}>
              <div className="grid gap-4 md:grid-cols-2">
                <FormField label="Title" required htmlFor="create-prompt-title">
                  <Input
                    id="create-prompt-title"
                    value={createForm.title}
                    onChange={(e) => setCreateForm((prev) => ({ ...prev, title: e.target.value }))}
                    disabled={isCreating}
                  />
                </FormField>

                <FormField label="Category" htmlFor="create-prompt-category">
                  <Select
                    value={createForm.category}
                    onValueChange={(v) => setCreateForm((prev) => ({ ...prev, category: v as PromptCategory }))}
                    disabled={isCreating}
                  >
                    <SelectTrigger id="create-prompt-category">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CATEGORIES.map((c) => (
                        <SelectItem key={c.value} value={c.value}>
                          {c.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormField>
              </div>

              <FormField label="Description" htmlFor="create-prompt-description">
                <Input
                  id="create-prompt-description"
                  value={createForm.description}
                  onChange={(e) => setCreateForm((prev) => ({ ...prev, description: e.target.value }))}
                  disabled={isCreating}
                />
              </FormField>

              <FormField label="Content" required htmlFor="create-prompt-content">
                <Textarea
                  id="create-prompt-content"
                  value={createForm.content}
                  onChange={(e) => setCreateForm((prev) => ({ ...prev, content: e.target.value }))}
                  disabled={isCreating}
                  className="font-mono"
                  rows={10}
                />
              </FormField>

              <FormField
                label="Variables schema (JSON)"
                description="Leave empty for no variables."
                htmlFor="create-prompt-variables"
              >
                <Textarea
                  id="create-prompt-variables"
                  value={createForm.variablesSchemaText}
                  onChange={(e) => setCreateForm((prev) => ({ ...prev, variablesSchemaText: e.target.value }))}
                  disabled={isCreating}
                  className="font-mono"
                  rows={4}
                />
              </FormField>
            </form>

            <DialogFooter>
              <Button variant="outline" onClick={closeCreate} disabled={isCreating}>
                Cancel
              </Button>
              <Button type="submit" form="create-prompt-form" disabled={isCreating}>
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

        {/* Detail Dialog */}
        <Dialog
          open={Boolean(selectedPromptId)}
          onOpenChange={(open) => {
            if (!open && !detailLoading && !isCloning && !isSaving && !isPublishing) {
              closeDetail();
            }
          }}
        >
          <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{selectedPrompt ? selectedPrompt.title : "Prompt"}</DialogTitle>
              {selectedPrompt && (
                <div className="flex items-center gap-2 mt-2">
                  <Badge variant={selectedPrompt.owner_id ? "secondary" : "default"}>
                    {selectedPrompt.owner_id ? "Custom" : "Built-in"}
                  </Badge>
                  <Badge variant="outline">{selectedPrompt.visibility}</Badge>
                  <Badge variant="outline">{formatCategory(selectedPrompt.category)}</Badge>
                </div>
              )}
            </DialogHeader>

            {detailError && (
              <Alert variant="destructive">
                <AlertDescription>{detailError}</AlertDescription>
              </Alert>
            )}

            {detailLoading ? (
              <div className="flex items-center justify-center py-10">
                <Spinner size="md" />
                <span className="ml-3 text-sm text-muted-foreground">Loading prompt...</span>
              </div>
            ) : !selectedPrompt ? (
              <div className="py-6 text-center text-sm text-muted-foreground">
                Prompt not available.
              </div>
            ) : isEditing ? (
              <>
                {editError && (
                  <Alert variant="destructive">
                    <AlertDescription>{editError}</AlertDescription>
                  </Alert>
                )}

                <form id="edit-prompt-form" className="space-y-4" onSubmit={submitEdit}>
                  <div className="grid gap-4 md:grid-cols-2">
                    <FormField label="Title" required htmlFor="edit-prompt-title">
                      <Input
                        id="edit-prompt-title"
                        value={editForm.title}
                        onChange={(e) => setEditForm((prev) => ({ ...prev, title: e.target.value }))}
                        disabled={isSaving}
                      />
                    </FormField>

                    <FormField label="Category">
                      <div className="px-3 py-2 border rounded-md text-sm bg-muted">
                        {formatCategory(selectedPrompt.category)}
                      </div>
                    </FormField>
                  </div>

                  <FormField label="Description" htmlFor="edit-prompt-description">
                    <Input
                      id="edit-prompt-description"
                      value={editForm.description}
                      onChange={(e) => setEditForm((prev) => ({ ...prev, description: e.target.value }))}
                      disabled={isSaving}
                    />
                  </FormField>

                  <FormField label="Content" required htmlFor="edit-prompt-content">
                    <Textarea
                      id="edit-prompt-content"
                      value={editForm.content}
                      onChange={(e) => setEditForm((prev) => ({ ...prev, content: e.target.value }))}
                      disabled={isSaving}
                      className="font-mono"
                      rows={12}
                    />
                  </FormField>

                  <FormField label="Variables schema (JSON)" htmlFor="edit-prompt-variables">
                    <Textarea
                      id="edit-prompt-variables"
                      value={editForm.variablesSchemaText}
                      onChange={(e) => setEditForm((prev) => ({ ...prev, variablesSchemaText: e.target.value }))}
                      disabled={isSaving}
                      className="font-mono"
                      rows={6}
                    />
                  </FormField>
                </form>

                <DialogFooter>
                  <Button variant="outline" onClick={cancelEditing} disabled={isSaving}>
                    Cancel
                  </Button>
                  <Button type="submit" form="edit-prompt-form" disabled={isSaving}>
                    {isSaving ? (
                      <>
                        <Spinner size="xs" className="mr-2" />
                        Saving...
                      </>
                    ) : (
                      "Save"
                    )}
                  </Button>
                </DialogFooter>
              </>
            ) : (
              <>
                <div className="space-y-4">
                  <div className="grid gap-4 md:grid-cols-3">
                    <div className="bg-muted rounded-lg p-3">
                      <p className="text-xs font-medium text-muted-foreground uppercase">Version</p>
                      <p className="mt-1 text-sm">{selectedPrompt.version}</p>
                    </div>
                    <div className="bg-muted rounded-lg p-3">
                      <p className="text-xs font-medium text-muted-foreground uppercase">License</p>
                      <p className="mt-1 text-sm">{selectedPrompt.license}</p>
                    </div>
                    <div className="bg-muted rounded-lg p-3">
                      <p className="text-xs font-medium text-muted-foreground uppercase">Updated</p>
                      <p className="mt-1 text-sm">{formatDateTime(selectedPrompt.updated_at)}</p>
                    </div>
                  </div>

                  {selectedPrompt.description && (
                    <>
                      <Separator />
                      <div>
                        <h4 className="text-sm font-medium mb-2">Description</h4>
                        <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                          {selectedPrompt.description}
                        </p>
                      </div>
                    </>
                  )}

                  <Separator />
                  <div>
                    <h4 className="text-sm font-medium mb-2">Content</h4>
                    <pre className="p-4 bg-muted rounded-lg border border-border/50 overflow-x-auto text-sm font-mono whitespace-pre-wrap">
                      {selectedPrompt.content}
                    </pre>
                  </div>

                  <Separator />
                  <div>
                    <h4 className="text-sm font-medium mb-2">Variables schema</h4>
                    <pre className="p-4 bg-muted rounded-lg overflow-x-auto text-sm whitespace-pre-wrap">
                      {JSON.stringify(selectedPrompt.variables_schema ?? {}, null, 2)}
                    </pre>
                  </div>
                </div>

                <DialogFooter className="flex-wrap gap-2">
                  {canCloneSelected && (
                    <Button onClick={() => void cloneSelected()} disabled={isCloning}>
                      {isCloning ? (
                        <>
                          <Spinner size="xs" className="mr-2" />
                          Cloning...
                        </>
                      ) : (
                        "Clone"
                      )}
                    </Button>
                  )}

                  {canPublishSelected && (
                    <Button
                      variant="outline"
                      onClick={() => void publishSelected()}
                      disabled={isPublishing}
                    >
                      {isPublishing ? (
                        <>
                          <Spinner size="xs" className="mr-2" />
                          Publishing...
                        </>
                      ) : (
                        "Publish"
                      )}
                    </Button>
                  )}

                  {canEditSelected && (
                    <>
                      <Button variant="outline" onClick={startEditing}>
                        Edit
                      </Button>
                      <ConfirmButton
                        variant="destructive"
                        title={`Delete "${selectedPrompt.title}"`}
                        description="This will permanently delete the prompt. This action cannot be undone."
                        confirmText="Delete"
                        onConfirm={() => handleDelete(selectedPrompt)}
                      >
                        Delete
                      </ConfirmButton>
                    </>
                  )}

                  <Button variant="outline" onClick={closeDetail}>
                    Close
                  </Button>
                </DialogFooter>
              </>
            )}
          </DialogContent>
        </Dialog>
      </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
