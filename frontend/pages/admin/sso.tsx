import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";

import { useAuth } from "../../contexts/AuthContext";
import { scimApi, ssoApi, type ScimTokenInfo, type SsoProviderConfig } from "../../lib/api";
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
  FormField,
  Input,
  Spinner,
} from "@/components/ui";

const defaultConfig: SsoProviderConfig = {
  issuer_url: "",
  client_id: "",
  audience: "",
  email_domains: [],
  default_role: "member",
  enabled: false,
};

export default function AdminSsoPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [config, setConfig] = useState<SsoProviderConfig>(defaultConfig);
  const [clientSecret, setClientSecret] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [tokenInfo, setTokenInfo] = useState<ScimTokenInfo | null>(null);
  const [rotating, setRotating] = useState(false);
  const [newToken, setNewToken] = useState<string | null>(null);

  const canManage = user?.organization_role === "owner" || user?.organization_role === "admin";

  const domainsInput = useMemo(() => config.email_domains.join(", "), [config.email_domains]);

  useEffect(() => {
    if (!canManage) {
      return;
    }

    const load = async () => {
      try {
        const [provider, token] = await Promise.all([ssoApi.getProvider(), scimApi.getTokenInfo()]);
        setConfig(provider);
        setTokenInfo(token);
      } catch (err: any) {
        setError(err?.response?.data?.error?.message || "Failed to load SSO settings.");
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, [canManage]);

  const handleSave = async () => {
    setError(null);
    setSuccess(null);
    setSaving(true);
    try {
      const payload = {
        ...config,
        client_secret: clientSecret || undefined,
        email_domains: config.email_domains,
      };
      const updated = await ssoApi.updateProvider(payload);
      setConfig(updated);
      setClientSecret("");
      setSuccess("SSO settings updated.");
    } catch (err: any) {
      setError(err?.response?.data?.error?.message || "Failed to update SSO settings.");
    } finally {
      setSaving(false);
    }
  };

  const handleRotateToken = async () => {
    setError(null);
    setSuccess(null);
    setRotating(true);
    try {
      const token = await scimApi.rotateToken();
      setNewToken(token);
      const info = await scimApi.getTokenInfo();
      setTokenInfo(info);
    } catch (err: any) {
      setError(err?.response?.data?.error?.message || "Failed to rotate SCIM token.");
    } finally {
      setRotating(false);
    }
  };

  if (!canManage) {
    return (
      <div className="mx-auto max-w-2xl p-8">
        <Alert variant="destructive">
          <AlertDescription>You do not have access to manage SSO settings.</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-[70vh] items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-8">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">SSO & SCIM</h1>
        <p className="text-sm text-muted-foreground">
          Configure Auth0 SSO and manage SCIM provisioning tokens.
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {success && (
        <Alert className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600">
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Auth0 Provider</CardTitle>
          <CardDescription>Connect an Auth0 OIDC application for this organization.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <FormField label="Issuer URL" required htmlFor="issuer_url">
            <Input
              id="issuer_url"
              value={config.issuer_url}
              onChange={(e) => setConfig({ ...config, issuer_url: e.target.value })}
              placeholder="https://your-tenant.us.auth0.com"
            />
          </FormField>

          <FormField label="Client ID" required htmlFor="client_id">
            <Input
              id="client_id"
              value={config.client_id}
              onChange={(e) => setConfig({ ...config, client_id: e.target.value })}
              placeholder="Auth0 client ID"
            />
          </FormField>

          <FormField label="Client Secret" htmlFor="client_secret">
            <Input
              id="client_secret"
              type="password"
              value={clientSecret}
              onChange={(e) => setClientSecret(e.target.value)}
              placeholder="Leave blank to keep existing secret"
            />
          </FormField>

          <FormField label="Audience (optional)" htmlFor="audience">
            <Input
              id="audience"
              value={config.audience}
              onChange={(e) => setConfig({ ...config, audience: e.target.value })}
              placeholder="https://api.your-domain.com"
            />
          </FormField>

          <FormField label="Allowed Email Domains" htmlFor="email_domains">
            <Input
              id="email_domains"
              value={domainsInput}
              onChange={(e) =>
                setConfig({
                  ...config,
                  email_domains: e.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                })
              }
              placeholder="example.com, acme.co"
            />
          </FormField>

          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-foreground">Default Role</label>
            <select
              value={config.default_role}
              onChange={(e) =>
                setConfig({ ...config, default_role: e.target.value as SsoProviderConfig["default_role"] })
              }
              className="h-11 rounded-md border border-border bg-background px-3 text-sm"
            >
              <option value="owner">Owner</option>
              <option value="admin">Admin</option>
              <option value="member">Member</option>
              <option value="viewer">Viewer</option>
            </select>
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border px-3 py-3">
            <div>
              <p className="text-sm font-medium text-foreground">SSO Enabled</p>
              <p className="text-xs text-muted-foreground">
                Turn off to temporarily disable SSO login for this tenant.
              </p>
            </div>
            <Button
              variant={config.enabled ? "secondary" : "outline"}
              onClick={() => setConfig({ ...config, enabled: !config.enabled })}
            >
              {config.enabled ? "Enabled" : "Disabled"}
            </Button>
          </div>

          <div className="flex justify-end">
            <Button onClick={handleSave} disabled={saving}>
              {saving ? (
                <>
                  <Spinner size="xs" className="mr-2" />
                  Saving...
                </>
              ) : (
                "Save Settings"
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>SCIM Provisioning Token</CardTitle>
          <CardDescription>Use this token in Auth0 SCIM configuration.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant="outline">
              {tokenInfo?.token_last4 ? `Token ••••${tokenInfo.token_last4}` : "No token"}
            </Badge>
            {tokenInfo?.last_used_at && (
              <span className="text-xs text-muted-foreground">
                Last used {new Date(tokenInfo.last_used_at).toLocaleString()}
              </span>
            )}
          </div>

          {newToken && (
            <Alert className="border-amber-500/30 bg-amber-500/10 text-amber-700">
              <AlertDescription>
                New SCIM token (copy now): <span className="font-mono">{newToken}</span>
              </AlertDescription>
            </Alert>
          )}

          <div className="flex justify-between gap-3">
            <Button variant="outline" onClick={() => router.push("/admin/organization")}>
              Back to Organization
            </Button>
            <Button onClick={handleRotateToken} disabled={rotating}>
              {rotating ? (
                <>
                  <Spinner size="xs" className="mr-2" />
                  Rotating...
                </>
              ) : (
                "Rotate Token"
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
