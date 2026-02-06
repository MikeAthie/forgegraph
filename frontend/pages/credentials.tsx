import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { useRouter } from "next/router";
import { Plus, RefreshCw } from "lucide-react";

import DashboardLayout from "../components/DashboardLayout";
import ProtectedRoute from "../components/ProtectedRoute";
import { useAuth } from "../contexts/AuthContext";
import {
  credentialsApi,
  type CredentialOAuthProviderStatus,
  getApiErrorMessage,
  type Credential,
  type CredentialCreateInput,
  type OAuthIntegrationProvider,
} from "../lib/api";
import { showError, showSuccess } from "../lib/toast";
import { ERROR_FALLBACKS } from "../lib/error-messages";
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
  Switch,
} from "@/components/ui";

const PROVIDERS: { value: CredentialCreateInput["provider"]; label: string }[] = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "google", label: "Google AI" },
  { value: "gmail", label: "Gmail" },
  { value: "google_calendar", label: "Google Calendar" },
  { value: "google_tasks", label: "Google Tasks" },
  { value: "notion", label: "Notion" },
  { value: "slack", label: "Slack" },
  { value: "jira", label: "Jira" },
  { value: "linear", label: "Linear" },
  { value: "hubspot", label: "HubSpot" },
  { value: "google_drive", label: "Google Drive" },
  { value: "telegram", label: "Telegram" },
  { value: "twilio", label: "Twilio" },
];

const OAUTH_PROVIDERS: OAuthIntegrationProvider[] = [
  "gmail",
  "google_calendar",
  "google_tasks",
  "notion",
  "slack",
  "jira",
  "linear",
  "hubspot",
  "google_drive",
];

type OAuthProviderConfigForm = {
  client_id: string;
  client_secret: string;
  authorize_url: string;
  token_url: string;
  redirect_uri: string;
  scopes: string;
  enabled: boolean;
};

const formatDateTime = (isoString: string) => {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return isoString;
  }
  return date.toLocaleString();
};

const getProviderLabel = (provider: string) => {
  return PROVIDERS.find((p) => p.value === provider)?.label ?? provider;
};

const isOAuthProvider = (provider: string): provider is OAuthIntegrationProvider => {
  return OAUTH_PROVIDERS.includes(provider as OAuthIntegrationProvider);
};

export default function CredentialsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const canManageCredentials =
    user?.organization_role === "owner" || user?.organization_role === "admin";

  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [oauthProviders, setOauthProviders] = useState<CredentialOAuthProviderStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [oauthStartingProvider, setOauthStartingProvider] = useState<OAuthIntegrationProvider | null>(null);
  const [oauthConfigProvider, setOauthConfigProvider] = useState<OAuthIntegrationProvider | null>(null);
  const [oauthConfigOpen, setOauthConfigOpen] = useState(false);
  const [oauthConfigSaving, setOauthConfigSaving] = useState(false);
  const [providerPrefillApplied, setProviderPrefillApplied] = useState(false);
  const [oauthConfigForm, setOauthConfigForm] = useState<OAuthProviderConfigForm>({
    client_id: "",
    client_secret: "",
    authorize_url: "",
    token_url: "",
    redirect_uri: "",
    scopes: "",
    enabled: true,
  });

  const [formState, setFormState] = useState<CredentialCreateInput>({
    provider: "openai",
    name: "",
    api_key: "",
  });

  const fetchCredentials = useCallback(
    async (opts?: { silent?: boolean }) => {
      const silent = opts?.silent ?? false;
      if (!silent) {
        setLoading(true);
      } else {
        setIsRefreshing(true);
      }
      setError(null);

      try {
        const [credentialsData, oauthProviderData] = await Promise.all([
          credentialsApi.list(),
          canManageCredentials ? credentialsApi.listOAuthProviders() : Promise.resolve([]),
        ]);
        setCredentials(credentialsData);
        setOauthProviders(oauthProviderData);
      } catch (err: unknown) {
        setError(getApiErrorMessage(err, "Failed to load credentials."));
      } finally {
        if (!silent) {
          setLoading(false);
        }
        setIsRefreshing(false);
      }
    },
    [canManageCredentials],
  );

  useEffect(() => {
    void fetchCredentials();
  }, [fetchCredentials]);

  useEffect(() => {
    if (providerPrefillApplied || !router.isReady) return;

    const providerQuery = router.query.provider;
    const provider = Array.isArray(providerQuery) ? providerQuery[0] : providerQuery;
    if (!provider) {
      setProviderPrefillApplied(true);
      return;
    }

    const normalizedProvider = provider.toLowerCase();
    const providerOption = PROVIDERS.find((item) => item.value === normalizedProvider);
    if (!providerOption) {
      setProviderPrefillApplied(true);
      return;
    }

    setProviderPrefillApplied(true);
    if (isOAuthProvider(normalizedProvider)) {
      setOauthConfigProvider(normalizedProvider);
      setOauthConfigForm({
        client_id: "",
        client_secret: "",
        authorize_url: "",
        token_url: "",
        redirect_uri: "",
        scopes: "",
        enabled: true,
      });
      setOauthConfigOpen(true);
      return;
    }

    setFormState((prev) => ({
      ...prev,
      provider: providerOption.value,
      name: prev.name || `${providerOption.label} Credential`,
    }));
    setIsDialogOpen(true);
  }, [providerPrefillApplied, router.isReady, router.query.provider]);

  const resetForm = () => {
    setFormState({
      provider: "openai",
      name: "",
      api_key: "",
    });
  };

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isSubmitting) return;
    if (!canManageCredentials) {
      showError("Only organization admins can add credentials.");
      return;
    }

    setIsSubmitting(true);
    try {
      const created = await credentialsApi.create(formState);
      setCredentials((prev) => [created, ...prev]);
      showSuccess("Credential saved.");
      resetForm();
      setIsDialogOpen(false);
    } catch (err: unknown) {
      showError("Credential failed", getApiErrorMessage(err, ERROR_FALLBACKS.credential.create));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (credentialId: string) => {
    if (!canManageCredentials) {
      showError("Only organization admins can delete credentials.");
      return;
    }
    try {
      await credentialsApi.delete(credentialId);
      setCredentials((prev) => prev.filter((item) => item.id !== credentialId));
      showSuccess("Credential deleted.");
    } catch (err: unknown) {
      showError("Delete failed", getApiErrorMessage(err, ERROR_FALLBACKS.credential.delete));
    }
  };

  const hasCredentials = credentials.length > 0;

  const handleStartOAuth = useCallback(
    async (provider: OAuthIntegrationProvider) => {
      if (!canManageCredentials) {
        showError("Only organization admins can connect OAuth credentials.");
        return;
      }
      setOauthStartingProvider(provider);
      try {
        const response = await credentialsApi.startOAuth(provider);
        window.location.href = response.authorize_url;
      } catch (err: unknown) {
        showError(getApiErrorMessage(err, `Failed to start ${provider} OAuth setup.`));
      } finally {
        setOauthStartingProvider(null);
      }
    },
    [canManageCredentials],
  );

  const oauthProvidersByName = useMemo(() => {
    const map = new Map<OAuthIntegrationProvider, CredentialOAuthProviderStatus>();
    for (const provider of oauthProviders) {
      map.set(provider.provider, provider);
    }
    return map;
  }, [oauthProviders]);

  const openOAuthConfig = useCallback(
    (provider: OAuthIntegrationProvider) => {
      const status = oauthProvidersByName.get(provider);
      setOauthConfigProvider(provider);
      setOauthConfigForm({
        client_id: status?.client_id ?? "",
        client_secret: "",
        authorize_url: status?.authorize_url ?? "",
        token_url: status?.token_url ?? "",
        redirect_uri: status?.redirect_uri ?? "",
        scopes: (status?.scopes ?? []).join(" "),
        enabled: status?.enabled ?? true,
      });
      setOauthConfigOpen(true);
    },
    [oauthProvidersByName],
  );

  const handleSaveOAuthConfig = useCallback(async () => {
    if (!oauthConfigProvider) return;
    setOauthConfigSaving(true);
    try {
      await credentialsApi.upsertOAuthProviderConfig(oauthConfigProvider, {
        client_id: oauthConfigForm.client_id.trim(),
        client_secret: oauthConfigForm.client_secret.trim() || undefined,
        authorize_url: oauthConfigForm.authorize_url.trim(),
        token_url: oauthConfigForm.token_url.trim(),
        redirect_uri: oauthConfigForm.redirect_uri.trim(),
        scopes: oauthConfigForm.scopes
          .split(/\s+/)
          .map((item) => item.trim())
          .filter(Boolean),
        enabled: oauthConfigForm.enabled,
      });
      showSuccess(`${getProviderLabel(oauthConfigProvider)} OAuth config saved.`);
      setOauthConfigOpen(false);
      await fetchCredentials({ silent: true });
    } catch (err: unknown) {
      showError(getApiErrorMessage(err, "Failed to save OAuth provider config."));
    } finally {
      setOauthConfigSaving(false);
    }
  }, [fetchCredentials, oauthConfigForm, oauthConfigProvider]);

  const providerSummary = useMemo(() => {
    const counts = credentials.reduce<Record<string, number>>((acc, item) => {
      acc[item.provider] = (acc[item.provider] ?? 0) + 1;
      return acc;
    }, {});
    return Object.entries(counts).map(([provider, count]) => ({
      provider,
      count,
    }));
  }, [credentials]);

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h1 className="text-2xl font-semibold text-foreground">Credentials</h1>
              <p className="text-sm text-muted-foreground">
                Securely store provider keys for multi-model execution. Keys are encrypted and never shown in full.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={() => void fetchCredentials({ silent: true })}>
                {isRefreshing ? <Spinner className="mr-2 h-4 w-4" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                Refresh
              </Button>
              <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
                <Button onClick={() => setIsDialogOpen(true)} disabled={!canManageCredentials}>
                  <Plus className="mr-2 h-4 w-4" />
                  Add credential
                </Button>
                <DialogContent>
                  <form onSubmit={handleCreate} className="space-y-4">
                    <DialogHeader>
                      <DialogTitle>Add provider credential</DialogTitle>
                      <DialogDescription>
                        Store a provider API key for use in prompt nodes. The key is encrypted at rest.
                      </DialogDescription>
                    </DialogHeader>

                    <FormField label="Provider" htmlFor="provider">
                      <Select
                        value={formState.provider}
                        onValueChange={(value) =>
                          setFormState((prev) => ({
                            ...prev,
                            provider: value as CredentialCreateInput["provider"],
                          }))
                        }
                      >
                        <SelectTrigger id="provider">
                          <SelectValue placeholder="Select provider" />
                        </SelectTrigger>
                        <SelectContent>
                          {PROVIDERS.map((provider) => (
                            <SelectItem key={provider.value} value={provider.value}>
                              {provider.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </FormField>

                    <FormField label="Name" htmlFor="name" description="Friendly name to identify this key.">
                      <Input
                        id="name"
                        value={formState.name}
                        onChange={(event) => setFormState((prev) => ({ ...prev, name: event.target.value }))}
                        placeholder="Production OpenAI"
                        required
                      />
                    </FormField>

                    <FormField
                      label="API key"
                      htmlFor="api_key"
                      description="Stored securely. You will only see the last 4 characters later."
                    >
                      <Input
                        id="api_key"
                        type="password"
                        value={formState.api_key}
                        onChange={(event) => setFormState((prev) => ({ ...prev, api_key: event.target.value }))}
                        placeholder="sk-..."
                        required
                      />
                    </FormField>

                    <DialogFooter className="gap-2">
                      <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>
                        Cancel
                      </Button>
                      <Button type="submit" disabled={isSubmitting}>
                        {isSubmitting ? <Spinner className="mr-2 h-4 w-4" /> : null}
                        Save credential
                      </Button>
                    </DialogFooter>
                  </form>
                </DialogContent>
              </Dialog>
            </div>
          </div>

          {providerSummary.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {providerSummary.map((item) => (
                <Badge key={item.provider} variant="outline">
                  {getProviderLabel(item.provider)}: {item.count}
                </Badge>
              ))}
            </div>
          )}

          <Card>
          <CardHeader>
            <CardTitle>OAuth wizard integrations</CardTitle>
            <p className="text-sm text-muted-foreground">
                Connect Gmail, Google Calendar, Google Tasks, Notion, Slack, Jira, Linear, HubSpot,
                and Google Drive via OAuth. Use API key credentials for Telegram and Twilio.
              </p>
          </CardHeader>
            <CardContent className="space-y-3">
              {OAUTH_PROVIDERS.map((provider) => {
                const status = oauthProvidersByName.get(provider);
                const label = getProviderLabel(provider);
                const configured = Boolean(status?.configured);
                return (
                  <div key={provider} className="rounded-lg border border-border p-3">
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-1">
                        <p className="text-sm font-medium">{label}</p>
                        {!status ? (
                          <p className="text-xs text-muted-foreground">Provider status unavailable.</p>
                        ) : configured ? (
                          <p className="text-xs text-muted-foreground">
                            Configured. Redirect URI: {status.redirect_uri ?? "not set"}
                          </p>
                        ) : (
                          <p className="text-xs text-destructive">
                            Missing config fields: {status.missing_config_fields.join(", ")}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => openOAuthConfig(provider)}
                          disabled={!canManageCredentials}
                        >
                          Configure
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => void handleStartOAuth(provider)}
                          disabled={oauthStartingProvider === provider || !configured || !canManageCredentials}
                        >
                          {oauthStartingProvider === provider ? (
                            <>
                              <Spinner className="mr-2 h-4 w-4" />
                              Connecting...
                            </>
                          ) : (
                            "Connect"
                          )}
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          <Dialog open={oauthConfigOpen} onOpenChange={setOauthConfigOpen}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>
                  Configure {oauthConfigProvider ? getProviderLabel(oauthConfigProvider) : "OAuth"} provider
                </DialogTitle>
                <DialogDescription>
                  Store your OAuth app credentials for this organization. Client secret is encrypted at rest.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-3">
                <FormField label="Client ID" htmlFor="oauth-client-id">
                  <Input
                    id="oauth-client-id"
                    value={oauthConfigForm.client_id}
                    onChange={(event) =>
                      setOauthConfigForm((prev) => ({ ...prev, client_id: event.target.value }))
                    }
                    placeholder="client-id"
                  />
                </FormField>
                <FormField
                  label="Client secret"
                  htmlFor="oauth-client-secret"
                  description="Leave empty to keep existing secret."
                >
                  <Input
                    id="oauth-client-secret"
                    type="password"
                    value={oauthConfigForm.client_secret}
                    onChange={(event) =>
                      setOauthConfigForm((prev) => ({ ...prev, client_secret: event.target.value }))
                    }
                    placeholder="client-secret"
                  />
                </FormField>
                <FormField label="Authorize URL" htmlFor="oauth-authorize-url">
                  <Input
                    id="oauth-authorize-url"
                    value={oauthConfigForm.authorize_url}
                    onChange={(event) =>
                      setOauthConfigForm((prev) => ({ ...prev, authorize_url: event.target.value }))
                    }
                    placeholder="https://provider.example.com/oauth/authorize"
                  />
                </FormField>
                <FormField label="Token URL" htmlFor="oauth-token-url">
                  <Input
                    id="oauth-token-url"
                    value={oauthConfigForm.token_url}
                    onChange={(event) =>
                      setOauthConfigForm((prev) => ({ ...prev, token_url: event.target.value }))
                    }
                    placeholder="https://provider.example.com/oauth/token"
                  />
                </FormField>
                <FormField label="Redirect URI" htmlFor="oauth-redirect-uri">
                  <Input
                    id="oauth-redirect-uri"
                    value={oauthConfigForm.redirect_uri}
                    onChange={(event) =>
                      setOauthConfigForm((prev) => ({ ...prev, redirect_uri: event.target.value }))
                    }
                    placeholder="https://app.example.com/oauth/callback"
                  />
                </FormField>
                <FormField label="Scopes" htmlFor="oauth-scopes" description="Space-separated scopes">
                  <Input
                    id="oauth-scopes"
                    value={oauthConfigForm.scopes}
                    onChange={(event) =>
                      setOauthConfigForm((prev) => ({ ...prev, scopes: event.target.value }))
                    }
                    placeholder="scope1 scope2"
                  />
                </FormField>
                <div className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                  <p className="text-sm text-muted-foreground">Provider enabled</p>
                  <Switch
                    checked={oauthConfigForm.enabled}
                    onCheckedChange={(checked) =>
                      setOauthConfigForm((prev) => ({ ...prev, enabled: Boolean(checked) }))
                    }
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setOauthConfigOpen(false)}>
                  Cancel
                </Button>
                <Button onClick={() => void handleSaveOAuthConfig()} disabled={oauthConfigSaving}>
                  {oauthConfigSaving ? (
                    <>
                      <Spinner className="mr-2 h-4 w-4" />
                      Saving...
                    </>
                  ) : (
                    "Save config"
                  )}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          {!canManageCredentials && (
            <Alert>
              <AlertDescription>
                Only organization admins can create or delete credentials. You can still view existing keys.
              </AlertDescription>
            </Alert>
          )}

          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Spinner className="h-5 w-5" />
              Loading credentials...
            </div>
          ) : !hasCredentials ? (
            <EmptyState
              title="No credentials yet"
              description="Add a provider key to unlock multi-model prompt nodes."
              action={
                canManageCredentials ? (
                  <Button onClick={() => setIsDialogOpen(true)}>
                    <Plus className="mr-2 h-4 w-4" />
                    Add credential
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {credentials.map((credential) => {
                const oauthProvider = isOAuthProvider(credential.provider)
                  ? credential.provider
                  : null;
                return (
                <Card key={credential.id}>
                  <CardHeader className="flex flex-row items-start justify-between">
                    <div>
                      <CardTitle className="text-base">{credential.name}</CardTitle>
                      <p className="text-sm text-muted-foreground">{getProviderLabel(credential.provider)}</p>
                    </div>
                    {canManageCredentials ? (
                      <ConfirmButton
                        variant="destructive"
                        size="sm"
                        title="Delete credential?"
                        description="This will remove the key and any runs using it will fail until replaced."
                        onConfirm={() => handleDelete(credential.id)}
                      >
                        Delete
                      </ConfirmButton>
                    ) : (
                      <Badge variant="outline">Read only</Badge>
                    )}
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {credential.health_status !== "healthy" && (
                      <Badge variant="outline">
                        {credential.health_status === "expired" ? "OAuth expired" : "OAuth expiring soon"}
                      </Badge>
                    )}
                    {credential.health_message && (
                      <div className="text-xs text-muted-foreground">{credential.health_message}</div>
                    )}
                    {credential.requires_reauth &&
                      canManageCredentials &&
                      oauthProvider && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void handleStartOAuth(oauthProvider)}
                          disabled={oauthStartingProvider === oauthProvider}
                        >
                          {oauthStartingProvider === oauthProvider ? (
                            <>
                              <Spinner className="mr-2 h-4 w-4" />
                              Reconnecting...
                            </>
                          ) : (
                            "Reconnect OAuth"
                          )}
                        </Button>
                      )}
                    <div className="text-sm text-muted-foreground">Key hint</div>
                    <div className="font-mono text-sm">{credential.key_hint}</div>
                    {credential.token_expires_at && (
                      <div className="text-xs text-muted-foreground">
                        Expires {formatDateTime(credential.token_expires_at)}
                      </div>
                    )}
                    <div className="text-xs text-muted-foreground">Created {formatDateTime(credential.created_at)}</div>
                  </CardContent>
                </Card>
                );
              })}
            </div>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
