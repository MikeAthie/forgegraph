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

export type ApiMeta = {
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

export type ApiErrorDetail = {
  field?: string;
  issue?: string;
  [key: string]: unknown;
};

export type ApiErrorResponse = {
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
    me: "/api/orgs/me",
    members: "/api/orgs/members",
    memberDetail: (userId: string) => `/api/orgs/members/${userId}`,
  },
  health: {
    memory: "/api/health/memory",
  },
  metrics: {
    summary: "/api/metrics/summary",
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

export const setAccessToken = (token: string | null): void => {
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
    oldest_pending_age_seconds: number | null;
    by_tenant: Array<{
      tenant_id: string;
      pending: number;
      processing: number;
      total: number;
    }>;
  };
  slo: {
    run_success_rate_target: number;
    run_p95_latency_ms_target: number;
    queue_max_depth_target: number;
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
  };
  generated_at: string;
};

export interface GraphDetail {
  id: string;
  owner_id: string;
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

export type PromptCategory = "research" | "summarization" | "email" | "extraction" | "reasoning" | "other";

export type PromptVisibility = "private" | "public";

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

export type TemplateCloneInput = {
  name?: string;
  description?: string;
  provider?: string;
  model?: string;
  credential_id?: string;
};

export type TemplateCloneResult = {
  graph_id: string;
  graph_version_id: string;
  graph_name: string;
  template_id: string;
};

export type MarketplaceRelease = {
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

export type MarketplaceRuntimeManifestPackage = {
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

export type MarketplaceRuntimeManifestTool = {
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

export interface IdentityStatus {
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

export const templatesApi = {
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

export type RunStatus = "pending" | "running" | "paused" | "succeeded" | "failed" | "canceled" | string;

export type NodeRunStatus = "pending" | "running" | "succeeded" | "failed" | "skipped" | string;

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
}

export interface MemoryObservationPreview {
  id?: string;
  type?: string;
  title?: string;
  scope?: string;
  topic_key?: string;
  tool_name?: string;
  content_preview?: string;
}

export interface NodeMemoryActivity {
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

export interface RunMemoryOperation extends NodeMemoryActivity {
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
  // Human Gate pause fields
  paused_node_id?: string | null;
  pause_payload?: {
    prompt_message?: string;
    required_fields?: string[];
    node_id?: string;
    node_name?: string;
  } | null;
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

export interface TaskRecord {
  id: string;
  organization_id: string;
  execution_id: string;
  agent_id: string | null;
  title: string;
  status: "pending" | "running" | "waiting" | "succeeded" | "failed" | "canceled" | string;
  priority: "low" | "normal" | "high" | "urgent" | string;
  summary: string;
  source_node_id: string;
  current_step_id: string | null;
  current_decision_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DecisionRecord {
  id: string;
  organization_id: string;
  execution_id: string | null;
  task_id: string | null;
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

export interface CostAggregate {
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

export interface AccountingOverview {
  organization_id: string;
  total_cost_usd: number;
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
  memory: {
    active_observation_count: number;
    recent_topics: string[];
  };
  policy: {
    configured: boolean;
    allowed_providers: string[];
    allowed_models: string[];
    http_default_deny: boolean;
  };
  accounting: AccountingOverview;
  generated_at: string;
}

export interface ResumeRunInput {
  node_id: string;
  input_json: {
    approved: boolean;
    fields?: Record<string, string>;
    feedback?: string;
  };
}

export interface InvokeRunInput {
  thread_id: string;
  input_json?: Record<string, unknown>;
}

export interface ReplayRunInput {
  node_id?: string;
}

export const runsApi = {
  list: async (): Promise<RunListItem[]> => {
    const response = await api.get<ApiSuccessResponse<RunListItem[]>>(API_PATHS.runs.list);
    return response.data.data;
  },

  get: async (runId: string): Promise<RunDetail> => {
    const response = await api.get<ApiSuccessResponse<RunDetail>>(API_PATHS.runs.detail(runId));
    return response.data.data;
  },

  start: async (input: { graph_version_id: string; input_json?: Record<string, unknown> }): Promise<RunDetail> => {
    const response = await api.post<ApiSuccessResponse<RunDetail>>(API_PATHS.runs.start, input);
    return response.data.data;
  },

  invoke: async (input: InvokeRunInput): Promise<RunDetail> => {
    const response = await api.post<ApiSuccessResponse<RunDetail>>(API_PATHS.runs.invoke, input);
    return response.data.data;
  },

  cancel: async (runId: string): Promise<RunDetail> => {
    const response = await api.post<ApiSuccessResponse<RunDetail>>(API_PATHS.runs.cancel(runId), {});
    return response.data.data;
  },

  resume: async (runId: string, input: ResumeRunInput): Promise<{ resumed: boolean }> => {
    const response = await api.post<ApiSuccessResponse<{ resumed: boolean }>>(API_PATHS.runs.resume(runId), input);
    return response.data.data;
  },

  replay: async (runId: string, input?: ReplayRunInput): Promise<RunDetail> => {
    const response = await api.post<ApiSuccessResponse<RunDetail>>(API_PATHS.runs.replay(runId), input ?? {});
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

export default api;
