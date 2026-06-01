import { useCallback, useEffect, useMemo, useReducer, type FormEvent, type SetStateAction } from "react";
import { useRouter } from "next/router";
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

type PromptEditFormState = {
  title: string;
  description: string;
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

const isPromptOwnershipFilter = (value: unknown): value is PromptOwnershipFilter =>
  value === "all" || value === "builtin" || value === "mine";

const isPromptCategory = (value: unknown): value is PromptCategory =>
  typeof value === "string" && CATEGORIES.some((category) => category.value === value);

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

const emptyPromptForm: PromptFormState = {
  title: "",
  description: "",
  category: "other",
  content: "",
  variablesSchemaText: "",
};

const emptyPromptEditForm: PromptEditFormState = {
  title: "",
  description: "",
  content: "",
  variablesSchemaText: "",
};

type PromptsPageState = {
  ownership: PromptOwnershipFilter;
  category: string;
  searchDraft: string;
  searchQuery: string;
  prompts: PromptListItem[];
  loading: boolean;
  error: string | null;
  isCreateOpen: boolean;
  isCreating: boolean;
  createError: string | null;
  createForm: PromptFormState;
  selectedPromptId: string | null;
  selectedPrompt: PromptDetail | null;
  detailLoading: boolean;
  detailError: string | null;
  isCloning: boolean;
  isEditing: boolean;
  isSaving: boolean;
  editError: string | null;
  editForm: PromptEditFormState;
  isPublishing: boolean;
};

type PromptsPageAction = {
  patch: Partial<PromptsPageState> | ((state: PromptsPageState) => Partial<PromptsPageState>);
};

const initialPromptsPageState: PromptsPageState = {
  ownership: "all",
  category: "",
  searchDraft: "",
  searchQuery: "",
  prompts: [],
  loading: true,
  error: null,
  isCreateOpen: false,
  isCreating: false,
  createError: null,
  createForm: emptyPromptForm,
  selectedPromptId: null,
  selectedPrompt: null,
  detailLoading: false,
  detailError: null,
  isCloning: false,
  isEditing: false,
  isSaving: false,
  editError: null,
  editForm: emptyPromptEditForm,
  isPublishing: false,
};

function promptsPageReducer(state: PromptsPageState, action: PromptsPageAction): PromptsPageState {
  const patch = typeof action.patch === "function" ? action.patch(state) : action.patch;
  return { ...state, ...patch };
}

function resolveStateAction<T>(value: SetStateAction<T>, current: T): T {
  return typeof value === "function" ? (value as (current: T) => T)(current) : value;
}

function usePromptsPageController() {
  const router = useRouter();
  const { replace } = router;
  const { user } = useAuth();
  const [pageState, dispatchPageState] = useReducer(promptsPageReducer, initialPromptsPageState);
  const {
    ownership,
    category,
    searchDraft,
    searchQuery,
    prompts,
    loading,
    error,
    isCreateOpen,
    isCreating,
    createError,
    createForm,
    selectedPromptId,
    selectedPrompt,
    detailLoading,
    detailError,
    isCloning,
    isEditing,
    isSaving,
    editError,
    editForm,
    isPublishing,
  } = pageState;
  const setPageField = useCallback(
    <K extends keyof PromptsPageState>(key: K, value: SetStateAction<PromptsPageState[K]>) => {
      dispatchPageState({
        patch: (current) => ({ [key]: resolveStateAction(value, current[key]) }) as Partial<PromptsPageState>,
      });
    },
    [],
  );
  const setOwnership = useCallback(
    (value: SetStateAction<PromptOwnershipFilter>) => setPageField("ownership", value),
    [setPageField],
  );
  const setCategory = useCallback((value: SetStateAction<string>) => setPageField("category", value), [setPageField]);
  const setSearchDraft = useCallback(
    (value: SetStateAction<string>) => setPageField("searchDraft", value),
    [setPageField],
  );
  const setSearchQuery = useCallback(
    (value: SetStateAction<string>) => setPageField("searchQuery", value),
    [setPageField],
  );
  const setPrompts = useCallback(
    (value: SetStateAction<PromptListItem[]>) => setPageField("prompts", value),
    [setPageField],
  );
  const setIsCreateOpen = useCallback(
    (value: SetStateAction<boolean>) => setPageField("isCreateOpen", value),
    [setPageField],
  );
  const setIsCreating = useCallback(
    (value: SetStateAction<boolean>) => setPageField("isCreating", value),
    [setPageField],
  );
  const setCreateError = useCallback(
    (value: SetStateAction<string | null>) => setPageField("createError", value),
    [setPageField],
  );
  const setCreateForm = useCallback(
    (value: SetStateAction<PromptFormState>) => setPageField("createForm", value),
    [setPageField],
  );
  const setSelectedPromptId = useCallback(
    (value: SetStateAction<string | null>) => setPageField("selectedPromptId", value),
    [setPageField],
  );
  const setSelectedPrompt = useCallback(
    (value: SetStateAction<PromptDetail | null>) => setPageField("selectedPrompt", value),
    [setPageField],
  );
  const setDetailLoading = useCallback(
    (value: SetStateAction<boolean>) => setPageField("detailLoading", value),
    [setPageField],
  );
  const setDetailError = useCallback(
    (value: SetStateAction<string | null>) => setPageField("detailError", value),
    [setPageField],
  );
  const setIsCloning = useCallback(
    (value: SetStateAction<boolean>) => setPageField("isCloning", value),
    [setPageField],
  );
  const setIsEditing = useCallback(
    (value: SetStateAction<boolean>) => setPageField("isEditing", value),
    [setPageField],
  );
  const setIsSaving = useCallback((value: SetStateAction<boolean>) => setPageField("isSaving", value), [setPageField]);
  const setEditError = useCallback(
    (value: SetStateAction<string | null>) => setPageField("editError", value),
    [setPageField],
  );
  const setEditForm = useCallback(
    (value: SetStateAction<PromptEditFormState>) => setPageField("editForm", value),
    [setPageField],
  );
  const setIsPublishing = useCallback(
    (value: SetStateAction<boolean>) => setPageField("isPublishing", value),
    [setPageField],
  );

  const filters = useMemo(
    () => ({ ownership, category: category || undefined, search: searchQuery || undefined }),
    [ownership, category, searchQuery],
  );

  useEffect(() => {
    if (!router.isReady) return;
    const nextOwnership = isPromptOwnershipFilter(router.query.ownership) ? router.query.ownership : "all";
    const nextCategory = isPromptCategory(router.query.category) ? router.query.category : "";
    const nextSearch = typeof router.query.q === "string" ? router.query.q : "";
    dispatchPageState({
      patch: {
        ownership: nextOwnership,
        category: nextCategory,
        searchDraft: nextSearch,
        searchQuery: nextSearch.trim(),
      },
    });
  }, [router.isReady, router.query.category, router.query.ownership, router.query.q]);

  const replacePromptQuery = useCallback(
    (next: { ownership?: PromptOwnershipFilter; category?: string; q?: string; prompt?: string | null }) => {
      if (!router.isReady) return;
      const queryParams = { ...router.query };
      delete queryParams.ownership;
      delete queryParams.category;
      delete queryParams.q;
      delete queryParams.prompt;
      queryParams.ownership = next.ownership ?? ownership;
      const nextCategory = next.category ?? category;
      const nextSearch = next.q ?? searchQuery;
      const nextPrompt = next.prompt !== undefined ? next.prompt : selectedPromptId;
      if (nextCategory) queryParams.category = nextCategory;
      if (nextSearch.trim()) queryParams.q = nextSearch.trim();
      if (nextPrompt) queryParams.prompt = nextPrompt;
      void replace({ pathname: router.pathname, query: queryParams }, undefined, { shallow: true, scroll: false });
    },
    [category, ownership, replace, router, searchQuery, selectedPromptId],
  );

  const updateOwnership = (value: PromptOwnershipFilter) => {
    setOwnership(value);
    replacePromptQuery({ ownership: value });
  };
  const updateCategory = (value: string) => {
    const nextCategory = value === "all" ? "" : value;
    setCategory(nextCategory);
    replacePromptQuery({ category: nextCategory });
  };
  const applySearch = (value: string) => {
    const normalized = value.trim();
    setSearchQuery(normalized);
    replacePromptQuery({ q: normalized });
  };

  const refreshPrompts = useCallback(async () => {
    dispatchPageState({ patch: { loading: true, error: null } });
    try {
      const data = await promptsApi.list(filters);
      dispatchPageState({ patch: { prompts: data, loading: false, error: null } });
    } catch (err: unknown) {
      dispatchPageState({ patch: { error: getApiErrorMessage(err, "Failed to load prompts."), loading: false } });
    }
  }, [filters]);

  useEffect(() => {
    let isActive = true;
    const loadPrompts = async () => {
      dispatchPageState({ patch: { loading: true, error: null } });
      try {
        const data = await promptsApi.list(filters);
        if (!isActive) return;
        dispatchPageState({ patch: { prompts: data, loading: false, error: null } });
      } catch (err: unknown) {
        if (!isActive) return;
        dispatchPageState({ patch: { error: getApiErrorMessage(err, "Failed to load prompts."), loading: false } });
      }
    };
    void loadPrompts();
    return () => {
      isActive = false;
    };
  }, [filters]);

  const openCreate = () => {
    setCreateError(null);
    setCreateForm({ title: "", description: "", category: "other", content: "", variablesSchemaText: "" });
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

  const openDetail = useCallback(
    async (promptId: string, syncUrl = true) => {
      setSelectedPromptId(promptId);
      setSelectedPrompt(null);
      setDetailError(null);
      setIsEditing(false);
      setEditError(null);
      setDetailLoading(true);
      try {
        const detail = await promptsApi.get(promptId);
        setSelectedPrompt(detail);
        if (syncUrl) replacePromptQuery({ prompt: promptId });
      } catch (err: unknown) {
        setDetailError(getApiErrorMessage(err, "Failed to load prompt."));
      } finally {
        setDetailLoading(false);
      }
    },
    [
      replacePromptQuery,
      setDetailError,
      setDetailLoading,
      setEditError,
      setIsEditing,
      setSelectedPrompt,
      setSelectedPromptId,
    ],
  );

  const closeDetail = useCallback(
    (syncUrl = true) => {
      if (detailLoading || isCloning || isSaving || isPublishing) return;
      setSelectedPromptId(null);
      setSelectedPrompt(null);
      setDetailError(null);
      setIsEditing(false);
      setEditError(null);
      if (syncUrl) replacePromptQuery({ prompt: null });
    },
    [
      detailLoading,
      isCloning,
      isPublishing,
      isSaving,
      replacePromptQuery,
      setDetailError,
      setEditError,
      setIsEditing,
      setSelectedPrompt,
      setSelectedPromptId,
    ],
  );

  useEffect(() => {
    if (!router.isReady) return;
    const promptId = typeof router.query.prompt === "string" ? router.query.prompt : "";
    if (promptId && promptId !== selectedPromptId) void openDetail(promptId, false);
    if (!promptId && selectedPromptId && !detailLoading && !isCloning && !isSaving && !isPublishing) closeDetail(false);
  }, [
    closeDetail,
    detailLoading,
    isCloning,
    isPublishing,
    isSaving,
    openDetail,
    router.isReady,
    router.query.prompt,
    selectedPromptId,
  ]);

  const canCloneSelected = Boolean(
    selectedPrompt && selectedPrompt.visibility === "public" && selectedPrompt.owner_id !== user?.id,
  );
  const isOrgAdmin = user?.organization_role === "owner" || user?.organization_role === "admin";
  const canEditSelected = Boolean(
    selectedPrompt && user?.id && selectedPrompt.owner_id && (selectedPrompt.owner_id === user.id || isOrgAdmin),
  );
  const canPublishSelected = Boolean(
    selectedPrompt && canEditSelected && selectedPrompt.visibility !== "public" && isOrgAdmin,
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
      setPrompts((prev) => prev.map((p) => (p.id === updated.id ? { ...p, visibility: updated.visibility } : p)));
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
      showError("Delete failed", getApiErrorMessage(err, ERROR_FALLBACKS.prompt.delete));
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
  const visiblePrompts = prompts.slice(0, 50);
  const hiddenPromptCount = Math.max(prompts.length - visiblePrompts.length, 0);

  return {
    ownership,
    category,
    searchDraft,
    prompts,
    loading,
    error,
    isCreateOpen,
    isCreating,
    createError,
    createForm,
    selectedPromptId,
    selectedPrompt,
    detailLoading,
    detailError,
    isCloning,
    isEditing,
    isSaving,
    editError,
    editForm,
    isPublishing,
    canCloneSelected,
    canEditSelected,
    canPublishSelected,
    emptyStateTitle,
    emptyStateDescription,
    visiblePrompts,
    hiddenPromptCount,
    setSearchDraft,
    setCreateForm,
    setIsCreateOpen,
    setEditForm,
    updateOwnership,
    updateCategory,
    applySearch,
    refreshPrompts,
    openCreate,
    closeCreate,
    submitCreate,
    openDetail,
    closeDetail,
    cloneSelected,
    startEditing,
    cancelEditing,
    submitEdit,
    publishSelected,
    handleDelete,
  };
}

type PromptsPageController = ReturnType<typeof usePromptsPageController>;

function PromptsHero({ controller }: { controller: PromptsPageController }) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-border/50 bg-card/60 backdrop-blur-sm p-6">
      <div className="pointer-events-none absolute inset-0 bg-linear-to-br from-primary/12 via-violet-500/8 to-fuchsia-500/8" />
      <div className="relative flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight bg-linear-to-r from-primary via-violet-500 to-fuchsia-500 bg-clip-text text-transparent">
            Prompts
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Browse built-in prompts and manage your own prompt library.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={() => void controller.refreshPrompts()} disabled={controller.loading}>
            <RefreshCw aria-hidden="true" />
            Refresh
          </Button>
          <Button onClick={controller.openCreate}>
            <Plus aria-hidden="true" />
            New prompt
          </Button>
        </div>
      </div>
    </div>
  );
}

function PromptFilters({ controller }: { controller: PromptsPageController }) {
  return (
    <Card className="border-border/50 bg-card/60 backdrop-blur-sm">
      <CardContent className="pt-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            {OWNERSHIP_OPTIONS.map((option) => (
              <Button
                key={option.value}
                variant={controller.ownership === option.value ? "default" : "outline"}
                size="sm"
                onClick={() => controller.updateOwnership(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end">
            <Select value={controller.category || "all"} onValueChange={controller.updateCategory}>
              <SelectTrigger className="w-full sm:w-48">
                <SelectValue placeholder="All categories" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {CATEGORIES.map((category) => (
                  <SelectItem key={category.value} value={category.value}>
                    {category.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <SearchInput
              value={controller.searchDraft}
              onChange={controller.setSearchDraft}
              placeholder="Search prompts"
              className="w-full sm:w-64"
              onSearch={controller.applySearch}
              debounceMs={300}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function PromptsListSection({ controller }: { controller: PromptsPageController }) {
  if (controller.loading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Spinner size="md" />
        <span className="ml-3 text-sm text-muted-foreground">Loading prompts</span>
      </div>
    );
  }
  if (controller.prompts.length === 0) {
    return (
      <EmptyState
        className="py-10"
        title={controller.emptyStateTitle}
        description={controller.emptyStateDescription}
        action={
          controller.ownership !== "builtin" ? (
            <Button onClick={controller.openCreate}>Create a prompt</Button>
          ) : undefined
        }
      />
    );
  }

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {controller.visiblePrompts.map((prompt) => (
          <PromptCard key={prompt.id} prompt={prompt} onOpen={() => void controller.openDetail(prompt.id)} />
        ))}
      </div>
      {controller.hiddenPromptCount > 0 ? (
        <p className="text-sm text-muted-foreground">
          Showing first 50 of {controller.prompts.length} prompts. Narrow the filters or search to reduce the list.
        </p>
      ) : null}
    </>
  );
}

function PromptCard({ prompt, onOpen }: { prompt: PromptListItem; onOpen: () => void }) {
  return (
    <Card className={prompt.is_builtin ? "border-primary/30 bg-primary/5" : ""}>
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
        <CardDescription className="line-clamp-2">{prompt.description || "No description"}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between text-xs text-muted-foreground mb-3">
          <span>{formatCategory(prompt.category)}</span>
          <span>{formatDateTime(prompt.created_at)}</span>
        </div>
        <Button variant="outline" size="sm" className="w-full" onClick={onOpen}>
          View
        </Button>
      </CardContent>
    </Card>
  );
}

function PromptFormFields({
  form,
  disabled,
  onChange,
  mode,
  category,
}: {
  form: PromptFormState | PromptEditFormState;
  disabled: boolean;
  onChange: (value: SetStateAction<any>) => void;
  mode: "create" | "edit";
  category?: string;
}) {
  const prefix = mode === "create" ? "create" : "edit";
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        <FormField label="Title" required htmlFor={`${prefix}-prompt-title`}>
          <Input
            id={`${prefix}-prompt-title`}
            name={`${prefix}_prompt_title`}
            autoComplete="off"
            value={form.title}
            onChange={(e) => onChange((prev: any) => ({ ...prev, title: e.target.value }))}
            disabled={disabled}
          />
        </FormField>
        {mode === "create" ? (
          <FormField label="Category" htmlFor="create-prompt-category">
            <Select
              value={(form as PromptFormState).category}
              onValueChange={(v) => onChange((prev: PromptFormState) => ({ ...prev, category: v as PromptCategory }))}
              disabled={disabled}
            >
              <SelectTrigger id="create-prompt-category">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CATEGORIES.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FormField>
        ) : (
          <FormField label="Category">
            <div className="px-3 py-2 border rounded-md text-sm bg-muted">
              {category ? formatCategory(category) : "Other"}
            </div>
          </FormField>
        )}
      </div>
      <FormField label="Description" htmlFor={`${prefix}-prompt-description`}>
        <Input
          id={`${prefix}-prompt-description`}
          name={`${prefix}_prompt_description`}
          autoComplete="off"
          value={form.description}
          onChange={(e) => onChange((prev: any) => ({ ...prev, description: e.target.value }))}
          disabled={disabled}
        />
      </FormField>
      <FormField label="Content" required htmlFor={`${prefix}-prompt-content`}>
        <Textarea
          id={`${prefix}-prompt-content`}
          name={`${prefix}_prompt_content`}
          autoComplete="off"
          value={form.content}
          onChange={(e) => onChange((prev: any) => ({ ...prev, content: e.target.value }))}
          disabled={disabled}
          className="font-mono"
          rows={mode === "create" ? 10 : 12}
        />
      </FormField>
      <FormField
        label="Variables schema (JSON)"
        description={mode === "create" ? "Leave empty for no variables." : undefined}
        htmlFor={`${prefix}-prompt-variables`}
      >
        <Textarea
          id={`${prefix}-prompt-variables`}
          name={`${prefix}_prompt_variables_schema`}
          autoComplete="off"
          value={form.variablesSchemaText}
          onChange={(e) => onChange((prev: any) => ({ ...prev, variablesSchemaText: e.target.value }))}
          disabled={disabled}
          className="font-mono"
          rows={mode === "create" ? 4 : 6}
        />
      </FormField>
    </>
  );
}

function CreatePromptDialog({ controller }: { controller: PromptsPageController }) {
  return (
    <Dialog
      open={controller.isCreateOpen}
      onOpenChange={(open) => !controller.isCreating && controller.setIsCreateOpen(open)}
    >
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Create new prompt</DialogTitle>
          <DialogDescription>Create a reusable prompt template.</DialogDescription>
        </DialogHeader>
        {controller.createError ? (
          <Alert variant="destructive">
            <AlertDescription>{controller.createError}</AlertDescription>
          </Alert>
        ) : null}
        <form id="create-prompt-form" className="space-y-4" onSubmit={controller.submitCreate}>
          <PromptFormFields
            form={controller.createForm}
            disabled={controller.isCreating}
            onChange={controller.setCreateForm}
            mode="create"
          />
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={controller.closeCreate} disabled={controller.isCreating}>
            Cancel
          </Button>
          <Button type="submit" form="create-prompt-form" disabled={controller.isCreating}>
            {controller.isCreating ? (
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
  );
}

function PromptDetailDialog({ controller }: { controller: PromptsPageController }) {
  return (
    <Dialog
      open={Boolean(controller.selectedPromptId)}
      onOpenChange={(open) => {
        if (
          !open &&
          !controller.detailLoading &&
          !controller.isCloning &&
          !controller.isSaving &&
          !controller.isPublishing
        )
          controller.closeDetail();
      }}
    >
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <PromptDetailHeader selectedPrompt={controller.selectedPrompt} />
        {controller.detailError ? (
          <Alert variant="destructive">
            <AlertDescription>{controller.detailError}</AlertDescription>
          </Alert>
        ) : null}
        <PromptDetailBody controller={controller} />
      </DialogContent>
    </Dialog>
  );
}

function PromptDetailHeader({ selectedPrompt }: { selectedPrompt: PromptDetail | null }) {
  return (
    <DialogHeader>
      <DialogTitle>{selectedPrompt ? selectedPrompt.title : "Prompt"}</DialogTitle>
      <DialogDescription>
        {selectedPrompt
          ? selectedPrompt.description || "Review prompt details, variables, and sharing controls."
          : "Loading prompt details."}
      </DialogDescription>
      {selectedPrompt ? (
        <div className="flex items-center gap-2 mt-2">
          <Badge variant={selectedPrompt.owner_id ? "secondary" : "default"}>
            {selectedPrompt.owner_id ? "Custom" : "Built-in"}
          </Badge>
          <Badge variant="outline">{selectedPrompt.visibility}</Badge>
          <Badge variant="outline">{formatCategory(selectedPrompt.category)}</Badge>
        </div>
      ) : null}
    </DialogHeader>
  );
}

function PromptDetailBody({ controller }: { controller: PromptsPageController }) {
  if (controller.detailLoading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Spinner size="md" />
        <span className="ml-3 text-sm text-muted-foreground">Loading prompt</span>
      </div>
    );
  }
  if (!controller.selectedPrompt) {
    return <div className="py-6 text-center text-sm text-muted-foreground">Prompt not available.</div>;
  }
  if (controller.isEditing) {
    return <PromptEditPanel controller={controller} selectedPrompt={controller.selectedPrompt} />;
  }
  return <PromptReadOnlyDetail controller={controller} selectedPrompt={controller.selectedPrompt} />;
}

function PromptEditPanel({
  controller,
  selectedPrompt,
}: {
  controller: PromptsPageController;
  selectedPrompt: PromptDetail;
}) {
  return (
    <>
      {controller.editError ? (
        <Alert variant="destructive">
          <AlertDescription>{controller.editError}</AlertDescription>
        </Alert>
      ) : null}
      <form id="edit-prompt-form" className="space-y-4" onSubmit={controller.submitEdit}>
        <PromptFormFields
          form={controller.editForm}
          disabled={controller.isSaving}
          onChange={controller.setEditForm}
          mode="edit"
          category={selectedPrompt.category}
        />
      </form>
      <DialogFooter>
        <Button variant="outline" onClick={controller.cancelEditing} disabled={controller.isSaving}>
          Cancel
        </Button>
        <Button type="submit" form="edit-prompt-form" disabled={controller.isSaving}>
          {controller.isSaving ? (
            <>
              <Spinner size="xs" className="mr-2" />
              Saving
            </>
          ) : (
            "Save"
          )}
        </Button>
      </DialogFooter>
    </>
  );
}

function PromptReadOnlyDetail({
  controller,
  selectedPrompt,
}: {
  controller: PromptsPageController;
  selectedPrompt: PromptDetail;
}) {
  return (
    <>
      <div className="space-y-4">
        <div className="grid gap-4 md:grid-cols-3">
          <PromptMetaBox label="Version" value={selectedPrompt.version} />
          <PromptMetaBox label="License" value={selectedPrompt.license} />
          <PromptMetaBox label="Updated" value={formatDateTime(selectedPrompt.updated_at)} />
        </div>
        {selectedPrompt.description ? (
          <>
            <Separator />
            <div>
              <h4 className="text-sm font-medium mb-2">Description</h4>
              <p className="text-sm text-muted-foreground whitespace-pre-wrap">{selectedPrompt.description}</p>
            </div>
          </>
        ) : null}
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
      <PromptDetailFooter controller={controller} selectedPrompt={selectedPrompt} />
    </>
  );
}

function PromptMetaBox({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-muted rounded-lg p-3">
      <p className="text-xs font-medium text-muted-foreground uppercase">{label}</p>
      <p className="mt-1 text-sm">{value}</p>
    </div>
  );
}

function PromptDetailFooter({
  controller,
  selectedPrompt,
}: {
  controller: PromptsPageController;
  selectedPrompt: PromptDetail;
}) {
  return (
    <DialogFooter className="flex-wrap gap-2">
      {controller.canCloneSelected ? (
        <Button onClick={() => void controller.cloneSelected()} disabled={controller.isCloning}>
          {controller.isCloning ? (
            <>
              <Spinner size="xs" className="mr-2" />
              Cloning
            </>
          ) : (
            "Clone"
          )}
        </Button>
      ) : null}
      {controller.canPublishSelected ? (
        <Button variant="outline" onClick={() => void controller.publishSelected()} disabled={controller.isPublishing}>
          {controller.isPublishing ? (
            <>
              <Spinner size="xs" className="mr-2" />
              Publishing
            </>
          ) : (
            "Publish"
          )}
        </Button>
      ) : null}
      {controller.canEditSelected ? (
        <>
          <Button variant="outline" onClick={controller.startEditing}>
            Edit
          </Button>
          <ConfirmButton
            variant="destructive"
            title={`Delete "${selectedPrompt.title}"`}
            description="This will permanently delete the prompt. This action cannot be undone."
            confirmText="Delete"
            onConfirm={() => controller.handleDelete(selectedPrompt)}
          >
            Delete
          </ConfirmButton>
        </>
      ) : null}
      <Button variant="outline" onClick={() => controller.closeDetail()}>
        Close
      </Button>
    </DialogFooter>
  );
}

export default function PromptsPage() {
  const controller = usePromptsPageController();

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <PromptsHero controller={controller} />
          <PromptFilters controller={controller} />
          {controller.error ? (
            <Alert variant="destructive">
              <AlertDescription>{controller.error}</AlertDescription>
            </Alert>
          ) : null}
          <PromptsListSection controller={controller} />
          <CreatePromptDialog controller={controller} />
          <PromptDetailDialog controller={controller} />
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
