import { useMemo, useReducer, useEffect } from "react";
import { useRouter } from "next/router";
import { ArrowRight, ShieldCheck } from "lucide-react";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
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
  status: {
    state: "unavailable",
    message: "No SSO provider is configured for this workspace yet.",
  },
};

type SsoPageState = {
  config: SsoProviderConfig;
  clientSecret: string;
  loading: boolean;
  saving: boolean;
  error: string | null;
  success: string | null;
  tokenInfo: ScimTokenInfo | null;
  rotating: boolean;
  newToken: string | null;
};

type SsoPageAction =
  | { type: "loadSucceeded"; config: SsoProviderConfig; tokenInfo: ScimTokenInfo }
  | { type: "loadFailed"; error: string }
  | { type: "updateConfig"; patch: Partial<SsoProviderConfig> }
  | { type: "setClientSecret"; value: string }
  | { type: "saveStarted" }
  | { type: "saveSucceeded"; config: SsoProviderConfig }
  | { type: "saveFailed"; error: string }
  | { type: "rotateStarted" }
  | { type: "rotateSucceeded"; token: string; tokenInfo: ScimTokenInfo }
  | { type: "rotateFailed"; error: string };

const initialState: SsoPageState = {
  config: defaultConfig,
  clientSecret: "",
  loading: true,
  saving: false,
  error: null,
  success: null,
  tokenInfo: null,
  rotating: false,
  newToken: null,
};

function ssoPageReducer(state: SsoPageState, action: SsoPageAction): SsoPageState {
  switch (action.type) {
    case "loadSucceeded":
      return { ...state, config: action.config, tokenInfo: action.tokenInfo, loading: false, error: null };
    case "loadFailed":
      return { ...state, loading: false, error: action.error };
    case "updateConfig":
      return { ...state, config: { ...state.config, ...action.patch } };
    case "setClientSecret":
      return { ...state, clientSecret: action.value };
    case "saveStarted":
      return { ...state, saving: true, error: null, success: null };
    case "saveSucceeded":
      return {
        ...state,
        config: action.config,
        clientSecret: "",
        saving: false,
        success: "SSO settings updated.",
      };
    case "saveFailed":
      return { ...state, saving: false, error: action.error };
    case "rotateStarted":
      return { ...state, rotating: true, error: null, success: null };
    case "rotateSucceeded":
      return { ...state, rotating: false, newToken: action.token, tokenInfo: action.tokenInfo };
    case "rotateFailed":
      return { ...state, rotating: false, error: action.error };
    default:
      return state;
  }
}

function formatUtcDateTime(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toISOString().replace("T", " ").replace(".000Z", " UTC");
}

function getApiErrorMessage(err: unknown, fallback: string): string {
  return (
    (err as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error?.message ?? fallback
  );
}

export default function AdminSsoPage() {
  const { push } = useRouter();
  const { user } = useAuth();
  const [state, dispatch] = useReducer(ssoPageReducer, initialState);
  const { config, clientSecret, loading, saving, error, success, tokenInfo, rotating, newToken } = state;

  const canManage = user?.organization_role === "owner" || user?.organization_role === "admin";
  const domainsInput = useMemo(() => config.email_domains.join(", "), [config.email_domains]);

  useEffect(() => {
    if (!canManage) {
      return;
    }

    const load = async () => {
      try {
        const [provider, token] = await Promise.all([ssoApi.getProvider(), scimApi.getTokenInfo()]);
        dispatch({ type: "loadSucceeded", config: provider, tokenInfo: token });
      } catch (err) {
        dispatch({ type: "loadFailed", error: getApiErrorMessage(err, "Failed to load SSO settings.") });
      }
    };

    void load();
  }, [canManage]);

  const handleSave = async () => {
    dispatch({ type: "saveStarted" });
    try {
      const updated = await ssoApi.updateProvider({
        ...config,
        client_secret: clientSecret || undefined,
        email_domains: config.email_domains,
      });
      dispatch({ type: "saveSucceeded", config: updated });
    } catch (err) {
      dispatch({ type: "saveFailed", error: getApiErrorMessage(err, "Failed to update SSO settings.") });
    }
  };

  const handleRotateToken = async () => {
    dispatch({ type: "rotateStarted" });
    try {
      const token = await scimApi.rotateToken();
      const info = await scimApi.getTokenInfo();
      dispatch({ type: "rotateSucceeded", token, tokenInfo: info });
    } catch (err) {
      dispatch({ type: "rotateFailed", error: getApiErrorMessage(err, "Failed to rotate SCIM token.") });
    }
  };

  if (!canManage) {
    return <SsoAccessDenied />;
  }

  if (loading) {
    return <SsoLoadingState />;
  }

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
          <SsoPageHeader />
          <SsoFeedback error={error} success={success} />
          <IdentityStatusGrid config={config} tokenInfo={tokenInfo} />
          <SsoTruthAlert onBack={() => push("/admin")} />
          <AuthProviderCard
            config={config}
            clientSecret={clientSecret}
            domainsInput={domainsInput}
            saving={saving}
            onConfigChange={(patch) => dispatch({ type: "updateConfig", patch })}
            onClientSecretChange={(value) => dispatch({ type: "setClientSecret", value })}
            onSave={handleSave}
          />
          <ScimTokenCard
            tokenInfo={tokenInfo}
            newToken={newToken}
            rotating={rotating}
            onBack={() => push("/admin/organization")}
            onRotate={handleRotateToken}
          />
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function SsoAccessDenied() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="mx-auto max-w-2xl p-8">
          <Alert variant="destructive">
            <AlertDescription>You do not have access to manage SSO settings.</AlertDescription>
          </Alert>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function SsoLoadingState() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex h-[70vh] items-center justify-center">
          <Spinner size="lg" />
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function SsoPageHeader() {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-foreground">SSO & SCIM</h1>
      <p className="text-sm text-muted-foreground">
        Review identity readiness before changing provider or provisioning settings.
      </p>
    </div>
  );
}

function SsoFeedback({ error, success }: { error: string | null; success: string | null }) {
  return (
    <>
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
    </>
  );
}

function IdentityStatusGrid({ config, tokenInfo }: { config: SsoProviderConfig; tokenInfo: ScimTokenInfo | null }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <IdentityStatusCard
        title="SSO status"
        description="Auth0 sign-in availability for this workspace."
        status={config.status}
        secondaryDetail={config.enabled ? "Provider is enabled." : "Provider is disabled."}
      />
      <IdentityStatusCard
        title="SCIM status"
        description="Provisioning readiness based on token issuance and use."
        status={
          tokenInfo?.status ?? {
            state: "unavailable",
            message: "No SCIM token has been issued for this workspace yet.",
          }
        }
        secondaryDetail={
          tokenInfo?.token_last4
            ? `Current token ••••${tokenInfo.token_last4}`
            : "Generate a token to connect your identity provider."
        }
      />
    </div>
  );
}

function SsoTruthAlert({ onBack }: { onBack: () => void }) {
  return (
    <Alert className="border-sky-500/30 bg-sky-500/10 text-sky-800 dark:text-sky-100">
      <ShieldCheck className="size-4" />
      <AlertDescription className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <span>
          Identity stays truthful here: unavailable means nothing is configured, partial means configuration exists but
          is not fully active yet, and configured means the feature is ready for operators to rely on.
        </span>
        <Button variant="ghost" className="justify-start px-0 sm:justify-center" onClick={onBack}>
          Back to Governance Hub
          <ArrowRight className="ml-1 size-4" aria-hidden="true" />
        </Button>
      </AlertDescription>
    </Alert>
  );
}

function AuthProviderCard({
  config,
  clientSecret,
  domainsInput,
  saving,
  onConfigChange,
  onClientSecretChange,
  onSave,
}: {
  config: SsoProviderConfig;
  clientSecret: string;
  domainsInput: string;
  saving: boolean;
  onConfigChange: (patch: Partial<SsoProviderConfig>) => void;
  onClientSecretChange: (value: string) => void;
  onSave: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Auth0 Provider</CardTitle>
        <CardDescription>Connect an Auth0 OIDC application for this workspace.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <FormField label="Issuer URL" required htmlFor="issuer_url">
          <Input
            id="issuer_url"
            value={config.issuer_url}
            onChange={(e) => onConfigChange({ issuer_url: e.target.value })}
            placeholder="https://your-tenant.us.auth0.com"
          />
        </FormField>
        <FormField label="Client ID" required htmlFor="client_id">
          <Input
            id="client_id"
            value={config.client_id}
            onChange={(e) => onConfigChange({ client_id: e.target.value })}
            placeholder="Auth0 client ID"
          />
        </FormField>
        <FormField label="Client Secret" htmlFor="client_secret">
          <Input
            id="client_secret"
            type="password"
            value={clientSecret}
            onChange={(e) => onClientSecretChange(e.target.value)}
            placeholder="Leave blank to keep existing secret"
          />
        </FormField>
        <FormField label="Audience (optional)" htmlFor="audience">
          <Input
            id="audience"
            value={config.audience}
            onChange={(e) => onConfigChange({ audience: e.target.value })}
            placeholder="https://api.your-domain.com"
          />
        </FormField>
        <FormField label="Allowed Email Domains" htmlFor="email_domains">
          <Input
            id="email_domains"
            value={domainsInput}
            onChange={(e) =>
              onConfigChange({
                email_domains: e.target.value.split(",").flatMap((item) => {
                  const trimmed = item.trim();
                  return trimmed ? [trimmed] : [];
                }),
              })
            }
            placeholder="example.com, acme.co"
          />
        </FormField>
        <DefaultRoleField value={config.default_role} onChange={(value) => onConfigChange({ default_role: value })} />
        <SsoEnabledToggle enabled={config.enabled} onToggle={() => onConfigChange({ enabled: !config.enabled })} />
        <div className="flex justify-end">
          <Button onClick={onSave} disabled={saving}>
            {saving ? (
              <>
                <Spinner size="xs" className="mr-2" />
                Saving
              </>
            ) : (
              "Save Settings"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function DefaultRoleField({
  value,
  onChange,
}: {
  value: SsoProviderConfig["default_role"];
  onChange: (value: SsoProviderConfig["default_role"]) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor="pages-admin-sso-262" className="text-sm font-medium text-foreground">
        Default Role
      </label>
      <select
        id="pages-admin-sso-262"
        value={value}
        onChange={(e) => onChange(e.target.value as SsoProviderConfig["default_role"])}
        className="h-11 rounded-md border border-border bg-background px-3 text-sm"
      >
        <option value="owner">Owner</option>
        <option value="admin">Admin</option>
        <option value="member">Member</option>
        <option value="viewer">Viewer</option>
      </select>
    </div>
  );
}

function SsoEnabledToggle({ enabled, onToggle }: { enabled: boolean; onToggle: () => void }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border p-3">
      <div>
        <p className="text-sm font-medium text-foreground">SSO Enabled</p>
        <p className="text-xs text-muted-foreground">Turn off to temporarily disable SSO login for this tenant.</p>
      </div>
      <Button variant={enabled ? "secondary" : "outline"} onClick={onToggle}>
        {enabled ? "Enabled" : "Disabled"}
      </Button>
    </div>
  );
}

function ScimTokenCard({
  tokenInfo,
  newToken,
  rotating,
  onBack,
  onRotate,
}: {
  tokenInfo: ScimTokenInfo | null;
  newToken: string | null;
  rotating: boolean;
  onBack: () => void;
  onRotate: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>SCIM Provisioning Token</CardTitle>
        <CardDescription>Use this token in Auth0 SCIM configuration.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <Badge variant="outline">{tokenInfo?.token_last4 ? `Token ••••${tokenInfo.token_last4}` : "No token"}</Badge>
          {tokenInfo?.last_used_at && (
            <span className="text-xs text-muted-foreground">Last used {formatUtcDateTime(tokenInfo.last_used_at)}</span>
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
          <Button variant="outline" onClick={onBack}>
            Back to Workspace Access
          </Button>
          <Button onClick={onRotate} disabled={rotating}>
            {rotating ? (
              <>
                <Spinner size="xs" className="mr-2" />
                Rotating…
              </>
            ) : (
              "Rotate Token"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function IdentityStatusCard({
  title,
  description,
  status,
  secondaryDetail,
}: {
  title: string;
  description: string;
  status: { state: "configured" | "partial" | "unavailable"; message: string };
  secondaryDetail: string;
}) {
  const badgeVariant =
    status.state === "configured" ? "secondary" : status.state === "partial" ? "outline" : "destructive";
  const label =
    status.state === "configured" ? "Configured" : status.state === "partial" ? "Partially configured" : "Unavailable";

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle>{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
          <Badge variant={badgeVariant}>{label}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-sm text-foreground">{status.message}</p>
        <p className="text-xs text-muted-foreground">{secondaryDetail}</p>
      </CardContent>
    </Card>
  );
}
