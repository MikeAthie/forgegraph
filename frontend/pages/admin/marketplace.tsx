import { useCallback, useEffect, useMemo, useReducer, type SetStateAction } from "react";
import { useRouter } from "next/router";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
import { useAuth } from "../../contexts/AuthContext";
import {
  getApiErrorMessage,
  marketplaceApi,
  type MarketplacePackage,
  type MarketplaceReleaseSummary,
  type MarketplaceRuntimeManifestPreview,
} from "../../lib/api";
import {
  getMarketplacePackageBadges,
  getMarketplacePackageReason,
  getMarketplacePackageStatusLabel,
  getMarketplaceReasonLabel,
  getMarketplaceReleaseLabel,
} from "../../lib/marketplace-runtime";
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
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
  Switch,
} from "@/components/ui";

type ReleaseFormState = {
  package_slug: string;
  package_name: string;
  version: string;
  package_kind: "template_http" | "template_prompt" | "runtime_tool" | "runtime_transform";
  cloud_allowed: boolean;
  runtime_tool_name: string;
  runtime_http_url: string;
  runtime_transform_name: string;
};

const DEFAULT_RELEASE_FORM: ReleaseFormState = {
  package_slug: "",
  package_name: "",
  version: "1.0.0",
  package_kind: "template_http",
  cloud_allowed: true,
  runtime_tool_name: "",
  runtime_http_url: "https://example.com/runtime/tool",
  runtime_transform_name: "",
};

const PACKAGE_KIND_TO_EXECUTION_TYPE = {
  template_http: "http",
  template_prompt: "prompt",
  runtime_tool: "tool",
  runtime_transform: "transform",
} as const;

const PACKAGE_KIND_OPTIONS = [
  { value: "template_http", label: "Template HTTP", help: "Editor preset only. Adds a configured HTTP node." },
  { value: "template_prompt", label: "Template Prompt", help: "Editor preset only. Adds a configured prompt node." },
  {
    value: "runtime_tool",
    label: "Runtime Tool",
    help: "Executable tool. Delivered to the runtime service when ready.",
  },
  {
    value: "runtime_transform",
    label: "Runtime Transform",
    help: "Reserved contract. Stored now, Cloud execution still blocked.",
  },
] as const;

type MarketplaceAdminState = {
  catalog: MarketplacePackage[];
  installed: MarketplacePackage[];
  releases: MarketplaceReleaseSummary[];
  runtimePreview: MarketplaceRuntimeManifestPreview | null;
  loading: boolean;
  error: string | null;
  installingSlug: string | null;
  reviewingReleaseId: string | null;
  publishing: boolean;
  releaseForm: ReleaseFormState;
};

type MarketplaceAdminAction = {
  patch: Partial<MarketplaceAdminState> | ((state: MarketplaceAdminState) => Partial<MarketplaceAdminState>);
};

const initialMarketplaceAdminState: MarketplaceAdminState = {
  catalog: [],
  installed: [],
  releases: [],
  runtimePreview: null,
  loading: true,
  error: null,
  installingSlug: null,
  reviewingReleaseId: null,
  publishing: false,
  releaseForm: DEFAULT_RELEASE_FORM,
};

function marketplaceAdminReducer(
  state: MarketplaceAdminState,
  action: MarketplaceAdminAction,
): MarketplaceAdminState {
  const patch = typeof action.patch === "function" ? action.patch(state) : action.patch;
  return { ...state, ...patch };
}

function resolveStateAction<T>(value: SetStateAction<T>, current: T): T {
  return typeof value === "function" ? (value as (current: T) => T)(current) : value;
}

function buildRuntimeManifest(form: ReleaseFormState): Record<string, unknown> | null {
  if (form.package_kind === "runtime_tool") {
    const toolName = form.runtime_tool_name.trim() || form.package_slug.trim().replace(/-/g, "_");
    return {
      name: toolName,
      version: form.version.trim(),
      kind: "http",
      description: `${form.package_name.trim() || form.package_slug.trim()} runtime tool`,
      http: {
        url: form.runtime_http_url.trim() || "https://example.com/runtime/tool",
        method: "POST",
      },
    };
  }

  if (form.package_kind === "runtime_transform") {
    const transformName = form.runtime_transform_name.trim() || form.package_slug.trim().replace(/-/g, "_");
    return {
      name: transformName,
      version: form.version.trim(),
      kind: "transform",
    };
  }

  return null;
}

export default function MarketplaceAdminPage() {
  const router = useRouter();
  const { push } = router;
  const { user } = useAuth();
  const canManage = user?.organization_role === "owner" || user?.organization_role === "admin";
  const canReview = user?.organization_role === "owner";

  const [pageState, dispatchPageState] = useReducer(marketplaceAdminReducer, initialMarketplaceAdminState);
  const {
    catalog,
    installed,
    releases,
    runtimePreview,
    loading,
    error,
    installingSlug,
    reviewingReleaseId,
    publishing,
    releaseForm,
  } = pageState;
  const setPageField = useCallback(
    <K extends keyof MarketplaceAdminState>(key: K, value: SetStateAction<MarketplaceAdminState[K]>) => {
      dispatchPageState({
        patch: (current) => ({ [key]: resolveStateAction(value, current[key]) }) as Partial<MarketplaceAdminState>,
      });
    },
    [],
  );
  const setCatalog = useCallback((value: SetStateAction<MarketplacePackage[]>) => setPageField("catalog", value), [setPageField]);
  const setInstalled = useCallback((value: SetStateAction<MarketplacePackage[]>) => setPageField("installed", value), [setPageField]);
  const setReleases = useCallback((value: SetStateAction<MarketplaceReleaseSummary[]>) => setPageField("releases", value), [setPageField]);
  const setRuntimePreview = useCallback((value: SetStateAction<MarketplaceRuntimeManifestPreview | null>) => setPageField("runtimePreview", value), [setPageField]);
  const setLoading = useCallback((value: SetStateAction<boolean>) => setPageField("loading", value), [setPageField]);
  const setError = useCallback((value: SetStateAction<string | null>) => setPageField("error", value), [setPageField]);
  const setInstallingSlug = useCallback((value: SetStateAction<string | null>) => setPageField("installingSlug", value), [setPageField]);
  const setReviewingReleaseId = useCallback((value: SetStateAction<string | null>) => setPageField("reviewingReleaseId", value), [setPageField]);
  const setPublishing = useCallback((value: SetStateAction<boolean>) => setPageField("publishing", value), [setPageField]);
  const setReleaseForm = useCallback((value: SetStateAction<ReleaseFormState>) => setPageField("releaseForm", value), [setPageField]);

  const refreshData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [catalogData, installedData, releasesData, runtimePreviewData] = await Promise.all([
        marketplaceApi.listPackages(),
        marketplaceApi.listInstalled(),
        canManage ? marketplaceApi.listReleases() : Promise.resolve([]),
        canManage ? marketplaceApi.getRuntimePreview() : Promise.resolve(null),
      ]);
      setCatalog(catalogData);
      setInstalled(installedData);
      setReleases(releasesData);
      setRuntimePreview(runtimePreviewData);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to load marketplace data."));
    } finally {
      setLoading(false);
    }
  }, [canManage]);

  useEffect(() => {
    void refreshData();
  }, [refreshData]);

  const installedBySlug = useMemo(() => {
    const map = new Map<string, MarketplacePackage>();
    for (const item of installed) {
      map.set(item.slug, item);
    }
    return map;
  }, [installed]);

  const pendingReleases = useMemo(() => releases.filter((release) => release.status === "pending_review"), [releases]);

  const installedStats = useMemo(() => {
    return installed.reduce(
      (acc, pkg) => {
        const state = pkg.runtime_delivery?.state ?? "unknown";
        if (state === "ready") acc.ready += 1;
        else if (state === "template") acc.template += 1;
        else if (state === "blocked") acc.blocked += 1;
        else if (state === "invalid") acc.invalid += 1;
        return acc;
      },
      { ready: 0, template: 0, blocked: 0, invalid: 0 },
    );
  }, [installed]);

  const executionNodeType = PACKAGE_KIND_TO_EXECUTION_TYPE[releaseForm.package_kind];

  const handleInstall = useCallback(
    async (pkg: MarketplacePackage) => {
      setInstallingSlug(pkg.slug);
      setError(null);
      try {
        await marketplaceApi.install(pkg.slug);
        await refreshData();
      } catch (err: unknown) {
        setError(getApiErrorMessage(err, "Failed to install package."));
      } finally {
        setInstallingSlug(null);
      }
    },
    [refreshData],
  );

  const handleReview = useCallback(
    async (releaseId: string, decision: "approved" | "rejected") => {
      setReviewingReleaseId(releaseId);
      setError(null);
      try {
        await marketplaceApi.reviewRelease(releaseId, decision);
        await refreshData();
      } catch (err: unknown) {
        setError(getApiErrorMessage(err, "Failed to review release."));
      } finally {
        setReviewingReleaseId(null);
      }
    },
    [refreshData],
  );

  const handlePublishRelease = useCallback(async () => {
    if (!releaseForm.package_slug.trim() || !releaseForm.version.trim()) {
      setError("Package slug and version are required.");
      return;
    }

    if (releaseForm.package_kind === "runtime_tool" && !releaseForm.runtime_http_url.trim()) {
      setError("Runtime tool releases require an HTTP endpoint URL.");
      return;
    }

    setPublishing(true);
    setError(null);
    try {
      const runtimeManifest = buildRuntimeManifest(releaseForm);
      const toolName =
        releaseForm.package_kind === "runtime_tool"
          ? releaseForm.runtime_tool_name.trim() || releaseForm.package_slug.trim().replace(/-/g, "_")
          : "";

      await marketplaceApi.createRelease({
        package_slug: releaseForm.package_slug.trim(),
        package_name: releaseForm.package_name.trim() || undefined,
        version: releaseForm.version.trim(),
        package_kind: releaseForm.package_kind,
        execution_node_type: executionNodeType,
        ui_schema: {
          label: releaseForm.package_name.trim() || releaseForm.package_slug.trim(),
          description: "Published from admin marketplace",
          category: "integration",
        },
        config_schema: { type: "object" },
        config_defaults: releaseForm.package_kind === "runtime_tool" ? { tool: toolName } : {},
        runtime_manifest: runtimeManifest,
        cloud_allowed: releaseForm.cloud_allowed,
      });
      setReleaseForm(DEFAULT_RELEASE_FORM);
      await refreshData();
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to submit release."));
    } finally {
      setPublishing(false);
    }
  }, [executionNodeType, refreshData, releaseForm]);

  if (!canManage) {
    return (
      <ProtectedRoute>
        <DashboardLayout>
          <Card className="max-w-2xl">
            <CardHeader>
              <CardTitle>Marketplace</CardTitle>
              <CardDescription>Workspace admins can manage marketplace packages.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" onClick={() => void push("/admin/organization")}>
                Back to Workspace Access
              </Button>
            </CardContent>
          </Card>
        </DashboardLayout>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="space-y-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold">Marketplace</h1>
              <p className="text-sm text-muted-foreground">
                Install template presets and runtime packages with explicit delivery status.
              </p>
            </div>
            <Button variant="outline" onClick={() => void refreshData()} disabled={loading}>
              {loading ? <Spinner size="xs" /> : "Refresh"}
            </Button>
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <div className="grid gap-4 md:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Runtime-ready</CardTitle>
                <CardDescription>Included in tenant manifest delivery.</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-semibold">{installedStats.ready}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Template-only</CardTitle>
                <CardDescription>Editor presets only. No runtime code is shipped.</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-semibold">{installedStats.template}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Blocked</CardTitle>
                <CardDescription>Installed, but not executable in the current product mode.</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-semibold">{installedStats.blocked}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Invalid</CardTitle>
                <CardDescription>Package metadata needs operator review before delivery.</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-semibold">{installedStats.invalid}</p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Approved packages</CardTitle>
              <CardDescription>
                Template packages stay addable as editor presets. Only ready runtime packages are delivered to the
                runtime service.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading ? (
                <div className="flex items-center gap-3 text-sm text-muted-foreground">
                  <Spinner size="sm" />
                  Loading packages…
                </div>
              ) : catalog.length === 0 ? (
                <p className="text-sm text-muted-foreground">No approved packages found.</p>
              ) : (
                catalog.map((pkg) => {
                  const currentInstall = installedBySlug.get(pkg.slug);
                  const installedVersion = currentInstall?.installed_release?.version ?? null;
                  const latestVersion = pkg.latest_release?.version ?? "-";
                  const upToDate = installedVersion && installedVersion === latestVersion;
                  const statusLabel = getMarketplacePackageStatusLabel(currentInstall ?? pkg);
                  const reason = getMarketplacePackageReason(currentInstall ?? pkg);
                  const badges = getMarketplacePackageBadges(currentInstall ?? pkg);

                  return (
                    <div
                      key={pkg.slug}
                      className="flex items-start justify-between gap-4 rounded-lg border border-border p-3"
                    >
                      <div className="space-y-1">
                        <p className="text-sm font-medium">{pkg.name}</p>
                        <p className="text-xs text-muted-foreground">{pkg.summary}</p>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="outline">{pkg.category}</Badge>
                          {badges.map((badge) => (
                            <Badge key={`${pkg.slug}-${badge}`} variant="secondary">
                              {badge}
                            </Badge>
                          ))}
                          <Badge variant="outline">latest {latestVersion}</Badge>
                          {installedVersion && (
                            <Badge variant={upToDate ? "default" : "outline"}>installed {installedVersion}</Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {statusLabel}
                          {reason ? ` · ${reason}` : ""}
                        </p>
                      </div>
                      <Button size="sm" onClick={() => void handleInstall(pkg)} disabled={installingSlug === pkg.slug}>
                        {installingSlug === pkg.slug
                          ? "Installing"
                          : installedVersion
                            ? upToDate
                              ? "Reinstall"
                              : "Update"
                            : "Install"}
                      </Button>
                    </div>
                  );
                })
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Runtime manifest preview</CardTitle>
              <CardDescription>
                Operator view of the tenant-scoped manifest payload available to the runtime service without local file
                edits.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {!runtimePreview ? (
                <p className="text-sm text-muted-foreground">Runtime preview not available.</p>
              ) : (
                <>
                  <div className="grid gap-3 md:grid-cols-3">
                    <div className="rounded-lg border border-border p-3">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">Manifest checksum</p>
                      <p className="mt-1 break-all font-mono text-xs text-foreground">
                        {runtimePreview.checksum || "-"}
                      </p>
                    </div>
                    <div className="rounded-lg border border-border p-3">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">Runtime tools</p>
                      <p className="mt-1 text-lg font-semibold">{runtimePreview.tools.length}</p>
                    </div>
                    <div className="rounded-lg border border-border p-3">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">Generated</p>
                      <p className="mt-1 text-sm text-foreground">{runtimePreview.generated_at || "-"}</p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <h3 className="text-sm font-medium">Delivery status by installed package</h3>
                    {runtimePreview.packages.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No installed packages are currently part of the preview payload.
                      </p>
                    ) : (
                      runtimePreview.packages.map((entry) => (
                        <div
                          key={`${entry.package_slug}-${entry.release_id}`}
                          className="rounded-lg border border-border p-3"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-medium">{entry.package_name}</p>
                            <Badge variant="outline">{getMarketplaceReleaseLabel(entry.package_kind)}</Badge>
                            <Badge variant={entry.delivery_state === "ready" ? "default" : "secondary"}>
                              {entry.delivery_state}
                            </Badge>
                            <Badge variant="outline">v{entry.release_version}</Badge>
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {getMarketplaceReasonLabel(entry.delivery_reason)}
                          </p>
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            checksum: {entry.manifest_checksum || "-"}
                          </p>
                        </div>
                      ))
                    )}
                  </div>

                  {runtimePreview.tools.length > 0 && (
                    <div className="space-y-2">
                      <h3 className="text-sm font-medium">Delivered tools</h3>
                      <div className="flex flex-wrap gap-2">
                        {runtimePreview.tools.map((tool) => (
                          <Badge key={`${tool.name}-${tool.version || "latest"}`} variant="outline">
                            {tool.name}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Publish release</CardTitle>
              <CardDescription>Submit a package release with explicit template vs runtime semantics.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="packageSlug">Package slug</Label>
                  <Input
                    id="packageSlug"
                    value={releaseForm.package_slug}
                    onChange={(event) => setReleaseForm((prev) => ({ ...prev, package_slug: event.target.value }))}
                    placeholder="slack-alerts"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="packageName">Package name</Label>
                  <Input
                    id="packageName"
                    value={releaseForm.package_name}
                    onChange={(event) => setReleaseForm((prev) => ({ ...prev, package_name: event.target.value }))}
                    placeholder="Slack Alerts"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="releaseVersion">Version</Label>
                  <Input
                    id="releaseVersion"
                    value={releaseForm.version}
                    onChange={(event) => setReleaseForm((prev) => ({ ...prev, version: event.target.value }))}
                    placeholder="1.0.0"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="packageKind">Package class</Label>
                  <Select
                    value={releaseForm.package_kind}
                    onValueChange={(value) =>
                      setReleaseForm((prev) => ({
                        ...prev,
                        package_kind: value as ReleaseFormState["package_kind"],
                      }))
                    }
                  >
                    <SelectTrigger id="packageKind">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PACKAGE_KIND_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    {PACKAGE_KIND_OPTIONS.find((option) => option.value === releaseForm.package_kind)?.help}
                  </p>
                </div>
              </div>

              <div className="rounded-lg border border-border p-3 text-sm">
                <p className="font-medium text-foreground">Derived execution node type: {executionNodeType}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Package class governs the release shape. The execution node type is derived from it.
                </p>
              </div>

              {releaseForm.package_kind === "runtime_tool" && (
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="runtimeToolName">Runtime tool name</Label>
                    <Input
                      id="runtimeToolName"
                      value={releaseForm.runtime_tool_name}
                      onChange={(event) =>
                        setReleaseForm((prev) => ({ ...prev, runtime_tool_name: event.target.value }))
                      }
                      placeholder="crm_lookup"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="runtimeHttpUrl">Runtime HTTP URL</Label>
                    <Input
                      id="runtimeHttpUrl"
                      value={releaseForm.runtime_http_url}
                      onChange={(event) =>
                        setReleaseForm((prev) => ({ ...prev, runtime_http_url: event.target.value }))
                      }
                      placeholder="https://example.com/runtime/tool"
                    />
                  </div>
                </div>
              )}

              {releaseForm.package_kind === "runtime_transform" && (
                <div className="space-y-2">
                  <Label htmlFor="runtimeTransformName">Runtime transform name</Label>
                  <Input
                    id="runtimeTransformName"
                    value={releaseForm.runtime_transform_name}
                    onChange={(event) =>
                      setReleaseForm((prev) => ({ ...prev, runtime_transform_name: event.target.value }))
                    }
                    placeholder="normalize_customer_record"
                  />
                </div>
              )}

              {(releaseForm.package_kind === "runtime_tool" || releaseForm.package_kind === "runtime_transform") && (
                <div className="flex items-center justify-between rounded-lg border border-border p-3">
                  <div>
                    <p className="text-sm font-medium text-foreground">Cloud allowed</p>
                    <p className="text-xs text-muted-foreground">
                      Disable this for self-host-only releases. Runtime tools backed by exec must stay off in Cloud.
                    </p>
                  </div>
                  <Switch
                    checked={releaseForm.cloud_allowed}
                    onCheckedChange={(checked) => setReleaseForm((prev) => ({ ...prev, cloud_allowed: checked }))}
                    aria-label="Cloud allowed"
                  />
                </div>
              )}

              <Button onClick={() => void handlePublishRelease()} disabled={publishing}>
                {publishing ? "Submitting" : "Submit release"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Release review queue</CardTitle>
              <CardDescription>Pending release approvals. Owner role required for approval decisions.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {pendingReleases.length === 0 ? (
                <p className="text-sm text-muted-foreground">No pending releases.</p>
              ) : (
                pendingReleases.map((release) => (
                  <div
                    key={release.id}
                    className="flex items-center justify-between rounded-lg border border-border p-3"
                  >
                    <div>
                      <p className="text-sm font-medium">
                        {release.package_name} v{release.version}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {release.package_slug} · {getMarketplaceReleaseLabel(release.package_kind)} ·{" "}
                        {release.execution_node_type}
                        {release.cloud_allowed ? " · cloud-allowed" : " · self-host only"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{release.status}</Badge>
                      {canReview && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => void handleReview(release.id, "rejected")}
                            disabled={reviewingReleaseId === release.id}
                          >
                            Reject
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => void handleReview(release.id, "approved")}
                            disabled={reviewingReleaseId === release.id}
                          >
                            Approve
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
