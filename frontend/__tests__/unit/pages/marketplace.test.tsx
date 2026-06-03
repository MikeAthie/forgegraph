import type { ReactNode } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/router";

import MarketplaceAdminPage from "@/pages/admin/marketplace";
import { useAuth } from "@/contexts/AuthContext";
import { marketplaceApi } from "@/lib/api";

jest.mock("@/components/DashboardLayout", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

jest.mock("@/components/ProtectedRoute", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

jest.mock("@/contexts/AuthContext");
jest.mock("@/lib/api", () => {
  const actual = jest.requireActual("@/lib/api");
  return {
    ...actual,
    marketplaceApi: {
      ...actual.marketplaceApi,
      listPackages: jest.fn(),
      listInstalled: jest.fn(),
      listReleases: jest.fn(),
      getRuntimePreview: jest.fn(),
      install: jest.fn(),
      reviewRelease: jest.fn(),
      createRelease: jest.fn(),
    },
  };
});
jest.mock("next/router", () => ({
  useRouter: jest.fn(),
}));

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
const mockedMarketplaceApi = marketplaceApi as jest.Mocked<typeof marketplaceApi>;

const buildReadyPackage = () => ({
  id: "pkg-ready",
  slug: "crm-lookup",
  name: "CRM Lookup",
  summary: "Runtime-backed CRM lookup.",
  category: "developer",
  icon: "sparkles",
  docs_url: "",
  homepage_url: "",
  latest_release: {
    id: "rel-ready",
    version: "1.0.0",
    changelog: "",
    status: "approved",
    package_kind: "runtime_tool",
    execution_node_type: "tool",
    ui_schema: { label: "CRM Lookup" },
    config_schema: { type: "object" },
    config_defaults: { tool: "crm_lookup" },
    runtime_manifest: {
      name: "crm_lookup",
      version: "1.0.0",
      kind: "http",
      http: { url: "https://example.com/crm", method: "POST" },
    },
    manifest_version: 1,
    cloud_allowed: true,
    review_notes: "",
    created_at: "2026-02-05T12:00:00Z",
  },
  installed_release: {
    id: "rel-ready",
    version: "1.0.0",
    changelog: "",
    status: "approved",
    package_kind: "runtime_tool",
    execution_node_type: "tool",
    ui_schema: { label: "CRM Lookup" },
    config_schema: { type: "object" },
    config_defaults: { tool: "crm_lookup" },
    runtime_manifest: {
      name: "crm_lookup",
      version: "1.0.0",
      kind: "http",
      http: { url: "https://example.com/crm", method: "POST" },
    },
    manifest_version: 1,
    cloud_allowed: true,
    review_notes: "",
    created_at: "2026-02-05T12:00:00Z",
  },
  installed_at: "2026-02-05T12:00:00Z",
  install_metadata: {
    source: "marketplace",
    runtime_delivery: { state: "ready" },
  },
  runtime_delivery: {
    state: "ready",
    reason: "ready",
    package_kind: "runtime_tool",
    cloud_allowed: true,
    manifest_version: 1,
    checksum: "abc123",
  },
});

const buildHermesGatewayPackage = () => ({
  id: "pkg-hermes",
  slug: "hermes-telegram-gateway",
  name: "Hermes Telegram Gateway",
  summary: "Connect Telegram bot conversations, voice messages, and channel delivery to workflows.",
  category: "communication",
  icon: "telegram",
  docs_url: "https://github.com/NousResearch/hermes-agent/tree/main/gateway/platforms",
  homepage_url: "https://github.com/NousResearch/hermes-agent",
  latest_release: {
    id: "rel-hermes",
    version: "1.0.0",
    changelog: "Seeded from NousResearch Hermes Agent gateway platform catalog.",
    status: "approved",
    package_kind: "template_http",
    execution_node_type: "http",
    ui_schema: {
      label: "Hermes Telegram Gateway",
      source: "NousResearch/hermes-agent",
      source_path: "gateway/platforms/telegram.py",
      setup_fields: ["TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS"],
    },
    config_schema: { type: "object" },
    config_defaults: { url: "https://api.telegram.org/bot{{credential.api_key}}/sendMessage" },
    runtime_manifest: null,
    manifest_version: 2,
    cloud_allowed: true,
    review_notes: "",
    created_at: "2026-02-05T12:00:00Z",
  },
  installed_release: null,
  runtime_delivery: {
    state: "template",
    reason: "template_only",
    package_kind: "template_http",
    cloud_allowed: true,
    manifest_version: 2,
    checksum: null,
  },
});

const buildTemplatePackage = () => ({
  id: "pkg-template",
  slug: "template-http",
  name: "Template HTTP",
  summary: "Template-only HTTP preset.",
  category: "developer",
  icon: "sparkles",
  docs_url: "",
  homepage_url: "",
  latest_release: {
    id: "rel-template",
    version: "1.0.0",
    changelog: "",
    status: "approved",
    package_kind: "template_http",
    execution_node_type: "http",
    ui_schema: { label: "Template HTTP" },
    config_schema: { type: "object" },
    config_defaults: { url: "https://example.com" },
    runtime_manifest: null,
    manifest_version: 1,
    cloud_allowed: true,
    review_notes: "",
    created_at: "2026-02-05T12:00:00Z",
  },
  installed_release: {
    id: "rel-template",
    version: "1.0.0",
    changelog: "",
    status: "approved",
    package_kind: "template_http",
    execution_node_type: "http",
    ui_schema: { label: "Template HTTP" },
    config_schema: { type: "object" },
    config_defaults: { url: "https://example.com" },
    runtime_manifest: null,
    manifest_version: 1,
    cloud_allowed: true,
    review_notes: "",
    created_at: "2026-02-05T12:00:00Z",
  },
  installed_at: "2026-02-05T12:00:00Z",
  install_metadata: {
    source: "marketplace",
    runtime_delivery: { state: "template" },
  },
  runtime_delivery: {
    state: "template",
    reason: "template_only",
    package_kind: "template_http",
    cloud_allowed: true,
    manifest_version: 1,
    checksum: null,
  },
});

describe("MarketplaceAdminPage", () => {
  const user = userEvent.setup();

  beforeAll(() => {
    Object.defineProperty(HTMLElement.prototype, "hasPointerCapture", {
      configurable: true,
      value: () => false,
    });
    Object.defineProperty(HTMLElement.prototype, "setPointerCapture", {
      configurable: true,
      value: () => {},
    });
    Object.defineProperty(HTMLElement.prototype, "releasePointerCapture", {
      configurable: true,
      value: () => {},
    });
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: () => {},
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseRouter.mockReturnValue({
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      pathname: "/admin/marketplace",
      query: {},
      asPath: "/admin/marketplace",
    } as any);
    mockUseAuth.mockReturnValue({
      user: {
        id: "user-1",
        email: "admin@example.com",
        created_at: "2026-01-01T00:00:00Z",
        is_active: true,
        default_organization_id: "org-1",
        organization_role: "admin",
      },
      isAuthenticated: true,
      loading: false,
      error: null,
      login: jest.fn(),
      register: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn(),
      clearError: jest.fn(),
    });
    mockedMarketplaceApi.listPackages.mockResolvedValue([]);
    mockedMarketplaceApi.listInstalled.mockResolvedValue([]);
    mockedMarketplaceApi.listReleases.mockResolvedValue([]);
    mockedMarketplaceApi.getRuntimePreview.mockResolvedValue({
      tenant_id: "org-1",
      manifest_version: 1,
      checksum: "preview-checksum",
      generated_at: "2026-03-12T10:00:00Z",
      packages: [],
      tools: [],
    });
    mockedMarketplaceApi.install.mockResolvedValue({} as any);
    mockedMarketplaceApi.reviewRelease.mockResolvedValue({} as any);
    mockedMarketplaceApi.createRelease.mockResolvedValue({
      id: "release-1",
      package_slug: "crm-lookup",
      version: "1.0.0",
      status: "pending_review",
    });
  });

  it("renders runtime preview and truthful delivery labels", async () => {
    mockedMarketplaceApi.listPackages.mockResolvedValue([buildReadyPackage(), buildTemplatePackage()] as any);
    mockedMarketplaceApi.listInstalled.mockResolvedValue([buildReadyPackage(), buildTemplatePackage()] as any);
    mockedMarketplaceApi.getRuntimePreview.mockResolvedValue({
      tenant_id: "org-1",
      manifest_version: 1,
      checksum: "preview-checksum",
      generated_at: "2026-03-12T10:00:00Z",
      packages: [
        {
          package_slug: "crm-lookup",
          package_name: "CRM Lookup",
          release_id: "rel-ready",
          release_version: "1.0.0",
          package_kind: "runtime_tool",
          delivery_state: "ready",
          delivery_reason: "ready",
          cloud_allowed: true,
          manifest_version: 1,
          manifest_checksum: "abc123",
        },
        {
          package_slug: "template-http",
          package_name: "Template HTTP",
          release_id: "rel-template",
          release_version: "1.0.0",
          package_kind: "template_http",
          delivery_state: "template",
          delivery_reason: "template_only",
          cloud_allowed: true,
          manifest_version: 1,
          manifest_checksum: null,
        },
      ],
      tools: [{ name: "crm_lookup", kind: "http", version: "1.0.0" }],
    });

    render(<MarketplaceAdminPage />);

    expect(await screen.findByText(/runtime manifest preview/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/preview-checksum/i)).toBeInTheDocument();
    });
    expect(screen.getAllByText(/runtime-ready/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/template only/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/crm_lookup/i)).toBeInTheDocument();
  });

  it("surfaces Hermes gateway connector source metadata and setup keys", async () => {
    mockedMarketplaceApi.listPackages.mockResolvedValue([buildHermesGatewayPackage()] as any);

    render(<MarketplaceAdminPage />);

    expect(await screen.findByText(/Hermes gateway connector catalog/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/1 gateway connectors/i)).toBeInTheDocument();
    });
    expect(screen.getAllByText(/NousResearch\/hermes-agent/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/gateway\/platforms\/telegram.py/i)).toBeInTheDocument();
    expect(screen.getAllByText(/TELEGRAM_BOT_TOKEN/i).length).toBeGreaterThan(0);
  });

  it("derives release payloads from the selected package class", async () => {
    render(<MarketplaceAdminPage />);

    expect(await screen.findByText(/publish release/i)).toBeInTheDocument();

    await act(async () => user.type(screen.getByLabelText(/package slug/i), "crm-lookup"));
    await act(async () => user.type(screen.getByLabelText(/package name/i), "CRM Lookup"));
    await act(async () => user.click(screen.getByRole("button", { name: /submit release/i })));

    await waitFor(() => {
      expect(mockedMarketplaceApi.createRelease).toHaveBeenCalledWith(
        expect.objectContaining({
          package_slug: "crm-lookup",
          package_name: "CRM Lookup",
          package_kind: "template_http",
          execution_node_type: "http",
          config_defaults: {},
          runtime_manifest: null,
        }),
      );
    });
  });
});
