import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { QuickToolBar } from "@/components/graph-editor/QuickToolBar";
import type { MarketplacePackage } from "@/lib/api";

let idCounter = 0;
const nextId = () => `id-${++idCounter}`;

const buildPackage = (overrides: Partial<MarketplacePackage>): MarketplacePackage => ({
  id: nextId(),
  slug: "slack-alerts",
  name: "Slack Alerts",
  summary: "Send Slack alerts.",
  category: "communication",
  icon: "slack",
  docs_url: "",
  homepage_url: "",
  latest_release: {
    id: nextId(),
    version: "1.0.0",
    changelog: "",
    status: "approved",
    package_kind: "runtime_tool",
    execution_node_type: "tool",
    ui_schema: { label: "Slack Alerts" },
    config_schema: { type: "object" },
    config_defaults: { tool: "slack_alerts" },
    runtime_manifest: {
      name: "slack_alerts",
      version: "1.0.0",
      kind: "http",
      http: { url: "https://slack.com/api/chat.postMessage", method: "POST" },
    },
    manifest_version: 1,
    cloud_allowed: true,
    review_notes: "",
    created_at: "2026-02-05T12:00:00Z",
  },
  installed_release: {
    id: nextId(),
    version: "1.0.0",
    changelog: "",
    status: "approved",
    package_kind: "runtime_tool",
    execution_node_type: "tool",
    ui_schema: { label: "Slack Alerts" },
    config_schema: { type: "object" },
    config_defaults: { tool: "slack_alerts" },
    runtime_manifest: {
      name: "slack_alerts",
      version: "1.0.0",
      kind: "http",
      http: { url: "https://slack.com/api/chat.postMessage", method: "POST" },
    },
    manifest_version: 1,
    cloud_allowed: true,
    review_notes: "",
    created_at: "2026-02-05T12:00:00Z",
  },
  installed_at: "2026-02-05T12:00:00Z",
  runtime_delivery: {
    state: "ready",
    reason: "ready",
    package_kind: "runtime_tool",
    cloud_allowed: true,
    manifest_version: 1,
    checksum: "abc123",
  },
  ...overrides,
});

describe("QuickToolBar", () => {
  const setupUser = () => {
    const user = userEvent.setup();
    return {
      ...user,
      click: (element: HTMLElement) => act(async () => user.click(element)),
      type: (element: HTMLElement, text: string) => act(async () => user.type(element, text)),
    };
  };

  it("renders installed integration tools from marketplace payload", () => {
    const packages = [
      buildPackage({ slug: "slack-alerts", name: "Slack Alerts", icon: "slack" }),
      buildPackage({ slug: "notion-page-upsert", name: "Notion Page Upsert", icon: "notion" }),
    ];
    const onSelectPackage = jest.fn();

    render(<QuickToolBar marketplaceNodes={packages} onSelectPackage={onSelectPackage} />);

    // Tiles render package names as labels below icons
    expect(screen.getByText("Slack Alerts")).toBeInTheDocument();
    expect(screen.getByText("Notion Page Upsert")).toBeInTheDocument();
    // "More" button opens the browse dialog
    expect(screen.getByRole("button", { name: /browse tool actions/i })).toBeInTheDocument();
  });

  it("calls onSelectPackage when a featured tool is clicked", async () => {
    const user = setupUser();
    const packages = [buildPackage({ slug: "slack-alerts", name: "Slack Alerts" })];
    const onSelectPackage = jest.fn();

    render(<QuickToolBar marketplaceNodes={packages} onSelectPackage={onSelectPackage} />);

    // Tile buttons use the package name as their title and visible label
    await user.click(screen.getByRole("button", { name: /slack alerts/i }));

    expect(onSelectPackage).toHaveBeenCalledTimes(1);
    expect(onSelectPackage).toHaveBeenCalledWith(expect.objectContaining({ slug: "slack-alerts" }));
  });

  it("supports browse dialog search and selection", async () => {
    const user = setupUser();
    const packages = [
      buildPackage({ slug: "slack-alerts", name: "Slack Alerts" }),
      buildPackage({ slug: "gmail-send-email", name: "Gmail Send Email", icon: "gmail" }),
    ];
    const onSelectPackage = jest.fn();

    render(<QuickToolBar marketplaceNodes={packages} onSelectPackage={onSelectPackage} />);

    await user.click(screen.getByRole("button", { name: /browse tool actions/i }));
    const search = screen.getByRole("textbox", { name: /search tool actions/i });
    await user.type(search, "gmail");
    await user.click(screen.getByRole("button", { name: /gmail send email/i }));

    expect(onSelectPackage).toHaveBeenCalledWith(expect.objectContaining({ slug: "gmail-send-email" }));
  });

  it("hides template-only packages from quick add", () => {
    const packages = [
      buildPackage({
        slug: "template-only",
        name: "Template Only",
        runtime_delivery: {
          state: "template",
          reason: "template_only",
          package_kind: "template_http",
          cloud_allowed: true,
          manifest_version: 1,
          checksum: null,
        },
        latest_release: {
          ...buildPackage({}).latest_release!,
          package_kind: "template_http",
          execution_node_type: "http",
          config_defaults: { url: "https://example.com" },
          runtime_manifest: null,
        },
        installed_release: {
          ...buildPackage({}).installed_release!,
          package_kind: "template_http",
          execution_node_type: "http",
          config_defaults: { url: "https://example.com" },
          runtime_manifest: null,
        },
      }),
    ];

    render(<QuickToolBar marketplaceNodes={packages} onSelectPackage={jest.fn()} />);

    expect(screen.queryByRole("button", { name: /add template only integration node/i })).not.toBeInTheDocument();
    expect(screen.getByText(/no runtime-ready tool actions yet/i)).toBeInTheDocument();
  });
});
