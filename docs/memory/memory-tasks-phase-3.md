# Phase 3: Semantic Long-Term Memory

## Objective
Add vector-based long-term memory with pgvector, embedding pipeline, semantic search, and engine integration.

## Prerequisites
- Phase 2 complete (summarization and memory config)
- PostgreSQL available in docker-compose
- Embedding provider credentials configured

---

## Task List

### P3-T01: Add pgvector Extension to PostgreSQL
**Files:**
- `docker-compose.yml`
- `backend/infrastructure/orm/migrations/0013_pgvector_setup.py`

- [ ] Update postgres image to pgvector build.
- [ ] Add migration to enable vector extension.
- [ ] Verify extension available in DB.

```python
operations = [
    migrations.RunSQL(
        "CREATE EXTENSION IF NOT EXISTS vector;",
        reverse_sql="DROP EXTENSION IF EXISTS vector;"
    ),
]
```

**Acceptance Criteria:**
- [ ] pgvector extension installed
- [ ] Migration applies cleanly
- [ ] Existing data preserved

---

### P3-T02: Create Memory Chunk Django Model
**Files:**
- `backend/domain/entities/memory_chunk.py`
- `backend/infrastructure/orm/migrations/0014_memory_chunks.py`
- `backend/infrastructure/orm/models.py`

- [ ] Add MemoryChunk model with VectorField.
- [ ] Include tenant, agent, run, session scopes.
- [ ] Add IVFFlat vector index.
- [ ] Add basic indexes for tenant and agent lookups.

```python
class MemoryChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant_id = models.UUIDField(db_index=True)
    agent_id = models.UUIDField(null=True, db_index=True)
    run_id = models.UUIDField(null=True, db_index=True)
    session_id = models.UUIDField(null=True, db_index=True)
    content = models.TextField()
    chunk_type = models.CharField(max_length=20)
    metadata = models.JSONField(default=dict)
    embedding = VectorField(dimensions=1536)
    embedding_model = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    source_timestamp = models.DateTimeField()
```

**Acceptance Criteria:**
- [ ] Model created with vector field
- [ ] Vector index created
- [ ] Test insert/query succeeds

---

### P3-T03: Implement Embedding Service
**Files:**
- `backend/application/services/embedding_service.py`
- `backend/adapters/embedding/openai_embedder.py`
- `backend/adapters/embedding/voyage_embedder.py`

- [ ] Define EmbeddingService interface.
- [ ] Implement OpenAI embedder (default) and optional Voyage embedder.
- [ ] Support batching and rate limiting.
- [ ] Cache embeddings for duplicate text.
- [ ] Add unit tests with mocked API.

```python
class EmbeddingService(ABC):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def dimension(self) -> int:
        raise NotImplementedError
```

**Acceptance Criteria:**
- [ ] Embeddings are correct dimension
- [ ] Batch size handles 100+ texts
- [ ] Rate limits respected
- [ ] Cache reduces duplicate calls
- [ ] Tests pass

---

### P3-T04: Create Chunking Strategy Service
**Files:**
- `backend/application/services/chunking_service.py`

- [ ] Define ChunkingStrategy interface.
- [ ] Implement TurnBased, TopicBased, and SlidingWindow strategies.
- [ ] Set default to TurnBased with overlap.
- [ ] Add unit tests for chunk boundaries.

```python
class ChunkingStrategy(ABC):
    def chunk(self, messages: list[Message]) -> list[Chunk]:
        raise NotImplementedError
```

**Acceptance Criteria:**
- [ ] Strategies handle empty and short inputs
- [ ] Overlap preserves context
- [ ] Configurable chunk sizes
- [ ] Unit tests cover all strategies

---

### P3-T05: Implement Async Embedding Pipeline
**Files:**
- `backend/application/services/embedding_pipeline.py`
- `backend/adapters/worker/embedding_worker.py`

- [ ] Build pipeline: chunk -> embed -> store.
- [ ] Integrate Celery task for async processing.
- [ ] Add retries with exponential backoff.
- [ ] Add bulk create to repository.
- [ ] Add integration test with sample messages.

**Acceptance Criteria:**
- [ ] Messages processed end-to-end
- [ ] Chunks stored with embeddings
- [ ] Celery task runs asynchronously
- [ ] Batch processing works for 100+ messages
- [ ] Retries handle transient failures

---

### P3-T06: Implement Vector Similarity Search
**Files:**
- `backend/application/services/vector_search_service.py`
- `backend/adapters/repository/memory_chunk_repository.py`

- [ ] Embed query text.
- [ ] Run similarity search with pgvector.
- [ ] Apply hybrid ranking (semantic + recency).
- [ ] Filter by threshold and top_k.
- [ ] Add unit and integration tests.

```sql
SELECT *, 1 - (embedding <=> %s) as similarity
FROM memory_chunks
WHERE tenant_id = %s AND agent_id = %s
ORDER BY embedding <=> %s
LIMIT %s;
```

**Acceptance Criteria:**
- [ ] Relevant chunks returned for queries
- [ ] Hybrid ranking boosts recent content
- [ ] Query latency <100ms for 10k chunks
- [ ] Threshold filtering works

---

### P3-T07: Create Memory Retrieval gRPC Endpoint
**Files:**
- `engine/proto/engine.proto`
- Regenerate `engine/proto/engine.pb.go`
- `backend/adapters/grpc/memory_service.py`

- [ ] Add RetrieveMemoryRequest/Response to proto.
- [ ] Implement Django gRPC service for retrieval.
- [ ] Generate Go client and wire into engine.
- [ ] Add timeout and fallback behavior.
- [ ] Add integration test for gRPC retrieval.

**Acceptance Criteria:**
- [ ] gRPC endpoint responds within 100ms
- [ ] Engine can query memory service
- [ ] Failures are handled gracefully

---

### P3-T08: Integrate Vector Memory into Prompt Executor
**Files:**
- `engine/adapter/executor/prompt_executor.go`

- [ ] Retrieve memories via gRPC when Tier3 enabled.
- [ ] Format memories block in prompt.
- [ ] Log retrieval failures without blocking execution.
- [ ] Add integration test verifying prompt includes memories.

**Acceptance Criteria:**
- [ ] Relevant memories included in prompt
- [ ] No hard failure when retrieval fails
- [ ] Latency overhead <100ms

---

### P3-T09: Add Vector Memory Configuration
**Files:**
- `backend/infrastructure/orm/models.py`
- `backend/infrastructure/orm/migrations/0015_vector_config.py`
- `frontend/components/graph-editor/dialogs/MemoryConfigDialog.tsx`

- [ ] Add vector config fields to MemoryConfiguration.
- [ ] Serialize new fields in API responses.
- [ ] Add UI controls for top_k, threshold, recency weight, model.
- [ ] Validate thresholds and ranges.

Model fields:
```python
vector_enabled = models.BooleanField(default=False)
vector_top_k = models.PositiveIntegerField(default=5)
vector_threshold = models.FloatField(default=0.7)
vector_recency_weight = models.FloatField(default=0.2)
embedding_model = models.CharField(max_length=50, default='text-embedding-ada-002')
```

**Acceptance Criteria:**
- [ ] Migration adds vector fields
- [ ] Frontend shows vector settings
- [ ] Validation enforces threshold 0.5-0.99
- [ ] Config passed to engine

---

### P3-T10: Implement Memory Garbage Collection
**Files:**
- `backend/application/services/memory_gc.py`
- `backend/adapters/worker/gc_worker.py`

- [ ] Remove chunks for deleted tenants/users.
- [ ] Clean old chunks based on retention policy.
- [ ] Reindex vector indices periodically.
- [ ] Schedule daily Celery beat task.
- [ ] Add metrics for storage and cleanup.

**Acceptance Criteria:**
- [ ] Deleted user chunks removed within 24 hours
- [ ] Old chunks cleaned by age policy
- [ ] Batch cleanup avoids spikes
- [ ] Metrics reflect cleanup activity

---

## Acceptance Criteria (Phase 3 Overall)

1. pgvector enabled and migrations applied
2. Memory chunks stored with embeddings
3. Embedding pipeline processes messages asynchronously
4. Vector search returns relevant chunks with hybrid ranking
5. Engine retrieves memories via gRPC and includes them in prompts
6. Vector configuration editable in UI
7. Garbage collection keeps storage bounded

## Status: NOT STARTED

## Dependencies

- Phase 2 complete

## Output

- [ ] pgvector-enabled Postgres setup
- [ ] MemoryChunk model and repository
- [ ] Embedding service and pipeline
- [ ] Vector search service
- [ ] gRPC retrieval endpoint
- [ ] Prompt executor integration
- [ ] Vector configuration UI
- [ ] Memory GC jobs and metrics
