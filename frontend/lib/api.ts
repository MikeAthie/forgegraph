import axios, { type AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from "axios";
import type { GraphJson, GraphVersion, CreateGraphVersionInput } from "./graph-types";

export interface User {
  id: string;
  email: string;
  created_at: string;
  is_active: boolean;
}

export interface AccessTokenResponse {
  access: string;
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

export const getApiErrorMessage = (err: unknown, fallback: string) => {
  const data = (err as AxiosError)?.response?.data as any;
  if (!data) {
    return fallback;
  }

  if (typeof data === "string") {
    return data;
  }

  if (data.error) {
    if (typeof data.error === "string") {
      return data.error;
    }
    return data.error.message || data.error.detail || fallback;
  }

  return data.detail || data.message || fallback;
};

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);
const API_PATHS = {
  auth: {
    login: "/api/auth/login",
    register: "/api/auth/register",
    logout: "/api/auth/logout",
    refresh: "/api/auth/refresh",
    me: "/api/auth/me",
  },
  graphs: {
    listCreate: "/api/graphs/",
    detail: (graphId: string) => `/api/graphs/${graphId}`,
    versions: (graphId: string) => `/api/graphs/${graphId}/versions`,
    latestVersion: (graphId: string) => `/api/graphs/${graphId}/versions/latest`,
    versionDetail: (graphId: string, versionId: string) =>
      `/api/graphs/${graphId}/versions/${versionId}`,
  },
  prompts: {
    listCreate: "/api/prompts/",
    detail: (promptId: string) => `/api/prompts/${promptId}`,
    clone: (promptId: string) => `/api/prompts/${promptId}/clone`,
    publish: (promptId: string) => `/api/prompts/${promptId}/publish`,
  },
  runs: {
    list: "/api/runs/",
    detail: (runId: string) => `/api/runs/${runId}`,
    start: "/api/runs/start",
    cancel: (runId: string) => `/api/runs/${runId}/cancel`,
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

const authClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

export const getAccessToken = (): string | null => {
  return accessToken;
};

export const clearTokens = (): void => {
  accessToken = null;
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
        accessToken = access;
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
    accessToken = response.data.access;
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
      accessToken = response.data.access;
      processQueue(null, accessToken);
      return response.data;
    } catch (refreshError: unknown) {
      processQueue(refreshError, null);
      clearTokens();
      throw refreshError;
    } finally {
      isRefreshing = false;
    }
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

export interface GraphDetail {
  id: string;
  owner_id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  versions: GraphVersionSummary[];
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
    const response = await api.patch<ApiSuccessResponse<GraphListItem>>(
      API_PATHS.graphs.detail(graphId),
      input,
    );
    return response.data.data;
  },

  delete: async (graphId: string): Promise<void> => {
    await api.delete(API_PATHS.graphs.detail(graphId));
  },

  listVersions: async (graphId: string): Promise<GraphVersionSummary[]> => {
    const response = await api.get<ApiSuccessResponse<GraphVersionSummary[]>>(
      API_PATHS.graphs.versions(graphId),
    );
    return response.data.data;
  },

  getLatestVersion: async (graphId: string): Promise<GraphVersion | null> => {
    try {
      const response = await api.get<ApiSuccessResponse<GraphVersion>>(
        API_PATHS.graphs.latestVersion(graphId),
      );
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
    const response = await api.post<ApiSuccessResponse<GraphVersion>>(
      API_PATHS.graphs.versions(graphId),
      input,
    );
    return response.data.data;
  },
};

export type PromptCategory =
  | "research"
  | "summarization"
  | "email"
  | "extraction"
  | "reasoning"
  | "other";

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
    const response = await api.post<ApiSuccessResponse<PromptDetail>>(
      API_PATHS.prompts.publish(promptId),
      input ?? {},
    );
    return response.data.data;
  },
};

export type RunStatus =
  | "pending"
  | "running"
  | "paused"
  | "succeeded"
  | "failed"
  | "canceled"
  | string;

export type NodeRunStatus = "pending" | "running" | "succeeded" | "failed" | "skipped" | string;

export interface RunListItem {
  id: string;
  graph_id: string;
  graph_name: string;
  graph_version_id: string;
  graph_version: number;
  status: RunStatus;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
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
}

export interface RunDetail {
  id: string;
  owner_id: string;
  graph_id: string;
  graph_name: string;
  graph_version_id: string;
  graph_version: number;
  status: RunStatus;
  started_at: string | null;
  ended_at: string | null;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown> | null;
  error_message: string;
  duration_ms: number | null;
  node_runs: NodeRunItem[];
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

  cancel: async (runId: string): Promise<RunDetail> => {
    const response = await api.post<ApiSuccessResponse<RunDetail>>(API_PATHS.runs.cancel(runId), {});
    return response.data.data;
  },
};

export default api;
