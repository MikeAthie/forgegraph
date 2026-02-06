import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Plus, RefreshCw } from "lucide-react";

import DashboardLayout from "../components/DashboardLayout";
import ProtectedRoute from "../components/ProtectedRoute";
import { useAuth } from "../contexts/AuthContext";
import {
  credentialsApi,
  getApiErrorMessage,
  type Credential,
  type CredentialCreateInput,
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
} from "@/components/ui";

const PROVIDERS: { value: CredentialCreateInput["provider"]; label: string }[] = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "google", label: "Google AI" },
];

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

export default function CredentialsPage() {
  const { user } = useAuth();
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

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
        const data = await credentialsApi.list();
        setCredentials(data);
      } catch (err: unknown) {
        setError(getApiErrorMessage(err, "Failed to load credentials."));
      } finally {
        if (!silent) {
          setLoading(false);
        }
        setIsRefreshing(false);
      }
    },
    [],
  );

  useEffect(() => {
    void fetchCredentials();
  }, [fetchCredentials]);

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
<<<<<<< Updated upstream
  const canManageCredentials =
    user?.organization_role === "owner" || user?.organization_role === "admin";
=======

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
        showError("OAuth failed", getApiErrorMessage(err, ERROR_FALLBACKS.credential.oauth));
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
      showError("Config failed", getApiErrorMessage(err, ERROR_FALLBACKS.credential.oauth));
    } finally {
      setOauthConfigSaving(false);
    }
  }, [fetchCredentials, oauthConfigForm, oauthConfigProvider]);
>>>>>>> Stashed changes

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
              {credentials.map((credential) => (
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
                    <div className="text-sm text-muted-foreground">Key hint</div>
                    <div className="font-mono text-sm">{credential.key_hint}</div>
                    <div className="text-xs text-muted-foreground">Created {formatDateTime(credential.created_at)}</div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
