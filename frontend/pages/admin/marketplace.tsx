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
  getMarketplacePackageSetupFields,
  getMarketplacePackageSourceLabel,
  getMarketplacePackageSourcePath,
  getMarketplacePackageStatusLabel,
  getMarketplaceReasonLabel,
  getMarketplaceReleaseLabel,
  isHermesGatewayPackage,
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

function marketplaceAdminReducer(state: MarketplaceAdminState, action: MarketplaceAdminAction): MarketplaceAdminState {
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
      category: "communication",
      description: `${form.package_name.trim() || form.package_slug.trim()} runtime tool`,
      visibility: "public",
      input_schema: { type: "object" },
      output_schema: { type: "object" },
      execution: {
        type: "http",
        timeout_seconds: 30,
        http: {
          url: form.runtime_http_url.trim() || "https://example.com/runtime/tool",
          method: "POST",
          headers: { "Content-Type": "application/json" },
        },
      },
      side_effects: { type: "external", idempotent: false },
    };
  }

  if (form.package_kind === "runtime_transform") {
    const transformName = form.runtime_transform_name.trim() || form.package_slug.trim().replace(/-/g, "_");
    return {
      name: transformName,
      version: form.version.trim(),
      kind: "transform",
      category: "transform",
      input_schema: { type: "object" },
      output_schema: { type: "object" },
      transform: { expression: "input" },
    };
  }

  return null;
}

function useMarketplaceAdminController() {
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
  const setCatalog = useCallback(
    (value: SetStateAction<MarketplacePackage[]>) => setPageField("catalog", value),
    [setPageField],
  );
  const setInstalled = useCallback(
    (value: SetStateAction<MarketplacePackage[]>) => setPageField("installed", value),
    [setPageField],
  );
  const setReleases = useCallback(
    (value: SetStateAction<MarketplaceReleaseSummary[]>) => setPageField("releases", value),
    [setPageField],
  );
  const setRuntimePreview = useCallback(
    (value: SetStateAction<MarketplaceRuntimeManifestPreview | null>) => setPageField("runtimePreview", value),
    [setPageField],
  );
  const setLoading = useCallback((value: SetStateAction<boolean>) => setPageField("loading", value), [setPageField]);
  const setError = useCallback((value: SetStateAction<string | null>) => setPageField("error", value), [setPageField]);
  const setInstallingSlug = useCallback(
    (value: SetStateAction<string | null>) => setPageField("installingSlug", value),
    [setPageField],
  );
  const setReviewingReleaseId = useCallback(
    (value: SetStateAction<string | null>) => setPageField("reviewingReleaseId", value),
    [setPageField],
  );
  const setPublishing = useCallback(
    (value: SetStateAction<boolean>) => setPageField("publishing", value),
    [setPageField],
  );
  const setReleaseForm = useCallback(
    (value: SetStateAction<ReleaseFormState>) => setPageField("releaseForm", value),
    [setPageField],
  );

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
  }, [canManage, setCatalog, setError, setInstalled, setLoading, setReleases, setRuntimePreview]);

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
  const hermesGatewayPackages = useMemo(() => catalog.filter((pkg) => isHermesGatewayPackage(pkg)), [catalog]);
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
    [refreshData, setError, setInstallingSlug],
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
    [refreshData, setError, setReviewingReleaseId],
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
        manifest_version: 2,
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
  }, [executionNodeType, refreshData, releaseForm, setError, setPublishing, setReleaseForm]);

  return {
    push,
    canManage,
    canReview,
    catalog,
    runtimePreview,
    loading,
    error,
    installingSlug,
    reviewingReleaseId,
    publishing,
    releaseForm,
    installedBySlug,
    pendingReleases,
    hermesGatewayPackages,
    installedStats,
    executionNodeType,
    refreshData,
    handleInstall,
    handleReview,
    handlePublishRelease,
    setReleaseForm,
  };
}

type MarketplaceAdminController = ReturnType<typeof useMarketplaceAdminController>;

function MarketplaceNoAccess({ onBack }: { onBack: () => void }) {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle>Marketplace</CardTitle>
            <CardDescription>Workspace admins can manage marketplace packages.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" onClick={onBack}>
              Back to Workspace Access
            </Button>
          </CardContent>
        </Card>
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function MarketplaceHeader({ controller }: { controller: MarketplaceAdminController }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Marketplace</h1>
        <p className="text-sm text-muted-foreground">
          Install template presets and runtime packages with explicit delivery status.
        </p>
      </div>
      <Button variant="outline" onClick={() => void controller.refreshData()} disabled={controller.loading}>
        {controller.loading ? <Spinner size="xs" /> : "Refresh"}
      </Button>
    </div>
  );
}

function RuntimeStatsGrid({ stats }: { stats: MarketplaceAdminController["installedStats"] }) {
  return (
    <div className="grid gap-4 md:grid-cols-4">
      <RuntimeStatCard title="Runtime-ready" description="Included in tenant manifest delivery." value={stats.ready} />
      <RuntimeStatCard
        title="Template-only"
        description="Editor presets only. No runtime code is shipped."
        value={stats.template}
      />
      <RuntimeStatCard
        title="Blocked"
        description="Installed, but not executable in the current product mode."
        value={stats.blocked}
      />
      <RuntimeStatCard
        title="Invalid"
        description="Package metadata needs operator review before delivery."
        value={stats.invalid}
      />
    </div>
  );
}

function RuntimeStatCard({ title, description, value }: { title: string; description: string; value: number }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold">{value}</p>
      </CardContent>
    </Card>
  );
}

function HermesGatewayCoverageCard({ controller }: { controller: MarketplaceAdminController }) {
  const packages = controller.hermesGatewayPackages;
  const installedCount = packages.filter((pkg) => controller.installedBySlug.has(pkg.slug)).length;
  const setupFields = Array.from(new Set(packages.flatMap((pkg) => getMarketplacePackageSetupFields(pkg)))).slice(
    0,
    10,
  );

  return (
    <Card className="overflow-hidden border-border/80 bg-gradient-to-br from-card via-card to-muted/40">
      <CardHeader>
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <CardTitle>Hermes gateway connector catalog</CardTitle>
            <CardDescription>
              Messaging-platform templates copied from NousResearch/hermes-agent gateway adapters and mapped into
              backend-owned marketplace packages.
            </CardDescription>
          </div>
          <Badge variant="outline">{packages.length} gateway connectors</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {packages.length === 0 ? (
          <p className="text-sm text-muted-foreground">Hermes gateway connector seeds have not been applied yet.</p>
        ) : (
          <>
            <div className="grid gap-3 md:grid-cols-3">
              <RuntimePreviewMetric label="Gateway templates" value={String(packages.length)} />
              <RuntimePreviewMetric label="Installed" value={`${installedCount}/${packages.length}`} />
              <RuntimePreviewMetric label="Source" value="NousResearch/hermes-agent" />
            </div>
            <div className="flex flex-wrap gap-2">
              {packages.map((pkg) => (
                <Badge key={pkg.slug} variant={controller.installedBySlug.has(pkg.slug) ? "default" : "secondary"}>
                  {pkg.name.replace(/^Hermes\s+/i, "")}
                </Badge>
              ))}
            </div>
            {setupFields.length > 0 ? (
              <div className="rounded-lg border border-border/80 bg-background/70 p-3">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Common setup keys surfaced in package schemas
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {setupFields.map((field) => (
                    <Badge key={field} variant="outline" className="font-mono text-[11px]">
                      {field}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ApprovedPackagesCard({ controller }: { controller: MarketplaceAdminController }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Approved packages</CardTitle>
        <CardDescription>
          Template packages stay addable as editor presets. Only ready runtime packages are delivered to the runtime
          service.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {controller.loading ? (
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <Spinner size="sm" />
            Loading packages&hellip;
          </div>
        ) : controller.catalog.length === 0 ? (
          <p className="text-sm text-muted-foreground">No approved packages found.</p>
        ) : (
          controller.catalog.map((pkg) => <ApprovedPackageRow key={pkg.slug} pkg={pkg} controller={controller} />)
        )}
      </CardContent>
    </Card>
  );
}

function ApprovedPackageRow({ pkg, controller }: { pkg: MarketplacePackage; controller: MarketplaceAdminController }) {
  const currentInstall = controller.installedBySlug.get(pkg.slug);
  const installedVersion = currentInstall?.installed_release?.version ?? null;
  const latestVersion = pkg.latest_release?.version ?? "-";
  const upToDate = installedVersion && installedVersion === latestVersion;
  const statusLabel = getMarketplacePackageStatusLabel(currentInstall ?? pkg);
  const reason = getMarketplacePackageReason(currentInstall ?? pkg);
  const badges = getMarketplacePackageBadges(currentInstall ?? pkg);
  const sourceLabel = getMarketplacePackageSourceLabel(currentInstall ?? pkg);
  const sourcePath = getMarketplacePackageSourcePath(currentInstall ?? pkg);
  const setupFields = getMarketplacePackageSetupFields(currentInstall ?? pkg);

  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
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
          {installedVersion ? (
            <Badge variant={upToDate ? "default" : "outline"}>installed {installedVersion}</Badge>
          ) : null}
        </div>
        <p className="text-xs text-muted-foreground">
          {statusLabel}
          {reason ? ` · ${reason}` : ""}
        </p>
        {sourceLabel ? (
          <p className="text-xs text-muted-foreground">
            Source: {sourceLabel}
            {sourcePath ? ` · ${sourcePath}` : ""}
          </p>
        ) : null}
        {setupFields.length > 0 ? (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {setupFields.slice(0, 4).map((field) => (
              <Badge key={`${pkg.slug}-${field}`} variant="outline" className="font-mono text-[10px]">
                {field}
              </Badge>
            ))}
            {setupFields.length > 4 ? (
              <Badge variant="outline" className="font-mono text-[10px]">
                +{setupFields.length - 4}
              </Badge>
            ) : null}
          </div>
        ) : null}
      </div>
      <Button
        size="sm"
        onClick={() => void controller.handleInstall(pkg)}
        disabled={controller.installingSlug === pkg.slug}
      >
        {controller.installingSlug === pkg.slug
          ? "Installing"
          : installedVersion
            ? upToDate
              ? "Reinstall"
              : "Update"
            : "Install"}
      </Button>
    </div>
  );
}

function RuntimeManifestPreviewCard({ preview }: { preview: MarketplaceRuntimeManifestPreview | null }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Runtime manifest preview</CardTitle>
        <CardDescription>
          Operator view of the tenant-scoped manifest payload available to the runtime service without local file edits.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!preview ? (
          <p className="text-sm text-muted-foreground">Runtime preview not available.</p>
        ) : (
          <RuntimeManifestPreview preview={preview} />
        )}
      </CardContent>
    </Card>
  );
}

function RuntimeManifestPreview({ preview }: { preview: MarketplaceRuntimeManifestPreview }) {
  return (
    <>
      <div className="grid gap-3 md:grid-cols-3">
        <RuntimePreviewMetric label="Manifest checksum" value={preview.checksum || "-"} mono />
        <RuntimePreviewMetric label="Runtime tools" value={String(preview.tools.length)} />
        <RuntimePreviewMetric label="Generated" value={preview.generated_at || "-"} />
      </div>
      <RuntimePackagesList preview={preview} />
      {preview.tools.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Delivered tools</h3>
          <div className="flex flex-wrap gap-2">
            {preview.tools.map((tool) => (
              <Badge key={`${tool.name}-${tool.version || "latest"}`} variant="outline">
                {tool.name}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}
    </>
  );
}

function RuntimePreviewMetric({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={mono ? "mt-1 break-all font-mono text-xs text-foreground" : "mt-1 text-lg font-semibold"}>
        {value}
      </p>
    </div>
  );
}

function RuntimePackagesList({ preview }: { preview: MarketplaceRuntimeManifestPreview }) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">Delivery status by installed package</h3>
      {preview.packages.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No installed packages are currently part of the preview payload.
        </p>
      ) : (
        preview.packages.map((entry) => (
          <div key={`${entry.package_slug}-${entry.release_id}`} className="rounded-lg border border-border p-3">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-medium">{entry.package_name}</p>
              <Badge variant="outline">{getMarketplaceReleaseLabel(entry.package_kind)}</Badge>
              <Badge variant={entry.delivery_state === "ready" ? "default" : "secondary"}>{entry.delivery_state}</Badge>
              <Badge variant="outline">v{entry.release_version}</Badge>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{getMarketplaceReasonLabel(entry.delivery_reason)}</p>
            <p className="mt-1 text-[11px] text-muted-foreground">checksum: {entry.manifest_checksum || "-"}</p>
          </div>
        ))
      )}
    </div>
  );
}

function PublishReleaseCard({ controller }: { controller: MarketplaceAdminController }) {
  const { releaseForm } = controller;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Publish release</CardTitle>
        <CardDescription>Submit a package release with explicit template vs runtime semantics.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <ReleaseTextField
            id="packageSlug"
            label="Package slug"
            value={releaseForm.package_slug}
            placeholder="slack-alerts"
            field="package_slug"
            controller={controller}
          />
          <ReleaseTextField
            id="packageName"
            label="Package name"
            value={releaseForm.package_name}
            placeholder="Slack Alerts"
            field="package_name"
            controller={controller}
          />
          <ReleaseTextField
            id="releaseVersion"
            label="Version"
            value={releaseForm.version}
            placeholder="1.0.0"
            field="version"
            controller={controller}
          />
          <ReleaseKindSelect controller={controller} />
        </div>
        <div className="rounded-lg border border-border p-3 text-sm">
          <p className="font-medium text-foreground">Derived execution node type: {controller.executionNodeType}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Package class governs the release shape. The execution node type is derived from it.
          </p>
        </div>
        {releaseForm.package_kind === "runtime_tool" ? <RuntimeToolFields controller={controller} /> : null}
        {releaseForm.package_kind === "runtime_transform" ? (
          <ReleaseTextField
            id="runtimeTransformName"
            label="Runtime transform name"
            value={releaseForm.runtime_transform_name}
            placeholder="normalize_customer_record"
            field="runtime_transform_name"
            controller={controller}
          />
        ) : null}
        {releaseForm.package_kind === "runtime_tool" || releaseForm.package_kind === "runtime_transform" ? (
          <CloudAllowedSwitch controller={controller} />
        ) : null}
        <Button onClick={() => void controller.handlePublishRelease()} disabled={controller.publishing}>
          {controller.publishing ? "Submitting" : "Submit release"}
        </Button>
      </CardContent>
    </Card>
  );
}

function ReleaseTextField({
  id,
  label,
  value,
  placeholder,
  field,
  controller,
}: {
  id: string;
  label: string;
  value: string;
  placeholder: string;
  field: keyof ReleaseFormState;
  controller: MarketplaceAdminController;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        value={value}
        onChange={(event) => controller.setReleaseForm((prev) => ({ ...prev, [field]: event.target.value }))}
        placeholder={placeholder}
      />
    </div>
  );
}

function ReleaseKindSelect({ controller }: { controller: MarketplaceAdminController }) {
  return (
    <div className="space-y-2">
      <Label htmlFor="packageKind">Package class</Label>
      <Select
        value={controller.releaseForm.package_kind}
        onValueChange={(value) =>
          controller.setReleaseForm((prev) => ({ ...prev, package_kind: value as ReleaseFormState["package_kind"] }))
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
        {PACKAGE_KIND_OPTIONS.find((option) => option.value === controller.releaseForm.package_kind)?.help}
      </p>
    </div>
  );
}

function RuntimeToolFields({ controller }: { controller: MarketplaceAdminController }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <ReleaseTextField
        id="runtimeToolName"
        label="Runtime tool name"
        value={controller.releaseForm.runtime_tool_name}
        placeholder="crm_lookup"
        field="runtime_tool_name"
        controller={controller}
      />
      <ReleaseTextField
        id="runtimeHttpUrl"
        label="Runtime HTTP URL"
        value={controller.releaseForm.runtime_http_url}
        placeholder="https://example.com/runtime/tool"
        field="runtime_http_url"
        controller={controller}
      />
    </div>
  );
}

function CloudAllowedSwitch({ controller }: { controller: MarketplaceAdminController }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border p-3">
      <div>
        <p className="text-sm font-medium text-foreground">Cloud allowed</p>
        <p className="text-xs text-muted-foreground">
          Disable this for self-host-only releases. Runtime tools backed by exec must stay off in Cloud.
        </p>
      </div>
      <Switch
        checked={controller.releaseForm.cloud_allowed}
        onCheckedChange={(checked) => controller.setReleaseForm((prev) => ({ ...prev, cloud_allowed: checked }))}
        aria-label="Cloud allowed"
      />
    </div>
  );
}

function ReleaseReviewQueue({ controller }: { controller: MarketplaceAdminController }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Release review queue</CardTitle>
        <CardDescription>Pending release approvals. Owner role required for approval decisions.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {controller.pendingReleases.length === 0 ? (
          <p className="text-sm text-muted-foreground">No pending releases.</p>
        ) : (
          controller.pendingReleases.map((release) => (
            <ReleaseReviewRow key={release.id} release={release} controller={controller} />
          ))
        )}
      </CardContent>
    </Card>
  );
}

function ReleaseReviewRow({
  release,
  controller,
}: {
  release: MarketplaceReleaseSummary;
  controller: MarketplaceAdminController;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border p-3">
      <div>
        <p className="text-sm font-medium">
          {release.package_name} v{release.version}
        </p>
        <p className="text-xs text-muted-foreground">
          {release.package_slug} · {getMarketplaceReleaseLabel(release.package_kind)} · {release.execution_node_type}
          {release.cloud_allowed ? " · cloud-allowed" : " · self-host only"}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant="outline">{release.status}</Badge>
        {controller.canReview ? (
          <>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void controller.handleReview(release.id, "rejected")}
              disabled={controller.reviewingReleaseId === release.id}
            >
              Reject
            </Button>
            <Button
              size="sm"
              onClick={() => void controller.handleReview(release.id, "approved")}
              disabled={controller.reviewingReleaseId === release.id}
            >
              Approve
            </Button>
          </>
        ) : null}
      </div>
    </div>
  );
}

export default function MarketplaceAdminPage() {
  const controller = useMarketplaceAdminController();

  if (!controller.canManage) {
    return <MarketplaceNoAccess onBack={() => void controller.push("/admin/organization")} />;
  }

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="space-y-6">
          <MarketplaceHeader controller={controller} />
          {controller.error ? (
            <Alert variant="destructive">
              <AlertDescription>{controller.error}</AlertDescription>
            </Alert>
          ) : null}
          <RuntimeStatsGrid stats={controller.installedStats} />
          <HermesGatewayCoverageCard controller={controller} />
          <ApprovedPackagesCard controller={controller} />
          <RuntimeManifestPreviewCard preview={controller.runtimePreview} />
          <PublishReleaseCard controller={controller} />
          <ReleaseReviewQueue controller={controller} />
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
