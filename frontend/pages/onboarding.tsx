import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { CircleHelp, ExternalLink, Plus, Search, Star, X } from "lucide-react";

import DashboardLayout from "../components/DashboardLayout";
import ProtectedRoute from "../components/ProtectedRoute";
import {
  credentialsApi,
  getApiErrorMessage,
  runsApi,
  templatesApi,
  onboardingApi,
  type Credential,
  type GraphTemplate,
  type OnboardingMilestone,
} from "../lib/api";
import {
  buildTemplatePreview,
  buildTemplateQuickStarts,
} from "../lib/template-quick-starts";
import {
  ONBOARDING_DOC_LINKS,
  buildCredentialRemediation,
  buildRunRemediation,
  getOnboardingProgress,
  type OnboardingRemediation,
} from "../lib/onboarding-guide";
import { ERROR_FALLBACKS } from "../lib/error-messages";
import { showError, showSuccess } from "../lib/toast";
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Switch,
  Spinner,
  Textarea,
} from "@/components/ui";

const PROVIDERS = ["openai", "anthropic"] as const;

const MODEL_OPTIONS: Record<string, string[]> = {
  openai: ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
  anthropic: ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
};

const API_KEY_PLACEHOLDERS: Record<string, string> = {
  openai: "sk-proj-xxxxxxxxxxxxxxxxxxxx",
  anthropic: "sk-ant-api03-xxxxxxxxxxxxxxxxxxxx",
  google: "AIzaSyxxxxxxxxxxxxxxxxxxxx",
  gmail: "OAuth credential",
  telegram: "Bot token from @BotFather",
  twilio: "Twilio SID / Auth Token",
};

function HelpTip({ text, testId }: { text: string; testId?: string }) {
  return (
    <button
      type="button"
      title={text}
      aria-label={`Help: ${text}`}
      data-testid={testId}
      className="inline-flex h-4 w-4 items-center justify-center rounded text-muted-foreground hover:text-foreground"
    >
      <CircleHelp className="h-3.5 w-3.5" />
    </button>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const [templates, setTemplates] = useState<GraphTemplate[]>([]);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [graphName, setGraphName] = useState("");
  const [provider, setProvider] = useState<string>("openai");
  const [model, setModel] = useState<string>("gpt-4");
  const [credentialId, setCredentialId] = useState<string>("");
  const [milestones, setMilestones] = useState<OnboardingMilestone[]>([]);
  const [useSampleData, setUseSampleData] = useState(true);
  const [customInput, setCustomInput] = useState("{}");

  // Template search state
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  // Credential creation state
  const [showCredentialForm, setShowCredentialForm] = useState(false);
  const [newCredentialName, setNewCredentialName] = useState("");
  const [newCredentialKey, setNewCredentialKey] = useState("");
  const [isCreatingCredential, setIsCreatingCredential] = useState(false);
  const [ratingInFlight, setRatingInFlight] = useState(false);
  const [ratedTemplateId, setRatedTemplateId] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [credentialRemediation, setCredentialRemediation] = useState<OnboardingRemediation | null>(null);
  const [runRemediation, setRunRemediation] = useState<OnboardingRemediation | null>(null);

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.id === selectedTemplateId) ?? null,
    [templates, selectedTemplateId],
  );

  const filteredCredentials = useMemo(
    () =>
      credentials.filter(
        (cred) => cred.provider === provider && cred.health_status !== "revoked",
      ),
    [credentials, provider],
  );

  const availableModels = useMemo(() => MODEL_OPTIONS[provider] ?? [], [provider]);
  const quickStarts = useMemo(() => buildTemplateQuickStarts(templates), [templates]);

  const selectedQuickStart = useMemo(() => {
    if (!selectedTemplate) return null;
    return quickStarts.find((quickStart) => quickStart.template.id === selectedTemplate.id) ?? null;
  }, [quickStarts, selectedTemplate]);

  const selectedTemplatePreview = useMemo(() => {
    if (!selectedTemplate) return null;
    return buildTemplatePreview(selectedTemplate, credentials, selectedQuickStart?.title);
  }, [credentials, selectedQuickStart?.title, selectedTemplate]);

  // Extract unique categories from templates
  const categories = useMemo(() => {
    const cats = new Set<string>();
    templates.forEach((t) => {
      if (t.category) cats.add(t.category);
    });
    return Array.from(cats).sort();
  }, [templates]);

  // Extract unique tags from templates
  const allTags = useMemo(() => {
    const tags = new Set<string>();
    templates.forEach((t) => {
      t.tags?.forEach((tag) => tags.add(tag));
    });
    return Array.from(tags).sort();
  }, [templates]);

  // Filter templates based on search and category
  const filteredTemplates = useMemo(() => {
    return templates.filter((template) => {
      const matchesSearch =
        !searchQuery ||
        template.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        template.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        template.tags?.some((tag) => tag.toLowerCase().includes(searchQuery.toLowerCase()));

      const matchesCategory = !selectedCategory || template.category === selectedCategory;

      return matchesSearch && matchesCategory;
    });
  }, [templates, searchQuery, selectedCategory]);

  // Completion states for visual feedback
  const hasTemplate = Boolean(selectedTemplateId);
  const hasCredential = Boolean(
    credentialId && filteredCredentials.some((credential) => credential.id === credentialId),
  );

  const checklist = useMemo(() => {
    if (milestones.length > 0) {
      return milestones;
    }
    return [
      { key: "select_template", label: "Template selected", completed: hasTemplate, completed_at: null },
      { key: "attach_credential", label: "Credential attached", completed: hasCredential, completed_at: null },
      { key: "run_template", label: "First run started", completed: false, completed_at: null },
    ] satisfies OnboardingMilestone[];
  }, [milestones, hasTemplate, hasCredential]);
  const checklistProgress = useMemo(() => getOnboardingProgress(checklist), [checklist]);

  const completeMilestone = useCallback(
    async (milestone: string, metadata?: Record<string, unknown>) => {
      try {
        await onboardingApi.complete(milestone, metadata);
      } catch (err) {
        console.warn("Failed to update milestone", err);
        return;
      }

      setMilestones((prev) => {
        const now = new Date().toISOString();
        const existing = prev.find((item) => item.key === milestone);
        if (!existing) {
          return [
            ...prev,
            { key: milestone, label: milestone, completed: true, completed_at: now },
          ];
        }
        if (existing.completed) {
          return prev;
        }
        return prev.map((item) =>
          item.key === milestone
            ? { ...item, completed: true, completed_at: item.completed_at ?? now }
            : item,
        );
      });
    },
    [],
  );

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [templatesData, credentialsData, milestonesData] = await Promise.all([
        templatesApi.list(),
        credentialsApi.list(),
        onboardingApi.list(),
      ]);
      setTemplates(templatesData);
      setCredentials(credentialsData);
      setMilestones(milestonesData);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to load onboarding data."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (availableModels.length && !availableModels.includes(model)) {
      setModel(availableModels[0]);
    }
  }, [availableModels, model]);

  useEffect(() => {
    setShowCredentialForm(false);
    setCredentialRemediation(null);
  }, [provider]);

  useEffect(() => {
    if (filteredCredentials.length === 0) {
      if (credentialId) {
        setCredentialId("");
      }
      return;
    }

    const selectedIsStillValid = filteredCredentials.some(
      (credential) => credential.id === credentialId,
    );
    if (!selectedIsStillValid) {
      setCredentialId(filteredCredentials[0].id);
    }
  }, [credentialId, filteredCredentials]);

  useEffect(() => {
    setRunRemediation(null);
  }, [selectedTemplateId, credentialId, useSampleData]);

  useEffect(() => {
    if (credentialId) {
      void completeMilestone("attach_credential", { provider });
    }
  }, [credentialId, provider, completeMilestone]);

  useEffect(() => {
    if (!useSampleData) {
      const baseInput = selectedTemplate?.sample_input ?? {};
      setCustomInput(JSON.stringify(baseInput, null, 2));
    }
  }, [selectedTemplate, useSampleData]);

  // Auto-show credential form if no credentials exist for selected provider
  useEffect(() => {
    if (!loading && filteredCredentials.length === 0) {
      setShowCredentialForm(true);
    }
  }, [loading, filteredCredentials.length]);

  const handleCreateCredential = async () => {
    if (!newCredentialName.trim() || !newCredentialKey.trim()) {
      showError("Missing details", "Add a name and API key.");
      return;
    }

    setIsCreatingCredential(true);
    try {
      setCredentialRemediation(null);
      const created = await credentialsApi.create({
        name: newCredentialName.trim(),
        provider,
        api_key: newCredentialKey.trim(),
      });
      setCredentials((prev) => [created, ...prev]);
      setCredentialId(created.id);
      setNewCredentialName("");
      setNewCredentialKey("");
      setShowCredentialForm(false);
      showSuccess("Credential saved", `${created.name} is ready to use.`);
    } catch (err: unknown) {
      const message = getApiErrorMessage(err, ERROR_FALLBACKS.credential.create);
      setCredentialRemediation(
        buildCredentialRemediation({
          message,
          provider,
        }),
      );
      showError("Credential failed", message);
    } finally {
      setIsCreatingCredential(false);
    }
  };

  const handleRateTemplate = async (rating: number) => {
    if (!selectedTemplate || ratingInFlight) return;
    setRatingInFlight(true);
    try {
      await templatesApi.rate(selectedTemplate.id, { rating });
      setRatedTemplateId(selectedTemplate.id);
      showSuccess("Thanks for the rating", "Template feedback saved.");
    } catch (err: unknown) {
      showError("Rating failed", getApiErrorMessage(err, "Unable to save rating."));
    } finally {
      setRatingInFlight(false);
    }
  };

  const handleRun = async () => {
    if (!selectedTemplate) return;
    const resolvedCredentialId = credentialId || filteredCredentials[0]?.id || "";
    if (!resolvedCredentialId) {
      const message = `Select a ${provider} credential before running this template.`;
      setRunRemediation(
        buildRunRemediation({
          message,
          hasTemplate: true,
          hasCredential: false,
          useSampleData,
        }),
      );
      showError("Run blocked", message);
      return;
    }

    let inputPayload: Record<string, unknown> = selectedTemplate.sample_input || {};
    if (!useSampleData) {
      try {
        const parsed = customInput.trim() ? JSON.parse(customInput) : {};
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          showError("Invalid JSON", "Custom input must be a JSON object.");
          return;
        }
        inputPayload = parsed as Record<string, unknown>;
      } catch (err) {
        showError("Invalid JSON", "Custom input must be valid JSON.");
        return;
      }
    }

    setIsRunning(true);
    try {
      setRunRemediation(null);
      const clone = await templatesApi.clone(selectedTemplate.id, {
        name: graphName.trim() || undefined,
        provider,
        model,
        credential_id: resolvedCredentialId,
      });
      const run = await runsApi.start({
        graph_version_id: clone.graph_version_id,
        input_json: inputPayload,
      });
      void completeMilestone("run_template", { template_id: selectedTemplate.id });
      showSuccess("Run started", "Live execution is now streaming.");
      await router.push(`/runs/${run.id}`);
    } catch (err: unknown) {
      const message = getApiErrorMessage(err, ERROR_FALLBACKS.run.start);
      setRunRemediation(
        buildRunRemediation({
          message,
          hasTemplate: Boolean(selectedTemplate),
          hasCredential: Boolean(credentialId),
          useSampleData,
        }),
      );
      showError("Run failed", message);
    } finally {
      setIsRunning(false);
    }
  };

  const clearFilters = () => {
    setSearchQuery("");
    setSelectedCategory(null);
  };

  const handleSelectTemplate = useCallback(
    (template: GraphTemplate, options?: { graphName?: string; provider?: string; model?: string }) => {
      setSelectedTemplateId(template.id);
      setGraphName(options?.graphName ?? template.name);

      if (options?.provider && PROVIDERS.includes(options.provider as (typeof PROVIDERS)[number])) {
        setProvider(options.provider);
        const providerModels = MODEL_OPTIONS[options.provider];
        if (providerModels?.length) {
          if (options.model && providerModels.includes(options.model)) {
            setModel(options.model);
          } else {
            setModel(providerModels[0]);
          }
        }
      }

      void completeMilestone("select_template", { template_id: template.id });
    },
    [completeMilestone],
  );

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <div className="relative overflow-hidden rounded-3xl border border-border/40 bg-card/70 p-6 shadow-lg backdrop-blur-sm">
            <div
              className="pointer-events-none absolute inset-0"
              style={{
                backgroundImage:
                  "radial-gradient(circle at 10% 20%, rgba(14, 116, 144, 0.15), transparent 55%), radial-gradient(circle at 80% 0%, rgba(59, 130, 246, 0.12), transparent 50%), linear-gradient(120deg, rgba(15, 23, 42, 0.04), rgba(255, 255, 255, 0))",
              }}
            />
            <div className="relative flex flex-col gap-2">
              <Badge variant="outline" className="border-cyan-400/40 text-cyan-700 dark:text-cyan-200 w-fit">
                Demo Onboarding
              </Badge>
              <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-foreground">
                Template → Credential → Live Run
              </h1>
              <p className="text-sm text-muted-foreground">
                Get to a live, streaming run in under three minutes.
              </p>
              <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-muted-foreground">
                <span className="rounded-full border border-border/60 bg-background/60 px-2 py-0.5">
                  Tip: quick starts prefill provider + model
                </span>
                <a
                  href={ONBOARDING_DOC_LINKS.templates}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-primary hover:underline"
                >
                  Learn onboarding basics
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            </div>
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {loading ? (
            <div className="flex items-center justify-center gap-3 rounded-2xl border border-border/40 bg-card/50 py-12">
              <Spinner size="md" />
              <span className="text-sm text-muted-foreground">Loading onboarding…</span>
            </div>
          ) : (
            <div className="grid gap-4 lg:grid-cols-3">
              {/* Template Selection Card */}
              <Card className={`border-border/50 bg-card/60 ${hasTemplate ? "border-green-500/30" : ""}`}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2">
                      1. Pick a template
                      {hasTemplate && (
                        <Badge variant="outline" className="border-green-500/50 text-green-600 dark:text-green-400 text-xs">
                          ✓
                        </Badge>
                      )}
                    </CardTitle>
                    <a
                      href={ONBOARDING_DOC_LINKS.templates}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                    >
                      Learn more
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  {quickStarts.length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Quick starts
                        </span>
                        <Badge variant="outline" className="text-[10px]">
                          1-click select
                        </Badge>
                      </div>
                      <div className="grid gap-2">
                        {quickStarts.map((quickStart) => (
                          <button
                            key={quickStart.id}
                            type="button"
                            data-testid={`quick-start-card-${quickStart.id}`}
                            onClick={() =>
                              handleSelectTemplate(quickStart.template, {
                                graphName: quickStart.title,
                                provider: quickStart.recommendedProvider,
                                model: quickStart.recommendedModel,
                              })
                            }
                            className={`rounded-xl border px-3 py-2 text-left transition ${
                              selectedTemplateId === quickStart.template.id
                                ? "border-primary/70 bg-primary/10"
                                : "border-border/50 hover:border-primary/40"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-xs font-semibold text-foreground">{quickStart.title}</span>
                              <Badge variant="secondary" className="text-[10px]">
                                v{quickStart.template.version}
                              </Badge>
                            </div>
                            <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2">
                              {quickStart.description}
                            </p>
                            <div className="mt-2 flex flex-wrap gap-1">
                              {quickStart.requiredProviders.slice(0, 3).map((requiredProvider) => (
                                <span
                                  key={`${quickStart.id}-${requiredProvider}`}
                                  className="rounded-full border border-border/60 bg-muted/40 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
                                >
                                  {requiredProvider}
                                </span>
                              ))}
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Search Bar */}
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search templates..."
                      className="pl-9 pr-8"
                    />
                    {searchQuery && (
                      <button
                        type="button"
                        onClick={() => setSearchQuery("")}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    )}
                  </div>

                  {/* Category Pills */}
                  {categories.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {categories.map((category) => (
                        <button
                          type="button"
                          key={category}
                          onClick={() => setSelectedCategory(selectedCategory === category ? null : category)}
                          className={`rounded-full px-2.5 py-1 text-xs font-medium transition ${
                            selectedCategory === category
                              ? "bg-primary text-primary-foreground"
                              : "bg-muted/50 text-muted-foreground hover:bg-muted"
                          }`}
                        >
                          {category}
                        </button>
                      ))}
                      {(searchQuery || selectedCategory) && (
                        <button
                          type="button"
                          onClick={clearFilters}
                          className="rounded-full px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground transition"
                        >
                          Clear
                        </button>
                      )}
                    </div>
                  )}

                  {/* Tag Pills (show if no categories or as secondary filter) */}
                  {categories.length === 0 && allTags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {allTags.slice(0, 6).map((tag) => (
                        <button
                          type="button"
                          key={tag}
                          onClick={() => setSearchQuery(tag)}
                          className="rounded-full px-2.5 py-1 text-xs font-medium bg-muted/50 text-muted-foreground hover:bg-muted transition"
                        >
                          {tag}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Template List */}
                  <div className="max-h-[280px] overflow-y-auto space-y-2 pr-1">
                    {filteredTemplates.length === 0 ? (
                      <div className="text-center py-6">
                        <p className="text-sm text-muted-foreground">
                          {templates.length === 0
                            ? "No templates available yet."
                            : "No templates match your search."}
                        </p>
                        {(searchQuery || selectedCategory) && (
                          <Button variant="ghost" size="sm" onClick={clearFilters} className="mt-2">
                            Clear filters
                          </Button>
                        )}
                      </div>
                    ) : (
                      filteredTemplates.map((template) => (
                        <button
                          type="button"
                          key={template.id}
                          onClick={() => handleSelectTemplate(template)}
                          className={`w-full rounded-xl border px-3 py-3 text-left text-sm transition ${
                            selectedTemplateId === template.id
                              ? "border-primary/70 bg-primary/10"
                              : "border-border/50 hover:border-primary/40"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-semibold">{template.name}</span>
                            <div className="flex items-center gap-1">
                              <Badge variant="outline" className="shrink-0 text-[10px]">
                                v{template.version}
                              </Badge>
                              <Badge variant="secondary" className="shrink-0">
                                {template.estimated_minutes} min
                              </Badge>
                            </div>
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
                            {template.description}
                          </p>
                          {(template.rating_count > 0 || template.usage_count > 0) && (
                            <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                              {template.rating_count > 0 && (
                                <span>
                                  ★ {template.rating_average?.toFixed(1) ?? "0.0"} ({template.rating_count})
                                </span>
                              )}
                              {template.usage_count > 0 && <span>{template.usage_count} uses</span>}
                              {typeof template.run_success_rate === "number" && (
                                <span>{Math.round(template.run_success_rate * 100)}% success</span>
                              )}
                            </div>
                          )}
                          {template.tags && template.tags.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-2">
                              {template.tags.slice(0, 3).map((tag) => (
                                <span
                                  key={tag}
                                  className="text-[10px] px-1.5 py-0.5 rounded bg-muted/50 text-muted-foreground"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                        </button>
                      ))
                    )}
                  </div>

                  {selectedTemplate?.guide_steps?.length ? (
                    <div className="rounded-xl border border-border/50 bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                      <div className="text-[11px] font-semibold text-foreground mb-1">Quick guide</div>
                      <div className="space-y-1">
                        {selectedTemplate.guide_steps.map((step, idx) => (
                          <div key={`${selectedTemplate.id}-step-${idx}`} className="flex items-start gap-2">
                            <span className="mt-0.5 text-[10px] text-muted-foreground">•</span>
                            <span>{step}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {selectedTemplate ? (
                    <div className="flex items-center justify-between rounded-xl border border-border/50 bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                      <span>
                        Rate this template{" "}
                        {ratedTemplateId === selectedTemplate.id ? "✓" : ""}
                      </span>
                      <div className="flex items-center gap-1">
                        {[1, 2, 3, 4, 5].map((rating) => (
                          <button
                            key={`${selectedTemplate.id}-rating-${rating}`}
                            type="button"
                            onClick={() => void handleRateTemplate(rating)}
                            disabled={ratingInFlight}
                            className="text-muted-foreground hover:text-foreground transition"
                          >
                            <Star className="h-3.5 w-3.5" />
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </CardContent>
              </Card>

              {/* Credentials Card */}
              <Card className={`border-border/50 bg-card/60 ${hasCredential ? "border-green-500/30" : ""}`}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2">
                      2. Attach credentials
                      {hasCredential && (
                        <Badge variant="outline" className="border-green-500/50 text-green-600 dark:text-green-400 text-xs">
                          ✓
                        </Badge>
                      )}
                    </CardTitle>
                    <a
                      href={ONBOARDING_DOC_LINKS.credentials}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                    >
                      Learn more
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  {credentialRemediation && (
                    <Alert variant="destructive" data-testid="credential-remediation-alert">
                      <AlertTitle>{credentialRemediation.title}</AlertTitle>
                      <AlertDescription>
                        <p className="mt-1">{credentialRemediation.summary}</p>
                        <ul className="mt-2 list-disc space-y-1 pl-4 text-xs">
                          {credentialRemediation.steps.map((step) => (
                            <li key={step}>{step}</li>
                          ))}
                        </ul>
                        <a
                          href={credentialRemediation.docsUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                        >
                          View troubleshooting guide
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      </AlertDescription>
                    </Alert>
                  )}

                  <div>
                    <div className="mb-1 flex items-center gap-1">
                      <label className="text-xs text-muted-foreground">Provider</label>
                      <HelpTip
                        testId="provider-help-tip"
                        text="Choose the API provider that will run prompt nodes in this template."
                      />
                    </div>
                    <Select value={provider} onValueChange={setProvider}>
                      <SelectTrigger>
                        <SelectValue placeholder="Provider" />
                      </SelectTrigger>
                      <SelectContent>
                        {PROVIDERS.map((item) => (
                          <SelectItem key={item} value={item}>
                            {item}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <div className="mb-1 flex items-center gap-1">
                      <label className="text-xs text-muted-foreground">Model</label>
                      <HelpTip
                        testId="model-help-tip"
                        text="Pick a model that balances quality and cost for your first test run."
                      />
                    </div>
                    <Select value={model} onValueChange={setModel}>
                      <SelectTrigger>
                        <SelectValue placeholder="Model" />
                      </SelectTrigger>
                      <SelectContent>
                        {availableModels.map((item) => (
                          <SelectItem key={item} value={item}>
                            {item}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Credential Selection */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-1">
                        <label className="text-xs text-muted-foreground">API Credential</label>
                        <HelpTip
                          testId="credential-help-tip"
                          text="Credentials are stored once and can be reused across templates and runs."
                        />
                      </div>
                      {filteredCredentials.length > 0 && !showCredentialForm && (
                        <button
                          type="button"
                          onClick={() => setShowCredentialForm(true)}
                          className="text-xs text-primary hover:underline flex items-center gap-1"
                        >
                          <Plus className="h-3 w-3" />
                          Add new
                        </button>
                      )}
                    </div>

                  {filteredCredentials.length > 0 ? (
                      <Select value={credentialId} onValueChange={setCredentialId}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select a credential" />
                        </SelectTrigger>
                        <SelectContent>
                          {filteredCredentials.map((cred) => (
                            <SelectItem key={cred.id} value={cred.id}>
                              {cred.name} · {cred.key_hint}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <div className="rounded-lg border border-dashed border-border/50 bg-muted/20 p-3 text-xs text-muted-foreground text-center">
                        No {provider} credentials found. Add one below.
                      </div>
                    )}
                  </div>

                  {/* Credential Creation Form */}
                  {showCredentialForm && (
                    <div className="rounded-xl border border-border/50 bg-muted/20 p-3 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-foreground">Add {provider} API key</span>
                          <a
                            href={ONBOARDING_DOC_LINKS.credentials}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
                          >
                            Docs
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        </div>
                        {filteredCredentials.length > 0 && (
                          <button
                            type="button"
                            onClick={() => setShowCredentialForm(false)}
                            className="text-muted-foreground hover:text-foreground"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                      <div>
                        <div className="mb-1 flex items-center gap-1">
                          <span className="text-[11px] text-muted-foreground">Credential label</span>
                          <HelpTip text="Use a descriptive label like Team OpenAI Prod to identify this key later." />
                        </div>
                        <Input
                          value={newCredentialName}
                          onChange={(e) => setNewCredentialName(e.target.value)}
                          placeholder="My OpenAI Key"
                          name="api-key-label"
                          autoComplete="one-time-code"
                          data-1p-ignore
                          data-lpignore="true"
                          data-form-type="other"
                        />
                        <p className="text-[10px] text-muted-foreground mt-1">A label to identify this key</p>
                      </div>
                      <div>
                        <div className="mb-1 flex items-center gap-1">
                          <span className="text-[11px] text-muted-foreground">Secret key</span>
                          <HelpTip text="Paste the exact key value from your provider console. Keys are never shown in full after save." />
                        </div>
                        <Input
                          value={newCredentialKey}
                          onChange={(e) => setNewCredentialKey(e.target.value)}
                          placeholder={API_KEY_PLACEHOLDERS[provider] || "sk-..."}
                          type="password"
                          name="api-key-secret"
                          autoComplete="one-time-code"
                          data-1p-ignore
                          data-lpignore="true"
                          data-form-type="other"
                        />
                        <p className="text-[10px] text-muted-foreground mt-1">
                          Your {provider} API key from{" "}
                          {provider === "openai" && <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">platform.openai.com</a>}
                          {provider === "anthropic" && <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">console.anthropic.com</a>}
                          {provider === "google" && <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">aistudio.google.com</a>}
                        </p>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleCreateCredential}
                        disabled={isCreatingCredential || !newCredentialName.trim() || !newCredentialKey.trim()}
                        className="w-full"
                      >
                        {isCreatingCredential ? <Spinner size="xs" className="mr-2" /> : null}
                        Save API key
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Launch Card */}
              <Card className={`border-border/50 bg-card/60 ${hasTemplate && hasCredential ? "border-primary/30" : ""}`}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">3. Launch the run</CardTitle>
                    <a
                      href={ONBOARDING_DOC_LINKS.troubleshooting}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                    >
                      Learn more
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  {runRemediation && (
                    <Alert variant="destructive" data-testid="run-remediation-alert">
                      <AlertTitle>{runRemediation.title}</AlertTitle>
                      <AlertDescription>
                        <p className="mt-1">{runRemediation.summary}</p>
                        <ul className="mt-2 list-disc space-y-1 pl-4 text-xs">
                          {runRemediation.steps.map((step) => (
                            <li key={step}>{step}</li>
                          ))}
                        </ul>
                        <a
                          href={runRemediation.docsUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                        >
                          View remediation guide
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      </AlertDescription>
                    </Alert>
                  )}

                  <div>
                    <div className="mb-1 flex items-center gap-1">
                      <label className="text-xs text-muted-foreground">Graph name</label>
                      <HelpTip
                        testId="graph-name-help-tip"
                        text="This name is used for the cloned graph created from the selected template."
                      />
                    </div>
                    <Input
                      value={graphName}
                      onChange={(e) => setGraphName(e.target.value)}
                      placeholder="Demo graph"
                    />
                  </div>
                  {selectedTemplate ? (
                    <div
                      data-testid="template-preview-panel"
                      className="rounded-xl border border-border/50 bg-muted/30 px-3 py-3 text-sm space-y-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="font-semibold">{selectedQuickStart?.title ?? selectedTemplate.name}</div>
                          <div className="text-xs text-muted-foreground">{selectedTemplate.description}</div>
                        </div>
                        {selectedTemplatePreview ? (
                          <div className="flex items-center gap-1">
                            <Badge variant="outline">{selectedTemplatePreview.versionLabel}</Badge>
                            {selectedTemplate.is_latest && (
                              <Badge variant="secondary" className="text-[10px]">
                                latest
                              </Badge>
                            )}
                          </div>
                        ) : null}
                      </div>

                      {selectedTemplatePreview && (
                        <div className="space-y-2 text-xs">
                          <div>
                            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                              Template metadata
                            </div>
                            {selectedTemplatePreview.versionNote ? (
                              <p className="mt-1 text-muted-foreground">{selectedTemplatePreview.versionNote}</p>
                            ) : (
                              <p className="mt-1 text-muted-foreground">No changelog provided for this version.</p>
                            )}
                          </div>

                          <div>
                            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                              Expected output
                            </div>
                            <p className="mt-1 text-muted-foreground">{selectedTemplatePreview.expectedOutput}</p>
                          </div>

                          <div>
                            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                              Required credentials
                            </div>
                            <div className="mt-1 grid gap-1">
                              {selectedTemplatePreview.requiredCredentials.map((requiredCredential) => (
                                <div
                                  key={`${selectedTemplate.id}-${requiredCredential.provider}`}
                                  className="flex items-center justify-between rounded-md border border-border/50 bg-background/60 px-2 py-1"
                                >
                                  <span className="font-medium text-foreground">
                                    {requiredCredential.label}
                                  </span>
                                  <span
                                    className={
                                      requiredCredential.connected
                                        ? "text-green-600 dark:text-green-400"
                                        : "text-amber-600 dark:text-amber-400"
                                    }
                                  >
                                    {requiredCredential.connected
                                      ? "Connected"
                                      : `Missing (${requiredCredential.placeholder})`}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>

                          {selectedTemplatePreview.placeholderVariables.length > 0 && (
                            <div>
                              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                                Boilerplate placeholders
                              </div>
                              <div className="mt-1 flex flex-wrap gap-1">
                                {selectedTemplatePreview.placeholderVariables.map((placeholder) => (
                                  <span
                                    key={`${selectedTemplate.id}-${placeholder}`}
                                    className="rounded-full border border-border/70 bg-background/70 px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
                                  >
                                    {placeholder}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="rounded-xl border border-dashed border-border/50 bg-muted/20 px-3 py-4 text-sm text-muted-foreground text-center">
                      Select a template to continue
                    </div>
                  )}

                  <div className="rounded-xl border border-border/50 bg-muted/20 px-3 py-3 text-sm space-y-2">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-1">
                          <div className="text-xs font-medium text-foreground">Sample data mode</div>
                          <HelpTip
                            testId="sample-data-help-tip"
                            text="Enable for a safe first run with template-provided input. Disable to supply custom JSON."
                          />
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          Use the template&apos;s sample input for a sandboxed run.
                        </div>
                      </div>
                      <Switch checked={useSampleData} onCheckedChange={setUseSampleData} />
                    </div>
                    {!useSampleData && (
                      <div className="space-y-1">
                        <div className="flex items-center gap-1">
                          <div className="text-[11px] text-muted-foreground">Custom input (JSON)</div>
                          <HelpTip
                            testId="custom-input-help-tip"
                            text={"Input must be a valid JSON object. Example: {\"message\":\"hello\"}"}
                          />
                        </div>
                        <Textarea
                          value={customInput}
                          onChange={(e) => setCustomInput(e.target.value)}
                          rows={6}
                          className="text-xs"
                        />
                      </div>
                    )}
                  </div>
                  <Button
                    onClick={handleRun}
                    disabled={!selectedTemplate || isRunning}
                    className="w-full"
                  >
                    {isRunning ? <Spinner size="xs" className="mr-2" /> : null}
                    Create & run
                  </Button>

                  {/* Completion checklist */}
                  <div className="space-y-2 pt-2 text-xs text-muted-foreground">
                    <div
                      data-testid="onboarding-checklist-progress"
                      className="rounded-lg border border-border/50 bg-muted/30 px-2.5 py-2"
                    >
                      <div className="flex items-center justify-between text-[11px]">
                        <span>Checklist progress</span>
                        <span data-testid="onboarding-checklist-progress-label">
                          {checklistProgress.completed}/{checklistProgress.total} ({checklistProgress.percentage}%)
                        </span>
                      </div>
                      <div className="mt-2 h-1.5 w-full rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-primary transition-[width]"
                          style={{ width: `${checklistProgress.percentage}%` }}
                        />
                      </div>
                    </div>
                    {checklist.map((item) => (
                      <div
                        key={item.key}
                        className={`flex items-center gap-2 ${item.completed ? "text-green-600 dark:text-green-400" : ""}`}
                      >
                        <span>{item.completed ? "✓" : "○"}</span>
                        <span>{item.label}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
