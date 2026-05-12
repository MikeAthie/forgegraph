import axios, { type AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from "axios";
import type { GraphJson, GraphVersion, CreateGraphVersionInput } from "./graph-types";
import { sanitizeErrorMessage } from "./error-messages";

export interface User {
  id: string;
  email: string;
  created_at: string;
  is_active: boolean;
  default_organization_id?: string | null;
  organization_role?: "owner" | "admin" | "member" | "viewer" | null;
}

export interface AccessTokenResponse {
  access: string;
}

export interface WebSocketTicketResponse {
  ticket: string;
  expires_in_seconds: number;
  expires_at?: string;
  org_id?: string;
}

type ApiMeta = {
  requestId: string;
  timestamp: string;
  pagination?: {
    page: number;
    pageSize: number;
    totalCount: number;
    totalPages: number;
    hasNext: boolean;
    hasPrevious: boolean;
  };
};

export type ApiSuccessResponse<T> = {
  data: T;
  meta: ApiMeta;
};

type ApiErrorDetail = {
  field?: string;
  issue?: string;
  [key: string]: unknown;
};

type ApiErrorResponse = {
  error: {
    code: string;
    message: string;
    details?: ApiErrorDetail[];
    documentationUrl?: string;
  };
  meta: ApiMeta;
};

/**
 * Extract and sanitize an error message from an API error.
 *
 * This function extracts the error message from various response formats
 * and sanitizes it to provide user-friendly messages instead of technical details.
 *
 * @param err - The error object (typically an AxiosError)
 * @param fallback - Fallback message if no error message can be extracted
 * @returns A user-friendly error message
 */
export const getApiErrorMessage = (err: unknown, fallback: string): string => {
  const axiosError = err as AxiosError;
  const data = axiosError?.response?.data as any;

  // If no response data, check for network errors
  if (!data) {
    if (axiosError?.message) {
      return sanitizeErrorMessage(axiosError.message, fallback);
    }
    return fallback;
  }

  // Extract raw message from various response formats
  let rawMessage: string | undefined;

  if (typeof data === "string") {
    rawMessage = data;
  } else if (data.error) {
    if (typeof data.error === "string") {
      rawMessage = data.error;
    } else {
      rawMessage = data.error.message || data.error.detail;
    }
  } else {
    rawMessage = data.detail || data.message;
  }

  // Sanitize and return the message
  if (rawMessage) {
    return sanitizeErrorMessage(rawMessage, fallback);
  }

  return fallback;
};

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const API_PATHS = {
  wsTicket: "/api/ws-ticket",
  auth: {
    login: "/api/auth/login",
    register: "/api/auth/register",
    logout: "/api/auth/logout",
    refresh: "/api/auth/refresh",
    me: "/api/auth/me",
    wsTicket: "/api/auth/ws-ticket",
    ssoLogin: "/api/auth/sso/auth0/login",
    ssoCallback: "/api/auth/sso/auth0/callback",
    ssoProvider: "/api/auth/sso/provider",
  },
  graphs: {
    listCreate: "/api/graphs/",
    detail: (graphId: string) => `/api/graphs/${graphId}`,
    versions: (graphId: string) => `/api/graphs/${graphId}/versions`,
    latestVersion: (graphId: string) => `/api/graphs/${graphId}/versions/latest`,
    versionDetail: (graphId: string, versionId: string) => `/api/graphs/${graphId}/versions/${versionId}`,
    memoryConfig: (graphId: string) => `/api/graphs/${graphId}/memory-config`,
  },
  prompts: {
    listCreate: "/api/prompts/",
    detail: (promptId: string) => `/api/prompts/${promptId}`,
    clone: (promptId: string) => `/api/prompts/${promptId}/clone`,
    publish: (promptId: string) => `/api/prompts/${promptId}/publish`,
  },
  credentials: {
    listCreate: "/api/credentials/",
    detail: (credentialId: string) => `/api/credentials/${credentialId}`,
    oauthProviders: "/api/credentials/oauth/providers",
    oauthStart: "/api/credentials/oauth/start",
    oauthCallback: "/api/credentials/oauth/callback",
  },
  integrations: {
    httpTest: "/api/integrations/http/test",
  },
  interaction: {
    currentBrief: "/api/interaction/briefs/current",
    events: "/api/interaction/events",
  },
  inventory: {
    overview: "/api/inventory/overview",
    reservations: "/api/inventory/reservations",
    releaseReservation: (reservationId: string) => `/api/inventory/reservations/${reservationId}/release`,
    extendReservation: (reservationId: string) => `/api/inventory/reservations/${reservationId}/extend`,
    orderShell: (reservationId: string) => `/api/inventory/reservations/${reservationId}/order-shell`,
    expireDue: "/api/inventory/reservations/expire-due",
  },
  commerce: {
    checkoutSessions: "/api/commerce/checkout-sessions",
    overview: "/api/commerce/overview",
    orders: "/api/commerce/orders",
    orderDetail: (orderId: string) => `/api/commerce/orders/${orderId}`,
    fulfillmentBlock: (orderId: string) => `/api/commerce/orders/${orderId}/fulfillment/block`,
    fulfillmentReady: (orderId: string) => `/api/commerce/orders/${orderId}/fulfillment/mark-ready`,
    fulfillmentShip: (orderId: string) => `/api/commerce/orders/${orderId}/fulfillment/ship`,
    fulfillmentDeliver: (orderId: string) => `/api/commerce/orders/${orderId}/fulfillment/deliver`,
    operatorNote: (orderId: string) => `/api/commerce/orders/${orderId}/operator-note`,
  },
  companyOps: {
    overview: "/api/company-ops/overview",
    signals: "/api/company-ops/signals",
    qualifySignal: (signalId: string) => `/api/company-ops/signals/${signalId}/qualify`,
    opportunities: "/api/company-ops/opportunities",
    opportunityStatus: (opportunityId: string) => `/api/company-ops/opportunities/${opportunityId}/status`,
    publicationDrafts: "/api/company-ops/publication-drafts",
    publicationDraftApproval: (draftId: string) => `/api/company-ops/publication-drafts/${draftId}/request-approval`,
    procurementDrafts: "/api/company-ops/procurement-drafts",
    procurementDraftApproval: (draftId: string) => `/api/company-ops/procurement-drafts/${draftId}/request-approval`,
    operations: "/api/company-ops/operations",
    operationObjectiveEvaluation: (operationId: string) =>
      `/api/company-ops/operations/${operationId}/objective-evaluation`,
  },
  operatingModels: {
    packs: "/api/operating-model-packs",
    pack: (packId: string) => `/api/operating-model-packs/${packId}`,
    compilePack: (packId: string) => `/api/operating-model-packs/${packId}/compile`,
    companyOperatingModel: (companyId: string) => `/api/companies/${companyId}/operating-model`,
    installPack: (companyId: string, packId: string) =>
      `/api/companies/${companyId}/operating-model/packs/${packId}/install`,
    upgradePack: (companyId: string, packId: string) =>
      `/api/companies/${companyId}/operating-model/packs/${packId}/upgrade`,
    removePack: (companyId: string, packId: string) => `/api/companies/${companyId}/operating-model/packs/${packId}`,
    programs: (companyId: string) => `/api/companies/${companyId}/programs`,
    program: (programId: string) => `/api/programs/${programId}`,
    advanceStage: (programId: string, stageId: string) => `/api/programs/${programId}/stages/${stageId}/advance`,
    launchStageOperation: (programId: string, stageId: string) =>
      `/api/programs/${programId}/stages/${stageId}/operations/launch`,
    generateStageOutputs: (programId: string, stageId: string) =>
      `/api/programs/${programId}/stages/${stageId}/outputs/generate`,
    validationPacket: (programId: string) => `/api/programs/${programId}/validation-packet`,
    assertions: "/api/assertions",
    validationDecisions: "/api/validation-decisions",
    workArtifacts: "/api/work-artifacts",
    workArtifact: (artifactId: string) => `/api/work-artifacts/${artifactId}`,
    artifactRevisions: (artifactId: string) => `/api/work-artifacts/${artifactId}/revisions`,
    artifactLineage: (artifactId: string) => `/api/work-artifacts/${artifactId}/lineage`,
    canonicalRevision: (artifactId: string) => `/api/work-artifacts/${artifactId}/canonical-revision`,
    runEvaluation: "/api/evaluations/run",
    evaluation: (evaluationId: string) => `/api/evaluations/${evaluationId}`,
    periodicReviews: "/api/periodic-reviews",
    runPeriodicReview: (reviewId: string) => `/api/periodic-reviews/${reviewId}/run`,
    metricSnapshots: "/api/metric-snapshots",
    reportRuns: "/api/report-runs",
    policyEvaluations: "/api/policy-evaluations",
    toolExecutions: "/api/tool-executions",
    reworkPlans: "/api/rework-plans",
    executeReworkPlan: (planId: string) => `/api/rework-plans/${planId}/execute`,
    stateProjections: "/api/state-projections",
  },
  companyBlueprints: {
    compile: "/api/company-blueprints/compile",
    createCompany: "/api/companies/from-blueprint",
  },
  storefront: {
    products: (companySlug: string) => `/api/storefront/${companySlug}/products`,
    checkoutSessions: (companySlug: string) => `/api/storefront/${companySlug}/checkout-sessions`,
    orderStatus: (companySlug: string, token: string) => `/api/storefront/${companySlug}/orders/${token}`,
  },
  runs: {
    list: "/api/runs/",
    detail: (runId: string) => `/api/runs/${runId}`,
    start: "/api/runs/start",
    invoke: "/api/runs/invoke",
    cancel: (runId: string) => `/api/runs/${runId}/cancel`,
    resume: (runId: string) => `/api/runs/${runId}/resume`,
    replay: (runId: string) => `/api/runs/${runId}/replay`,
  },
  approvals: {
    list: "/api/approvals/",
    count: "/api/approvals/count",
    detail: (approvalId: string) => `/api/approvals/${approvalId}`,
  },
  archive: {
    assets: "/api/archive/assets",
    assetVersions: (assetId: string) => `/api/archive/assets/${assetId}/versions`,
    assetVersionContent: (assetId: string, versionId: string) =>
      `/api/archive/assets/${assetId}/versions/${versionId}/content`,
    mediaGenerations: "/api/archive/media-generations",
    mediaGeneration: (jobId: string) => `/api/archive/media-generations/${jobId}`,
    mediaGenerationPoll: (jobId: string) => `/api/archive/media-generations/${jobId}/poll`,
  },
  workflows: {
    listCreate: "/api/workflows/",
    detail: (workflowId: string) => `/api/workflows/${workflowId}`,
    versions: (workflowId: string) => `/api/workflows/${workflowId}/versions`,
    latestVersion: (workflowId: string) => `/api/workflows/${workflowId}/versions/latest`,
    versionDetail: (workflowId: string, versionId: string) => `/api/workflows/${workflowId}/versions/${versionId}`,
    memoryConfig: (workflowId: string) => `/api/workflows/${workflowId}/memory-config`,
  },
  executions: {
    list: "/api/executions/",
    detail: (executionId: string) => `/api/executions/${executionId}`,
    start: "/api/executions/start",
    invoke: "/api/executions/invoke",
    cancel: (executionId: string) => `/api/executions/${executionId}/cancel`,
    resume: (executionId: string) => `/api/executions/${executionId}/resume`,
    replay: (executionId: string) => `/api/executions/${executionId}/replay`,
  },
  decisions: {
    list: "/api/decisions/",
    count: "/api/decisions/count",
    detail: (decisionId: string) => `/api/decisions/${decisionId}`,
  },
  agents: {
    list: "/api/agents/",
    detail: (agentId: string) => `/api/agents/${agentId}`,
  },
  tasks: {
    list: "/api/tasks/",
    detail: (taskId: string) => `/api/tasks/${taskId}`,
    judge: (taskId: string) => `/api/tasks/${taskId}/judge`,
    judgeEvaluation: (taskId: string) => `/api/tasks/${taskId}/judge/evaluate`,
  },
  operator: {
    runState: (runId: string) => `/api/operator/runs/${runId}/state`,
    taskState: (taskId: string) => `/api/operator/tasks/${taskId}/state`,
    runtimeIntentBacklog: "/api/operator/runtime-intents/backlog",
    deadLetters: "/api/operator/dead-letters",
    replayEventDeadLetter: (deadLetterId: string) => `/api/operator/event-dead-letters/${deadLetterId}/replay`,
    acknowledgeEventDeadLetter: (deadLetterId: string) =>
      `/api/operator/event-dead-letters/${deadLetterId}/acknowledge`,
    replayIntent: (intentId: string) => `/api/operator/runtime-intents/${intentId}/replay`,
    acknowledgeIntent: (intentId: string) => `/api/operator/runtime-intents/${intentId}/acknowledge`,
    forceFailRun: (runId: string) => `/api/operator/runs/${runId}/force-fail`,
    forceCancelRun: (runId: string) => `/api/operator/runs/${runId}/force-cancel`,
    forceRehydrateRun: (runId: string) => `/api/operator/runs/${runId}/force-rehydrate`,
    wsSubscribers: "/api/operator/ws/subscribers",
    orgLoad: "/api/operator/org-load",
  },
  ops: {
    deadLetters: "/api/ops/dead-letters",
    deadLetter: (deadLetterKey: string) => `/api/ops/dead-letters/${encodeURIComponent(deadLetterKey)}`,
    replayDeadLetter: (deadLetterKey: string) => `/api/ops/dead-letters/${encodeURIComponent(deadLetterKey)}/replay`,
    resolveDeadLetter: (deadLetterKey: string) => `/api/ops/dead-letters/${encodeURIComponent(deadLetterKey)}/resolve`,
    projectionLag: "/api/ops/projection-lag",
    eventSpool: "/api/ops/event-spool",
    runtimeIntentLag: "/api/ops/runtime-intent-lag",
  },
  accounting: {
    overview: "/api/accounting/",
    ledger: "/api/accounting/ledger",
  },
  systemState: {
    overview: "/api/system-state/overview",
  },
  analytics: {
    memoryUsage: "/api/analytics/memory/usage",
    memoryExport: "/api/analytics/memory/export",
    memoryCosts: "/api/analytics/memory/costs",
    memoryPerformance: "/api/analytics/memory/performance",
    llmUsage: "/api/analytics/llm/usage",
    llmExport: "/api/analytics/llm/export",
    llmCosts: "/api/analytics/llm/costs",
    llmBudget: "/api/analytics/llm/budget",
    llmQuota: "/api/analytics/llm/quota",
  },
  memory: {
    listCreate: "/api/memory/observations",
    search: "/api/memory/observations/search",
    timeline: "/api/memory/observations/timeline",
    context: "/api/memory/observations/context",
    detail: (observationId: string) => `/api/memory/observations/${observationId}`,
  },
  templates: {
    list: "/api/templates/",
    clone: (templateId: string) => `/api/templates/${templateId}/clone`,
    versions: (templateId: string) => `/api/templates/${templateId}/versions`,
    ratings: (templateId: string) => `/api/templates/${templateId}/ratings`,
  },
  marketplace: {
    packages: "/api/marketplace/packages",
    installed: "/api/marketplace/installed",
    install: (slug: string) => `/api/marketplace/packages/${slug}/install`,
    runtimePreview: "/api/marketplace/runtime-manifest-preview",
    releases: "/api/marketplace/releases",
    reviewRelease: (releaseId: string) => `/api/marketplace/releases/${releaseId}/review`,
  },
  onboarding: {
    milestones: "/api/onboarding/milestones",
  },
  auditLogs: {
    list: "/api/audit-logs/",
  },
  policies: {
    guardrails: "/api/policies/guardrails",
  },
  retention: {
    policy: "/api/retention/",
    cleanup: "/api/retention/cleanup",
    export: "/api/retention/export",
  },
  orgs: {
    listCreate: "/api/orgs/",
    current: "/api/orgs/current",
    me: "/api/orgs/me",
    members: "/api/orgs/members",
    memberDetail: (userId: string) => `/api/orgs/members/${userId}`,
  },
  health: {
    memory: "/api/health/memory",
  },
  metrics: {
    summary: "/api/metrics/summary",
    slo: "/api/metrics/slo",
  },
  scim: {
    token: "/api/scim/token",
    rotate: "/api/scim/token/rotate",
  },
  billing: {
    plans: "/api/billing/plans",
    subscription: "/api/billing/subscription",
    checkout: "/api/billing/checkout",
    portal: "/api/billing/portal",
  },
} as const;

const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

export type IdempotencyOptions = {
  idempotencyKey?: string;
};

const idempotencyConfig = (options?: IdempotencyOptions) =>
  options?.idempotencyKey
    ? {
        headers: {
          "Idempotency-Key": options.idempotencyKey,
        },
      }
    : undefined;

// Refresh token is stored in a HttpOnly cookie; keep access token in-memory.
let accessToken: string | null = null;
const E2E_ACCESS_TOKEN_KEY = "__FORGEGRAPH_E2E_ACCESS_TOKEN__";

const authClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

export const getAccessToken = (): string | null => {
  if (!accessToken && typeof window !== "undefined") {
    const seededToken =
      (window as Window & { [E2E_ACCESS_TOKEN_KEY]?: string | null })[E2E_ACCESS_TOKEN_KEY] ??
      window.sessionStorage.getItem(E2E_ACCESS_TOKEN_KEY);
    if (typeof seededToken === "string" && seededToken.length > 0) {
      accessToken = seededToken;
    }
  }
  return accessToken;
};

const setAccessToken = (token: string | null): void => {
  accessToken = token;
  if (typeof window !== "undefined") {
    (window as Window & { [E2E_ACCESS_TOKEN_KEY]?: string | null })[E2E_ACCESS_TOKEN_KEY] = token;
    if (token) {
      window.sessionStorage.setItem(E2E_ACCESS_TOKEN_KEY, token);
    } else {
      window.sessionStorage.removeItem(E2E_ACCESS_TOKEN_KEY);
    }
  }
};

export const clearTokens = (): void => {
  accessToken = null;
  if (typeof window !== "undefined") {
    delete (window as Window & { [E2E_ACCESS_TOKEN_KEY]?: string | null })[E2E_ACCESS_TOKEN_KEY];
    window.sessionStorage.removeItem(E2E_ACCESS_TOKEN_KEY);
  }
};

api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getAccessToken();
    if (token) {
      const headers = config.headers as Record<string, string>;
      headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

type FailedQueueItem = {
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
};

type RetriableRequestConfig = InternalAxiosRequestConfig & { _retry?: boolean };

let isRefreshing = false;
let failedQueue: FailedQueueItem[] = [];

const processQueue = (error: unknown, token: string | null = null): void => {
  for (const prom of failedQueue) {
    if (error) {
      prom.reject(error);
      continue;
    }

    if (!token) {
      prom.reject(new Error("No token provided"));
      continue;
    }

    prom.resolve(token);
  }
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetriableRequestConfig | undefined;

    if (!originalRequest) {
      return Promise.reject(error);
    }

    const requestUrl = originalRequest.url ?? "";
    const isAuthEndpoint =
      requestUrl.includes(API_PATHS.auth.login) ||
      requestUrl.includes(API_PATHS.auth.register) ||
      requestUrl.includes(API_PATHS.auth.refresh);

    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      if (isRefreshing) {
        return new Promise<string>((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            (originalRequest.headers as Record<string, string>).Authorization = `Bearer ${token}`;
            return api(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const response = await authClient.post<AccessTokenResponse>(API_PATHS.auth.refresh, {});

        const { access } = response.data;
        setAccessToken(access);
        processQueue(null, access);

        (originalRequest.headers as Record<string, string>).Authorization = `Bearer ${access}`;
        return api(originalRequest);
      } catch (refreshError: unknown) {
        processQueue(refreshError, null);
        clearTokens();

        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }

        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  },
);

export const authApi = {
  login: async (email: string, password: string): Promise<AccessTokenResponse> => {
    const response = await api.post<AccessTokenResponse>(API_PATHS.auth.login, { email, password });
    setAccessToken(response.data.access);
    return response.data;
  },

  register: async (email: string, password: string): Promise<User> => {
    const response = await api.post<User>(API_PATHS.auth.register, { email, password });
    return response.data;
  },

  createWsTicket: async (): Promise<WebSocketTicketResponse> => {
    const response = await api.post<WebSocketTicketResponse>(API_PATHS.auth.wsTicket, {});
    return response.data;
  },

  logout: async (): Promise<void> => {
    try {
      await api.post(API_PATHS.auth.logout, {});
    } catch (error: unknown) {
      console.error("Logout error:", error);
    }
    clearTokens();
  },

  getMe: async (): Promise<User> => {
    const response = await api.get<User>(API_PATHS.auth.me);
    return response.data;
  },

  refreshToken: async (): Promise<AccessTokenResponse> => {
    if (isRefreshing) {
      const token = await new Promise<string>((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      });
      return { access: token };
    }

    isRefreshing = true;

    try {
      const response = await authClient.post<AccessTokenResponse>(API_PATHS.auth.refresh, {});
      setAccessToken(response.data.access);
      processQueue(null, response.data.access);
      return response.data;
    } catch (refreshError: unknown) {
      processQueue(refreshError, null);
      clearTokens();
      throw refreshError;
    } finally {
      isRefreshing = false;
    }
  },

  getSsoAuthorizeUrl: async (email: string): Promise<string> => {
    const response = await api.get<{ authorize_url: string }>(API_PATHS.auth.ssoLogin, {
      params: { email },
    });
    return response.data.authorize_url;
  },

  exchangeSsoCode: async (code: string, state: string): Promise<AccessTokenResponse> => {
    const response = await api.post<AccessTokenResponse>(API_PATHS.auth.ssoCallback, { code, state });
    setAccessToken(response.data.access);
    return response.data;
  },

  issueWsTicket: async (): Promise<WebSocketTicketResponse> => {
    const response = await api.post<WebSocketTicketResponse>(API_PATHS.wsTicket, {});
    return response.data;
  },
};

export interface GraphListItem {
  id: string;
  organization_id?: string | null;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  version_count: number;
  latest_version: number | null;
}

export interface GraphVersionSummary {
  id: string;
  version: number;
  checksum: string;
  created_at: string;
}

export interface Organization {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface OrganizationListItem extends Organization {
  role: OrganizationMember["role"];
  is_default: boolean;
  joined_at: string;
}

export interface OrganizationMember {
  user_id: string;
  email: string;
  role: "owner" | "admin" | "member" | "viewer";
  is_default: boolean;
  joined_at: string;
}

export type OrganizationRoleCapabilities = {
  can_view_observations: boolean;
  can_delete_observations: boolean;
  can_manage_retention: boolean;
  can_export_memory_data: boolean;
  can_manage_members: boolean;
};

export type OrganizationMeResponse = {
  organization: Organization;
  organizations: OrganizationListItem[];
  role: OrganizationMember["role"];
  governance: {
    current_role_capabilities: OrganizationRoleCapabilities;
    role_capabilities: Record<OrganizationMember["role"], OrganizationRoleCapabilities>;
  };
};

export type TenantGuardrailPolicy = {
  http_allowlist: string[];
  http_denylist: string[];
  http_default_deny: boolean;
  allowed_providers: string[];
  allowed_models: string[];
  summary: {
    runtime_mode: "cloud" | "self_hosted" | string;
    http_access_mode: "open" | "allowlist_first" | "default_deny" | string;
    egress_allowlist_count: number;
    egress_denylist_count: number;
    provider_allowlist_count: number;
    model_allowlist_count: number;
    exec_tools_policy: "restricted_in_cloud" | "package_and_policy_controlled" | string;
    curated_memory_enabled: boolean;
    curated_memory_vector_indexing_enabled: boolean;
  };
};

export type TenantRetentionPolicyResponse = {
  runs_retention_days: number | null;
  run_logs_retention_days: number | null;
  audit_logs_retention_days: number | null;
  usage_retention_days: number | null;
};

export type RetentionCleanupPreview = {
  tenant_id: string;
  dry_run: boolean;
  retention_days: {
    runs: number | null;
    run_logs: number | null;
    audit_logs: number | null;
    usage: number | null;
  };
  runs_deleted: number;
  run_logs_deleted: number;
  run_events_deleted: number;
  node_runs_deleted: number;
  run_checkpoints_deleted: number;
  approval_tasks_deleted: number;
  audit_logs_deleted: number;
  llm_usage_deleted: number;
  memory_usage_deleted: number;
  total_deleted: number;
  errors: string[];
};

export type RetentionExportType = "runs" | "run_events" | "node_runs" | "audit_logs" | "usage" | "memory_usage";

export type MemoryHealthResponse = {
  redis: {
    healthy: boolean;
    latency_ms: number;
    error?: string;
  };
  grpc?: {
    configured: boolean;
    healthy?: boolean;
    error?: string;
  };
  metrics?: {
    memory_gc_deleted_retention_total: number;
    memory_gc_deleted_tenant_total: number;
    memory_gc_deleted_missing_users_total: number;
    memory_gc_last_run_at: string | null;
    memory_gc_last_reindex: string | null;
    memory_grpc_requests_total: number;
    memory_grpc_errors_total: number;
    memory_observation_index_jobs_total: number;
    memory_observation_index_success_total: number;
    memory_observation_index_delete_total: number;
    memory_observation_index_enqueue_errors_total: number;
    memory_observation_delete_enqueue_errors_total: number;
  };
};

export type MetricsSummary = {
  runs: {
    started_total: number;
    completed_total: number;
    failed_total: number;
    canceled_total: number;
    success_rate: number | null;
    failure_rate: number | null;
    latency_ms_p50: number | null;
    latency_ms_p95: number | null;
    window_size: number;
    active_total: number;
  };
  queue: {
    pending: number;
    processing: number;
    total_depth: number;
    backlog?: number;
    stalled_runs?: number;
    oldest_pending_age_seconds: number | null;
    by_tenant: Array<{
      tenant_id: string;
      pending: number;
      processing: number;
      total: number;
    }>;
  };
  websocket?: {
    active_connections: number;
    connection_failures_total: number;
    messages_sent_total: number;
    messages_dropped_total: number;
    messages_filtered_total: number;
    slow_client_disconnects_total: number;
    message_rate_per_minute: number;
    send_latency_ms_p50: number | null;
    send_latency_ms_p95: number | null;
  };
  api?: {
    requests_total: number;
    server_errors_total: number;
    timeout_like_requests_total: number;
    timeout_like_rate_per_minute: number;
    timeout_threshold_ms: number;
    latency_ms_p50: number | null;
    latency_ms_p95: number | null;
    callback_auth_failures_total: number;
    callback_auth_failures_by_reason: Record<string, number>;
  };
  runtime_transport?: {
    backlog: number;
    lag: number;
    pending: number;
    dead_letter_count: number;
    source: string;
    error: string;
  };
  slo: {
    api_availability_beta_target?: number;
    api_availability_production_target?: number;
    runtime_intent_processing_p95_ms_target?: number;
    approval_to_resume_p95_ms_target?: number;
    task_projection_lag_p95_ms_target?: number;
    dead_letter_visibility_seconds_target?: number;
    silent_task_loss_max?: number;
    run_success_rate_target: number;
    run_p95_latency_ms_target: number;
    queue_max_depth_target: number;
    api_p95_latency_ms_target?: number;
    websocket_send_p95_latency_ms_target?: number;
  };
  guardrails: {
    run_max_active_per_tenant: number;
    run_input_max_bytes: number;
    queue_max_concurrency_per_tenant: number;
  };
  violations: {
    run_success_rate: boolean;
    run_p95_latency: boolean;
    queue_depth: boolean;
    api_p95_latency?: boolean;
    websocket_send_p95_latency?: boolean;
  };
  sre?: SreReadinessSummary;
  generated_at: string;
};

type SreObjective = {
  id: string;
  title: string;
  target: number;
  actual: number | null;
  unit: string;
  comparison: "gte" | "lte";
  status: "passing" | "breaching" | "no_data";
  source: string;
  observed_count: number;
  missing_data: boolean;
  description?: string;
};

type SreDashboardPanel = {
  id: string;
  title: string;
  value: unknown;
  unit: string;
  missing_data: boolean;
};

type SreAlert = {
  id: string;
  title: string;
  state: "ok" | "active" | "no_data";
  severity: "warning" | "critical" | string;
  evidence: Record<string, unknown>;
  runbook: string;
};

export type SreReadinessSummary = {
  catalog_version: number;
  catalog_path: string;
  release_tier: string;
  window_seconds: number;
  objectives: SreObjective[];
  dashboard_panels: SreDashboardPanel[];
  alerts: {
    active_total: number;
    items: SreAlert[];
  };
  catalog_validation: {
    missing_slos: string[];
    missing_dashboard_panels: string[];
    missing_alerts: string[];
  };
  generated_at: string;
};

export interface GraphDetail {
  id: string;
  owner_id: string;
  organization_id?: string | null;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  versions: GraphVersionSummary[];
}

export interface MemoryConfig {
  id: string;
  graph: string | null;
  user: string | null;
  buffer_enabled: boolean;
  buffer_size: number;
  auto_prepend: boolean;
  redis_enabled: boolean;
  redis_summary_ttl: number;
  redis_facts_ttl: number;
  vector_enabled: boolean;
  vector_top_k: number;
  vector_threshold: number;
  vector_recency_weight: number;
  embedding_model: string;
  summarization_enabled: boolean;
  summarization_threshold: number;
  summarization_keep_recent: number;
  summarization_model: string;
  created_at: string;
  updated_at: string;
}

export type GraphCreateInput = {
  name: string;
  description?: string;
};

export type GraphUpdateInput = {
  name?: string;
  description?: string;
};

export const graphsApi = {
  list: async (): Promise<GraphListItem[]> => {
    const response = await api.get<ApiSuccessResponse<GraphListItem[]>>(API_PATHS.graphs.listCreate);
    return response.data.data;
  },

  create: async (input: GraphCreateInput): Promise<GraphListItem> => {
    const response = await api.post<ApiSuccessResponse<GraphListItem>>(API_PATHS.graphs.listCreate, input);
    return response.data.data;
  },

  get: async (graphId: string): Promise<GraphDetail> => {
    const response = await api.get<ApiSuccessResponse<GraphDetail>>(API_PATHS.graphs.detail(graphId));
    return response.data.data;
  },

  update: async (graphId: string, input: GraphUpdateInput): Promise<GraphListItem> => {
    const response = await api.patch<ApiSuccessResponse<GraphListItem>>(API_PATHS.graphs.detail(graphId), input);
    return response.data.data;
  },

  delete: async (graphId: string): Promise<void> => {
    await api.delete(API_PATHS.graphs.detail(graphId));
  },

  listVersions: async (graphId: string): Promise<GraphVersionSummary[]> => {
    const response = await api.get<ApiSuccessResponse<GraphVersionSummary[]>>(API_PATHS.graphs.versions(graphId));
    return response.data.data;
  },

  getLatestVersion: async (graphId: string): Promise<GraphVersion | null> => {
    try {
      const response = await api.get<ApiSuccessResponse<GraphVersion>>(API_PATHS.graphs.latestVersion(graphId));
      return response.data.data;
    } catch (error) {
      // 404 means no versions exist yet
      if ((error as AxiosError)?.response?.status === 404) {
        return null;
      }
      throw error;
    }
  },

  getVersion: async (graphId: string, versionId: string): Promise<GraphVersion> => {
    const response = await api.get<ApiSuccessResponse<GraphVersion>>(
      API_PATHS.graphs.versionDetail(graphId, versionId),
    );
    return response.data.data;
  },

  createVersion: async (graphId: string, input: CreateGraphVersionInput): Promise<GraphVersion> => {
    const response = await api.post<ApiSuccessResponse<GraphVersion>>(API_PATHS.graphs.versions(graphId), input);
    return response.data.data;
  },

  getMemoryConfig: async (graphId: string): Promise<MemoryConfig> => {
    const response = await api.get<ApiSuccessResponse<MemoryConfig>>(API_PATHS.graphs.memoryConfig(graphId));
    return response.data.data;
  },

  updateMemoryConfig: async (graphId: string, input: Partial<MemoryConfig>): Promise<MemoryConfig> => {
    const response = await api.patch<ApiSuccessResponse<MemoryConfig>>(API_PATHS.graphs.memoryConfig(graphId), input);
    return response.data.data;
  },
};

type InventorySummary = {
  total_units: number;
  available_units: number;
  held_units: number;
  sold_units: number;
  removed_units: number;
  low_stock_products: number;
  last_piece_products?: number;
  sold_out_products?: number;
  active_holds: number;
};

type StockStateSummary = {
  active_count: number;
  low_stock_count: number;
  last_piece_count: number;
  sold_out_count: number;
  definition_used: string;
};

export type InventoryProduct = {
  id: string;
  company_id: string;
  sku: string;
  model: string;
  name: string;
  variant: string;
  color: string;
  photo_url: string;
  price_mxn: string;
  cost_mxn: string;
  target_margin_pct: string | null;
  anchor_model: boolean;
  scarcity_tag: string;
  status: string;
  total_units: number;
  available_units: number;
  held_units: number;
  sold_units: number;
  removed_units: number;
  stock_state?: "active" | "low_stock" | "last_piece" | "sold_out" | null | string;
  created_at: string;
  updated_at: string;
};

export type InventoryOrderShell = {
  id: string;
  company_id: string;
  reservation_id: string;
  order_number: string;
  public_reference?: string;
  public_status_token?: string;
  status: string;
  stripe_session_id?: string;
  stripe_payment_intent_id?: string;
  stripe_checkout_url?: string;
  customer_email?: string;
  customer_name?: string;
  paid_at?: string | null;
  payment_expired_at?: string | null;
  commerce_payment?: CommercePayment | null;
  created_at: string;
  updated_at: string;
};

type CommercePayment = {
  id: string;
  company_id?: string;
  reservation_id?: string;
  order_id?: string;
  product_id?: string;
  provider?: string;
  status: string;
  amount_mxn: string;
  currency: string;
  quantity?: number;
  stripe_session_id?: string;
  stripe_payment_intent_id?: string;
  checkout_url?: string;
  latest_event_id?: string;
  customer_email?: string;
  customer_name?: string;
  error_message?: string;
  paid_at?: string | null;
  expired_at?: string | null;
};

export type InventoryReservation = {
  id: string;
  company_id: string;
  product_id: string;
  product_sku: string;
  product_model: string;
  status: string;
  quantity: number;
  buyer_alias: string;
  channel: string;
  note: string;
  expires_at: string;
  released_at: string | null;
  converted_at: string | null;
  order_shell: InventoryOrderShell | null;
  created_at: string;
  updated_at: string;
};

type InventoryEvent = {
  id: string;
  company_id: string;
  product_id: string | null;
  product_sku: string;
  reservation_id: string | null;
  order_id: string | null;
  actor_user_id: string | null;
  event_type: string;
  quantity_delta: number;
  message: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type InventoryOverview = {
  company_id: string;
  generated_at: string;
  summary: InventorySummary;
  stock_state_summary?: StockStateSummary;
  products: InventoryProduct[];
  reservations: InventoryReservation[];
  events: InventoryEvent[];
};

export type CreateInventoryReservationInput = {
  company_id: string;
  product_id?: string;
  sku?: string;
  quantity: number;
  buyer_alias?: string;
  channel?: "manual" | "instagram" | "whatsapp" | "dm" | "storefront" | "other";
  note?: string;
  ttl_minutes?: number;
};

export type CommerceCheckoutSessionResponse = {
  checkout_url: string;
  stripe_session_id: string;
  payment: CommercePayment;
  order_shell: InventoryOrderShell;
  reservation: InventoryReservation;
};

export type StorefrontProduct = {
  id: string;
  sku: string;
  model: string;
  name: string;
  variant: string;
  color: string;
  photo_url: string;
  price_amount?: string;
  price_mxn: string;
  currency?: string;
  anchor_model: boolean;
  scarcity_tag: string;
  available_units: number;
  sold_out: boolean;
};

export type StorefrontProductsResponse = {
  company_id: string;
  company_slug: string;
  storefront_display_name?: string;
  currency: string;
  products: StorefrontProduct[];
};

export type CommerceFulfillment = {
  id: string;
  order_id: string;
  payment_id: string;
  reservation_id: string;
  status: string;
  reason_code: string;
  operator_note: string;
  carrier: string;
  tracking_number: string;
  tracking_url: string;
  shipped_at: string | null;
  delivered_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CommerceOrder = {
  id: string;
  company_id: string;
  order_number: string;
  public_reference: string;
  status: string;
  product: {
    id: string;
    sku: string;
    model: string;
    name: string;
    photo_url: string;
  };
  quantity: number;
  buyer_alias: string;
  channel: string;
  payment: CommercePayment | null;
  fulfillment: CommerceFulfillment | null;
  paid_at: string | null;
  payment_expired_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CommerceOperationsOverview = {
  company_id: string;
  generated_at: string;
  storefront: {
    id: string;
    company_id: string;
    slug: string;
    display_name: string;
    enabled: boolean;
    currency: string;
  } | null;
  summary: {
    orders_total: number;
    orders_paid: number;
    orders_pending_payment: number;
    orders_stuck: number;
    payments_succeeded: number;
    payments_review_required: number;
    fulfillment_pending: number;
    fulfillment_ready: number;
    fulfillment_blocked: number;
    fulfillment_shipped: number;
    fulfillment_delivered: number;
    cash_sales_mxn: string;
  };
  stuck_orders: CommerceOrder[];
  recent_orders: CommerceOrder[];
  fulfillment_events: Array<{
    id: string;
    fulfillment_id: string;
    order_id: string;
    actor_user_id: string | null;
    event_type: string;
    status_from: string;
    status_to: string;
    message: string;
    metadata: Record<string, unknown>;
    created_at: string;
  }>;
};

export type StorefrontOrderStatusResponse = {
  storefront: {
    slug: string;
    display_name: string;
    currency: string;
  } | null;
  order: {
    reference: string;
    status: string;
    payment_status: string;
    fulfillment_status: string;
    item: {
      sku: string;
      model: string;
      name: string;
      quantity: number;
    };
    paid_at: string | null;
    updated_at: string;
  };
};

export type CompanySignal = {
  id: string;
  company_id: string;
  product_id: string | null;
  order_id: string | null;
  fulfillment_id: string | null;
  operation_id: string | null;
  signal_type: string;
  status: string;
  source: string;
  external_key: string;
  title: string;
  summary: string;
  channel: string;
  contact_alias: string;
  metadata: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
  updated_at: string;
};

export type CompanyOpportunity = {
  id: string;
  company_id: string;
  signal_id: string | null;
  product_id: string | null;
  reservation_id: string | null;
  order_id: string | null;
  status: string;
  title: string;
  summary: string;
  contact_alias: string;
  channel: string;
  estimated_value_amount: string;
  currency: string;
  next_action: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type PublicationDraft = {
  id: string;
  company_id: string;
  signal_id: string | null;
  opportunity_id: string | null;
  origin_operation_id: string | null;
  asset_id: string | null;
  asset_version_id: string | null;
  media_job_id: string | null;
  approval_task_id: string | null;
  title: string;
  channel: string;
  audience: string;
  body: string;
  call_to_action: string;
  status: string;
  approved_at: string | null;
  published_at: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type CreatePublicationDraftInput = {
  company_id: string;
  title: string;
  channel?: string;
  audience?: string;
  body?: string;
  call_to_action?: string;
  signal_id?: string | null;
  opportunity_id?: string | null;
  asset_id?: string | null;
  asset_version_id?: string | null;
  media_job_id?: string | null;
};

export type ProcurementDraft = {
  id: string;
  company_id: string;
  origin_operation_id: string | null;
  approval_task_id: string | null;
  title: string;
  rationale: string;
  budget_amount: string;
  currency: string;
  status: string;
  approved_at: string | null;
  metadata: Record<string, unknown>;
  lines: Array<{
    id: string;
    product_id: string | null;
    sku: string;
    description: string;
    quantity: number;
    unit_cost_amount: string;
    currency: string;
    metadata: Record<string, unknown>;
  }>;
  created_at: string;
  updated_at: string;
};

export type ArchiveAsset = {
  id: string;
  organization_id: string;
  company_id: string;
  title: string;
  asset_type: string;
  source_key: string;
  origin_operation_id: string | null;
  origin_task_id: string | null;
  origin_node_run_id: string | null;
  origin_deliverable_id: string | null;
  created_by_type: string;
  created_by_id: string | null;
  status: string;
  metadata: Record<string, unknown>;
  latest_version_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ArchiveAssetVersion = {
  id: string;
  asset_id: string;
  version_number: number;
  content_uri: string;
  content_hash: string | null;
  mime_type: string | null;
  size_bytes: number;
  provenance: Record<string, unknown>;
  created_at: string;
};

export type MediaGenerationJob = {
  id: string;
  organization_id: string;
  company_id: string;
  requested_by_id: string | null;
  credential_id: string | null;
  modality: "image" | "video" | string;
  provider: string;
  model: string;
  prompt: string;
  prompt_hash: string;
  idempotency_key: string;
  status: string;
  provider_operation_name: string | null;
  output_asset_id: string | null;
  output_asset_version_id: string | null;
  output_mime_type: string | null;
  output_size_bytes: number | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
};

export type CompanyOpsOperation = {
  id: string;
  company_id: string;
  graph_version_id: string;
  status: string;
  operation_type: string;
  operation_brief: string;
  context_pack_id: string;
  objective_contract_id: string | null;
  objective_contract: CompanyOperationObjective | null;
  started_at: string | null;
  created_at: string | null;
};

export type CompanyOperationObjective = {
  id: string;
  company_id: string;
  operation_id: string;
  source_signal_id: string | null;
  run_type: string;
  status: string;
  run_goal: string;
  hypothesis: string;
  target_signal: string;
  action_plan: Array<{
    department: string;
    responsibility: string;
  }>;
  integrity_gates: Record<string, unknown>;
  success_score: number | null;
  miss_analysis: string;
  next_decision: string;
  evaluated_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CompanyOpsOverview = {
  company_id: string;
  generated_at: string;
  summary: {
    signals_new: number;
    signals_qualified: number;
    opportunities_open: number;
    publication_drafts: number;
    procurement_drafts: number;
    paid_orders: number;
    stuck_orders: number;
    low_stock_products: number;
    cash_sales_mxn: string;
  };
  stock_state_summary?: StockStateSummary;
  recommended_operations: Array<{
    operation_type: string;
    label: string;
    reason: string;
  }>;
  signals: CompanySignal[];
  opportunities: CompanyOpportunity[];
  publication_drafts: PublicationDraft[];
  procurement_drafts: ProcurementDraft[];
  objective_contracts: CompanyOperationObjective[];
  recent_decisions: Array<{
    id: string;
    operation_id: string | null;
    approval_task_id: string | null;
    decision_type: string;
    status: string;
    context: Record<string, unknown>;
    resolution: Record<string, unknown>;
    requested_at: string | null;
    resolved_at: string | null;
  }>;
  policies: Array<{
    id: string;
    title: string;
    scope_type: string;
    scope_id: string;
    status: string;
    confidence: number;
    condition: Record<string, unknown>;
    recommendation: Record<string, unknown>;
  }>;
};

export const inventoryApi = {
  getOverview: async (companyId: string): Promise<InventoryOverview> => {
    const response = await api.get<ApiSuccessResponse<{ inventory: InventoryOverview }>>(API_PATHS.inventory.overview, {
      params: { company_id: companyId },
    });
    return response.data.data.inventory;
  },

  createReservation: async (
    input: CreateInventoryReservationInput,
    options: IdempotencyOptions,
  ): Promise<InventoryReservation> => {
    const response = await api.post<ApiSuccessResponse<{ reservation: InventoryReservation }>>(
      API_PATHS.inventory.reservations,
      input,
      idempotencyConfig(options),
    );
    return response.data.data.reservation;
  },

  releaseReservation: async (
    reservationId: string,
    input: { reason?: string },
    options: IdempotencyOptions,
  ): Promise<InventoryReservation> => {
    const response = await api.post<ApiSuccessResponse<{ reservation: InventoryReservation }>>(
      API_PATHS.inventory.releaseReservation(reservationId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.reservation;
  },

  extendReservation: async (
    reservationId: string,
    input: { minutes: number },
    options: IdempotencyOptions,
  ): Promise<InventoryReservation> => {
    const response = await api.post<ApiSuccessResponse<{ reservation: InventoryReservation }>>(
      API_PATHS.inventory.extendReservation(reservationId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.reservation;
  },

  createOrderShell: async (reservationId: string, options: IdempotencyOptions): Promise<InventoryOrderShell> => {
    const response = await api.post<ApiSuccessResponse<{ order_shell: InventoryOrderShell }>>(
      API_PATHS.inventory.orderShell(reservationId),
      {},
      idempotencyConfig(options),
    );
    return response.data.data.order_shell;
  },

  expireDue: async (companyId: string, options: IdempotencyOptions): Promise<{ expired_count: number }> => {
    const response = await api.post<ApiSuccessResponse<{ expired_count: number }>>(
      API_PATHS.inventory.expireDue,
      { company_id: companyId },
      idempotencyConfig(options),
    );
    return response.data.data;
  },
};

export const commerceApi = {
  createCheckoutSession: async (
    input: { company_id: string; reservation_id?: string; order_shell_id?: string },
    options: IdempotencyOptions,
  ): Promise<CommerceCheckoutSessionResponse> => {
    const response = await api.post<ApiSuccessResponse<CommerceCheckoutSessionResponse>>(
      API_PATHS.commerce.checkoutSessions,
      input,
      idempotencyConfig(options),
    );
    return response.data.data;
  },

  getOverview: async (companyId: string): Promise<CommerceOperationsOverview> => {
    const response = await api.get<ApiSuccessResponse<{ commerce: CommerceOperationsOverview }>>(
      API_PATHS.commerce.overview,
      { params: { company_id: companyId } },
    );
    return response.data.data.commerce;
  },

  listOrders: async (companyId: string): Promise<{ company_id: string; orders: CommerceOrder[] }> => {
    const response = await api.get<ApiSuccessResponse<{ company_id: string; orders: CommerceOrder[] }>>(
      API_PATHS.commerce.orders,
      { params: { company_id: companyId } },
    );
    return response.data.data;
  },

  blockFulfillment: async (
    orderId: string,
    input: { reason_code?: string; note?: string },
    options: IdempotencyOptions,
  ): Promise<CommerceFulfillment> => {
    const response = await api.post<ApiSuccessResponse<{ fulfillment: CommerceFulfillment }>>(
      API_PATHS.commerce.fulfillmentBlock(orderId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.fulfillment;
  },

  markFulfillmentReady: async (
    orderId: string,
    input: { note?: string },
    options: IdempotencyOptions,
  ): Promise<CommerceFulfillment> => {
    const response = await api.post<ApiSuccessResponse<{ fulfillment: CommerceFulfillment }>>(
      API_PATHS.commerce.fulfillmentReady(orderId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.fulfillment;
  },

  shipFulfillment: async (
    orderId: string,
    input: { carrier?: string; tracking_number?: string; tracking_url?: string; note?: string },
    options: IdempotencyOptions,
  ): Promise<CommerceFulfillment> => {
    const response = await api.post<ApiSuccessResponse<{ fulfillment: CommerceFulfillment }>>(
      API_PATHS.commerce.fulfillmentShip(orderId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.fulfillment;
  },

  deliverFulfillment: async (
    orderId: string,
    input: { note?: string },
    options: IdempotencyOptions,
  ): Promise<CommerceFulfillment> => {
    const response = await api.post<ApiSuccessResponse<{ fulfillment: CommerceFulfillment }>>(
      API_PATHS.commerce.fulfillmentDeliver(orderId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.fulfillment;
  },
};

export const companyOpsApi = {
  getOverview: async (companyId: string): Promise<CompanyOpsOverview> => {
    const response = await api.get<ApiSuccessResponse<{ company_ops: CompanyOpsOverview }>>(
      API_PATHS.companyOps.overview,
      { params: { company_id: companyId } },
    );
    return response.data.data.company_ops;
  },

  createSignal: async (
    input: {
      company_id: string;
      signal_type: string;
      title: string;
      summary?: string;
      source?: string;
      external_key?: string;
      channel?: string;
      contact_alias?: string;
      product_id?: string | null;
      order_id?: string | null;
      fulfillment_id?: string | null;
      metadata?: Record<string, unknown>;
    },
    options: IdempotencyOptions,
  ): Promise<CompanySignal> => {
    const response = await api.post<ApiSuccessResponse<{ signal: CompanySignal }>>(
      API_PATHS.companyOps.signals,
      input,
      idempotencyConfig(options),
    );
    return response.data.data.signal;
  },

  qualifySignal: async (
    signalId: string,
    input: { title?: string; summary?: string; next_action?: string },
    options: IdempotencyOptions,
  ): Promise<CompanyOpportunity> => {
    const response = await api.post<ApiSuccessResponse<{ opportunity: CompanyOpportunity }>>(
      API_PATHS.companyOps.qualifySignal(signalId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.opportunity;
  },

  createPublicationDraft: async (
    input: CreatePublicationDraftInput,
    options: IdempotencyOptions,
  ): Promise<PublicationDraft> => {
    const response = await api.post<ApiSuccessResponse<{ publication_draft: PublicationDraft }>>(
      API_PATHS.companyOps.publicationDrafts,
      input,
      idempotencyConfig(options),
    );
    return response.data.data.publication_draft;
  },

  requestPublicationApproval: async (
    draftId: string,
    input: { note?: string },
    options: IdempotencyOptions,
  ): Promise<PublicationDraft> => {
    const response = await api.post<ApiSuccessResponse<{ publication_draft: PublicationDraft }>>(
      API_PATHS.companyOps.publicationDraftApproval(draftId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.publication_draft;
  },

  requestProcurementApproval: async (
    draftId: string,
    input: { note?: string },
    options: IdempotencyOptions,
  ): Promise<ProcurementDraft> => {
    const response = await api.post<ApiSuccessResponse<{ procurement_draft: ProcurementDraft }>>(
      API_PATHS.companyOps.procurementDraftApproval(draftId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.procurement_draft;
  },

  launchOperation: async (
    input: {
      company_id: string;
      operation_type: string;
      source_signal_id?: string | null;
      context_note?: string;
      run_type?: string;
      run_goal?: string;
      hypothesis?: string;
      target_signal?: string;
    },
    options: IdempotencyOptions,
  ): Promise<CompanyOpsOperation> => {
    const response = await api.post<ApiSuccessResponse<{ operation: CompanyOpsOperation }>>(
      API_PATHS.companyOps.operations,
      input,
      idempotencyConfig(options),
    );
    return response.data.data.operation;
  },

  evaluateOperationObjective: async (
    operationId: string,
    input: {
      success_score: number;
      miss_analysis?: string;
      next_decision?: string;
      integrity_gates?: Record<string, unknown>;
    },
    options: IdempotencyOptions,
  ): Promise<CompanyOperationObjective> => {
    const response = await api.post<ApiSuccessResponse<{ objective_contract: CompanyOperationObjective }>>(
      API_PATHS.companyOps.operationObjectiveEvaluation(operationId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.objective_contract;
  },
};

export const archiveApi = {
  listAssets: async (
    companyId: string,
    params?: { asset_type?: string; status?: string; operation_id?: string },
  ): Promise<{ assets: ArchiveAsset[] }> => {
    const response = await api.get<ApiSuccessResponse<{ assets: ArchiveAsset[] }>>(API_PATHS.archive.assets, {
      params: {
        company_id: companyId,
        ...(params?.asset_type ? { asset_type: params.asset_type } : {}),
        ...(params?.status ? { status: params.status } : {}),
        ...(params?.operation_id ? { operation_id: params.operation_id } : {}),
      },
    });
    return response.data.data;
  },

  listAssetVersions: async (assetId: string): Promise<{ versions: ArchiveAssetVersion[] }> => {
    const response = await api.get<ApiSuccessResponse<{ versions: ArchiveAssetVersion[] }>>(
      API_PATHS.archive.assetVersions(assetId),
    );
    return response.data.data;
  },

  getAssetVersionContent: async (assetId: string, versionId: string): Promise<Blob> => {
    const response = await api.get<Blob>(API_PATHS.archive.assetVersionContent(assetId, versionId), {
      responseType: "blob",
    });
    return response.data;
  },

  createMediaGeneration: async (
    input: {
      company_id: string;
      credential_id: string;
      modality: "image" | "video";
      prompt: string;
      idempotency_key?: string;
      model?: string;
    },
    options?: IdempotencyOptions,
  ): Promise<MediaGenerationJob> => {
    const response = await api.post<ApiSuccessResponse<{ media_generation: MediaGenerationJob }>>(
      API_PATHS.archive.mediaGenerations,
      input,
      idempotencyConfig(options),
    );
    return response.data.data.media_generation;
  },

  getMediaGeneration: async (jobId: string): Promise<MediaGenerationJob> => {
    const response = await api.get<ApiSuccessResponse<{ media_generation: MediaGenerationJob }>>(
      API_PATHS.archive.mediaGeneration(jobId),
    );
    return response.data.data.media_generation;
  },

  pollMediaGeneration: async (jobId: string): Promise<MediaGenerationJob> => {
    const response = await api.post<ApiSuccessResponse<{ media_generation: MediaGenerationJob }>>(
      API_PATHS.archive.mediaGenerationPoll(jobId),
    );
    return response.data.data.media_generation;
  },
};

export const storefrontApi = {
  listProducts: async (companySlug: string): Promise<StorefrontProductsResponse> => {
    const response = await api.get<ApiSuccessResponse<StorefrontProductsResponse>>(
      API_PATHS.storefront.products(companySlug),
    );
    return response.data.data;
  },

  createCheckoutSession: async (
    companySlug: string,
    input: { product_id?: string; sku?: string; quantity?: number; buyer_alias?: string },
    options: IdempotencyOptions,
  ): Promise<CommerceCheckoutSessionResponse> => {
    const response = await api.post<ApiSuccessResponse<CommerceCheckoutSessionResponse>>(
      API_PATHS.storefront.checkoutSessions(companySlug),
      input,
      idempotencyConfig(options),
    );
    return response.data.data;
  },

  getOrderStatus: async (companySlug: string, token: string): Promise<StorefrontOrderStatusResponse> => {
    const response = await api.get<ApiSuccessResponse<StorefrontOrderStatusResponse>>(
      API_PATHS.storefront.orderStatus(companySlug, token),
    );
    return response.data.data;
  },
};

export type PromptCategory = "research" | "summarization" | "email" | "extraction" | "reasoning" | "other";

type PromptVisibility = "private" | "public";

export interface PromptListItem {
  id: string;
  title: string;
  description: string;
  category: PromptCategory | string;
  visibility: PromptVisibility | string;
  is_builtin: boolean;
  created_at: string;
}

export interface PromptDetail {
  id: string;
  owner_id: string | null;
  title: string;
  description: string;
  category: PromptCategory | string;
  content: string;
  variables_schema: Record<string, unknown>;
  version: string;
  license: string;
  visibility: PromptVisibility | string;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
}

export type PromptCreateInput = {
  title: string;
  description?: string;
  category: PromptCategory | string;
  content: string;
  variables_schema?: Record<string, unknown>;
};

export type PromptUpdateInput = {
  title?: string;
  description?: string;
  content?: string;
  variables_schema?: Record<string, unknown>;
};

export type PromptOwnershipFilter = "all" | "mine" | "builtin";

export type Credential = {
  id: string;
  provider: string;
  name: string;
  key_hint: string;
  is_oauth_connection: boolean;
  token_expires_at: string | null;
  health_status: "healthy" | "expiring_soon" | "expired" | string;
  requires_reauth: boolean;
  health_message: string | null;
  created_at: string;
};

export type CredentialCreateInput = {
  provider: string;
  name: string;
  api_key: string;
};

export type OAuthIntegrationProvider =
  | "gmail"
  | "google_calendar"
  | "google_tasks"
  | "notion"
  | "slack"
  | "jira"
  | "linear"
  | "hubspot"
  | "google_drive";

export type CredentialOAuthProviderStatus = {
  provider: OAuthIntegrationProvider;
  configured: boolean;
  missing_config_fields: string[];
  has_provider_config: boolean;
  configuration_mode?: "environment" | string;
  enabled: boolean;
  client_id: string;
  authorize_url: string;
  token_url: string;
  redirect_uri: string | null;
  scopes: string[];
  authorize_extra_params: Record<string, unknown>;
  token_extra_params: Record<string, unknown>;
};

export type HttpNodeTestInput = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  url: string;
  headers?: Record<string, string>;
  body?: string;
  provider?: string;
  credential_id?: string;
  account_sid?: string;
  timeout_seconds?: number;
};

export type HttpNodeTestResult = {
  status_code: number;
  ok: boolean;
  headers: Record<string, string>;
  body: unknown;
};

export type GraphTemplate = {
  id: string;
  group_id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  estimated_minutes: number;
  sample_input: Record<string, unknown>;
  guide_steps: string[];
  version: number;
  changelog: string;
  is_latest: boolean;
  visibility: "public" | "organization" | "private" | string;
  owner_organization_id: string | null;
  rating_average: number | null;
  rating_count: number;
  usage_count: number;
  run_success_rate?: number | null;
};

type TemplateCloneInput = {
  name?: string;
  description?: string;
  provider?: string;
  model?: string;
  credential_id?: string;
};

type TemplateCloneResult = {
  graph_id: string;
  graph_version_id: string;
  graph_name: string;
  template_id: string;
};

type MarketplaceRelease = {
  id: string;
  version: string;
  changelog: string;
  status: "draft" | "pending_review" | "approved" | "rejected" | string;
  package_kind: "template_http" | "template_prompt" | "runtime_tool" | "runtime_transform" | string;
  execution_node_type: "http" | "prompt" | "tool" | "transform" | string;
  ui_schema: Record<string, unknown>;
  config_schema: Record<string, unknown>;
  config_defaults: Record<string, unknown>;
  runtime_manifest: Record<string, unknown> | null;
  manifest_version: number | null;
  cloud_allowed: boolean;
  review_notes: string;
  created_at: string;
};

export type MarketplacePackage = {
  id: string;
  slug: string;
  name: string;
  summary: string;
  category: string;
  icon: string;
  docs_url: string;
  homepage_url: string;
  latest_release: MarketplaceRelease | null;
  installed_release?: MarketplaceRelease | null;
  installed_at?: string | null;
  install_metadata?: Record<string, unknown> | null;
  runtime_delivery?: {
    state: "ready" | "blocked" | "invalid" | "template" | string;
    reason: string;
    package_kind: string;
    cloud_allowed: boolean;
    manifest_version: number | null;
    checksum?: string | null;
  } | null;
};

type MarketplaceRuntimeManifestPackage = {
  package_slug: string;
  package_name: string;
  release_id: string;
  release_version: string;
  package_kind: string;
  delivery_state: string;
  delivery_reason: string;
  cloud_allowed: boolean;
  manifest_version: number | null;
  manifest_checksum: string | null;
};

type MarketplaceRuntimeManifestTool = {
  name: string;
  version?: string;
  kind: string;
  description?: string;
  [key: string]: unknown;
};

export type MarketplaceRuntimeManifestPreview = {
  tenant_id: string;
  manifest_version: number;
  checksum: string;
  generated_at: string;
  packages: MarketplaceRuntimeManifestPackage[];
  tools: MarketplaceRuntimeManifestTool[];
};

export type MarketplaceReleaseSummary = {
  id: string;
  package_slug: string;
  package_name: string;
  version: string;
  status: "draft" | "pending_review" | "approved" | "rejected" | string;
  package_kind: "template_http" | "template_prompt" | "runtime_tool" | "runtime_transform" | string;
  execution_node_type: "http" | "prompt" | "tool" | "transform" | string;
  cloud_allowed: boolean;
  created_at: string;
};

export const promptsApi = {
  list: async (filters?: {
    category?: string;
    ownership?: PromptOwnershipFilter;
    search?: string;
  }): Promise<PromptListItem[]> => {
    const response = await api.get<ApiSuccessResponse<PromptListItem[]>>(API_PATHS.prompts.listCreate, {
      params: filters,
    });
    return response.data.data;
  },

  create: async (input: PromptCreateInput): Promise<PromptDetail> => {
    const response = await api.post<ApiSuccessResponse<PromptDetail>>(API_PATHS.prompts.listCreate, input);
    return response.data.data;
  },

  get: async (promptId: string): Promise<PromptDetail> => {
    const response = await api.get<ApiSuccessResponse<PromptDetail>>(API_PATHS.prompts.detail(promptId));
    return response.data.data;
  },

  update: async (promptId: string, input: PromptUpdateInput): Promise<PromptDetail> => {
    const response = await api.patch<ApiSuccessResponse<PromptDetail>>(API_PATHS.prompts.detail(promptId), input);
    return response.data.data;
  },

  delete: async (promptId: string): Promise<void> => {
    await api.delete(API_PATHS.prompts.detail(promptId));
  },

  clone: async (promptId: string): Promise<PromptDetail> => {
    const response = await api.post<ApiSuccessResponse<PromptDetail>>(API_PATHS.prompts.clone(promptId), {});
    return response.data.data;
  },

  publish: async (promptId: string, input?: { license?: string }): Promise<PromptDetail> => {
    const response = await api.post<ApiSuccessResponse<PromptDetail>>(API_PATHS.prompts.publish(promptId), input ?? {});
    return response.data.data;
  },
};

export interface BillingPlan {
  id: string;
  name: string;
  stripe_price_id: string;
  stripe_product_id: string;
  entitlements: Record<string, any>;
}

export interface BillingSubscription {
  plan: {
    id: string | null;
    name: string | null;
    entitlements: Record<string, any>;
  } | null;
  status: string;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  stripe_customer_id: string;
  stripe_subscription_id: string;
}

export const billingApi = {
  listPlans: async (): Promise<BillingPlan[]> => {
    const response = await api.get<ApiSuccessResponse<BillingPlan[]>>(API_PATHS.billing.plans);
    return response.data.data;
  },
  getSubscription: async (): Promise<BillingSubscription | null> => {
    const response = await api.get<ApiSuccessResponse<{ subscription: BillingSubscription | null }>>(
      API_PATHS.billing.subscription,
    );
    return response.data.data.subscription;
  },
  createCheckout: async (planId: string): Promise<string> => {
    const response = await api.post<ApiSuccessResponse<{ checkout_url: string }>>(API_PATHS.billing.checkout, {
      plan_id: planId,
    });
    return response.data.data.checkout_url;
  },
  createPortal: async (): Promise<string> => {
    const response = await api.post<ApiSuccessResponse<{ portal_url: string }>>(API_PATHS.billing.portal, {});
    return response.data.data.portal_url;
  },
};

export interface SsoProviderConfig {
  issuer_url: string;
  client_id: string;
  audience: string;
  email_domains: string[];
  default_role: "owner" | "admin" | "member" | "viewer";
  enabled: boolean;
  status: IdentityStatus;
}

interface IdentityStatus {
  state: "configured" | "partial" | "unavailable";
  message: string;
}

export const ssoApi = {
  getProvider: async (): Promise<SsoProviderConfig> => {
    const response = await api.get<SsoProviderConfig>(API_PATHS.auth.ssoProvider);
    return response.data;
  },
  updateProvider: async (payload: Partial<SsoProviderConfig> & { client_secret?: string }) => {
    const response = await api.put<SsoProviderConfig>(API_PATHS.auth.ssoProvider, payload);
    return response.data;
  },
};

export interface ScimTokenInfo {
  token_last4: string | null;
  created_at: string | null;
  last_used_at: string | null;
  rotated_at: string | null;
  status: IdentityStatus;
}

export const scimApi = {
  getTokenInfo: async (): Promise<ScimTokenInfo> => {
    const response = await api.get<ScimTokenInfo>(API_PATHS.scim.token);
    return response.data;
  },
  rotateToken: async (): Promise<string> => {
    const response = await api.post<{ token: string }>(API_PATHS.scim.rotate, {});
    return response.data.token;
  },
};

export const credentialsApi = {
  list: async (): Promise<Credential[]> => {
    const response = await api.get<ApiSuccessResponse<Credential[]>>(API_PATHS.credentials.listCreate);
    return response.data.data;
  },
  create: async (input: CredentialCreateInput): Promise<Credential> => {
    const response = await api.post<ApiSuccessResponse<Credential>>(API_PATHS.credentials.listCreate, input);
    return response.data.data;
  },
  delete: async (credentialId: string): Promise<void> => {
    await api.delete(API_PATHS.credentials.detail(credentialId));
  },
  listOAuthProviders: async (): Promise<CredentialOAuthProviderStatus[]> => {
    const response = await api.get<ApiSuccessResponse<CredentialOAuthProviderStatus[]>>(
      API_PATHS.credentials.oauthProviders,
    );
    return response.data.data;
  },
  startOAuth: async (
    provider: OAuthIntegrationProvider,
    name?: string,
  ): Promise<{ provider: OAuthIntegrationProvider; authorize_url: string; redirect_uri: string }> => {
    const response = await api.post<
      ApiSuccessResponse<{ provider: OAuthIntegrationProvider; authorize_url: string; redirect_uri: string }>
    >(API_PATHS.credentials.oauthStart, { provider, name });
    return response.data.data;
  },
  completeOAuthCallback: async (input: { code: string; state: string }): Promise<Credential> => {
    const response = await api.post<ApiSuccessResponse<Credential>>(API_PATHS.credentials.oauthCallback, input);
    return response.data.data;
  },
};

export const integrationsApi = {
  runHttpNodeTest: async (input: HttpNodeTestInput): Promise<HttpNodeTestResult> => {
    const response = await api.post<ApiSuccessResponse<HttpNodeTestResult>>(API_PATHS.integrations.httpTest, input);
    return response.data.data;
  },
};

const templatesApi = {
  list: async (): Promise<GraphTemplate[]> => {
    const response = await api.get<ApiSuccessResponse<GraphTemplate[]>>(API_PATHS.templates.list);
    return response.data.data;
  },
  listVersions: async (templateId: string): Promise<GraphTemplate[]> => {
    const response = await api.get<ApiSuccessResponse<GraphTemplate[]>>(API_PATHS.templates.versions(templateId));
    return response.data.data;
  },
  clone: async (templateId: string, input: TemplateCloneInput): Promise<TemplateCloneResult> => {
    const response = await api.post<ApiSuccessResponse<TemplateCloneResult>>(
      API_PATHS.templates.clone(templateId),
      input,
    );
    return response.data.data;
  },
  rate: async (templateId: string, input: { rating: number; comment?: string }): Promise<void> => {
    await api.post<ApiSuccessResponse<{ template_id: string; rating: number }>>(
      API_PATHS.templates.ratings(templateId),
      input,
    );
  },
};

export const marketplaceApi = {
  listPackages: async (): Promise<MarketplacePackage[]> => {
    const response = await api.get<ApiSuccessResponse<MarketplacePackage[]>>(API_PATHS.marketplace.packages);
    return response.data.data;
  },
  listInstalled: async (): Promise<MarketplacePackage[]> => {
    const response = await api.get<ApiSuccessResponse<MarketplacePackage[]>>(API_PATHS.marketplace.installed);
    return response.data.data;
  },
  getRuntimePreview: async (): Promise<MarketplaceRuntimeManifestPreview> => {
    const response = await api.get<ApiSuccessResponse<MarketplaceRuntimeManifestPreview>>(
      API_PATHS.marketplace.runtimePreview,
    );
    return response.data.data;
  },
  install: async (slug: string, input?: { version?: string }): Promise<MarketplacePackage> => {
    const response = await api.post<ApiSuccessResponse<MarketplacePackage>>(
      API_PATHS.marketplace.install(slug),
      input ?? {},
    );
    return response.data.data;
  },
  listReleases: async (): Promise<MarketplaceReleaseSummary[]> => {
    const response = await api.get<ApiSuccessResponse<MarketplaceReleaseSummary[]>>(API_PATHS.marketplace.releases);
    return response.data.data;
  },
  createRelease: async (input: {
    package_slug: string;
    package_name?: string;
    package_summary?: string;
    package_category?: string;
    package_icon?: string;
    version: string;
    changelog?: string;
    package_kind?: "template_http" | "template_prompt" | "runtime_tool" | "runtime_transform";
    execution_node_type: "http" | "prompt" | "tool" | "transform";
    ui_schema?: Record<string, unknown>;
    config_schema?: Record<string, unknown>;
    config_defaults?: Record<string, unknown>;
    runtime_manifest?: Record<string, unknown> | null;
    manifest_version?: number;
    cloud_allowed?: boolean;
    review_notes?: string;
  }): Promise<{ id: string; package_slug: string; version: string; status: string }> => {
    const response = await api.post<
      ApiSuccessResponse<{ id: string; package_slug: string; version: string; status: string }>
    >(API_PATHS.marketplace.releases, input);
    return response.data.data;
  },
  reviewRelease: async (releaseId: string, decision: "approved" | "rejected") => {
    const response = await api.patch<ApiSuccessResponse<{ id: string; status: string; reviewed_at: string | null }>>(
      API_PATHS.marketplace.reviewRelease(releaseId),
      { decision },
    );
    return response.data.data;
  },
};

export type OnboardingMilestone = {
  key: string;
  label: string;
  description?: string | null;
  completed: boolean;
  completed_at: string | null;
};

export const onboardingApi = {
  list: async (): Promise<OnboardingMilestone[]> => {
    const response = await api.get<ApiSuccessResponse<OnboardingMilestone[]>>(API_PATHS.onboarding.milestones);
    return response.data.data;
  },
  complete: async (milestone: string, metadata?: Record<string, unknown>): Promise<void> => {
    await api.post<ApiSuccessResponse<{ milestone: string }>>(API_PATHS.onboarding.milestones, {
      milestone,
      metadata: metadata ?? {},
    });
  },
};

type PMAction = "EXECUTE" | "ASK_CLARIFICATION" | "ASSUME_AND_CONTINUE" | "BLOCK";

type InteractionEventType =
  | "CREATE"
  | "MODIFY"
  | "CLARIFY"
  | "CONSTRAINT"
  | "PRIORITY_SHIFT"
  | "APPROVE"
  | "OVERRIDE";

type PriorityFrame = {
  speed: number;
  cost: number;
  quality: number;
  risk: number;
};

type OperatingBriefAssumption = {
  field: string;
  value: unknown;
  confidence: number;
  created_at: string;
};

export type OperatingBriefClarification = {
  question: string;
  blocking: boolean;
  related_field: string;
};

export type OperatingBrief = {
  id: string | null;
  organization_id: string | null;
  company_id: string | null;
  operation_id: string | null;
  objective: string | null;
  deliverable: string | null;
  constraints: string[];
  success_criteria: string[];
  stakeholders: string[];
  dependencies: string[];
  assumptions: OperatingBriefAssumption[];
  clarifications: OperatingBriefClarification[];
  priority_frame: PriorityFrame;
  autonomy_mode: "manual" | "assisted" | "autonomous" | string;
  created_at: string | null;
  updated_at: string | null;
};

type InteractionEvent = {
  id: string;
  brief_id: string;
  company_id: string;
  operation_id: string | null;
  sequence: number;
  type: InteractionEventType;
  actor: "user" | "system" | string;
  timestamp: string;
  raw_input: string;
  delta: Record<string, unknown>;
  affected_fields: string[];
  interpretation: Record<string, unknown>;
  pm_action: PMAction | string;
  plan_implications: InteractionPlanImplications;
  created_at: string;
};

type InteractionPlanImplications = {
  execution_ready: boolean;
  requires_plan_revision: boolean;
  active_operation_id: string | null;
  should_interrupt_active_operation: boolean;
  affected_fields: string[];
  blocking_clarifications: OperatingBriefClarification[];
  summary: string;
};

type InteractionInterpretation = {
  intent_classification: InteractionEventType;
  affected_fields: string[];
  confidence: number;
  rationale: string;
};

type InteractionPMAction = {
  action: PMAction;
  rationale: string;
};

export type CurrentOperatingBriefResponse = {
  brief: OperatingBrief;
};

export type InteractionEventResponse = {
  brief: OperatingBrief;
  event: InteractionEvent;
  interpretation: InteractionInterpretation;
  pm_action: InteractionPMAction;
  plan_implications: InteractionPlanImplications;
};

export type InteractionEventInput = {
  company_id: string;
  operation_id?: string | null;
  brief_id?: string | null;
  input: string;
};

export type RunStatus = "pending" | "running" | "paused" | "succeeded" | "failed" | "canceled" | string;

type NodeRunStatus = "pending" | "running" | "succeeded" | "failed" | "skipped" | string;

export type LLMMode = "managed" | "byok";

interface LLMAccessPayload {
  llm_mode?: LLMMode;
  provider?: string;
  credential_id?: string;
}

export interface RunLLMAccess {
  llm_mode: LLMMode;
  provider: string;
  credential_id?: string | null;
  api_key_present: boolean;
}

export interface RunListItem {
  id: string;
  thread_id?: string | null;
  graph_id: string;
  graph_name: string;
  graph_version_id: string;
  graph_version: number;
  status: RunStatus;
  queue_status?: string | null;
  queue_attempts?: number | null;
  queue_available_at?: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  trace_id?: string;
  memory_activity?: RunMemoryActivitySummary | null;
  llm_access?: RunLLMAccess | null;
}

interface MemoryObservationPreview {
  id?: string;
  type?: string;
  title?: string;
  scope?: string;
  topic_key?: string;
  tool_name?: string;
  content_preview?: string;
}

interface NodeMemoryActivity {
  category?: "save" | "retrieval" | "influence" | string;
  operation?: "save" | "search" | "context" | "timeline" | "context_use" | string;
  scope?: string;
  query?: string;
  count?: number;
  degraded?: boolean;
  strategies?: string[];
  saved?: boolean;
  saved_observation_count?: number;
  observation?: MemoryObservationPreview | null;
  observations?: MemoryObservationPreview[];
  observation_count?: number;
  curated_context_paths?: string[];
}

interface RunMemoryOperation extends NodeMemoryActivity {
  node_id: string;
  node_type: string;
  status: NodeRunStatus;
  attempt: number;
  duration_ms?: number | null;
}

export interface RunMemoryActivitySummary {
  has_activity: boolean;
  save_node_count: number;
  saved_observation_count: number;
  retrieval_node_count: number;
  retrieved_observation_count: number;
  influenced_node_count: number;
  influenced_observation_count: number;
  degraded: boolean;
  operations?: RunMemoryOperation[];
}

export interface MemoryObservation {
  id: string;
  tenant_id: string;
  graph_id: string | null;
  run_id: string | null;
  session_id: string | null;
  agent_id: string | null;
  memory_chunk_id: string | null;
  type: string;
  title: string;
  content: string;
  scope: string;
  topic_key: string;
  tool_name: string;
  source_event_id: string;
  source_event_type: string;
  fact_hash: string;
  provenance: Record<string, unknown>;
  cost_metadata: Record<string, unknown>;
  retention_policy: Record<string, unknown>;
  revision_count: number;
  duplicate_count: number;
  last_seen_at: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  is_deleted: boolean;
}

export interface MemoryObservationSearchParams {
  query?: string;
  graph_id?: string;
  run_id?: string;
  session_id?: string;
  agent_id?: string;
  scope?: string;
  type?: string;
  topic_key?: string;
  limit?: number;
  include_deleted?: boolean;
}

export interface MemoryObservationTimelineParams {
  graph_id?: string;
  run_id?: string;
  session_id?: string;
  agent_id?: string;
  scope?: string;
  limit?: number;
  include_deleted?: boolean;
}

export interface MemoryObservationContextParams {
  query?: string;
  graph_id?: string;
  run_id?: string;
  session_id?: string;
  agent_id?: string;
  limit?: number;
}

export interface ObservationContextResponse {
  observations: MemoryObservation[];
  degraded: boolean;
  strategies: string[];
  limit: number;
}

export interface NodeRunItem {
  id: string;
  node_id: string;
  node_type: string;
  status: NodeRunStatus;
  attempt: number;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown> | null;
  error_json: Record<string, unknown> | null;
  agent_trace?: AgentTrace | null;
  memory_activity?: NodeMemoryActivity | null;
}

export interface AgentEventItem {
  event: string;
  node_id?: string;
  node_type?: string;
  attempt?: number;
  step_index?: number;
  tool?: string;
  status?: string;
  stop_reason?: string;
  chunk_index?: number;
  [key: string]: unknown;
}

export interface AgentTraceStep {
  step_index?: number;
  action?: string;
  tool?: string;
  tool_input?: unknown;
  tool_output?: unknown;
  final_answer?: string;
  error?: string;
  approval_required?: boolean;
  response_model?: string;
  finish_reason?: string;
  usage?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface AgentTrace {
  final_output?: string;
  stop_reason?: string;
  step_count?: number;
  tool_call_count?: number;
  steps?: AgentTraceStep[];
  events?: AgentEventItem[];
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    [key: string]: unknown;
  } | null;
  approval_pending?: boolean;
  model?: string;
  provider?: string;
  allowed_tools?: string[];
  agent_node_id?: string;
  agent_node_name?: string;
  [key: string]: unknown;
}

export interface RunDetail {
  id: string;
  owner_id: string;
  thread_id?: string | null;
  graph_id: string;
  graph_name: string;
  graph_version_id: string;
  graph_version: number;
  status: RunStatus;
  queue_status?: string | null;
  queue_attempts?: number | null;
  queue_available_at?: string | null;
  started_at: string | null;
  ended_at: string | null;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown> | null;
  error_message: string;
  recovery_state?: string | null;
  recovery_reason?: string | null;
  resume_attempt_id?: string | null;
  duration_ms: number | null;
  trace_id?: string;
  node_runs: NodeRunItem[];
  agent_events?: AgentEventItem[] | null;
  timeline?: Array<{
    id: string;
    timestamp: string;
    kind: "event" | "decision" | "cost" | "error" | string;
    event_type: string;
    trace_id?: string | null;
    run_id: string;
    node_id?: string | null;
    status?: string | null;
    duration_ms?: number | null;
    cost_usd?: number | null;
    decision_id?: string | null;
    message?: string | null;
    error_message?: string | null;
    details?: Record<string, unknown> | null;
  }> | null;
  memory_activity?: RunMemoryActivitySummary | null;
  llm_access?: RunLLMAccess | null;
  // Human Gate pause fields
  paused_node_id?: string | null;
  pause_payload?: {
    prompt_message?: string;
    required_fields?: string[];
    node_id?: string;
    node_name?: string;
  } | null;
}

export interface ResumeRunResponse {
  resumed: boolean;
  run_id?: string;
  duplicate?: boolean;
  already_applied?: boolean;
  resume_attempt_id?: string;
  decision_status?: string;
  idempotency?: {
    status: "applied" | "already_applied" | "rejected" | "retry_required";
    idempotency_key: string;
    resource_type: string;
    resource_id: string;
  };
}

export interface ApprovalTask {
  id: string;
  run_id: string;
  run_name: string;
  graph_name: string;
  node_id: string;
  node_name: string;
  status: "pending" | "approved" | "rejected";
  prompt_message: string;
  payload?: {
    prompt_message?: string;
    required_fields?: string[];
  };
  result?: Record<string, unknown> | null;
  created_at: string;
  resolved_at?: string | null;
}

export interface AgentRegistryEntry {
  id: string;
  organization_id: string;
  slug: string;
  display_name: string;
  status: "idle" | "active" | "attention" | "offline" | string;
  source_workflow_id: string;
  source_workflow_revision_id: string | null;
  source_node_id: string;
  default_model: string;
  last_execution_id: string | null;
  last_seen_at: string | null;
  policy_snapshot_json: Record<string, unknown>;
  capabilities_json: Record<string, unknown>;
  task_count: number;
  pending_decisions: number;
  total_cost_usd: number;
  created_at: string;
  updated_at: string;
}

type TaskLifecycleStatus =
  | "created"
  | "queued"
  | "claimed"
  | "running"
  | "paused"
  | "waiting_for_decision"
  | "retry_scheduled"
  | "completed"
  | "failed"
  | "dead_lettered"
  | "cancelled"
  | string;

interface TaskDeadLetterSummary {
  id?: string;
  reason?: string;
  attempt_count?: number;
  last_error?: string;
  recovery_options?: string[];
  status?: string;
  intent_id?: string | null;
  created_at?: string | null;
  acknowledged_at?: string | null;
}

interface TaskRetrySummary {
  id?: string;
  operation_type?: string;
  idempotency_key?: string;
  attempt_number?: number;
  max_attempts?: number;
  retry_delay_ms?: number;
  retry_reason?: string;
  last_error?: string;
  owning_component?: string;
  next_scheduled_at?: string | null;
  terminal_fallback?: string;
  retry_class?: string;
  status?: string;
}

export interface TaskRecord {
  id: string;
  organization_id: string;
  execution_id: string;
  agent_id: string | null;
  title: string;
  status: TaskLifecycleStatus;
  priority: "low" | "normal" | "high" | "urgent" | string;
  summary: string;
  source_node_id: string;
  current_step_id: string | null;
  current_decision_id: string | null;
  lifecycle_task_id?: string | null;
  attempt_count?: number | null;
  retry_metadata?: Record<string, unknown> | null;
  latest_retry?: TaskRetrySummary | null;
  dead_letter?: TaskDeadLetterSummary | null;
  stale_event_count?: number | null;
  late_event_count?: number | null;
  recovery_options?: string[] | null;
  judge?: TaskJudgeSummary | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
}

interface TaskJudgeSummary {
  id: string;
  title: string;
  criteria_count: number;
  pass_threshold: number;
  status: "pending" | "passed" | "failed" | "inconclusive" | string;
  score: number | null;
  evaluated_at: string | null;
}

export interface TaskJudge {
  id: string;
  task_id: string;
  organization_id: string;
  execution_id: string;
  source_node_id: string;
  title: string;
  instructions: string;
  criteria: string[];
  pass_threshold: number;
  status: "pending" | "passed" | "failed" | "inconclusive" | string;
  score: number | null;
  result: Record<string, unknown>;
  evaluated_at: string | null;
  created_at: string;
  updated_at: string;
}

export type TaskJudgeInput = {
  title?: string;
  instructions?: string;
  criteria: string[];
  pass_threshold?: number;
  evidence_snapshot?: Record<string, unknown>;
};

export interface DecisionRecord {
  id: string;
  organization_id: string;
  execution_id: string | null;
  task_id: string | null;
  task_lifecycle_id?: string | null;
  agent_id: string | null;
  decision_type: "human_approval" | "policy_guardrail" | "marketplace_review" | "operator_intervention" | string;
  status: "pending" | "approved" | "rejected" | "resolved" | string;
  source_approval_task_id: string | null;
  context_json: Record<string, unknown>;
  resolution_json: Record<string, unknown>;
  requested_at: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface OperatorTaskLifecycle {
  id: string;
  run_id: string;
  organization_id: string;
  source_node_id: string;
  node_type: string;
  title: string;
  status: TaskLifecycleStatus;
  priority: string;
  summary: string;
  current_attempt: number;
  current_node_run_id?: string | null;
  current_decision_id?: string | null;
  retry_metadata?: Record<string, unknown> | null;
  recovery_options?: string[];
  unresolved_error?: string;
  stale_event_count: number;
  late_event_count: number;
  started_at?: string | null;
  ended_at?: string | null;
  last_transition_at?: string | null;
  latest_retry?: TaskRetrySummary | null;
  dead_letter?: TaskDeadLetterSummary | null;
}

export interface OperatorRunState {
  run: {
    id: string;
    status: RunStatus;
    current_attempt?: string | null;
    recovery_state?: string | null;
    recovery_reason?: string | null;
    resume_attempt_id?: string | null;
    last_progress_at?: string | null;
    last_heartbeat_at?: string | null;
    engine_instance_id?: string | null;
    error_message?: string;
  };
  active_tasks: OperatorTaskLifecycle[];
  tasks: OperatorTaskLifecycle[];
  pending_decisions: Array<{
    id: string;
    status: string;
    decision_type: string;
    task_id?: string | null;
    task_lifecycle_id?: string | null;
    requested_at?: string | null;
  }>;
  last_checkpoint?: { node_id: string; step_index: number; updated_at: string } | null;
  last_backend_state_mutation?: {
    id: string;
    event_type: string;
    outcome: string;
    to_status: string;
    occurred_at: string;
  } | null;
  last_engine_callback?: {
    id: string;
    event_type: string;
    created_at: string;
    payload?: Record<string, unknown> | string | null;
  } | null;
  unresolved_errors: string[];
  dead_letter_count: number;
  cost_to_date: number;
  memory_writes: number;
  audit_timeline: Array<{
    id: string;
    action: string;
    resource_type: string;
    created_at: string;
    metadata?: Record<string, unknown> | null;
  }>;
}

export interface OperatorRuntimeIntentBacklog {
  stream: string;
  dead_letter_stream: string;
  stream_length: number;
  pending: number;
  lag: number;
  backlog: number;
  dead_letter_count: number;
  recent_dead_letters: Array<{
    message_id: string;
    intent_id: string;
    intent_type: string;
    run_id: string;
    attempt_id: string;
    reason: string;
    error_class: string;
    dead_lettered_at: string;
  }>;
}

export interface OperatorDeadLetters {
  task_dead_letters: TaskDeadLetterSummary[];
  event_dead_letters: OperatorEventDeadLetter[];
  runtime_intent_outcomes: Array<{
    intent_id: string;
    run_id?: string | null;
    intent_type: string;
    attempt_id: string;
    reason: string;
    error_class: string;
    acknowledged_at?: string | null;
    processed_at: string;
  }>;
}

export interface OperatorEventDeadLetter {
  id: string;
  organization_id?: string | null;
  run_id?: string | null;
  event_id: string;
  idempotency_key: string;
  event_type: string;
  source: string;
  reason: string;
  error_class: string;
  retry_count: number;
  status: "active" | "acknowledged" | "replay_requested" | "resolved" | string;
  payload?: Record<string, unknown> | null;
  last_replay_action: string;
  replay_requested_at?: string | null;
  replay_requested_by?: string | null;
  acknowledged_at?: string | null;
  acknowledgement_reason: string;
  first_seen_at: string;
  last_seen_at: string;
}

type OpsDeadLetterKind = "task" | "event" | "runtime_intent";

export interface OpsDeadLetter {
  id: string;
  native_id: string;
  kind: OpsDeadLetterKind;
  organization_id?: string | null;
  run_id?: string | null;
  status: string;
  title: string;
  source: string;
  event_type?: string | null;
  event_id?: string | null;
  intent_id?: string | null;
  idempotency_key?: string | null;
  reason: string;
  last_error?: string | null;
  retry_count: number;
  attempt_count: number;
  created_at: string;
  last_seen_at: string;
  acknowledged_at?: string | null;
  recovery_options: string[];
  actions: string[];
}

export interface OpsDeadLetterDetail extends OpsDeadLetter {
  payload?: Record<string, unknown> | null;
  operator_actions: Array<{
    id: string;
    action: string;
    status: string;
    reason: string;
    actor_id?: string | null;
    idempotency_key?: string;
    metadata?: Record<string, unknown> | null;
    created_at: string;
  }>;
  audit_history: Array<{
    id: string;
    action: string;
    actor_id?: string | null;
    metadata?: Record<string, unknown> | null;
    created_at: string;
  }>;
}

export interface OpsDeadLetterList {
  organization_id: string;
  items: OpsDeadLetter[];
  counts: {
    total: number;
    active: number;
    task: number;
    event: number;
    runtime_intent: number;
  };
}

export interface OpsDeadLetterActionResponse {
  status: "replayed" | "replay_requested" | "resolved" | string;
  dead_letter: OpsDeadLetter;
  intent_id?: string;
  replay_message_id?: string;
  projection_names?: string[];
  processed?: number;
}

export interface OpsProjectionLag {
  organization_id: string;
  projection: ProjectionMetadata;
  latest_domain_event?: OpsDomainEventMetadata | null;
  cursors: Array<{
    projection_name: string;
    last_sequence: number;
    last_event_id: string;
    status: string;
    last_error: string;
    updated_at: string;
  }>;
  active_dead_letters: OpsDeadLetter[];
}

interface OpsDomainEventMetadata {
  id: string;
  organization_id: string;
  aggregate_type: string;
  aggregate_id: string;
  event_type: string;
  event_version: number;
  sequence: number;
  idempotency_key: string;
  payload_keys: string[];
  occurred_at: string;
  created_at: string;
}

export interface OpsEventSpool {
  organization_id: string;
  domain_events: {
    count: number;
    latest_sequence: number;
    recent: OpsDomainEventMetadata[];
  };
  state_feed_events: {
    count: number;
    latest_state_version: number;
    recent: Array<{
      id: string;
      event_id: string;
      organization_id: string;
      state_version: number;
      type: string;
      resource: { type: string; id: string };
      requires_refetch: boolean;
      occurred_at: string;
      created_at: string;
    }>;
  };
  dead_letters: {
    active_count: number;
    recent: OpsDeadLetter[];
  };
  generated_at: string;
}

export interface OpsRuntimeIntentLag {
  organization_id: string;
  stream: string;
  dead_letter_stream: string;
  stream_length: number;
  pending: number;
  lag: number;
  backlog: number;
  consumer_idle_ms: number;
  oldest_pending_idle_ms: number;
  dead_letter_count: number;
  source: string;
  error: string;
  recent_dead_letters: OperatorRuntimeIntentBacklog["recent_dead_letters"];
  recent_runtime_outcomes: OpsDeadLetter[];
  generated_at: string;
}

export interface OperatorOrgLoad {
  organization_id: string;
  runs: Record<string, number>;
  tasks: Array<{ status: string; count: number }>;
  retry_operations: Array<{ status: string; count: number }>;
  dead_letters: number;
  event_dead_letters?: number;
}

export interface OperatorWebSocketSubscribers {
  total: number;
  by_org: Record<string, number>;
  by_run: Record<string, number>;
  by_user: Record<string, number>;
  subscribers?: Array<Record<string, unknown>>;
}

export interface CostLedgerEntry {
  id: string;
  organization_id: string;
  execution_id: string | null;
  task_id: string | null;
  agent_id: string | null;
  workflow_revision_id: string | null;
  provider: string;
  model: string;
  cost_type: string;
  quantity: number;
  unit_cost_usd: number;
  total_cost_usd: number;
  occurred_at: string;
}

interface CostAggregate {
  id: string;
  grain: "hourly" | "daily" | string;
  period_start: string;
  period_end: string;
  provider: string;
  model: string;
  cost_type: string;
  total_cost_usd: number;
  total_quantity: number;
  entry_count: number;
}

export type MetricProvenance = {
  source: string;
  computed_at: string | null;
  freshness_ms: number | null;
  status: "available" | "not_instrumented" | "stale" | "error" | string;
  value?: number | null;
};

export type AccountingMetric =
  | {
      status: "available";
      value: number;
      currency: string;
      computed_at: string;
      source: string;
    }
  | {
      status: "not_instrumented";
      reason: string;
      computed_at: string;
      source: string;
    };

export type ProjectionMetadata = {
  computed_at: string;
  last_sequence?: number;
  state_feed_version?: number;
  lag_seconds?: number | null;
  status?: "fresh" | "stale" | "rebuilding" | "degraded" | string;
  projection_lag_ms: number | null;
  last_event_id: string;
  watermark: string | null;
  source?: string;
  last_updated_at?: string;
  freshness_ms?: number;
  stale?: boolean;
  degraded?: boolean;
};

export type OverviewSectionMetadata = {
  source: string;
  computed_at: string;
  last_updated_at: string;
  freshness_ms: number;
  status: "fresh" | "stale" | "rebuilding" | "degraded" | "available" | "not_instrumented" | string;
  stale: boolean;
  degraded: boolean;
};

type RunningOverviewSection = OverviewSectionMetadata & {
  active_agent_count: number;
  running_task_count: number;
  operation_count_24h: number;
  items: TaskRecord[];
};

type BlockedOverviewSection = OverviewSectionMetadata & {
  blocked_task_count: number;
  items: TaskRecord[];
};

type DecisionsOverviewSection = OverviewSectionMetadata & {
  pending_decision_count: number;
  items: DecisionRecord[];
};

type CostsOverviewSection = OverviewSectionMetadata & {
  total_cost_usd: number;
  currency: string;
  metric?: AccountingMetric;
  cost_by_type: Array<{
    cost_type: string;
    total_cost_usd: number;
    entry_count: number;
  }>;
};

type FailuresOverviewSection = OverviewSectionMetadata & {
  dead_letter_count: number;
  task_dead_letter_count: number;
  event_dead_letter_count: number;
  runtime_intent_dead_letter_count: number;
  runtime_intent_lag_seconds: number;
};

export interface AccountingOverview {
  organization_id: string;
  total_cost_usd: number;
  generated_at?: string;
  projection?: ProjectionMetadata;
  metrics?: {
    cost?: AccountingMetric;
    revenue?: AccountingMetric;
    profit?: AccountingMetric;
  };
  metric_provenance?: {
    total_cost_usd?: MetricProvenance;
    revenue?: MetricProvenance;
    profit?: MetricProvenance;
  };
  cost_by_type: Array<{
    cost_type: string;
    total_cost_usd: number;
    entry_count: number;
  }>;
  top_agents: Array<{
    id: string;
    display_name: string;
    status: string;
    total_cost_usd: number;
  }>;
  recent_aggregates: CostAggregate[];
}

export interface OrganizationStateSummary {
  organization: {
    id: string;
    name: string;
  };
  summary: {
    active_agent_count: number;
    active_task_count: number;
    pending_decision_count: number;
    execution_count_24h: number;
    memory_observation_count: number;
    total_cost_usd: number;
  };
  active_agents: AgentRegistryEntry[];
  active_tasks: TaskRecord[];
  pending_decisions: DecisionRecord[];
  recent_executions: Array<{
    id: string;
    workflow_id: string;
    workflow_name: string;
    workflow_revision_id: string;
    status: string;
    started_at: string | null;
    ended_at: string | null;
    duration_ms: number | null;
  }>;
  running?: RunningOverviewSection;
  blocked?: BlockedOverviewSection;
  decisions?: DecisionsOverviewSection;
  costs?: CostsOverviewSection;
  failures?: FailuresOverviewSection;
  memory: Partial<OverviewSectionMetadata> & {
    active_observation_count: number;
    memory_write_count_24h?: number;
    recent_topics: string[];
  };
  policy: {
    configured: boolean;
    allowed_providers: string[];
    allowed_models: string[];
    http_default_deny: boolean;
  };
  accounting: AccountingOverview;
  operations?: {
    status: "fresh" | "degraded" | string;
    dead_letter_count: number;
    task_dead_letter_count: number;
    event_dead_letter_count: number;
    runtime_intent_dead_letter_count: number;
    projection_status: string;
    projection_lag_seconds: number;
    runtime_intent_lag_seconds?: number;
    generated_at: string;
  };
  generated_at: string;
  projection?: ProjectionMetadata;
}

export interface ResumeRunInput {
  node_id: string;
  submit_id?: string;
  input_json: {
    approved: boolean;
    fields?: Record<string, string>;
    feedback?: string;
  };
}

export interface StartRunInput extends LLMAccessPayload {
  graph_version_id: string;
  input_json?: Record<string, unknown>;
}

export interface InvokeRunInput extends LLMAccessPayload {
  thread_id: string;
  input_json?: Record<string, unknown>;
}

export interface ReplayRunInput extends LLMAccessPayload {
  node_id?: string;
}

export const runsApi = {
  list: async (): Promise<RunListItem[]> => {
    const response = await api.get<ApiSuccessResponse<RunListItem[]>>(API_PATHS.runs.list);
    return response.data.data;
  },

  get: async (runId: string): Promise<RunDetail> => {
    const response = await api.get<ApiSuccessResponse<RunDetail>>(API_PATHS.runs.detail(runId), {
      params: {
        _ts: Date.now(),
      },
    });
    return response.data.data;
  },

  start: async (input: StartRunInput, options?: IdempotencyOptions): Promise<RunDetail> => {
    const response = await api.post<ApiSuccessResponse<RunDetail>>(
      API_PATHS.runs.start,
      input,
      idempotencyConfig(options),
    );
    return response.data.data;
  },

  invoke: async (input: InvokeRunInput, options?: IdempotencyOptions): Promise<RunDetail> => {
    const response = await api.post<ApiSuccessResponse<RunDetail>>(
      API_PATHS.runs.invoke,
      input,
      idempotencyConfig(options),
    );
    return response.data.data;
  },

  cancel: async (runId: string, options?: IdempotencyOptions): Promise<RunDetail> => {
    const response = await api.post<ApiSuccessResponse<RunDetail>>(
      API_PATHS.runs.cancel(runId),
      {},
      idempotencyConfig(options),
    );
    return response.data.data;
  },

  resume: async (runId: string, input: ResumeRunInput, options?: IdempotencyOptions): Promise<ResumeRunResponse> => {
    const response = await api.post<ApiSuccessResponse<ResumeRunResponse>>(
      API_PATHS.runs.resume(runId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data;
  },

  replay: async (runId: string, input?: ReplayRunInput, options?: IdempotencyOptions): Promise<RunDetail> => {
    const response = await api.post<ApiSuccessResponse<RunDetail>>(
      API_PATHS.runs.replay(runId),
      input ?? {},
      idempotencyConfig(options),
    );
    return response.data.data;
  },
};

export const interactionApi = {
  getCurrentBrief: async (companyId: string, operationId?: string | null): Promise<OperatingBrief> => {
    const response = await api.get<ApiSuccessResponse<CurrentOperatingBriefResponse>>(
      API_PATHS.interaction.currentBrief,
      {
        params: {
          company_id: companyId,
          ...(operationId ? { operation_id: operationId } : {}),
        },
      },
    );
    return response.data.data.brief;
  },

  submitEvent: async (input: InteractionEventInput): Promise<InteractionEventResponse> => {
    const response = await api.post<ApiSuccessResponse<InteractionEventResponse>>(API_PATHS.interaction.events, input);
    return response.data.data;
  },
};

export const memoryApi = {
  search: async (params?: MemoryObservationSearchParams): Promise<MemoryObservation[]> => {
    const response = await api.get<ApiSuccessResponse<MemoryObservation[]>>(API_PATHS.memory.search, {
      params,
    });
    return response.data.data;
  },

  timeline: async (params?: MemoryObservationTimelineParams): Promise<MemoryObservation[]> => {
    const response = await api.get<ApiSuccessResponse<MemoryObservation[]>>(API_PATHS.memory.timeline, {
      params,
    });
    return response.data.data;
  },

  get: async (observationId: string, params?: { include_deleted?: boolean }): Promise<MemoryObservation> => {
    const response = await api.get<ApiSuccessResponse<MemoryObservation>>(API_PATHS.memory.detail(observationId), {
      params,
    });
    return response.data.data;
  },

  getContext: async (params?: MemoryObservationContextParams): Promise<ObservationContextResponse> => {
    const response = await api.get<ApiSuccessResponse<ObservationContextResponse>>(API_PATHS.memory.context, {
      params,
    });
    return response.data.data;
  },
};

export const approvalsApi = {
  list: async (status?: string): Promise<ApprovalTask[]> => {
    const params = status ? { status } : {};
    const response = await api.get<ApiSuccessResponse<ApprovalTask[]>>(API_PATHS.approvals.list, { params });
    return response.data.data;
  },

  count: async (): Promise<{ count: number }> => {
    const response = await api.get<ApiSuccessResponse<{ count: number }>>(API_PATHS.approvals.count);
    return response.data.data;
  },

  get: async (approvalId: string): Promise<ApprovalTask> => {
    const response = await api.get<ApiSuccessResponse<ApprovalTask>>(API_PATHS.approvals.detail(approvalId));
    return response.data.data;
  },
};

export const workflowsApi = {
  list: async (): Promise<GraphListItem[]> => {
    const response = await api.get<ApiSuccessResponse<GraphListItem[]>>(API_PATHS.workflows.listCreate);
    return response.data.data;
  },
  create: async (input: GraphCreateInput): Promise<GraphListItem> => {
    const response = await api.post<ApiSuccessResponse<GraphListItem>>(API_PATHS.workflows.listCreate, input);
    return response.data.data;
  },
  get: async (workflowId: string): Promise<GraphDetail> => {
    const response = await api.get<ApiSuccessResponse<GraphDetail>>(API_PATHS.workflows.detail(workflowId));
    return response.data.data;
  },
  update: async (workflowId: string, input: GraphUpdateInput): Promise<GraphListItem> => {
    const response = await api.patch<ApiSuccessResponse<GraphListItem>>(API_PATHS.workflows.detail(workflowId), input);
    return response.data.data;
  },
  delete: async (workflowId: string): Promise<void> => {
    await api.delete(API_PATHS.workflows.detail(workflowId));
  },
  listRevisions: async (workflowId: string): Promise<GraphVersionSummary[]> => {
    const response = await api.get<ApiSuccessResponse<GraphVersionSummary[]>>(API_PATHS.workflows.versions(workflowId));
    return response.data.data;
  },
  getLatestRevision: async (workflowId: string): Promise<GraphVersion | null> => {
    try {
      const response = await api.get<ApiSuccessResponse<GraphVersion>>(API_PATHS.workflows.latestVersion(workflowId));
      return response.data.data;
    } catch (error) {
      if ((error as AxiosError)?.response?.status === 404) {
        return null;
      }
      throw error;
    }
  },
};

export const executionsApi = {
  list: async (): Promise<RunListItem[]> => {
    const response = await api.get<ApiSuccessResponse<RunListItem[]>>(API_PATHS.executions.list);
    return response.data.data;
  },
  get: async (executionId: string): Promise<RunDetail> => {
    const response = await api.get<ApiSuccessResponse<RunDetail>>(API_PATHS.executions.detail(executionId));
    return response.data.data;
  },
};

export const agentsApi = {
  list: async (): Promise<AgentRegistryEntry[]> => {
    const response = await api.get<ApiSuccessResponse<AgentRegistryEntry[]>>(API_PATHS.agents.list);
    return response.data.data;
  },
  get: async (agentId: string): Promise<AgentRegistryEntry> => {
    const response = await api.get<ApiSuccessResponse<AgentRegistryEntry>>(API_PATHS.agents.detail(agentId));
    return response.data.data;
  },
};

export const tasksApi = {
  list: async (status?: string): Promise<TaskRecord[]> => {
    const response = await api.get<ApiSuccessResponse<TaskRecord[]>>(API_PATHS.tasks.list, {
      params: status ? { status } : {},
    });
    return response.data.data;
  },
  get: async (taskId: string): Promise<TaskRecord> => {
    const response = await api.get<ApiSuccessResponse<TaskRecord>>(API_PATHS.tasks.detail(taskId));
    return response.data.data;
  },
  getJudge: async (taskId: string): Promise<TaskJudge | null> => {
    const response = await api.get<ApiSuccessResponse<{ judge: TaskJudge | null }>>(API_PATHS.tasks.judge(taskId));
    return response.data.data.judge;
  },
  saveJudge: async (taskId: string, input: TaskJudgeInput): Promise<TaskJudge> => {
    const response = await api.put<ApiSuccessResponse<{ judge: TaskJudge }>>(API_PATHS.tasks.judge(taskId), input);
    return response.data.data.judge;
  },
  deleteJudge: async (taskId: string): Promise<void> => {
    await api.delete<ApiSuccessResponse<{ judge: null }>>(API_PATHS.tasks.judge(taskId));
  },
  evaluateJudge: async (taskId: string): Promise<TaskJudge> => {
    const response = await api.post<ApiSuccessResponse<{ judge: TaskJudge }>>(API_PATHS.tasks.judgeEvaluation(taskId));
    return response.data.data.judge;
  },
};

export const operatorApi = {
  getRunState: async (runId: string): Promise<OperatorRunState> => {
    const response = await api.get<ApiSuccessResponse<OperatorRunState>>(API_PATHS.operator.runState(runId));
    return response.data.data;
  },
  getTaskState: async (
    taskId: string,
  ): Promise<{ task: OperatorTaskLifecycle; attempts: unknown[]; events: unknown[] }> => {
    const response = await api.get<
      ApiSuccessResponse<{ task: OperatorTaskLifecycle; attempts: unknown[]; events: unknown[] }>
    >(API_PATHS.operator.taskState(taskId));
    return response.data.data;
  },
  getRuntimeIntentBacklog: async (): Promise<OperatorRuntimeIntentBacklog> => {
    const response = await api.get<ApiSuccessResponse<OperatorRuntimeIntentBacklog>>(
      API_PATHS.operator.runtimeIntentBacklog,
    );
    return response.data.data;
  },
  getDeadLetters: async (): Promise<OperatorDeadLetters> => {
    const response = await api.get<ApiSuccessResponse<OperatorDeadLetters>>(API_PATHS.operator.deadLetters);
    return response.data.data;
  },
  replayIntent: async (
    intentId: string,
    reason: string,
    options?: IdempotencyOptions,
  ): Promise<{ intent_id: string; replay_message_id: string }> => {
    const response = await api.post<ApiSuccessResponse<{ intent_id: string; replay_message_id: string }>>(
      API_PATHS.operator.replayIntent(intentId),
      { reason },
      idempotencyConfig(options),
    );
    return response.data.data;
  },
  acknowledgeIntent: async (
    intentId: string,
    reason: string,
    options?: IdempotencyOptions,
  ): Promise<{ intent_id: string; acknowledged_at: string }> => {
    const response = await api.post<ApiSuccessResponse<{ intent_id: string; acknowledged_at: string }>>(
      API_PATHS.operator.acknowledgeIntent(intentId),
      { reason },
      idempotencyConfig(options),
    );
    return response.data.data;
  },
  replayEventDeadLetter: async (
    deadLetterId: string,
    reason: string,
    options?: IdempotencyOptions,
  ): Promise<OperatorEventDeadLetter> => {
    const response = await api.post<ApiSuccessResponse<OperatorEventDeadLetter>>(
      API_PATHS.operator.replayEventDeadLetter(deadLetterId),
      { reason },
      idempotencyConfig(options),
    );
    return response.data.data;
  },
  acknowledgeEventDeadLetter: async (
    deadLetterId: string,
    reason: string,
    options?: IdempotencyOptions,
  ): Promise<OperatorEventDeadLetter> => {
    const response = await api.post<ApiSuccessResponse<OperatorEventDeadLetter>>(
      API_PATHS.operator.acknowledgeEventDeadLetter(deadLetterId),
      { reason },
      idempotencyConfig(options),
    );
    return response.data.data;
  },
  forceFailRun: async (runId: string, reason: string, options?: IdempotencyOptions): Promise<OperatorRunState> => {
    const response = await api.post<ApiSuccessResponse<OperatorRunState>>(
      API_PATHS.operator.forceFailRun(runId),
      {
        reason,
      },
      idempotencyConfig(options),
    );
    return response.data.data;
  },
  forceCancelRun: async (runId: string, reason: string, options?: IdempotencyOptions): Promise<OperatorRunState> => {
    const response = await api.post<ApiSuccessResponse<OperatorRunState>>(
      API_PATHS.operator.forceCancelRun(runId),
      {
        reason,
      },
      idempotencyConfig(options),
    );
    return response.data.data;
  },
  forceRehydrateRun: async (runId: string, reason: string, options?: IdempotencyOptions): Promise<OperatorRunState> => {
    const response = await api.post<ApiSuccessResponse<OperatorRunState>>(
      API_PATHS.operator.forceRehydrateRun(runId),
      {
        reason,
      },
      idempotencyConfig(options),
    );
    return response.data.data;
  },
  getWebSocketSubscribers: async (): Promise<OperatorWebSocketSubscribers> => {
    const response = await api.get<ApiSuccessResponse<OperatorWebSocketSubscribers>>(API_PATHS.operator.wsSubscribers);
    return response.data.data;
  },
  getOrgLoad: async (): Promise<OperatorOrgLoad> => {
    const response = await api.get<ApiSuccessResponse<OperatorOrgLoad>>(API_PATHS.operator.orgLoad);
    return response.data.data;
  },
};

export const opsApi = {
  getDeadLetters: async (): Promise<OpsDeadLetterList> => {
    const response = await api.get<ApiSuccessResponse<OpsDeadLetterList>>(API_PATHS.ops.deadLetters);
    return response.data.data;
  },
  getDeadLetter: async (deadLetterKey: string): Promise<OpsDeadLetterDetail> => {
    const response = await api.get<ApiSuccessResponse<OpsDeadLetterDetail>>(API_PATHS.ops.deadLetter(deadLetterKey));
    return response.data.data;
  },
  replayDeadLetter: async (
    deadLetterKey: string,
    reason: string,
    options: IdempotencyOptions,
  ): Promise<OpsDeadLetterActionResponse> => {
    const response = await api.post<ApiSuccessResponse<OpsDeadLetterActionResponse>>(
      API_PATHS.ops.replayDeadLetter(deadLetterKey),
      { reason },
      idempotencyConfig(options),
    );
    return response.data.data;
  },
  resolveDeadLetter: async (
    deadLetterKey: string,
    reason: string,
    options?: IdempotencyOptions,
  ): Promise<OpsDeadLetterActionResponse> => {
    const response = await api.post<ApiSuccessResponse<OpsDeadLetterActionResponse>>(
      API_PATHS.ops.resolveDeadLetter(deadLetterKey),
      { reason },
      idempotencyConfig(options),
    );
    return response.data.data;
  },
  getProjectionLag: async (): Promise<OpsProjectionLag> => {
    const response = await api.get<ApiSuccessResponse<OpsProjectionLag>>(API_PATHS.ops.projectionLag);
    return response.data.data;
  },
  getEventSpool: async (): Promise<OpsEventSpool> => {
    const response = await api.get<ApiSuccessResponse<OpsEventSpool>>(API_PATHS.ops.eventSpool);
    return response.data.data;
  },
  getRuntimeIntentLag: async (): Promise<OpsRuntimeIntentLag> => {
    const response = await api.get<ApiSuccessResponse<OpsRuntimeIntentLag>>(API_PATHS.ops.runtimeIntentLag);
    return response.data.data;
  },
};

export const decisionsApi = {
  list: async (status?: string): Promise<DecisionRecord[]> => {
    const response = await api.get<ApiSuccessResponse<DecisionRecord[]>>(API_PATHS.decisions.list, {
      params: status ? { status } : {},
    });
    return response.data.data;
  },
  count: async (): Promise<{ count: number }> => {
    const response = await api.get<ApiSuccessResponse<{ count: number }>>(API_PATHS.decisions.count);
    return response.data.data;
  },
  get: async (decisionId: string): Promise<DecisionRecord> => {
    const response = await api.get<ApiSuccessResponse<DecisionRecord>>(API_PATHS.decisions.detail(decisionId));
    return response.data.data;
  },
};

export const accountingApi = {
  getOverview: async (): Promise<AccountingOverview> => {
    const response = await api.get<ApiSuccessResponse<AccountingOverview>>(API_PATHS.accounting.overview);
    return response.data.data;
  },
  listLedger: async (): Promise<CostLedgerEntry[]> => {
    const response = await api.get<ApiSuccessResponse<CostLedgerEntry[]>>(API_PATHS.accounting.ledger);
    return response.data.data;
  },
};

export const systemStateApi = {
  getOverview: async (): Promise<OrganizationStateSummary> => {
    const response = await api.get<ApiSuccessResponse<OrganizationStateSummary>>(API_PATHS.systemState.overview);
    return response.data.data;
  },
};

export const auditLogsApi = {
  list: async (params?: {
    action?: string;
    action_prefix?: string;
    resource_type?: string;
    resource_id?: string;
    actor_email?: string;
    created_from?: string;
    created_to?: string;
    q?: string;
    tenant_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<ApiSuccessResponse<AuditLogEntry[]>> => {
    const response = await api.get<ApiSuccessResponse<AuditLogEntry[]>>(API_PATHS.auditLogs.list, {
      params,
    });
    return response.data;
  },
};

export const organizationsApi = {
  list: async (): Promise<OrganizationListItem[]> => {
    const response = await api.get<ApiSuccessResponse<OrganizationListItem[]>>(API_PATHS.orgs.listCreate);
    return response.data.data;
  },

  create: async (input: { name: string; make_default?: boolean }): Promise<OrganizationListItem> => {
    const response = await api.post<ApiSuccessResponse<OrganizationListItem>>(API_PATHS.orgs.listCreate, input);
    return response.data.data;
  },

  switchCurrent: async (organizationId: string): Promise<OrganizationListItem> => {
    const response = await api.patch<ApiSuccessResponse<OrganizationListItem>>(API_PATHS.orgs.current, {
      organization_id: organizationId,
    });
    return response.data.data;
  },

  me: async (): Promise<OrganizationMeResponse> => {
    const response = await api.get<ApiSuccessResponse<OrganizationMeResponse>>(API_PATHS.orgs.me);
    return response.data.data;
  },

  listMembers: async (): Promise<OrganizationMember[]> => {
    const response = await api.get<ApiSuccessResponse<OrganizationMember[]>>(API_PATHS.orgs.members);
    return response.data.data;
  },

  addMember: async (input: { email: string; role: OrganizationMember["role"] }): Promise<OrganizationMember> => {
    const response = await api.post<ApiSuccessResponse<OrganizationMember>>(API_PATHS.orgs.members, input);
    return response.data.data;
  },

  updateMember: async (userId: string, input: { role: OrganizationMember["role"] }): Promise<OrganizationMember> => {
    const response = await api.patch<ApiSuccessResponse<OrganizationMember>>(
      API_PATHS.orgs.memberDetail(userId),
      input,
    );
    return response.data.data;
  },

  removeMember: async (userId: string): Promise<{ deleted: boolean }> => {
    const response = await api.delete<ApiSuccessResponse<{ deleted: boolean }>>(API_PATHS.orgs.memberDetail(userId));
    return response.data.data;
  },
};

export const policiesApi = {
  getGuardrails: async (): Promise<TenantGuardrailPolicy> => {
    const response = await api.get<ApiSuccessResponse<TenantGuardrailPolicy>>(API_PATHS.policies.guardrails);
    return response.data.data;
  },
};

export const retentionApi = {
  getPolicy: async (): Promise<TenantRetentionPolicyResponse> => {
    const response = await api.get<ApiSuccessResponse<TenantRetentionPolicyResponse>>(API_PATHS.retention.policy);
    return response.data.data;
  },
  previewCleanup: async (): Promise<RetentionCleanupPreview> => {
    const response = await api.post<ApiSuccessResponse<RetentionCleanupPreview>>(API_PATHS.retention.cleanup, {
      dry_run: true,
    });
    return response.data.data;
  },
  exportData: async (input: {
    type: RetentionExportType;
    startDate?: string;
    endDate?: string;
    limit?: number;
    offset?: number;
  }): Promise<Blob> => {
    const response = await api.get(API_PATHS.retention.export, {
      params: {
        type: input.type,
        start_date: input.startDate,
        end_date: input.endDate,
        limit: input.limit,
        offset: input.offset,
      },
      responseType: "blob",
    });
    return response.data as Blob;
  },
};

export const healthApi = {
  getMemory: async (): Promise<MemoryHealthResponse> => {
    const response = await api.get<MemoryHealthResponse>(API_PATHS.health.memory);
    return response.data;
  },
};

export const metricsApi = {
  getSummary: async (): Promise<MetricsSummary> => {
    const response = await api.get<ApiSuccessResponse<MetricsSummary>>(API_PATHS.metrics.summary);
    return response.data.data;
  },
  getSlo: async (): Promise<SreReadinessSummary> => {
    const response = await api.get<ApiSuccessResponse<SreReadinessSummary>>(API_PATHS.metrics.slo);
    return response.data.data;
  },
};

export type MemoryAnalyticsUsage = {
  period: string;
  start_date: string;
  end_date: string;
  tier1: {
    total_messages: number;
    avg_buffer_size: number;
    peak_buffer_size: number;
  };
  tier2: {
    redis_keys: number;
    storage_mb: number;
    hit_rate: number | null;
  };
  tier3: {
    chunks_stored: number;
    embeddings_generated: number;
    search_queries: number;
    avg_search_latency_ms: number | null;
  };
  curated_memory: {
    observations_total: number;
    observations_created_in_period: number;
    deleted_observations_total: number;
    indexed_observations_total: number;
    pending_index_total: number;
    graph_scope_total: number;
    run_scope_total: number;
    session_scope_total: number;
    retrieval_runs_in_period: number;
  };
  retention: {
    policy_configured: boolean;
    runs_retention_days: number | null;
    run_logs_retention_days: number | null;
    audit_logs_retention_days: number | null;
    usage_retention_days: number | null;
    observations_retention_days: number | null;
    memory_chunks_retention_days: number | null;
    observations_retention_mode: string;
    memory_chunks_retention_mode: string;
    summary: string;
  };
  costs: {
    summarization_usd: number;
    embedding_usd: number;
    total_usd: number;
  };
  usage_series: Array<{
    date: string;
    summarization_prompt_tokens: number;
    summarization_completion_tokens: number;
    summarization_total_tokens: number;
    summarization_cost_usd: number;
  }>;
  top_agents: Array<{
    agent_id: string | null;
    chunks: number;
  }>;
  totals: {
    summarization_prompt_tokens: number;
    summarization_completion_tokens: number;
    summarization_total_tokens: number;
  };
};

export type MemoryAnalyticsCosts = {
  period: string;
  start_date: string;
  end_date: string;
  currency: string;
  summarization_total_usd: number;
  embedding_total_usd: number;
  series: Array<{
    date: string;
    summarization_cost_usd: number;
  }>;
};

export type AuditLogEntry = {
  id: string;
  tenant_id: string;
  actor_email: string | null;
  action: string;
  resource_type: string;
  resource_id: string;
  description: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type MemoryAnalyticsPerformance = {
  period: string;
  start_date: string;
  end_date: string;
  vector: {
    search_queries: number;
    avg_search_latency_ms: number | null;
    chunks_indexed: number;
  };
  summarization: {
    runs: number;
    avg_latency_ms: number | null;
  };
  grpc: {
    requests_total: number;
    errors_total: number;
  };
  maintenance: {
    memory_gc_last_run_at: string | null;
    memory_gc_last_reindex: string | null;
  };
  indexing: {
    jobs_total: number;
    success_total: number;
    delete_total: number;
    enqueue_errors_total: number;
    delete_enqueue_errors_total: number;
    pending_observations_total: number;
    indexed_observations_total: number;
  };
};

export type LLMAnalyticsUsage = {
  period: string;
  start_date: string;
  end_date: string;
  totals: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost_usd: number;
  };
  series: Array<{
    date: string;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost_usd: number;
  }>;
  by_model: Array<{
    provider: string;
    model: string;
    total_tokens: number;
    cost_usd: number;
    calls: number;
  }>;
  by_provider: Array<{
    provider: string;
    total_tokens: number;
    cost_usd: number;
    calls: number;
  }>;
};

export type LLMAnalyticsCosts = {
  period: string;
  start_date: string;
  end_date: string;
  currency: string;
  total_usd: number;
  series: Array<{
    date: string;
    cost_usd: number;
  }>;
};

export type LLMBudgetStatus = {
  budget: {
    monthly_limit_usd: number;
    warning_threshold_pct: number;
  } | null;
  usage: {
    month_cost_usd: number;
  };
  warning_threshold_usd: number | null;
  warning: boolean;
  over_budget: boolean;
};

export type LLMQuotaStatus = {
  quota: {
    monthly_token_limit: number | null;
    monthly_cost_limit_usd: number | null;
  } | null;
  usage: {
    month_total_tokens: number;
    month_cost_usd: number;
  };
};

export type OperatingModelPack = {
  pack_id: string;
  base_pack_id: string;
  version: string;
  display_name: string;
  description: string;
  company_type_label: string;
  checksum: string;
  manifest: Record<string, unknown>;
  files: Record<string, unknown>;
};

export type OperatingModelInstallation = {
  id: string;
  company_id: string;
  pack_id: string;
  status: string;
  display_name: string;
  version: string;
  checksum: string;
  company_type_label?: string | null;
  config: Record<string, unknown>;
  dashboard: Record<string, unknown>;
  installed_at: string;
  updated_at: string;
};

export type CompanyProgramDTO = {
  id: string;
  company_id: string;
  pack_id: string;
  template_id: string;
  display_label: string;
  title: string;
  objective: string;
  status: string;
  current_stage_id: string;
  metadata: Record<string, unknown>;
  stages?: ProgramStageDTO[];
  created_at: string;
  updated_at: string;
};

type ProgramStageDTO = {
  id: string;
  program_id: string;
  stage_id: string;
  label: string;
  sequence: number;
  status: string;
  state: Record<string, unknown>;
  operation_template_ids?: string[];
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
};

export type ProgramOperationDTO = {
  id: string;
  company_id: string;
  status: string;
  operation_type: string;
  operation_label: string;
  operation_brief: string;
  program_id: string | null;
  stage_id: string | null;
  started_at: string | null;
  created_at: string | null;
};

export type AssertionRecordDTO = {
  id: string;
  company_id: string;
  program_id: string | null;
  kind: "FACT" | "OPINION" | "ASSUMPTION" | "QUESTION" | string;
  pack_label: string;
  category: string;
  statement: string;
  source: string;
  confidence: number;
  validation_status: string;
  evidence_refs: unknown[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type WorkArtifactDTO = {
  id: string;
  company_id: string;
  title: string;
  artifact_type: string;
  program_id?: string | null;
  status: string;
  metadata: Record<string, unknown>;
  canonical_revision_id: string | null;
  revisions?: ArtifactRevisionDTO[];
  created_at: string;
  updated_at: string;
};

export type ArtifactRevisionDTO = {
  id: string;
  asset_id: string;
  version_number: number;
  label: string;
  content_uri: string;
  content_hash: string;
  mime_type: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type ArtifactLineageDTO = {
  artifact: WorkArtifactDTO;
  dependencies: Array<{
    id: string;
    source_asset_id: string;
    source_revision_id: string | null;
    target_asset_id: string;
    target_revision_id: string | null;
    dependency_type: string;
    reason: string;
    metadata: Record<string, unknown>;
    created_at: string;
  }>;
};

export type ValidationDecisionDTO = {
  id: string;
  company_id: string;
  program_id: string | null;
  assertion_id: string | null;
  asset_id: string | null;
  asset_version_id: string | null;
  decision: "ACCEPT" | "REJECT" | "EDIT" | "DEFER" | "NEEDS_RESEARCH" | string;
  category: string;
  rationale: string;
  proposed_change: Record<string, unknown>;
  created_at: string;
};

export type ValidationPacketDTO = {
  company_id: string;
  program_id: string;
  program_label: string;
  current_stage_id: string;
  assertions: AssertionRecordDTO[];
  artifacts: WorkArtifactDTO[];
  findings: Array<{
    id: string;
    evaluation_id: string;
    severity: string;
    issue_type: string;
    message: string;
    suggested_fix: string;
    blocking: boolean;
    evidence_refs: unknown[];
  }>;
  decision_options: string[];
};

export type EvaluationRunDTO = {
  id: string;
  company_id: string;
  program_id: string | null;
  asset_id: string | null;
  asset_version_id: string | null;
  profile_id: string;
  status: "PASS" | "WARN" | "BLOCK" | "RUNNING" | "FAILED" | string;
  score: number | null;
  grade: string;
  input_refs: unknown[];
  result: Record<string, unknown>;
  findings: Array<{
    id: string;
    severity: string;
    issue_type: string;
    message: string;
    evidence_refs: unknown[];
    suggested_fix: string;
    blocking: boolean;
    created_at: string;
  }>;
  scorecard: {
    dimensions: Record<string, unknown>;
    composite_score: number;
    grade: string;
  } | null;
  created_at: string;
  evaluated_at: string | null;
};

export type PeriodicReviewDTO = {
  id: string;
  company_id: string;
  program_id: string | null;
  pack_id: string;
  template_id: string;
  display_name: string;
  cadence: string;
  timezone: string;
  evaluation_profile_id: string;
  report_template_id: string;
  history_projection_type: string;
  enabled: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type MetricSnapshotDTO = {
  id: string;
  company_id: string;
  program_id: string | null;
  review_definition_id: string | null;
  period_start: string;
  period_end: string;
  metric_values: Record<string, unknown>;
  metric_sources: Record<string, unknown>;
  source_type: string;
  notes: string;
  created_at: string;
};

export type ReportRunDTO = {
  id: string;
  company_id: string;
  program_id: string | null;
  review_definition_id: string | null;
  metric_snapshot_id: string | null;
  report_template_id: string;
  period_start: string;
  period_end: string;
  evaluation_run_ids: string[];
  artifact: WorkArtifactDTO | null;
  artifact_revision_id: string | null;
  generated_sections: Record<string, unknown>;
  source_refs: unknown[];
  created_at: string;
};

export type PolicyEvaluationDTO = {
  id: string;
  company_id: string;
  policy_pack_id: string | null;
  action_type: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;
  status: string;
  input: Record<string, unknown>;
  trace: Record<string, unknown>;
  decision_record_id: string | null;
  approval_task_id: string | null;
  created_at: string;
};

export type ReworkPlanDTO = {
  id: string;
  company_id: string;
  program_id: string | null;
  status: string;
  trigger_summary: string;
  impact: Record<string, unknown>;
  required_approvals: unknown[];
  estimated_effort: Record<string, unknown>;
  items: unknown[];
  created_at: string;
  updated_at: string;
  executed_at: string | null;
};

export type ToolExecutionReceiptDTO = {
  tool_execution_id: string;
  company_id: string;
  operation_id: string;
  tool_id: string;
  label: string;
  dry_run: boolean;
  side_effects: string;
  status: string;
  policy_evaluation: PolicyEvaluationDTO | null;
};

export type StageOutputGenerationDTO = {
  workflow_id: string;
  program_id: string;
  stage_id: string;
  status: string;
  created_artifacts: WorkArtifactDTO[];
  evaluations: EvaluationRunDTO[];
  created_signals: Array<{
    id: string;
    title: string;
    summary: string;
    status: string;
    metadata: Record<string, unknown>;
  }>;
  blockers: Array<Record<string, unknown>>;
  skipped: Array<Record<string, unknown>>;
  state_projection: StateProjectionDTO;
};

export type StateProjectionDTO = {
  id: string;
  company_id: string;
  program_id: string | null;
  projection_type: string;
  display_label: string;
  source_refs: unknown[];
  json_state: Record<string, unknown>;
  markdown_summary: string;
  generated_by: string;
  created_at: string;
  updated_at: string;
};

export type CompanyOperatingModelDTO = {
  company_id: string;
  installed_packs: OperatingModelInstallation[];
  programs: CompanyProgramDTO[];
  evaluation_profiles?: Array<{
    profile_id: string;
    display_name: string;
    mode: string;
  }>;
  policy_packs?: Array<{
    policy_pack_id: string;
    display_name: string;
  }>;
  signal_taxonomies?: Array<{
    taxonomy_id: string;
    display_name: string;
  }>;
  periodic_reviews?: Array<{
    id: string;
    template_id: string;
    display_name: string;
    cadence: string;
    evaluation_profile_id: string;
    report_template_id: string;
    history_projection_type: string;
    enabled: boolean;
  }>;
};

export type CompanyBlueprintInput = {
  company_name: string;
  objective: string;
  blueprint_id?: string;
  services?: string[];
  regions?: string[];
  autonomy_mode: "manual" | "assisted" | "autonomous" | string;
  ai_access_mode: "managed" | "byok" | string;
  intelligence_provider?: string;
};

export type CompanyFromBlueprintInput = CompanyBlueprintInput & {
  launch_first_operation?: boolean;
  operation_brief?: string;
  credential_id?: string | null;
};

export type CompanyFromBlueprintResult = {
  company_id: string;
  graph_version_id: string;
  graph_json: GraphJson;
  template_ids: string[];
  department_groups: Array<Record<string, unknown>>;
  first_operation_id: string | null;
  idempotent_replay: boolean;
};

export const companyBlueprintsApi = {
  compile: async (input: CompanyBlueprintInput): Promise<Record<string, unknown>> => {
    const response = await api.post<ApiSuccessResponse<Record<string, unknown>>>(
      API_PATHS.companyBlueprints.compile,
      input,
    );
    return response.data.data;
  },
  createCompany: async (
    input: CompanyFromBlueprintInput,
    options?: IdempotencyOptions,
  ): Promise<CompanyFromBlueprintResult> => {
    const response = await api.post<ApiSuccessResponse<CompanyFromBlueprintResult>>(
      API_PATHS.companyBlueprints.createCompany,
      input,
      idempotencyConfig(options),
    );
    return response.data.data;
  },
};

export const operatingModelsApi = {
  listPacks: async (): Promise<OperatingModelPack[]> => {
    const response = await api.get<ApiSuccessResponse<{ packs: OperatingModelPack[] }>>(
      API_PATHS.operatingModels.packs,
    );
    return response.data.data.packs;
  },
  getPack: async (packId: string): Promise<OperatingModelPack> => {
    const response = await api.get<ApiSuccessResponse<{ pack: OperatingModelPack }>>(
      API_PATHS.operatingModels.pack(packId),
    );
    return response.data.data.pack;
  },
  compilePack: async (packId: string, input: Record<string, unknown>): Promise<Record<string, unknown>> => {
    const response = await api.post<ApiSuccessResponse<Record<string, unknown>>>(
      API_PATHS.operatingModels.compilePack(packId),
      input,
    );
    return response.data.data;
  },
  getCompanyOperatingModel: async (companyId: string): Promise<CompanyOperatingModelDTO> => {
    const response = await api.get<ApiSuccessResponse<{ operating_model: CompanyOperatingModelDTO }>>(
      API_PATHS.operatingModels.companyOperatingModel(companyId),
    );
    return response.data.data.operating_model;
  },
  installPack: async (
    companyId: string,
    packId: string,
    input: { config?: Record<string, unknown> },
    options?: IdempotencyOptions,
  ): Promise<OperatingModelInstallation> => {
    const response = await api.post<ApiSuccessResponse<{ installation: OperatingModelInstallation }>>(
      API_PATHS.operatingModels.installPack(companyId, packId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.installation;
  },
  listPrograms: async (companyId: string): Promise<CompanyProgramDTO[]> => {
    const response = await api.get<ApiSuccessResponse<{ programs: CompanyProgramDTO[] }>>(
      API_PATHS.operatingModels.programs(companyId),
    );
    return response.data.data.programs;
  },
  getProgram: async (programId: string): Promise<CompanyProgramDTO> => {
    const response = await api.get<ApiSuccessResponse<{ program: CompanyProgramDTO }>>(
      API_PATHS.operatingModels.program(programId),
    );
    return response.data.data.program;
  },
  createProgram: async (
    companyId: string,
    input: Record<string, unknown>,
    options?: IdempotencyOptions,
  ): Promise<CompanyProgramDTO> => {
    const response = await api.post<ApiSuccessResponse<{ program: CompanyProgramDTO }>>(
      API_PATHS.operatingModels.programs(companyId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.program;
  },
  advanceStage: async (
    programId: string,
    stageId: string,
    input: Record<string, unknown>,
    options?: IdempotencyOptions,
  ): Promise<CompanyProgramDTO> => {
    const response = await api.post<ApiSuccessResponse<{ program: CompanyProgramDTO }>>(
      API_PATHS.operatingModels.advanceStage(programId, stageId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.program;
  },
  launchStageOperation: async (
    programId: string,
    stageId: string,
    input: Record<string, unknown>,
    options?: IdempotencyOptions,
  ): Promise<ProgramOperationDTO> => {
    const response = await api.post<ApiSuccessResponse<{ operation: ProgramOperationDTO }>>(
      API_PATHS.operatingModels.launchStageOperation(programId, stageId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.operation;
  },
  generateStageOutputs: async (
    programId: string,
    stageId: string,
    input: Record<string, unknown>,
    options?: IdempotencyOptions,
  ): Promise<StageOutputGenerationDTO> => {
    const response = await api.post<ApiSuccessResponse<{ stage_output: StageOutputGenerationDTO }>>(
      API_PATHS.operatingModels.generateStageOutputs(programId, stageId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.stage_output;
  },
  getValidationPacket: async (programId: string): Promise<ValidationPacketDTO> => {
    const response = await api.get<ApiSuccessResponse<{ validation_packet: ValidationPacketDTO }>>(
      API_PATHS.operatingModels.validationPacket(programId),
    );
    return response.data.data.validation_packet;
  },
  listAssertions: async (params: Record<string, unknown>): Promise<AssertionRecordDTO[]> => {
    const response = await api.get<ApiSuccessResponse<{ assertions: AssertionRecordDTO[] }>>(
      API_PATHS.operatingModels.assertions,
      { params },
    );
    return response.data.data.assertions;
  },
  createAssertion: async (
    input: Record<string, unknown>,
    options?: IdempotencyOptions,
  ): Promise<AssertionRecordDTO> => {
    const response = await api.post<ApiSuccessResponse<{ assertion: AssertionRecordDTO }>>(
      API_PATHS.operatingModels.assertions,
      input,
      idempotencyConfig(options),
    );
    return response.data.data.assertion;
  },
  createValidationDecision: async (
    input: Record<string, unknown>,
    options?: IdempotencyOptions,
  ): Promise<ValidationDecisionDTO> => {
    const response = await api.post<ApiSuccessResponse<{ validation_decision: ValidationDecisionDTO }>>(
      API_PATHS.operatingModels.validationDecisions,
      input,
      idempotencyConfig(options),
    );
    return response.data.data.validation_decision;
  },
  listArtifacts: async (params: Record<string, unknown>): Promise<WorkArtifactDTO[]> => {
    const response = await api.get<ApiSuccessResponse<{ artifacts: WorkArtifactDTO[] }>>(
      API_PATHS.operatingModels.workArtifacts,
      { params },
    );
    return response.data.data.artifacts;
  },
  createArtifact: async (
    input: Record<string, unknown>,
    options?: IdempotencyOptions,
  ): Promise<{ artifact: WorkArtifactDTO; revision: ArtifactRevisionDTO }> => {
    const response = await api.post<ApiSuccessResponse<{ artifact: WorkArtifactDTO; revision: ArtifactRevisionDTO }>>(
      API_PATHS.operatingModels.workArtifacts,
      input,
      idempotencyConfig(options),
    );
    return response.data.data;
  },
  getArtifact: async (artifactId: string): Promise<WorkArtifactDTO> => {
    const response = await api.get<ApiSuccessResponse<{ artifact: WorkArtifactDTO }>>(
      API_PATHS.operatingModels.workArtifact(artifactId),
    );
    return response.data.data.artifact;
  },
  createArtifactRevision: async (
    artifactId: string,
    input: Record<string, unknown>,
    options?: IdempotencyOptions,
  ): Promise<ArtifactRevisionDTO> => {
    const response = await api.post<ApiSuccessResponse<{ revision: ArtifactRevisionDTO }>>(
      API_PATHS.operatingModels.artifactRevisions(artifactId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data.revision;
  },
  getArtifactLineage: async (artifactId: string): Promise<ArtifactLineageDTO> => {
    const response = await api.get<ApiSuccessResponse<{ lineage: ArtifactLineageDTO }>>(
      API_PATHS.operatingModels.artifactLineage(artifactId),
    );
    return response.data.data.lineage;
  },
  setCanonicalRevision: async (
    artifactId: string,
    revisionId: string,
    options?: IdempotencyOptions,
  ): Promise<WorkArtifactDTO> => {
    const response = await api.patch<ApiSuccessResponse<{ artifact: WorkArtifactDTO }>>(
      API_PATHS.operatingModels.canonicalRevision(artifactId),
      { revision_id: revisionId },
      idempotencyConfig(options),
    );
    return response.data.data.artifact;
  },
  runEvaluation: async (input: Record<string, unknown>, options?: IdempotencyOptions): Promise<EvaluationRunDTO> => {
    const response = await api.post<ApiSuccessResponse<{ evaluation: EvaluationRunDTO }>>(
      API_PATHS.operatingModels.runEvaluation,
      input,
      idempotencyConfig(options),
    );
    return response.data.data.evaluation;
  },
  listPeriodicReviews: async (params: Record<string, unknown>): Promise<PeriodicReviewDTO[]> => {
    const response = await api.get<ApiSuccessResponse<{ periodic_reviews: PeriodicReviewDTO[] }>>(
      API_PATHS.operatingModels.periodicReviews,
      { params },
    );
    return response.data.data.periodic_reviews;
  },
  createMetricSnapshot: async (
    input: Record<string, unknown>,
    options?: IdempotencyOptions,
  ): Promise<MetricSnapshotDTO> => {
    const response = await api.post<ApiSuccessResponse<{ metric_snapshot: MetricSnapshotDTO }>>(
      API_PATHS.operatingModels.metricSnapshots,
      input,
      idempotencyConfig(options),
    );
    return response.data.data.metric_snapshot;
  },
  listMetricSnapshots: async (params: Record<string, unknown>): Promise<MetricSnapshotDTO[]> => {
    const response = await api.get<ApiSuccessResponse<{ metric_snapshots: MetricSnapshotDTO[] }>>(
      API_PATHS.operatingModels.metricSnapshots,
      { params },
    );
    return response.data.data.metric_snapshots;
  },
  runPeriodicReview: async (
    reviewId: string,
    input: Record<string, unknown>,
    options?: IdempotencyOptions,
  ): Promise<{ evaluation: EvaluationRunDTO; report_run: ReportRunDTO }> => {
    const response = await api.post<ApiSuccessResponse<{ evaluation: EvaluationRunDTO; report_run: ReportRunDTO }>>(
      API_PATHS.operatingModels.runPeriodicReview(reviewId),
      input,
      idempotencyConfig(options),
    );
    return response.data.data;
  },
  listReportRuns: async (params: Record<string, unknown>): Promise<ReportRunDTO[]> => {
    const response = await api.get<ApiSuccessResponse<{ report_runs: ReportRunDTO[] }>>(
      API_PATHS.operatingModels.reportRuns,
      { params },
    );
    return response.data.data.report_runs;
  },
  evaluatePolicy: async (
    input: Record<string, unknown>,
    options?: IdempotencyOptions,
  ): Promise<PolicyEvaluationDTO> => {
    const response = await api.post<ApiSuccessResponse<{ policy_evaluation: PolicyEvaluationDTO }>>(
      API_PATHS.operatingModels.policyEvaluations,
      input,
      idempotencyConfig(options),
    );
    return response.data.data.policy_evaluation;
  },
  executeTool: async (
    input: Record<string, unknown>,
    options?: IdempotencyOptions,
  ): Promise<ToolExecutionReceiptDTO> => {
    const response = await api.post<ApiSuccessResponse<{ tool_execution: ToolExecutionReceiptDTO }>>(
      API_PATHS.operatingModels.toolExecutions,
      input,
      idempotencyConfig(options),
    );
    return response.data.data.tool_execution;
  },
  createReworkPlan: async (input: Record<string, unknown>, options?: IdempotencyOptions): Promise<ReworkPlanDTO> => {
    const response = await api.post<ApiSuccessResponse<{ rework_plan: ReworkPlanDTO }>>(
      API_PATHS.operatingModels.reworkPlans,
      input,
      idempotencyConfig(options),
    );
    return response.data.data.rework_plan;
  },
  executeReworkPlan: async (planId: string, options?: IdempotencyOptions): Promise<ReworkPlanDTO> => {
    const response = await api.post<ApiSuccessResponse<{ rework_plan: ReworkPlanDTO }>>(
      API_PATHS.operatingModels.executeReworkPlan(planId),
      {},
      idempotencyConfig(options),
    );
    return response.data.data.rework_plan;
  },
  listStateProjections: async (params: Record<string, unknown>): Promise<StateProjectionDTO[]> => {
    const response = await api.get<ApiSuccessResponse<{ state_projections: StateProjectionDTO[] }>>(
      API_PATHS.operatingModels.stateProjections,
      { params },
    );
    return response.data.data.state_projections;
  },
};

export const analyticsApi = {
  getMemoryUsage: async (period: string): Promise<MemoryAnalyticsUsage> => {
    const response = await api.get<ApiSuccessResponse<MemoryAnalyticsUsage>>(API_PATHS.analytics.memoryUsage, {
      params: { period },
    });
    return response.data.data;
  },
  getMemoryCosts: async (period: string): Promise<MemoryAnalyticsCosts> => {
    const response = await api.get<ApiSuccessResponse<MemoryAnalyticsCosts>>(API_PATHS.analytics.memoryCosts, {
      params: { period },
    });
    return response.data.data;
  },
  getMemoryPerformance: async (period: string): Promise<MemoryAnalyticsPerformance> => {
    const response = await api.get<ApiSuccessResponse<MemoryAnalyticsPerformance>>(
      API_PATHS.analytics.memoryPerformance,
      { params: { period } },
    );
    return response.data.data;
  },
  getLLMUsage: async (period: string): Promise<LLMAnalyticsUsage> => {
    const response = await api.get<ApiSuccessResponse<LLMAnalyticsUsage>>(API_PATHS.analytics.llmUsage, {
      params: { period },
    });
    return response.data.data;
  },
  getLLMCosts: async (period: string): Promise<LLMAnalyticsCosts> => {
    const response = await api.get<ApiSuccessResponse<LLMAnalyticsCosts>>(API_PATHS.analytics.llmCosts, {
      params: { period },
    });
    return response.data.data;
  },
  getLLMBudget: async (): Promise<LLMBudgetStatus> => {
    const response = await api.get<ApiSuccessResponse<LLMBudgetStatus>>(API_PATHS.analytics.llmBudget);
    return response.data.data;
  },
  setLLMBudget: async (input: {
    monthly_limit_usd: number;
    warning_threshold_pct: number;
  }): Promise<LLMBudgetStatus> => {
    const response = await api.put<ApiSuccessResponse<LLMBudgetStatus>>(API_PATHS.analytics.llmBudget, input);
    return response.data.data;
  },
  getLLMQuota: async (): Promise<LLMQuotaStatus> => {
    const response = await api.get<ApiSuccessResponse<LLMQuotaStatus>>(API_PATHS.analytics.llmQuota);
    return response.data.data;
  },
  exportLLMReport: async (input: {
    dataset: "usage" | "costs" | "budget" | "quota";
    format: "json" | "csv";
    period?: string;
  }): Promise<Blob> => {
    const { format, ...rest } = input;
    const response = await api.get(API_PATHS.analytics.llmExport, {
      params: { ...rest, export_format: format },
      responseType: "blob",
    });
    return response.data as Blob;
  },
  exportMemoryReport: async (input: { dataset?: "report"; format: "json" | "csv"; period?: string }): Promise<Blob> => {
    const { format, ...rest } = input;
    const response = await api.get(API_PATHS.analytics.memoryExport, {
      params: { dataset: "report", ...rest, export_format: format },
      responseType: "blob",
    });
    return response.data as Blob;
  },
};
