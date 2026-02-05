import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
import { useAuth } from "../../contexts/AuthContext";
import {
  getApiErrorMessage,
  marketplaceApi,
  type MarketplacePackage,
  type MarketplaceReleaseSummary,
} from "../../lib/api";
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
} from "@/components/ui";

type ReleaseFormState = {
  package_slug: string;
  package_name: string;
  version: string;
  execution_node_type: "http" | "prompt" | "tool" | "transform";
};

const DEFAULT_RELEASE_FORM: ReleaseFormState = {
  package_slug: "",
  package_name: "",
  version: "1.0.0",
  execution_node_type: "http",
};

export default function MarketplaceAdminPage() {
  const router = useRouter();
  const { user } = useAuth();
  const canManage = user?.organization_role === "owner" || user?.organization_role === "admin";
  const canReview = user?.organization_role === "owner";

  const [catalog, setCatalog] = useState<MarketplacePackage[]>([]);
  const [installed, setInstalled] = useState<MarketplacePackage[]>([]);
  const [releases, setReleases] = useState<MarketplaceReleaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [installingSlug, setInstallingSlug] = useState<string | null>(null);
  const [reviewingReleaseId, setReviewingReleaseId] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [releaseForm, setReleaseForm] = useState<ReleaseFormState>(DEFAULT_RELEASE_FORM);

  const refreshData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [catalogData, installedData, releasesData] = await Promise.all([
        marketplaceApi.listPackages(),
        marketplaceApi.listInstalled(),
        canManage ? marketplaceApi.listReleases() : Promise.resolve([]),
      ]);
      setCatalog(catalogData);
      setInstalled(installedData);
      setReleases(releasesData);
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

  const pendingReleases = useMemo(
    () => releases.filter((release) => release.status === "pending_review"),
    [releases],
  );

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
    setPublishing(true);
    setError(null);
    try {
      await marketplaceApi.createRelease({
        package_slug: releaseForm.package_slug.trim(),
        package_name: releaseForm.package_name.trim() || undefined,
        version: releaseForm.version.trim(),
        execution_node_type: releaseForm.execution_node_type,
        ui_schema: {
          label: releaseForm.package_name.trim() || releaseForm.package_slug.trim(),
          description: "Published from admin marketplace",
          category: "integration",
        },
        config_schema: { type: "object" },
        config_defaults: {},
      });
      setReleaseForm(DEFAULT_RELEASE_FORM);
      await refreshData();
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to submit release."));
    } finally {
      setPublishing(false);
    }
  }, [refreshData, releaseForm]);

  if (!canManage) {
    return (
      <ProtectedRoute>
        <DashboardLayout>
          <Card className="max-w-2xl">
            <CardHeader>
              <CardTitle>Marketplace</CardTitle>
              <CardDescription>Organization admins can manage marketplace packages.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" onClick={() => void router.push("/admin/organization")}>
                Back to Organization
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
                Discover approved node packages and install them into your org.
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

          <Card>
            <CardHeader>
              <CardTitle>Approved packages</CardTitle>
              <CardDescription>
                Installed packages are available in the Graph Editor palette under Marketplace.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading ? (
                <div className="flex items-center gap-3 text-sm text-muted-foreground">
                  <Spinner size="sm" />
                  Loading packages...
                </div>
              ) : catalog.length === 0 ? (
                <p className="text-sm text-muted-foreground">No approved packages found.</p>
              ) : (
                catalog.map((pkg) => {
                  const currentInstall = installedBySlug.get(pkg.slug);
                  const installedVersion = currentInstall?.installed_release?.version ?? null;
                  const latestVersion = pkg.latest_release?.version ?? "-";
                  const upToDate = installedVersion && installedVersion === latestVersion;
                  return (
                    <div
                      key={pkg.slug}
                      className="flex items-center justify-between rounded-lg border border-border p-3"
                    >
                      <div className="space-y-1">
                        <p className="text-sm font-medium">{pkg.name}</p>
                        <p className="text-xs text-muted-foreground">{pkg.summary}</p>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline">{pkg.category}</Badge>
                          <Badge variant="secondary">latest {latestVersion}</Badge>
                          {installedVersion && (
                            <Badge variant={upToDate ? "default" : "outline"}>
                              installed {installedVersion}
                            </Badge>
                          )}
                        </div>
                      </div>
                      <Button
                        size="sm"
                        onClick={() => void handleInstall(pkg)}
                        disabled={installingSlug === pkg.slug}
                      >
                        {installingSlug === pkg.slug
                          ? "Installing..."
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
              <CardTitle>Publish release</CardTitle>
              <CardDescription>Submit a node package release for owner review.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="packageSlug">Package slug</Label>
                  <Input
                    id="packageSlug"
                    value={releaseForm.package_slug}
                    onChange={(event) =>
                      setReleaseForm((prev) => ({ ...prev, package_slug: event.target.value }))
                    }
                    placeholder="slack-alerts"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="packageName">Package name</Label>
                  <Input
                    id="packageName"
                    value={releaseForm.package_name}
                    onChange={(event) =>
                      setReleaseForm((prev) => ({ ...prev, package_name: event.target.value }))
                    }
                    placeholder="Slack Alerts"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="releaseVersion">Version</Label>
                  <Input
                    id="releaseVersion"
                    value={releaseForm.version}
                    onChange={(event) =>
                      setReleaseForm((prev) => ({ ...prev, version: event.target.value }))
                    }
                    placeholder="1.0.0"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="executionType">Execution node type</Label>
                  <Select
                    value={releaseForm.execution_node_type}
                    onValueChange={(value) =>
                      setReleaseForm((prev) => ({
                        ...prev,
                        execution_node_type: value as ReleaseFormState["execution_node_type"],
                      }))
                    }
                  >
                    <SelectTrigger id="executionType">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="http">HTTP</SelectItem>
                      <SelectItem value="prompt">Prompt</SelectItem>
                      <SelectItem value="tool">Tool</SelectItem>
                      <SelectItem value="transform">Transform</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <Button onClick={() => void handlePublishRelease()} disabled={publishing}>
                {publishing ? "Submitting..." : "Submit release"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Release review queue</CardTitle>
              <CardDescription>
                Pending release approvals. Owner role required for approval decisions.
              </CardDescription>
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
                        {release.package_slug} · {release.execution_node_type}
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
