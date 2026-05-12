import { memoryApi, type MemoryObservation } from "@/lib/api";

export type MemoryScopeVM = "all" | "company" | "operation" | "session";

export type MemoryObservationVM = {
  id: string;
  title: string;
  content: string;
  scope: string;
  type: string;
  topic: string;
  toolName: string;
  sourceEventId: string;
  sourceEventType: string;
  factHash: string;
  provenance: Record<string, unknown>;
  costMetadata: Record<string, unknown>;
  retentionPolicy: Record<string, unknown>;
  companyId: string | null;
  operationId: string | null;
  sessionId: string | null;
  departmentId: string | null;
  chunkId: string | null;
  revisionCount: number;
  duplicateCount: number;
  lastSeenAt: string;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
  isDeleted: boolean;
};

function toBackendScope(scope?: string): string | undefined {
  if (scope === "company") return "graph";
  if (scope === "operation") return "run";
  if (scope === "session") return "session";
  return undefined;
}

function toProductScope(scope: string): string {
  if (scope === "graph") return "company";
  if (scope === "run") return "operation";
  return scope;
}

function toMemoryObservationVM(observation: MemoryObservation): MemoryObservationVM {
  return {
    id: observation.id,
    title: observation.title,
    content: observation.content,
    scope: toProductScope(observation.scope),
    type: observation.type,
    topic: observation.topic_key,
    toolName: observation.tool_name,
    sourceEventId: observation.source_event_id,
    sourceEventType: observation.source_event_type,
    factHash: observation.fact_hash,
    provenance: observation.provenance,
    costMetadata: observation.cost_metadata,
    retentionPolicy: observation.retention_policy,
    companyId: observation.graph_id,
    operationId: observation.run_id,
    sessionId: observation.session_id,
    departmentId: observation.agent_id,
    chunkId: observation.memory_chunk_id,
    revisionCount: observation.revision_count,
    duplicateCount: observation.duplicate_count,
    lastSeenAt: observation.last_seen_at,
    createdAt: observation.created_at,
    updatedAt: observation.updated_at,
    deletedAt: observation.deleted_at,
    isDeleted: observation.is_deleted,
  };
}

export const memoryRepository = {
  search: async (input: {
    query?: string;
    scope?: MemoryScopeVM;
    type?: string;
    limit?: number;
  }): Promise<MemoryObservationVM[]> => {
    const observations = await memoryApi.search({
      query: input.query,
      scope: toBackendScope(input.scope),
      type: input.type,
      limit: input.limit,
    });
    return observations.map(toMemoryObservationVM);
  },

  timeline: async (input: { scope?: MemoryScopeVM; limit?: number }): Promise<MemoryObservationVM[]> => {
    const observations = await memoryApi.timeline({
      scope: toBackendScope(input.scope),
      limit: input.limit,
    });
    return observations.map(toMemoryObservationVM);
  },

  get: async (observationId: string): Promise<MemoryObservationVM> => {
    const observation = await memoryApi.get(observationId);
    return toMemoryObservationVM(observation);
  },
};

type MemoryRepository = typeof memoryRepository;
