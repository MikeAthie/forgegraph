import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { useRouter } from "next/router";
import { CheckCircle2, CircleAlert, Copy, ExternalLink, Plus, RefreshCw } from "lucide-react";

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
  CardDescription,
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
  Separator,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
} from "@/components/ui";

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

const OAUTH_PROVIDER_SET = new Set<string>(OAUTH_PROVIDERS);
const MANUAL_PROVIDERS = PROVIDERS.filter((provider) => !OAUTH_PROVIDER_SET.has(provider.value));

type OAuthConnectionState = "ready" | "needs_reconnect" | "not_connected";

const buildFallbackRedirectUri = () => {
  const browserOrigin = typeof window !== "undefined" ? window.location.origin.replace(/\/$/, "") : "";
  const configuredBase = (process.env.NEXT_PUBLIC_APP_URL ?? "").replace(/\/$/, "");
  const base = browserOrigin || configuredBase || "http://localhost:3000";
  return `${base}/oauth/callback`;
};

const OAUTH_PROVIDER_GUIDANCE: Record<OAuthIntegrationProvider, { scopeHint: string; docsUrl: string }> = {
  gmail: {
    scopeHint: "Use Gmail send + readonly scopes for most templates.",
    docsUrl: "https://developers.google.com/identity/protocols/oauth2",
  },
  google_calendar: {
    scopeHint: "Use Calendar events + readonly scopes.",
    docsUrl: "https://developers.google.com/identity/protocols/oauth2",
  },
  google_tasks: {
    scopeHint: "Use Tasks + Tasks readonly scopes.",
    docsUrl: "https://developers.google.com/identity/protocols/oauth2",
  },
  notion: {
    scopeHint: "Use the scopes required by your Notion workspace actions.",
    docsUrl: "https://developers.notion.com/docs/authorization",
  },
  slack: {
    scopeHint: "chat:write and channels:read are common defaults.",
    docsUrl: "https://api.slack.com/authentication/oauth-v2",
  },
  jira: {
    scopeHint: "Include read/write Jira scopes and offline_access if needed.",
    docsUrl: "https://developer.atlassian.com/cloud/jira/software/oauth-2-3lo-apps/",
  },
  linear: {
    scopeHint: "Use read/write scopes depending on the workflow actions.",
    docsUrl: "https://developers.linear.app/docs/oauth-authentication",
  },
  hubspot: {
    scopeHint: "Add contact read/write scopes for CRM flows.",
    docsUrl: "https://developers.hubspot.com/docs/apps/developer-platform/build-apps/authentication/oauth",
  },
  google_drive: {
    scopeHint: "Use Drive file + metadata scopes.",
    docsUrl: "https://developers.google.com/identity/protocols/oauth2",
  },
};

const formatOAuthServiceMessage = (status: CredentialOAuthProviderStatus) => {
  const missingFields = status.missing_config_fields ?? [];

  if (missingFields.includes("provider_disabled")) {
    return "OAuth for this provider is disabled at the service level.";
  }
  if (missingFields.includes("provider_configuration")) {
    return "Service OAuth configuration is missing. Ask an admin to set provider env variables.";
  }
  if (missingFields.length > 0) {
    return `Service OAuth setup is incomplete (${missingFields.join(", ")}).`;
  }
  return "Service OAuth configuration is ready.";
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
  return OAUTH_PROVIDER_SET.has(provider);
};

export default function CredentialsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const canManageCredentials = user?.organization_role === "owner" || user?.organization_role === "admin";

  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [oauthProviders, setOauthProviders] = useState<CredentialOAuthProviderStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [oauthStartingProvider, setOauthStartingProvider] = useState<OAuthIntegrationProvider | null>(null);
  const [providerPrefillApplied, setProviderPrefillApplied] = useState(false);

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
      showSuccess(`Select ${providerOption.label} and click Connect account in OAuth integrations.`);
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

  const handleCopyText = useCallback(async (label: string, value: string) => {
    const trimmed = value.trim();
    if (!trimmed) {
      showError(`${label} is empty.`);
      return;
    }
    try {
      await navigator.clipboard.writeText(trimmed);
      showSuccess(`${label} copied.`);
    } catch {
      showError(`Could not copy ${label.toLowerCase()}.`);
    }
  }, []);

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

  const latestOauthCredentialByProvider = useMemo(() => {
    const map = new Map<OAuthIntegrationProvider, Credential>();
    for (const provider of OAUTH_PROVIDERS) {
      const latest = credentials
        .filter((credential) => credential.provider === provider && credential.is_oauth_connection)
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0];
      if (latest) {
        map.set(provider, latest);
      }
    }
    return map;
  }, [credentials]);

  const oauthConnectionStateByProvider = useMemo(() => {
    const map = new Map<OAuthIntegrationProvider, OAuthConnectionState>();
    for (const provider of OAUTH_PROVIDERS) {
      const latest = latestOauthCredentialByProvider.get(provider);
      if (!latest) {
        map.set(provider, "not_connected");
        continue;
      }

      const needsReconnect = latest.health_status === "revoked" || latest.health_status === "expired";
      map.set(provider, needsReconnect ? "needs_reconnect" : "ready");
    }
    return map;
  }, [latestOauthCredentialByProvider]);

  const oauthChecklist = useMemo(() => {
    const total = OAUTH_PROVIDERS.length;
    const serviceConfiguredCount = OAUTH_PROVIDERS.filter(
      (provider) => oauthProvidersByName.get(provider)?.configured,
    ).length;
    const connectedCount = OAUTH_PROVIDERS.filter(
      (provider) => oauthConnectionStateByProvider.get(provider) === "ready",
    ).length;
    const fallbackRedirectUri = buildFallbackRedirectUri();
    const configuredRedirectUri =
      OAUTH_PROVIDERS.map((provider) => oauthProvidersByName.get(provider)?.redirect_uri).find(
        (value): value is string => Boolean(value),
      ) ?? fallbackRedirectUri;

    return {
      total,
      serviceConfiguredCount,
      connectedCount,
      remainingConnections: total - connectedCount,
      redirectUri: configuredRedirectUri,
    };
  }, [oauthConnectionStateByProvider, oauthProvidersByName]);

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
                        Store API keys for non-OAuth providers used in prompt nodes. OAuth providers connect below.
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
                          {MANUAL_PROVIDERS.map((provider) => (
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
              <CardTitle>OAuth integrations</CardTitle>
              <CardDescription>
                OAuth apps are configured at service level via environment variables. From this page, you only connect
                and reconnect accounts.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="rounded-xl border border-border bg-muted/30 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-2">
                    <p className="text-sm font-medium">Connection checklist</p>
                    <p className="text-xs text-muted-foreground">
                      Connected {oauthChecklist.connectedCount} of {oauthChecklist.total} providers.
                    </p>
                  </div>
                  <Badge variant={oauthChecklist.remainingConnections === 0 ? "default" : "outline"}>
                    {oauthChecklist.remainingConnections === 0
                      ? "All connected"
                      : `${oauthChecklist.remainingConnections} remaining`}
                  </Badge>
                </div>
                <Separator className="my-3" />
                <div className="space-y-2 text-xs text-muted-foreground">
                  <p>
                    1. Service OAuth config ready: {oauthChecklist.serviceConfiguredCount} / {oauthChecklist.total}.
                  </p>
                  <p>2. Connect account for each provider you plan to use in your graph.</p>
                  <p>
                    Redirect URI configured in service:
                    <span className="mx-1 font-mono text-foreground">{oauthChecklist.redirectUri}</span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2 text-xs"
                      onClick={() => void handleCopyText("Redirect URI", oauthChecklist.redirectUri)}
                    >
                      <Copy className="mr-1 h-3.5 w-3.5" />
                      Copy
                    </Button>
                  </p>
                </div>
              </div>

              {OAUTH_PROVIDERS.map((provider) => {
                const status = oauthProvidersByName.get(provider);
                const label = getProviderLabel(provider);
                const serviceConfigured = Boolean(status?.configured);
                const connectionState = oauthConnectionStateByProvider.get(provider) ?? "not_connected";
                const guidance = OAUTH_PROVIDER_GUIDANCE[provider];
                const connectButtonLabel =
                  connectionState === "needs_reconnect" ? "Reconnect account" : "Connect account";

                return (
                  <div key={provider} className="rounded-lg border border-border p-3">
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium">{label}</p>
                          {connectionState === "ready" ? (
                            <Badge variant="outline" className="gap-1 text-emerald-600">
                              <CheckCircle2 className="h-3.5 w-3.5" />
                              Ready
                            </Badge>
                          ) : connectionState === "needs_reconnect" ? (
                            <Badge variant="outline" className="gap-1 text-amber-600">
                              <CircleAlert className="h-3.5 w-3.5" />
                              Reconnect needed
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="gap-1 text-amber-600">
                              <CircleAlert className="h-3.5 w-3.5" />
                              Not connected
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {guidance.scopeHint}{" "}
                          <a
                            href={guidance.docsUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 text-primary hover:underline"
                          >
                            OAuth docs
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        </p>
                        {!status ? (
                          <p className="text-xs text-muted-foreground">Provider status unavailable.</p>
                        ) : !serviceConfigured ? (
                          <p className="text-xs text-amber-700 dark:text-amber-400">
                            {formatOAuthServiceMessage(status)}
                          </p>
                        ) : connectionState === "ready" ? (
                          <p className="text-xs text-muted-foreground">
                            Account connected. Click Connect account again to rotate or reconnect.
                          </p>
                        ) : connectionState === "needs_reconnect" ? (
                          <p className="text-xs text-amber-700 dark:text-amber-400">
                            OAuth credential exists but requires reconnection.
                          </p>
                        ) : (
                          <p className="text-xs text-muted-foreground">
                            Service ready. Connect an account to use this provider.
                          </p>
                        )}
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        <Button
                          size="sm"
                          onClick={() => void handleStartOAuth(provider)}
                          disabled={oauthStartingProvider === provider || !serviceConfigured || !canManageCredentials}
                        >
                          {oauthStartingProvider === provider ? (
                            <>
                              <Spinner className="mr-2 h-4 w-4" />
                              Connecting...
                            </>
                          ) : (
                            connectButtonLabel
                          )}
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>

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
                const oauthProvider = isOAuthProvider(credential.provider) ? credential.provider : null;
                const isOAuthCredential = credential.is_oauth_connection;
                const isActiveOAuthCredential =
                  oauthProvider !== null && latestOauthCredentialByProvider.get(oauthProvider)?.id === credential.id;
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
                      {oauthProvider && !isOAuthCredential && <Badge variant="outline">API key only (not OAuth)</Badge>}
                      {oauthProvider && isOAuthCredential && isActiveOAuthCredential && (
                        <Badge variant="outline" className="text-emerald-600">
                          Active OAuth credential
                        </Badge>
                      )}
                      {oauthProvider && isOAuthCredential && !isActiveOAuthCredential && (
                        <Badge variant="outline">Older OAuth credential</Badge>
                      )}
                      {credential.health_status !== "healthy" && (
                        <Badge variant="outline">
                          {credential.health_status === "expired" ? "OAuth expired" : "OAuth expiring soon"}
                        </Badge>
                      )}
                      {credential.health_message && (
                        <div className="text-xs text-muted-foreground">{credential.health_message}</div>
                      )}
                      {credential.requires_reauth && canManageCredentials && oauthProvider && isOAuthCredential && (
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
                      <div className="text-xs text-muted-foreground">
                        Created {formatDateTime(credential.created_at)}
                      </div>
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
