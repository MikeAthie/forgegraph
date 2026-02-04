import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";

import DashboardLayout from "../components/DashboardLayout";
import ProtectedRoute from "../components/ProtectedRoute";
import {
  credentialsApi,
  getApiErrorMessage,
  runsApi,
  templatesApi,
  type Credential,
  type GraphTemplate,
} from "../lib/api";
import { showError, showSuccess } from "../lib/toast";
import {
  Alert,
  AlertDescription,
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
  Spinner,
} from "@/components/ui";

const PROVIDERS = ["openai", "anthropic"] as const;

const MODEL_OPTIONS: Record<string, string[]> = {
  openai: ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
  anthropic: ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
};

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [templates, setTemplates] = useState<GraphTemplate[]>([]);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [graphName, setGraphName] = useState("");
  const [provider, setProvider] = useState<string>("openai");
  const [model, setModel] = useState<string>("gpt-4");
  const [credentialId, setCredentialId] = useState<string>("");

  const [newCredentialName, setNewCredentialName] = useState("");
  const [newCredentialKey, setNewCredentialKey] = useState("");
  const [isCreatingCredential, setIsCreatingCredential] = useState(false);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.id === selectedTemplateId) ?? null,
    [templates, selectedTemplateId],
  );

  const filteredCredentials = useMemo(
    () => credentials.filter((cred) => cred.provider === provider),
    [credentials, provider],
  );

  const availableModels = useMemo(() => MODEL_OPTIONS[provider] ?? [], [provider]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [templatesData, credentialsData] = await Promise.all([
        templatesApi.list(),
        credentialsApi.list(),
      ]);
      setTemplates(templatesData);
      setCredentials(credentialsData);
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
    setCredentialId("");
  }, [provider]);

  const handleCreateCredential = async () => {
    if (!newCredentialName.trim() || !newCredentialKey.trim()) {
      showError("Missing details", "Add a name and API key.");
      return;
    }

    setIsCreatingCredential(true);
    try {
      const created = await credentialsApi.create({
        name: newCredentialName.trim(),
        provider,
        api_key: newCredentialKey.trim(),
      });
      setCredentials((prev) => [created, ...prev]);
      setCredentialId(created.id);
      setNewCredentialName("");
      setNewCredentialKey("");
      showSuccess("Credential added");
    } catch (err: unknown) {
      showError("Credential failed", getApiErrorMessage(err, "Unable to save credential."));
    } finally {
      setIsCreatingCredential(false);
    }
  };

  const handleRun = async () => {
    if (!selectedTemplate || !credentialId) return;
    setIsRunning(true);
    try {
      const clone = await templatesApi.clone(selectedTemplate.id, {
        name: graphName.trim() || undefined,
        provider,
        model,
        credential_id: credentialId,
      });
      const run = await runsApi.start({
        graph_version_id: clone.graph_version_id,
        input_json: selectedTemplate.sample_input || {},
      });
      showSuccess("Run started", "Live execution is now streaming.");
      await router.push(`/runs/${run.id}`);
    } catch (err: unknown) {
      showError("Run failed", getApiErrorMessage(err, "Unable to start demo run."));
    } finally {
      setIsRunning(false);
    }
  };

  const canProceed = useMemo(() => {
    if (step === 0) return Boolean(selectedTemplateId);
    if (step === 1) return Boolean(credentialId);
    return true;
  }, [step, selectedTemplateId, credentialId]);

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
            <>
              <div className="grid gap-4 lg:grid-cols-3">
                <Card className={`border-border/50 bg-card/60 ${step === 0 ? "shadow-lg" : ""}`}>
                  <CardHeader>
                    <CardTitle className="text-base">1. Pick a template</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {templates.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No templates available yet.</p>
                    ) : (
                      templates.map((template) => (
                        <button
                          type="button"
                          key={template.id}
                          onClick={() => {
                            setSelectedTemplateId(template.id);
                            setGraphName(template.name);
                          }}
                          className={`w-full rounded-xl border px-3 py-3 text-left text-sm transition ${
                            selectedTemplateId === template.id
                              ? "border-primary/70 bg-primary/10"
                              : "border-border/50 hover:border-primary/40"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-semibold">{template.name}</span>
                            <Badge variant="secondary">{template.estimated_minutes} min</Badge>
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">{template.description}</p>
                        </button>
                      ))
                    )}
                  </CardContent>
                </Card>

                <Card className={`border-border/50 bg-card/60 ${step === 1 ? "shadow-lg" : ""}`}>
                  <CardHeader>
                    <CardTitle className="text-base">2. Attach credentials</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <label className="text-xs text-muted-foreground">Provider</label>
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
                      <label className="text-xs text-muted-foreground">Model</label>
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

                    {filteredCredentials.length > 0 ? (
                      <div>
                        <label className="text-xs text-muted-foreground">Credential</label>
                        <Select value={credentialId} onValueChange={setCredentialId}>
                          <SelectTrigger>
                            <SelectValue placeholder="Select credential" />
                          </SelectTrigger>
                          <SelectContent>
                            {filteredCredentials.map((cred) => (
                              <SelectItem key={cred.id} value={cred.id}>
                                {cred.name} · ****{cred.key_hint}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    ) : (
                      <div className="rounded-xl border border-border/50 bg-muted/30 p-3 text-xs text-muted-foreground">
                        No {provider} credentials yet. Create one below.
                      </div>
                    )}

                    <div className="space-y-2">
                      <Input
                        value={newCredentialName}
                        onChange={(e) => setNewCredentialName(e.target.value)}
                        placeholder="Credential name"
                      />
                      <Input
                        value={newCredentialKey}
                        onChange={(e) => setNewCredentialKey(e.target.value)}
                        placeholder="API key"
                        type="password"
                      />
                      <Button
                        variant="outline"
                        onClick={handleCreateCredential}
                        disabled={isCreatingCredential}
                      >
                        {isCreatingCredential ? <Spinner size="xs" className="mr-2" /> : null}
                        Save credential
                      </Button>
                    </div>
                  </CardContent>
                </Card>

                <Card className={`border-border/50 bg-card/60 ${step === 2 ? "shadow-lg" : ""}`}>
                  <CardHeader>
                    <CardTitle className="text-base">3. Launch the run</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div>
                      <label className="text-xs text-muted-foreground">Graph name</label>
                      <Input
                        value={graphName}
                        onChange={(e) => setGraphName(e.target.value)}
                        placeholder="Demo graph"
                      />
                    </div>
                    {selectedTemplate ? (
                      <div className="rounded-xl border border-border/50 bg-muted/30 px-3 py-2 text-sm">
                        <div className="font-semibold">{selectedTemplate.name}</div>
                        <div className="text-xs text-muted-foreground">{selectedTemplate.description}</div>
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">Select a template to continue.</p>
                    )}
                    <Button
                      onClick={handleRun}
                      disabled={!selectedTemplate || !credentialId || isRunning}
                    >
                      {isRunning ? <Spinner size="xs" className="mr-2" /> : null}
                      Create & run
                    </Button>
                  </CardContent>
                </Card>
              </div>

              <div className="flex items-center justify-between">
                <div className="text-xs text-muted-foreground">Step {step + 1} of 3</div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setStep((prev) => Math.max(prev - 1, 0))}
                    disabled={step === 0}
                  >
                    Back
                  </Button>
                  <Button
                    onClick={() => setStep((prev) => Math.min(prev + 1, 2))}
                    disabled={!canProceed || step === 2}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
