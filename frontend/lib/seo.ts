export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://forgegraph.dev").replace(/\/$/, "");

export const SITE_NAME = "ForgeGraph";
export const SITE_TITLE = "ForgeGraph - AI Company Operating System";
export const SITE_DESCRIPTION =
  "ForgeGraph is an AI Company Operating System for creating, operating, and supervising AI-driven companies with objectives, departments, operations, approvals, deliverables, memory, and usage controls.";
export const SITE_KEYWORDS = [
  "AI company operating system",
  "AI company workspace",
  "AI operations",
  "AI departments",
  "AI deliverables",
  "autonomous company operations",
  "company command center",
  "AI approvals",
  "AI business operations",
  "AI operating models",
];

export const SOCIAL_IMAGE_PATH = "/og-image.png";
export const TWITTER_IMAGE_PATH = "/twitter-image.png";
export const SOCIAL_IMAGE_ALT =
  "ForgeGraph AI Company OS interface showing company operations, approvals, deliverables, and usage controls.";

export type SeoConfig = {
  title?: string;
  description?: string;
  canonicalPath?: string;
  imagePath?: string;
  twitterImagePath?: string;
  imageAlt?: string;
  keywords?: string[];
  noIndex?: boolean;
  type?: "website" | "article";
};

type RouteSeo = Omit<SeoConfig, "canonicalPath">;

const APP_ROUTE_SEO: Record<string, RouteSeo> = {
  "/": {
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    noIndex: false,
  },
  "/login": {
    title: "Sign In - ForgeGraph",
    description: "Sign in to ForgeGraph to operate AI-driven companies, review approvals, and continue company work.",
    noIndex: true,
  },
  "/register": {
    title: "Create Account - ForgeGraph",
    description: "Create a ForgeGraph account and start operating AI-driven companies from one company workspace.",
    noIndex: true,
  },
  "/companies": {
    title: "Companies - ForgeGraph",
    description: "Select, review, and operate AI-driven companies in ForgeGraph.",
    noIndex: true,
  },
  "/companies/new": {
    title: "Create an AI Company - ForgeGraph",
    description:
      "Create an AI-driven company by defining its objective, departments, operating rules, and first operation.",
    noIndex: true,
  },
  "/companies/[companyId]": {
    title: "Company Workspace - ForgeGraph",
    description:
      "Operate one AI-driven company with live operations, approvals, deliverables, memory, and usage controls.",
    noIndex: true,
  },
  "/graphs": {
    title: "Advanced Operating Models - ForgeGraph",
    description: "Manage the advanced operating models that define how ForgeGraph companies perform work.",
    noIndex: true,
  },
  "/workflows": {
    title: "Advanced Operating Models - ForgeGraph",
    description: "Manage advanced operating models behind ForgeGraph company operations.",
    noIndex: true,
  },
  "/workflows/[workflowId]": {
    title: "Advanced Operating Model Editor - ForgeGraph",
    description: "Edit an advanced operating model used by company operations.",
    noIndex: true,
  },
  "/runs": {
    title: "Operations - ForgeGraph",
    description: "Review ForgeGraph operation history, status, department activity, approvals, and deliverables.",
    noIndex: true,
  },
  "/runs/[runId]": {
    title: "Operation Detail - ForgeGraph",
    description: "Inspect one ForgeGraph operation, including department activity, deliverables, traces, and memory.",
    noIndex: true,
  },
  "/departments": {
    title: "Departments - ForgeGraph",
    description:
      "Review how ForgeGraph departments think, propose actions, join operations, and surface approval blockers.",
    noIndex: true,
  },
  "/agents": {
    title: "Departments - ForgeGraph",
    description: "Legacy route that redirects to ForgeGraph departments.",
    noIndex: true,
  },
  "/executions": {
    title: "Operations - ForgeGraph",
    description: "Legacy route that redirects to ForgeGraph operations.",
    noIndex: true,
  },
  "/executions/[executionId]": {
    title: "Operation Detail - ForgeGraph",
    description: "Legacy route that redirects to a ForgeGraph operation.",
    noIndex: true,
  },
  "/approvals": {
    title: "Approvals - ForgeGraph",
    description: "Review and resolve human decisions required by ForgeGraph company operations.",
    noIndex: true,
  },
  "/memory": {
    title: "Knowledge - ForgeGraph",
    description: "Inspect organization-scoped memory and knowledge used by ForgeGraph company operations.",
    noIndex: true,
  },
  "/settings": {
    title: "Settings - ForgeGraph",
    description: "Manage ForgeGraph organization, account, usage, and operating settings.",
    noIndex: true,
  },
  "/admin": {
    title: "Admin - ForgeGraph",
    description: "Manage ForgeGraph administrative settings, usage, organization controls, and governance.",
    noIndex: true,
  },
};

export function absoluteUrl(path = "/"): string {
  if (/^https?:\/\//i.test(path)) {
    return path;
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${SITE_URL}${normalizedPath}`;
}

function pathWithoutQuery(asPath?: string): string {
  const path = (asPath || "/").split("#")[0]?.split("?")[0] || "/";
  return path.startsWith("/") ? path : "/";
}

export function getRouteSeo(pathname: string, asPath?: string): SeoConfig {
  const routeSeo = APP_ROUTE_SEO[pathname] ?? {
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    noIndex: true,
  };

  return {
    ...routeSeo,
    canonicalPath: pathWithoutQuery(asPath),
  };
}
