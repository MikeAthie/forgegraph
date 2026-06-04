import type { MarketplacePackage } from "./api";

const DELIVERY_REASON_LABELS: Record<string, string> = {
  ready: "Runtime-ready",
  template_only: "Template only",
  cloud_not_allowed: "Self-host only",
  runtime_transform_not_supported: "Runtime transforms are not supported in Cloud yet",
  exec_not_supported_in_cloud: "Exec tools are blocked in Cloud",
  missing_runtime_manifest: "Missing runtime manifest",
  unsupported_runtime_tool_kind: "Unsupported runtime manifest kind",
};

const PACKAGE_KIND_LABELS: Record<string, string> = {
  template_http: "Template HTTP",
  template_prompt: "Template Prompt",
  runtime_tool: "Runtime Tool",
  runtime_transform: "Runtime Transform",
};

export function getMarketplaceReleaseLabel(packageKind?: string | null): string {
  if (!packageKind) return "Package";
  return PACKAGE_KIND_LABELS[packageKind] ?? packageKind.replace(/_/g, " ");
}

export function getMarketplaceReasonLabel(reason?: string | null): string {
  if (!reason) return "Unknown";
  return DELIVERY_REASON_LABELS[reason] ?? reason.replace(/_/g, " ");
}

function isMarketplacePackageInstalled(pkg: MarketplacePackage): boolean {
  return Boolean(pkg.installed_release);
}

function isMarketplacePackageRuntimeReady(pkg: MarketplacePackage): boolean {
  return isMarketplacePackageInstalled(pkg) && pkg.runtime_delivery?.state === "ready";
}

function isMarketplacePackageTemplateOnly(pkg: MarketplacePackage): boolean {
  return pkg.runtime_delivery?.state === "template";
}

export function canAddMarketplacePackageToEditor(pkg: MarketplacePackage): boolean {
  if (!isMarketplacePackageInstalled(pkg)) return false;
  const state = pkg.runtime_delivery?.state;
  return state === "ready" || state === "template";
}

export function canQuickAddMarketplacePackage(pkg: MarketplacePackage): boolean {
  return (
    isMarketplacePackageInstalled(pkg) &&
    pkg.runtime_delivery?.state === "ready" &&
    pkg.runtime_delivery?.package_kind === "runtime_tool"
  );
}

export function getMarketplacePackageStatusLabel(pkg: MarketplacePackage): string {
  const state = pkg.runtime_delivery?.state;
  if (state === "ready") return "Runtime-ready";
  if (state === "template") return "Template only";
  if (state === "blocked") return "Blocked";
  if (state === "invalid") return "Invalid";
  if (isMarketplacePackageInstalled(pkg)) return "Installed";
  return "Not installed";
}

export function getMarketplacePackageReason(pkg: MarketplacePackage): string | null {
  const state = pkg.runtime_delivery?.state;
  const reason = pkg.runtime_delivery?.reason;
  if (!reason) return null;
  if (state === "ready") return "This package is included in tenant manifest delivery.";
  if (state === "template") return "This package is an editor preset. It does not ship runtime code.";
  return getMarketplaceReasonLabel(reason);
}

export function getMarketplacePackageDescription(pkg: MarketplacePackage): string {
  const summary = (pkg.summary || "").trim();
  const reason = getMarketplacePackageReason(pkg);
  if (summary && reason) return `${summary} ${reason}`;
  if (summary) return summary;
  if (reason) return reason;
  return "Installed from marketplace.";
}

export function getMarketplacePackageBadges(pkg: MarketplacePackage): string[] {
  const badges = [
    "Marketplace",
    getMarketplaceReleaseLabel(pkg.runtime_delivery?.package_kind ?? pkg.installed_release?.package_kind ?? null),
    getMarketplacePackageStatusLabel(pkg),
  ];

  if (pkg.runtime_delivery?.cloud_allowed === false) {
    badges.push("Self-host");
  }

  return badges.filter((badge, index, all) => all.indexOf(badge) === index);
}

function getReleaseUiSchema(pkg: MarketplacePackage): Record<string, unknown> {
  return (pkg.installed_release?.ui_schema ?? pkg.latest_release?.ui_schema ?? {}) as Record<string, unknown>;
}

export function isHermesGatewayPackage(pkg: MarketplacePackage): boolean {
  const uiSchema = getReleaseUiSchema(pkg);
  return uiSchema.source === "NousResearch/hermes-agent" || pkg.slug.startsWith("hermes-");
}

export function getMarketplacePackageSourceLabel(pkg: MarketplacePackage): string | null {
  const uiSchema = getReleaseUiSchema(pkg);
  const source = typeof uiSchema.source === "string" ? uiSchema.source.trim() : "";
  if (source) return source;
  return isHermesGatewayPackage(pkg) ? "NousResearch/hermes-agent" : null;
}

export function getMarketplacePackageSourcePath(pkg: MarketplacePackage): string | null {
  const uiSchema = getReleaseUiSchema(pkg);
  const sourcePath = typeof uiSchema.source_path === "string" ? uiSchema.source_path.trim() : "";
  return sourcePath || null;
}

export function getMarketplacePackageSetupFields(pkg: MarketplacePackage): string[] {
  const uiSchema = getReleaseUiSchema(pkg);
  const setupFields = uiSchema.setup_fields;
  const capabilityFields =
    pkg.installed_release?.gateway_capability?.setup_requirements ??
    pkg.latest_release?.gateway_capability?.setup_requirements ??
    [];
  const fields = [
    ...(Array.isArray(setupFields) ? setupFields : []),
    ...(Array.isArray(capabilityFields) ? capabilityFields : []),
  ];
  return fields.filter((field): field is string => typeof field === "string" && field.trim().length > 0);
}
