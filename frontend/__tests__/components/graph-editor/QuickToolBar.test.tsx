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
    execution_node_type: "http",
    ui_schema: { label: "Slack Alerts" },
    config_schema: { type: "object" },
    config_defaults: { method: "POST", url: "https://slack.com/api/chat.postMessage" },
    created_at: "2026-02-05T12:00:00Z",
  },
  installed_release: {
    id: nextId(),
    version: "1.0.0",
    changelog: "",
    status: "approved",
    execution_node_type: "http",
    ui_schema: { label: "Slack Alerts" },
    config_schema: { type: "object" },
    config_defaults: { method: "POST", url: "https://slack.com/api/chat.postMessage" },
    created_at: "2026-02-05T12:00:00Z",
  },
  installed_at: "2026-02-05T12:00:00Z",
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

    render(
      <QuickToolBar
        marketplaceNodes={packages}
        onSelectPackage={onSelectPackage}
      />,
    );

    expect(screen.getByText("Quick Tools")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add slack alerts integration node/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add notion page upsert integration node/i })).toBeInTheDocument();
  });

  it("calls onSelectPackage when a featured tool is clicked", async () => {
    const user = setupUser();
    const packages = [buildPackage({ slug: "slack-alerts", name: "Slack Alerts" })];
    const onSelectPackage = jest.fn();

    render(
      <QuickToolBar
        marketplaceNodes={packages}
        onSelectPackage={onSelectPackage}
      />,
    );

    await user.click(screen.getByRole("button", { name: /add slack alerts integration node/i }));

    expect(onSelectPackage).toHaveBeenCalledTimes(1);
    expect(onSelectPackage).toHaveBeenCalledWith(
      expect.objectContaining({ slug: "slack-alerts" }),
    );
  });

  it("supports browse dialog search and selection", async () => {
    const user = setupUser();
    const packages = [
      buildPackage({ slug: "slack-alerts", name: "Slack Alerts" }),
      buildPackage({ slug: "gmail-send-email", name: "Gmail Send Email", icon: "gmail" }),
    ];
    const onSelectPackage = jest.fn();

    render(
      <QuickToolBar
        marketplaceNodes={packages}
        onSelectPackage={onSelectPackage}
      />,
    );

    await user.click(screen.getByRole("button", { name: /browse integration tools/i }));
    const search = screen.getByRole("textbox", { name: /search integration tools/i });
    await user.type(search, "gmail");
    await user.click(screen.getByRole("button", { name: /gmail send email/i }));

    expect(onSelectPackage).toHaveBeenCalledWith(
      expect.objectContaining({ slug: "gmail-send-email" }),
    );
  });
});
