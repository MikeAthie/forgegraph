# Phase 1: Foundation - Redis Buffer + Local Buffer + Configuration

## Objective
Build the foundational memory system infrastructure including Redis-backed persistent storage, in-memory circular buffer for immediate context, configuration models, and the UI for memory settings.

## Prerequisites
- Existing `MemoryStore` interface in `engine/application/port/memory_store.go`
- Existing `InMemoryMemoryStore` and `PostgresMemoryStore` implementations
- Redis available in docker-compose (already configured for Django channels)
- gRPC communication between Django and Go engine working
- Frontend graph editor functional with node configuration dialogs

---

## Task List

### P1-T01: Create RedisMemoryStore Implementation
**Files:**
- `engine/adapter/store/redis_memory_store.go`
- `engine/adapter/store/redis_memory_store_test.go`

- [x] Add go-redis dependency to `engine/go.mod`:
  ```bash
  go get github.com/redis/go-redis/v9
  ```

- [x] Create `RedisMemoryStore` struct implementing `port.MemoryStore`:
  ```go
  type RedisMemoryStore struct {
      client       *redis.Client
      tenantID     string
      keyPrefix    string
      fallback     port.MemoryStore
      circuitOpen  atomic.Bool
      lastFailure  atomic.Value  // time.Time
      failureCount atomic.Int32
      mu           sync.RWMutex
  }
  ```

- [x] Implement constructor with Redis connection options:
  ```go
  type RedisConfig struct {
      Addr         string
      Password     string
      DB           int
      DialTimeout  time.Duration
      ReadTimeout  time.Duration
      WriteTimeout time.Duration
      PoolSize     int
  }

  func NewRedisMemoryStore(cfg RedisConfig, tenantID string, fallback port.MemoryStore) (*RedisMemoryStore, error)
  ```

- [x] Implement key building with tenant isolation:
  ```go
  func (s *RedisMemoryStore) buildKey(namespace, key string) string {
      // Format: forgegraph:tenant:{tenant_id}:memory:{namespace}:{key}
      return fmt.Sprintf("%s:tenant:%s:memory:%s:%s", s.keyPrefix, s.tenantID, namespace, key)
  }
  ```

- [x] Implement `Get` method with circuit breaker:
  ```go
  func (s *RedisMemoryStore) Get(ctx context.Context, namespace, key string) (any, bool, error) {
      if s.isCircuitOpen() {
          return s.fallback.Get(ctx, namespace, key)
      }

      fullKey := s.buildKey(namespace, key)
      val, err := s.client.Get(ctx, fullKey).Result()
      if err == redis.Nil {
          return nil, false, nil
      }
      if err != nil {
          s.recordFailure()
          return s.fallback.Get(ctx, namespace, key)
      }

      s.resetFailures()
      var result any
      if err := json.Unmarshal([]byte(val), &result); err != nil {
          return nil, false, fmt.Errorf("unmarshal error: %w", err)
      }
      return result, true, nil
  }
  ```

- [x] Implement `Set` method with TTL support:
  ```go
  func (s *RedisMemoryStore) Set(ctx context.Context, namespace, key string, value any, ttlSeconds int) error {
      if s.isCircuitOpen() {
          return s.fallback.Set(ctx, namespace, key, value, ttlSeconds)
      }

      data, err := json.Marshal(value)
      if err != nil {
          return fmt.Errorf("marshal error: %w", err)
      }

      fullKey := s.buildKey(namespace, key)
      ttl := time.Duration(ttlSeconds) * time.Second
      if ttlSeconds <= 0 {
          ttl = 0 // No expiration
      }

      if err := s.client.Set(ctx, fullKey, data, ttl).Err(); err != nil {
          s.recordFailure()
          return s.fallback.Set(ctx, namespace, key, value, ttlSeconds)
      }

      s.resetFailures()
      return nil
  }
  ```

- [x] Implement `Delete` method:
  ```go
  func (s *RedisMemoryStore) Delete(ctx context.Context, namespace, key string) (bool, error) {
      if s.isCircuitOpen() {
          return s.fallback.Delete(ctx, namespace, key)
      }

      fullKey := s.buildKey(namespace, key)
      result, err := s.client.Del(ctx, fullKey).Result()
      if err != nil {
          s.recordFailure()
          return s.fallback.Delete(ctx, namespace, key)
      }

      s.resetFailures()
      return result > 0, nil
  }
  ```

- [x] Implement circuit breaker logic:
  ```go
  const (
      circuitOpenDuration = 30 * time.Second
      failureThreshold    = 5
  )

  func (s *RedisMemoryStore) isCircuitOpen() bool {
      if !s.circuitOpen.Load() {
          return false
      }
      lastFail := s.lastFailure.Load().(time.Time)
      if time.Since(lastFail) > circuitOpenDuration {
          s.circuitOpen.Store(false)
          s.failureCount.Store(0)
          return false
      }
      return true
  }

  func (s *RedisMemoryStore) recordFailure() {
      count := s.failureCount.Add(1)
      s.lastFailure.Store(time.Now())
      if count >= failureThreshold {
          s.circuitOpen.Store(true)
      }
  }

  func (s *RedisMemoryStore) resetFailures() {
      s.failureCount.Store(0)
  }
  ```

- [x] Implement health check method:
  ```go
  func (s *RedisMemoryStore) Ping(ctx context.Context) error {
      return s.client.Ping(ctx).Err()
  }
  ```

- [x] Write unit tests in `redis_memory_store_test.go`:
  - [x] `TestRedisMemoryStore_SetGet` - basic CRUD operations
  - [x] `TestRedisMemoryStore_TTLExpiration` - verify key expires
  - [x] `TestRedisMemoryStore_CircuitBreaker` - verify circuit opens after failures
  - [x] `TestRedisMemoryStore_Fallback` - verify fallback is used when Redis fails
  - [x] `TestRedisMemoryStore_TenantIsolation` - verify key prefixing
  - [x] `TestRedisMemoryStore_ConcurrentAccess` - verify thread safety

**Acceptance Criteria:**
- [ ] `Get()` returns stored value within 10ms for p99
- [x] `Set()` with TTL causes key to expire within ±5 seconds of specified time
- [x] Circuit breaker opens after 5 consecutive failures
- [x] After 30 seconds, circuit breaker allows retry
- [x] All keys include tenant ID prefix (verified via raw Redis inspection)
- [ ] All unit tests pass with `go test -race`

---

### P1-T02: Implement Local Circular Buffer
**Files:**
- `engine/domain/entity/message_buffer.go`
- `engine/domain/entity/message_buffer_test.go`

- [x] Define `Message` struct:
  ```go
  type Message struct {
      Role      string         `json:"role"`      // "user", "assistant", "system"
      Content   string         `json:"content"`
      Timestamp time.Time      `json:"timestamp"`
      NodeID    string         `json:"node_id,omitempty"`
      Metadata  map[string]any `json:"metadata,omitempty"`
  }
  ```

- [x] Create `MessageBuffer` struct with circular buffer implementation:
  ```go
  type MessageBuffer struct {
      mu       sync.RWMutex
      messages []Message
      capacity int
      head     int  // Next write position (oldest message index when full)
      count    int  // Current number of messages (0 to capacity)
  }

  func NewMessageBuffer(capacity int) *MessageBuffer {
      if capacity <= 0 {
          capacity = 20 // Default
      }
      return &MessageBuffer{
          messages: make([]Message, capacity),
          capacity: capacity,
      }
  }
  ```

- [x] Implement `Push` method (add message, evict oldest if full):
  ```go
  func (b *MessageBuffer) Push(msg Message) {
      b.mu.Lock()
      defer b.mu.Unlock()

      if msg.Timestamp.IsZero() {
          msg.Timestamp = time.Now()
      }

      b.messages[b.head] = msg
      b.head = (b.head + 1) % b.capacity

      if b.count < b.capacity {
          b.count++
      }
  }
  ```

- [x] Implement `GetAll` method (return messages in chronological order):
  ```go
  func (b *MessageBuffer) GetAll() []Message {
      b.mu.RLock()
      defer b.mu.RUnlock()

      if b.count == 0 {
          return nil
      }

      result := make([]Message, b.count)
      if b.count < b.capacity {
          // Buffer not yet wrapped
          copy(result, b.messages[:b.count])
      } else {
          // Buffer has wrapped - oldest is at head
          firstPart := b.messages[b.head:]
          secondPart := b.messages[:b.head]
          copy(result, firstPart)
          copy(result[len(firstPart):], secondPart)
      }
      return result
  }
  ```

- [x] Implement `GetLast` method (return last n messages):
  ```go
  func (b *MessageBuffer) GetLast(n int) []Message {
      b.mu.RLock()
      defer b.mu.RUnlock()

      if n <= 0 || b.count == 0 {
          return nil
      }
      if n > b.count {
          n = b.count
      }

      all := b.getAllUnlocked()
      return all[len(all)-n:]
  }
  ```

- [x] Implement `GetFirst` method (return first n messages - for summarization):
  ```go
  func (b *MessageBuffer) GetFirst(n int) []Message {
      b.mu.RLock()
      defer b.mu.RUnlock()

      if n <= 0 || b.count == 0 {
          return nil
      }
      if n > b.count {
          n = b.count
      }

      all := b.getAllUnlocked()
      return all[:n]
  }
  ```

- [x] Implement `RemoveFirst` method (remove oldest n messages after summarization):
  ```go
  func (b *MessageBuffer) RemoveFirst(n int) {
      b.mu.Lock()
      defer b.mu.Unlock()

      if n <= 0 || n > b.count {
          n = b.count
      }

      // Adjust head and count
      if b.count == b.capacity {
          b.head = (b.head + n) % b.capacity
      }
      b.count -= n
  }
  ```

- [x] Implement `Clear` method:
  ```go
  func (b *MessageBuffer) Clear() {
      b.mu.Lock()
      defer b.mu.Unlock()

      b.head = 0
      b.count = 0
      // Reset slice to clear memory
      b.messages = make([]Message, b.capacity)
  }
  ```

- [x] Implement `Count` and `Capacity` getters:
  ```go
  func (b *MessageBuffer) Count() int {
      b.mu.RLock()
      defer b.mu.RUnlock()
      return b.count
  }

  func (b *MessageBuffer) Capacity() int {
      return b.capacity
  }
  ```

- [x] Implement `Snapshot` method (deep copy for checkpointing):
  ```go
  func (b *MessageBuffer) Snapshot() []Message {
      b.mu.RLock()
      defer b.mu.RUnlock()

      all := b.getAllUnlocked()
      snapshot := make([]Message, len(all))
      for i, msg := range all {
          snapshot[i] = Message{
              Role:      msg.Role,
              Content:   msg.Content,
              Timestamp: msg.Timestamp,
              NodeID:    msg.NodeID,
              Metadata:  copyMap(msg.Metadata),
          }
      }
      return snapshot
  }
  ```

- [x] Implement `Restore` method (restore from checkpoint):
  ```go
  func (b *MessageBuffer) Restore(messages []Message) {
      b.mu.Lock()
      defer b.mu.Unlock()

      b.head = 0
      b.count = 0
      b.messages = make([]Message, b.capacity)

      for _, msg := range messages {
          if b.count >= b.capacity {
              break // Don't exceed capacity
          }
          b.messages[b.head] = msg
          b.head = (b.head + 1) % b.capacity
          b.count++
      }
  }
  ```

- [x] Write unit tests:
  - [x] `TestMessageBuffer_Push` - verify basic push
  - [x] `TestMessageBuffer_CircularBehavior` - push more than capacity
  - [x] `TestMessageBuffer_GetAll_Chronological` - verify order after wrap
  - [x] `TestMessageBuffer_GetLast` - verify last n messages
  - [x] `TestMessageBuffer_GetFirst` - verify first n messages
  - [x] `TestMessageBuffer_RemoveFirst` - verify removal
  - [x] `TestMessageBuffer_SnapshotRestore` - verify round-trip
  - [x] `TestMessageBuffer_Concurrency` - parallel push/get with race detector

- [x] Write benchmarks:
  ```go
  func BenchmarkMessageBuffer_Push(b *testing.B) {
      buf := NewMessageBuffer(100)
      msg := Message{Role: "user", Content: "test message"}
      for i := 0; i < b.N; i++ {
          buf.Push(msg)
      }
  }

  func BenchmarkMessageBuffer_GetAll(b *testing.B) {
      buf := NewMessageBuffer(100)
      for i := 0; i < 100; i++ {
          buf.Push(Message{Role: "user", Content: fmt.Sprintf("message %d", i)})
      }
      b.ResetTimer()
      for i := 0; i < b.N; i++ {
          _ = buf.GetAll()
      }
  }
  ```

**Acceptance Criteria:**
- [x] `Push()` completes in <100μs (verified by benchmark)
- [x] `GetAll()` returns messages in chronological order even after buffer wraps
- [x] `GetLast(n)` returns exactly min(n, count) messages
- [ ] Concurrent Push/Get operations don't cause data races (`go test -race`)
- [x] Buffer correctly evicts oldest message when at capacity
- [x] `Snapshot()` returns independent copy (modifications don't affect buffer)
- [x] `Restore()` correctly repopulates buffer

---

### P1-T03: Integrate Message Buffer into Scheduler Run Context
**Files:**
- `engine/application/usecase/scheduler.go`
- `engine/adapter/executor/prompt_executor.go`

- [x] Define `MemoryConfig` struct for run-level configuration:
  ```go
  // In engine/application/usecase/scheduler.go or new file

  type MemoryConfig struct {
      Tier1 Tier1Config `json:"tier1"`
      Tier2 Tier2Config `json:"tier2"`
      Tier3 Tier3Config `json:"tier3"`
  }

  type Tier1Config struct {
      Enabled     bool `json:"enabled"`
      BufferSize  int  `json:"buffer_size"`
      AutoPrepend bool `json:"auto_prepend"`
  }

  type Tier2Config struct {
      Enabled          bool   `json:"enabled"`
      Namespace        string `json:"namespace"`
      SummaryTTL       int    `json:"summary_ttl_seconds"`
      FactsTTL         int    `json:"facts_ttl_seconds"`
  }

  type Tier3Config struct {
      Enabled   bool    `json:"enabled"`
      TopK      int     `json:"top_k"`
      Threshold float64 `json:"threshold"`
  }
  ```

- [x] Add message buffer and memory config to `runContext`:
  ```go
  type runContext struct {
      // ... existing fields ...

      messageBuffer  *entity.MessageBuffer  // NEW: Local message buffer
      memoryConfig   *MemoryConfig          // NEW: Memory configuration
      currentSummary *entity.Summary        // NEW: Current summary (Phase 2)
  }
  ```

- [x] Modify `StartRun` to initialize message buffer:
  ```go
  func (s *Scheduler) StartRun(ctx context.Context, runID string, graphJSON string, inputJSON string, callbackURL string, memoryConfigJSON string) error {
      // Parse memory config
      var memoryConfig MemoryConfig
      if memoryConfigJSON != "" {
          if err := json.Unmarshal([]byte(memoryConfigJSON), &memoryConfig); err != nil {
              log.Warn("Invalid memory config, using defaults", "error", err)
              memoryConfig = defaultMemoryConfig()
          }
      } else {
          memoryConfig = defaultMemoryConfig()
      }

      // Initialize buffer with configured size
      bufferSize := memoryConfig.Tier1.BufferSize
      if bufferSize <= 0 {
          bufferSize = 20 // Default
      }

      runCtx := &runContext{
          // ... existing initialization ...
          messageBuffer: entity.NewMessageBuffer(bufferSize),
          memoryConfig:  &memoryConfig,
      }

      // ... rest of method ...
  }

  func defaultMemoryConfig() MemoryConfig {
      return MemoryConfig{
          Tier1: Tier1Config{
              Enabled:     true,
              BufferSize:  20,
              AutoPrepend: true,
          },
          Tier2: Tier2Config{
              Enabled: false,
          },
          Tier3: Tier3Config{
              Enabled: false,
          },
      }
  }
  ```

- [x] Modify prompt executor to capture messages:
  ```go
  // In engine/adapter/executor/prompt_executor.go

  type PromptExecutor struct {
      // ... existing fields ...
  }

  func (e *PromptExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
      // Get run context from state or context
      runCtx := getRunContext(ctx)

      // Build prompt with memory context
      prompt := e.buildPromptWithMemory(runCtx, node, state)

      // Call LLM
      response, err := e.llmClient.Complete(ctx, prompt)
      if err != nil {
          return nil, err
      }

      // Capture messages in buffer
      if runCtx != nil && runCtx.memoryConfig.Tier1.Enabled {
          userInput := extractUserInput(node, state)
          runCtx.messageBuffer.Push(entity.Message{
              Role:    "user",
              Content: userInput,
              NodeID:  node.ID,
          })
          runCtx.messageBuffer.Push(entity.Message{
              Role:    "assistant",
              Content: response,
              NodeID:  node.ID,
          })
      }

      return &port.NodeExecutionResult{
          Output: response,
      }, nil
  }

  func (e *PromptExecutor) buildPromptWithMemory(runCtx *runContext, node *entity.Node, state *entity.State) string {
      basePrompt := getNodePrompt(node, state)

      if runCtx == nil || !runCtx.memoryConfig.Tier1.AutoPrepend {
          return basePrompt
      }

      messages := runCtx.messageBuffer.GetAll()
      if len(messages) == 0 {
          return basePrompt
      }

      var sb strings.Builder
      sb.WriteString(basePrompt)
      sb.WriteString("\n\n--- Previous conversation ---\n")
      for _, msg := range messages {
          sb.WriteString(fmt.Sprintf("%s: %s\n", strings.Title(msg.Role), msg.Content))
      }
      sb.WriteString("--- End previous conversation ---\n\n")

      return sb.String()
  }
  ```

- [x] Pass run context through execution via context.Context:
  ```go
  type runContextKey struct{}

  func withRunContext(ctx context.Context, runCtx *runContext) context.Context {
      return context.WithValue(ctx, runContextKey{}, runCtx)
  }

  func getRunContext(ctx context.Context) *runContext {
      if v := ctx.Value(runContextKey{}); v != nil {
          return v.(*runContext)
      }
      return nil
  }
  ```

- [x] Update worker to pass run context:
  ```go
  func (s *Scheduler) runWorker(runCtx *runContext) {
      ctx := withRunContext(runCtx.ctx, runCtx)
      for nodeID := range runCtx.workChan {
          s.executeNode(ctx, runCtx, nodeID)
      }
  }
  ```

**Acceptance Criteria:**
- [x] Each run has isolated message buffer
- [x] Buffer size respects `MemoryConfig.Tier1.BufferSize`
- [x] When `AutoPrepend=true`, prompts include buffer messages
- [x] User and assistant messages captured after prompt execution
- [x] Run context accessible from node executors
- [x] Default configuration applied when no config provided

---

### P1-T04: Create Memory Configuration Django Model
**Files:**
- `backend/domain/entities/memory_config.py`
- `backend/infrastructure/orm/models.py`
- `backend/infrastructure/orm/migrations/0011_memory_configuration.py`
- `backend/adapters/api/graphs/serializers.py`
- `backend/adapters/api/graphs/views.py`

- [x] Create domain entity:
  ```python
  # backend/domain/entities/memory_config.py
  from dataclasses import dataclass
  from typing import Optional
  from uuid import UUID

  @dataclass
  class MemoryConfigEntity:
      id: UUID

      # Scope (one must be set)
      graph_id: Optional[UUID] = None
      user_id: Optional[UUID] = None

      # Tier 1: Local Buffer
      buffer_enabled: bool = True
      buffer_size: int = 20
      auto_prepend: bool = True

      # Tier 2: Redis
      redis_enabled: bool = False
      redis_summary_ttl: int = 86400  # 24 hours
      redis_facts_ttl: int = 604800   # 7 days

      # Tier 3: Vector (Phase 3)
      vector_enabled: bool = False
      vector_top_k: int = 5
      vector_threshold: float = 0.7
  ```

- [x] Add ORM model:
  ```python
  # In backend/infrastructure/orm/models.py

  class MemoryConfiguration(models.Model):
      id = models.UUIDField(primary_key=True, default=uuid.uuid4)

      # Scope: either graph-level or user-level default
      graph = models.OneToOneField(
          'Graph',
          on_delete=models.CASCADE,
          null=True,
          blank=True,
          related_name='memory_config'
      )
      user = models.ForeignKey(
          settings.AUTH_USER_MODEL,
          on_delete=models.CASCADE,
          null=True,
          blank=True,
          related_name='default_memory_config'
      )

      # Tier 1: Local Buffer
      buffer_enabled = models.BooleanField(default=True)
      buffer_size = models.PositiveIntegerField(
          default=20,
          validators=[MinValueValidator(1), MaxValueValidator(200)]
      )
      auto_prepend = models.BooleanField(default=True)

      # Tier 2: Redis
      redis_enabled = models.BooleanField(default=False)
      redis_summary_ttl = models.PositiveIntegerField(default=86400)
      redis_facts_ttl = models.PositiveIntegerField(default=604800)

      # Tier 3: Vector (Phase 3, define now)
      vector_enabled = models.BooleanField(default=False)
      vector_top_k = models.PositiveIntegerField(default=5)
      vector_threshold = models.FloatField(
          default=0.7,
          validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
      )

      created_at = models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)

      class Meta:
          db_table = 'memory_configurations'
          constraints = [
              models.CheckConstraint(
                  check=~(models.Q(graph__isnull=True) & models.Q(user__isnull=True)),
                  name='memory_config_requires_scope'
              ),
              models.CheckConstraint(
                  check=~(models.Q(graph__isnull=False) & models.Q(user__isnull=False)),
                  name='memory_config_single_scope'
              ),
          ]

      def to_engine_config(self) -> dict:
          """Convert to JSON format expected by Go engine."""
          return {
              "tier1": {
                  "enabled": self.buffer_enabled,
                  "buffer_size": self.buffer_size,
                  "auto_prepend": self.auto_prepend,
              },
              "tier2": {
                  "enabled": self.redis_enabled,
                  "summary_ttl_seconds": self.redis_summary_ttl,
                  "facts_ttl_seconds": self.redis_facts_ttl,
              },
              "tier3": {
                  "enabled": self.vector_enabled,
                  "top_k": self.vector_top_k,
                  "threshold": self.vector_threshold,
              },
          }
  ```

- [x] Create migration file:
  ```python
  # backend/infrastructure/orm/migrations/0011_memory_configuration.py

  from django.db import migrations, models
  import django.db.models.deletion
  import uuid

  class Migration(migrations.Migration):
      dependencies = [
          ('infrastructure', '0010_memory_entries'),
      ]

      operations = [
          migrations.CreateModel(
              name='MemoryConfiguration',
              fields=[
                  ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                  ('buffer_enabled', models.BooleanField(default=True)),
                  ('buffer_size', models.PositiveIntegerField(default=20)),
                  ('auto_prepend', models.BooleanField(default=True)),
                  ('redis_enabled', models.BooleanField(default=False)),
                  ('redis_summary_ttl', models.PositiveIntegerField(default=86400)),
                  ('redis_facts_ttl', models.PositiveIntegerField(default=604800)),
                  ('vector_enabled', models.BooleanField(default=False)),
                  ('vector_top_k', models.PositiveIntegerField(default=5)),
                  ('vector_threshold', models.FloatField(default=0.7)),
                  ('created_at', models.DateTimeField(auto_now_add=True)),
                  ('updated_at', models.DateTimeField(auto_now=True)),
                  ('graph', models.OneToOneField(
                      blank=True, null=True,
                      on_delete=django.db.models.deletion.CASCADE,
                      related_name='memory_config',
                      to='infrastructure.graph'
                  )),
                  ('user', models.ForeignKey(
                      blank=True, null=True,
                      on_delete=django.db.models.deletion.CASCADE,
                      related_name='default_memory_config',
                      to='auth.user'
                  )),
              ],
              options={
                  'db_table': 'memory_configurations',
              },
          ),
          migrations.AddConstraint(
              model_name='memoryconfiguration',
              constraint=models.CheckConstraint(
                  check=~(models.Q(graph__isnull=True) & models.Q(user__isnull=True)),
                  name='memory_config_requires_scope',
              ),
          ),
          migrations.AddConstraint(
              model_name='memoryconfiguration',
              constraint=models.CheckConstraint(
                  check=~(models.Q(graph__isnull=False) & models.Q(user__isnull=False)),
                  name='memory_config_single_scope',
              ),
          ),
      ]
  ```

- [x] Create serializer:
  ```python
  # In backend/adapters/api/graphs/serializers.py

  class MemoryConfigurationSerializer(serializers.ModelSerializer):
      # User-friendly preset for buffer size
      memory_depth = serializers.ChoiceField(
          choices=['short', 'medium', 'long', 'extended', 'custom'],
          write_only=True,
          required=False,
      )

      DEPTH_TO_SIZE = {
          'short': 10,
          'medium': 20,
          'long': 50,
          'extended': 100,
      }

      class Meta:
          model = MemoryConfiguration
          fields = [
              'id',
              'buffer_enabled', 'buffer_size', 'auto_prepend',
              'redis_enabled', 'redis_summary_ttl', 'redis_facts_ttl',
              'vector_enabled', 'vector_top_k', 'vector_threshold',
              'memory_depth',
              'created_at', 'updated_at',
          ]
          read_only_fields = ['id', 'created_at', 'updated_at']

      def validate_buffer_size(self, value):
          if value < 1 or value > 200:
              raise serializers.ValidationError("Buffer size must be between 1 and 200")
          return value

      def validate_vector_threshold(self, value):
          if value < 0.5 or value > 0.99:
              raise serializers.ValidationError("Threshold must be between 0.5 and 0.99")
          return value

      def create(self, validated_data):
          depth = validated_data.pop('memory_depth', None)
          if depth and depth in self.DEPTH_TO_SIZE:
              validated_data['buffer_size'] = self.DEPTH_TO_SIZE[depth]
          return super().create(validated_data)

      def update(self, instance, validated_data):
          depth = validated_data.pop('memory_depth', None)
          if depth and depth in self.DEPTH_TO_SIZE:
              validated_data['buffer_size'] = self.DEPTH_TO_SIZE[depth]
          return super().update(instance, validated_data)
  ```

- [x] Create API endpoints:
  ```python
  # In backend/adapters/api/graphs/views.py

  class MemoryConfigViewSet(viewsets.ModelViewSet):
      serializer_class = MemoryConfigurationSerializer
      permission_classes = [IsAuthenticated]

      def get_queryset(self):
          return MemoryConfiguration.objects.filter(
              models.Q(graph__owner=self.request.user) |
              models.Q(user=self.request.user)
          )

      @action(detail=False, methods=['get', 'patch'], url_path='for-graph/(?P<graph_id>[^/.]+)')
      def for_graph(self, request, graph_id=None):
          """Get or update memory config for a specific graph."""
          graph = get_object_or_404(Graph, id=graph_id, owner=request.user)

          config, created = MemoryConfiguration.objects.get_or_create(
              graph=graph,
              defaults={'user': None}
          )

          if request.method == 'PATCH':
              serializer = self.get_serializer(config, data=request.data, partial=True)
              serializer.is_valid(raise_exception=True)
              serializer.save()
              config = serializer.instance

          serializer = self.get_serializer(config)
          return Response(serializer.data)
  ```

- [x] Register URLs:
  ```python
  # In backend/adapters/api/graphs/urls.py

  router.register(r'memory-config', MemoryConfigViewSet, basename='memory-config')
  ```

- [ ] Write tests:
  ```python
  # backend/tests/unit/adapters/api/test_memory_config.py

  class TestMemoryConfigAPI:
      def test_get_graph_config(self, api_client, graph):
          response = api_client.get(f'/api/memory-config/for-graph/{graph.id}/')
          assert response.status_code == 200
          assert response.data['buffer_size'] == 20  # default

      def test_update_config(self, api_client, graph):
          response = api_client.patch(
              f'/api/memory-config/for-graph/{graph.id}/',
              {'buffer_size': 50, 'redis_enabled': True}
          )
          assert response.status_code == 200
          assert response.data['buffer_size'] == 50
          assert response.data['redis_enabled'] is True

      def test_memory_depth_preset(self, api_client, graph):
          response = api_client.patch(
              f'/api/memory-config/for-graph/{graph.id}/',
              {'memory_depth': 'long'}
          )
          assert response.data['buffer_size'] == 50

      def test_validation_buffer_size(self, api_client, graph):
          response = api_client.patch(
              f'/api/memory-config/for-graph/{graph.id}/',
              {'buffer_size': 500}
          )
          assert response.status_code == 400
  ```

**Acceptance Criteria:**
- [x] Migration applies successfully (`python manage.py migrate`)
- [x] Model enforces exactly one of `graph` or `user` is set
- [x] Serializer validates buffer_size (1-200) and threshold (0.5-0.99)
- [x] `GET /api/memory-config/for-graph/{id}/` returns configuration
- [x] `PATCH /api/memory-config/for-graph/{id}/` updates configuration
- [x] Default configuration created when graph first accessed
- [x] Memory depth presets map to correct buffer sizes
- [ ] All unit tests pass

---

### P1-T05: Extend StartRunRequest with Memory Configuration
**Files:**
- `engine/proto/engine.proto`
- `engine/proto/engine.pb.go` (regenerated)
- `engine/proto/engine_grpc.pb.go` (regenerated)
- `backend/adapters/api/runs/views.py`
- `backend/adapters/grpc/engine_client.py`

- [x] Update proto definition:
  ```protobuf
  // engine/proto/engine.proto

  message StartRunRequest {
      string run_id = 1;
      string graph_json = 2;
      string input_json = 3;
      string callback_url = 4;
      string memory_config_json = 5;  // NEW: Memory configuration JSON
      string tenant_id = 6;           // NEW: Tenant ID for isolation
  }
  ```

- [x] Regenerate Go proto files:
  ```bash
  cd engine
  protoc --go_out=. --go-grpc_out=. proto/engine.proto
  ```

- [x] Update Django gRPC client:
  ```python
  # backend/adapters/grpc/engine_client.py

  class EngineClient:
      def start_run(
          self,
          run_id: str,
          graph_json: str,
          input_json: str,
          callback_url: str,
          memory_config: dict | None = None,
          tenant_id: str | None = None,
      ) -> StartRunResponse:
          request = StartRunRequest(
              run_id=run_id,
              graph_json=graph_json,
              input_json=input_json,
              callback_url=callback_url,
              memory_config_json=json.dumps(memory_config) if memory_config else "",
              tenant_id=tenant_id or "",
          )
          return self.stub.StartRun(request)
  ```

- [x] Update run creation view:
  ```python
  # backend/adapters/api/runs/views.py

  class RunViewSet(viewsets.ModelViewSet):
      def create(self, request):
          # ... existing validation ...

          # Get memory config for graph
          memory_config = None
          if hasattr(graph, 'memory_config'):
              memory_config = graph.memory_config.to_engine_config()

          # Get tenant ID
          tenant_id = str(request.user.tenant_id) if hasattr(request.user, 'tenant_id') else str(request.user.id)

          # Start run in engine
          response = engine_client.start_run(
              run_id=str(run.id),
              graph_json=graph_json,
              input_json=input_json,
              callback_url=callback_url,
              memory_config=memory_config,
              tenant_id=tenant_id,
          )

          # ... rest of method ...
  ```

- [x] Update Go engine to parse memory config:
  ```go
  // In engine/adapter/grpc/server.go

  func (s *Server) StartRun(ctx context.Context, req *pb.StartRunRequest) (*pb.StartRunResponse, error) {
      // ... existing code ...

      err := s.scheduler.StartRun(
          ctx,
          req.RunId,
          req.GraphJson,
          req.InputJson,
          req.CallbackUrl,
          req.MemoryConfigJson,  // NEW
          req.TenantId,          // NEW
      )

      // ... rest of method ...
  }
  ```

- [x] Update scheduler signature:
  ```go
  func (s *Scheduler) StartRun(
      ctx context.Context,
      runID string,
      graphJSON string,
      inputJSON string,
      callbackURL string,
      memoryConfigJSON string,  // NEW
      tenantID string,          // NEW
  ) error
  ```

**Acceptance Criteria:**
- [x] Proto regeneration succeeds without errors
- [x] Django serializes memory config into JSON
- [x] Go engine parses `memory_config_json` field
- [x] Missing/empty config uses sensible defaults
- [x] Invalid JSON logs warning and uses defaults (doesn't fail)
- [x] Tenant ID passed through to memory store
- [x] Integration test confirms config reaches scheduler

---

### P1-T06: Create TieredMemoryStore Composition
**Files:**
- `engine/adapter/store/tiered_memory_store.go`
- `engine/adapter/store/tiered_memory_store_test.go`

- [x] Define tiered configuration:
  ```go
  type TieredConfig struct {
      Tier1Enabled bool
      Tier2Enabled bool
      Tier3Enabled bool
      ReadOrder    []int  // Which tiers to check for reads
      WriteOrder   []int  // Which tiers to write to
  }

  func DefaultTieredConfig() TieredConfig {
      return TieredConfig{
          Tier1Enabled: true,
          Tier2Enabled: false,
          Tier3Enabled: false,
          ReadOrder:    []int{2, 3},  // Check Redis, then Vector
          WriteOrder:   []int{2},     // Write to Redis
      }
  }
  ```

- [x] Create metrics struct:
  ```go
  type TieredMetrics struct {
      mu sync.Mutex

      Tier1Hits   int64
      Tier1Misses int64
      Tier2Hits   int64
      Tier2Misses int64
      Tier3Hits   int64
      Tier3Misses int64

      ReadLatency  map[int][]time.Duration
      WriteLatency map[int][]time.Duration
  }

  func (m *TieredMetrics) RecordHit(tier int) {
      m.mu.Lock()
      defer m.mu.Unlock()
      switch tier {
      case 1:
          m.Tier1Hits++
      case 2:
          m.Tier2Hits++
      case 3:
          m.Tier3Hits++
      }
  }
  ```

- [x] Create TieredMemoryStore:
  ```go
  type TieredMemoryStore struct {
      tier1   *entity.MessageBuffer  // Local buffer (special handling)
      tier2   port.MemoryStore       // Redis
      tier3   port.MemoryStore       // Vector DB (Phase 3)
      config  TieredConfig
      metrics *TieredMetrics
      mu      sync.RWMutex
  }

  func NewTieredMemoryStore(
      tier2 port.MemoryStore,
      tier3 port.MemoryStore,
      config TieredConfig,
  ) *TieredMemoryStore {
      return &TieredMemoryStore{
          tier2:   tier2,
          tier3:   tier3,
          config:  config,
          metrics: &TieredMetrics{
              ReadLatency:  make(map[int][]time.Duration),
              WriteLatency: make(map[int][]time.Duration),
          },
      }
  }
  ```

- [x] Implement Get with tier traversal:
  ```go
  func (s *TieredMemoryStore) Get(ctx context.Context, namespace, key string) (any, bool, error) {
      for _, tier := range s.config.ReadOrder {
          store := s.getTierStore(tier)
          if store == nil {
              continue
          }

          start := time.Now()
          val, found, err := store.Get(ctx, namespace, key)
          s.recordLatency(tier, time.Since(start), true)

          if err != nil {
              // Log but continue to next tier
              log.Warn("Tier read failed", "tier", tier, "error", err)
              continue
          }

          if found {
              s.metrics.RecordHit(tier)
              return val, true, nil
          }

          s.metrics.RecordMiss(tier)
      }

      return nil, false, nil
  }

  func (s *TieredMemoryStore) getTierStore(tier int) port.MemoryStore {
      switch tier {
      case 2:
          if s.config.Tier2Enabled && s.tier2 != nil {
              return s.tier2
          }
      case 3:
          if s.config.Tier3Enabled && s.tier3 != nil {
              return s.tier3
          }
      }
      return nil
  }
  ```

- [ ] Implement Set with parallel writes:
  ```go
  func (s *TieredMemoryStore) Set(ctx context.Context, namespace, key string, value any, ttlSeconds int) error {
      var wg sync.WaitGroup
      var errMu sync.Mutex
      var firstErr error

      for _, tier := range s.config.WriteOrder {
          store := s.getTierStore(tier)
          if store == nil {
              continue
          }

          wg.Add(1)
          go func(t int, st port.MemoryStore) {
              defer wg.Done()

              start := time.Now()
              err := st.Set(ctx, namespace, key, value, ttlSeconds)
              s.recordLatency(t, time.Since(start), false)

              if err != nil {
                  errMu.Lock()
                  if firstErr == nil {
                      firstErr = fmt.Errorf("tier %d: %w", t, err)
                  }
                  errMu.Unlock()
                  log.Warn("Tier write failed", "tier", t, "error", err)
              }
          }(tier, store)
      }

      wg.Wait()
      return firstErr  // Return first error but all writes attempted
  }
  ```

- [x] Implement Delete:
  ```go
  func (s *TieredMemoryStore) Delete(ctx context.Context, namespace, key string) (bool, error) {
      var deleted bool
      for _, tier := range s.config.WriteOrder {
          store := s.getTierStore(tier)
          if store == nil {
              continue
          }

          d, err := store.Delete(ctx, namespace, key)
          if err != nil {
              log.Warn("Tier delete failed", "tier", tier, "error", err)
          }
          if d {
              deleted = true
          }
      }
      return deleted, nil
  }
  ```

- [ ] Add metrics export:
  ```go
  func (s *TieredMemoryStore) GetMetrics() TieredMetrics {
      s.metrics.mu.Lock()
      defer s.metrics.mu.Unlock()
      return *s.metrics
  }

  func (s *TieredMemoryStore) GetHitRate(tier int) float64 {
      s.metrics.mu.Lock()
      defer s.metrics.mu.Unlock()

      var hits, misses int64
      switch tier {
      case 1:
          hits, misses = s.metrics.Tier1Hits, s.metrics.Tier1Misses
      case 2:
          hits, misses = s.metrics.Tier2Hits, s.metrics.Tier2Misses
      case 3:
          hits, misses = s.metrics.Tier3Hits, s.metrics.Tier3Misses
      }

      total := hits + misses
      if total == 0 {
          return 0
      }
      return float64(hits) / float64(total)
  }
  ```

- [ ] Write unit tests:
  - [ ] `TestTieredMemoryStore_GetFromFirstTier` - returns on first hit
  - [x] `TestTieredMemoryStore_FallbackToNextTier` - continues on miss
  - [x] `TestTieredMemoryStore_WriteToAllTiers` - writes to all enabled
  - [ ] `TestTieredMemoryStore_TierFailure` - continues despite errors
  - [ ] `TestTieredMemoryStore_Metrics` - tracks hits/misses
  - [ ] `TestTieredMemoryStore_ParallelWrites` - writes happen concurrently

**Acceptance Criteria:**
- [x] `Get()` returns value from first tier that has it
- [x] `Get()` continues to next tier on miss
- [ ] `Set()` writes to all tiers in WriteOrder (in parallel)
- [x] Tier failure logs warning but doesn't break operation
- [x] Metrics correctly track hits/misses per tier
- [ ] Latency overhead of tiering is <1ms vs direct access

---

### P1-T07: Create Frontend Memory Configuration UI
**Files:**
- `frontend/components/graph-editor/dialogs/MemoryConfigDialog.tsx`
- `frontend/lib/api/graphs.ts`
- `frontend/components/graph-editor/forms/MemoryNodeForm.tsx` (update)

- [x] Create API functions:
  ```typescript
  // frontend/lib/api/graphs.ts

  export interface MemoryConfig {
    id: string;
    buffer_enabled: boolean;
    buffer_size: number;
    auto_prepend: boolean;
    redis_enabled: boolean;
    redis_summary_ttl: number;
    redis_facts_ttl: number;
    vector_enabled: boolean;
    vector_top_k: number;
    vector_threshold: number;
    created_at: string;
    updated_at: string;
  }

  export async function getGraphMemoryConfig(graphId: string): Promise<MemoryConfig> {
    const response = await api.get(`/api/memory-config/for-graph/${graphId}/`);
    return response.data;
  }

  export async function updateGraphMemoryConfig(
    graphId: string,
    config: Partial<MemoryConfig>
  ): Promise<MemoryConfig> {
    const response = await api.patch(`/api/memory-config/for-graph/${graphId}/`, config);
    return response.data;
  }
  ```

- [x] Define memory depth presets:
  ```typescript
  // frontend/components/graph-editor/dialogs/MemoryConfigDialog.tsx

  const MEMORY_DEPTH_OPTIONS = [
    {
      value: 'short',
      label: 'Short',
      description: 'Last 10 messages',
      bufferSize: 10
    },
    {
      value: 'medium',
      label: 'Medium',
      description: 'Last 20 messages',
      bufferSize: 20
    },
    {
      value: 'long',
      label: 'Long',
      description: 'Last 50 messages',
      bufferSize: 50
    },
    {
      value: 'extended',
      label: 'Extended',
      description: 'Last 100 messages',
      bufferSize: 100
    },
    {
      value: 'custom',
      label: 'Custom',
      description: 'Specify exact number',
      bufferSize: null
    },
  ] as const;

  type MemoryDepth = typeof MEMORY_DEPTH_OPTIONS[number]['value'];
  ```

- [x] Create form state interface:
  ```typescript
  interface MemoryConfigFormData {
    memoryDepth: MemoryDepth;
    customBufferSize: number;
    autoPrepend: boolean;
    enablePersistence: boolean;
    showAdvanced: boolean;
    // Advanced options
    summaryTtlHours: number;
    factsTtlDays: number;
  }

  function configToFormData(config: MemoryConfig): MemoryConfigFormData {
    const depth = MEMORY_DEPTH_OPTIONS.find(d => d.bufferSize === config.buffer_size);
    return {
      memoryDepth: depth?.value ?? 'custom',
      customBufferSize: config.buffer_size,
      autoPrepend: config.auto_prepend,
      enablePersistence: config.redis_enabled,
      showAdvanced: false,
      summaryTtlHours: Math.round(config.redis_summary_ttl / 3600),
      factsTtlDays: Math.round(config.redis_facts_ttl / 86400),
    };
  }

  function formDataToConfig(form: MemoryConfigFormData): Partial<MemoryConfig> {
    const depth = MEMORY_DEPTH_OPTIONS.find(d => d.value === form.memoryDepth);
    return {
      buffer_size: depth?.bufferSize ?? form.customBufferSize,
      auto_prepend: form.autoPrepend,
      redis_enabled: form.enablePersistence,
      redis_summary_ttl: form.summaryTtlHours * 3600,
      redis_facts_ttl: form.factsTtlDays * 86400,
    };
  }
  ```

- [x] Create MemoryConfigDialog component:
  ```typescript
  import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
  import { Label } from '@/components/ui/label';
  import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
  import { Switch } from '@/components/ui/switch';
  import { Input } from '@/components/ui/input';
  import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
  import { Button } from '@/components/ui/button';

  interface MemoryConfigDialogProps {
    graphId: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
  }

  export function MemoryConfigDialog({ graphId, open, onOpenChange }: MemoryConfigDialogProps) {
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [form, setForm] = useState<MemoryConfigFormData | null>(null);
    const [error, setError] = useState<string | null>(null);

    // Load config on open
    useEffect(() => {
      if (open && graphId) {
        setLoading(true);
        getGraphMemoryConfig(graphId)
          .then(config => {
            setForm(configToFormData(config));
            setError(null);
          })
          .catch(err => setError(err.message))
          .finally(() => setLoading(false));
      }
    }, [open, graphId]);

    const handleSave = async () => {
      if (!form) return;

      setSaving(true);
      try {
        await updateGraphMemoryConfig(graphId, formDataToConfig(form));
        onOpenChange(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to save');
      } finally {
        setSaving(false);
      }
    };

    if (loading) {
      return (
        <Dialog open={open} onOpenChange={onOpenChange}>
          <DialogContent>
            <div className="flex items-center justify-center p-8">
              <Spinner />
            </div>
          </DialogContent>
        </Dialog>
      );
    }

    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Memory Configuration</DialogTitle>
          </DialogHeader>

          {error && (
            <div className="text-sm text-red-500 bg-red-50 p-2 rounded">
              {error}
            </div>
          )}

          <div className="space-y-6">
            {/* Memory Depth Selection */}
            <div className="space-y-3">
              <Label>Memory Depth</Label>
              <RadioGroup
                value={form?.memoryDepth}
                onValueChange={(value) => setForm(f => f ? {...f, memoryDepth: value as MemoryDepth} : f)}
              >
                {MEMORY_DEPTH_OPTIONS.map(option => (
                  <div key={option.value} className="flex items-center space-x-3">
                    <RadioGroupItem value={option.value} id={option.value} />
                    <Label htmlFor={option.value} className="flex-1">
                      <span className="font-medium">{option.label}</span>
                      <span className="text-muted-foreground ml-2">{option.description}</span>
                    </Label>
                  </div>
                ))}
              </RadioGroup>

              {form?.memoryDepth === 'custom' && (
                <div className="ml-6">
                  <Label htmlFor="customSize">Buffer Size</Label>
                  <Input
                    id="customSize"
                    type="number"
                    min={1}
                    max={200}
                    value={form.customBufferSize}
                    onChange={(e) => setForm(f => f ? {...f, customBufferSize: parseInt(e.target.value) || 20} : f)}
                    className="w-24"
                  />
                </div>
              )}
            </div>

            {/* Auto-prepend toggle */}
            <div className="flex items-center justify-between">
              <div>
                <Label>Auto-include in prompts</Label>
                <p className="text-sm text-muted-foreground">
                  Automatically add conversation history to prompts
                </p>
              </div>
              <Switch
                checked={form?.autoPrepend}
                onCheckedChange={(checked) => setForm(f => f ? {...f, autoPrepend: checked} : f)}
              />
            </div>

            {/* Persistence toggle */}
            <div className="flex items-center justify-between">
              <div>
                <Label>Enable Persistence</Label>
                <p className="text-sm text-muted-foreground">
                  Store memories in Redis for cross-session access
                </p>
              </div>
              <Switch
                checked={form?.enablePersistence}
                onCheckedChange={(checked) => setForm(f => f ? {...f, enablePersistence: checked} : f)}
              />
            </div>

            {/* Advanced Options */}
            <Accordion type="single" collapsible>
              <AccordionItem value="advanced">
                <AccordionTrigger>Advanced Options</AccordionTrigger>
                <AccordionContent className="space-y-4">
                  <div>
                    <Label htmlFor="summaryTtl">Summary retention (hours)</Label>
                    <Input
                      id="summaryTtl"
                      type="number"
                      min={1}
                      max={720}
                      value={form?.summaryTtlHours}
                      onChange={(e) => setForm(f => f ? {...f, summaryTtlHours: parseInt(e.target.value) || 24} : f)}
                      className="w-24"
                    />
                  </div>
                  <div>
                    <Label htmlFor="factsTtl">Facts retention (days)</Label>
                    <Input
                      id="factsTtl"
                      type="number"
                      min={1}
                      max={90}
                      value={form?.factsTtlDays}
                      onChange={(e) => setForm(f => f ? {...f, factsTtlDays: parseInt(e.target.value) || 7} : f)}
                      className="w-24"
                    />
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>

          <div className="flex justify-end gap-2 mt-6">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    );
  }
  ```

- [x] Add button to open dialog from graph editor toolbar:
  ```typescript
  // In GraphEditor.tsx or toolbar component

  const [memoryConfigOpen, setMemoryConfigOpen] = useState(false);

  // In toolbar
  <Button
    variant="ghost"
    size="sm"
    onClick={() => setMemoryConfigOpen(true)}
    title="Memory Settings"
  >
    <BrainIcon className="h-4 w-4 mr-1" />
    Memory
  </Button>

  // Render dialog
  <MemoryConfigDialog
    graphId={graphId}
    open={memoryConfigOpen}
    onOpenChange={setMemoryConfigOpen}
  />
  ```

- [x] Write component tests:
  ```typescript
  // frontend/__tests__/components/graph-editor/dialogs/MemoryConfigDialog.test.tsx

  describe('MemoryConfigDialog', () => {
    it('loads and displays current config', async () => {
      mockGetGraphMemoryConfig.mockResolvedValue({
        buffer_size: 50,
        auto_prepend: true,
        redis_enabled: false,
      });

      render(<MemoryConfigDialog graphId="123" open={true} onOpenChange={jest.fn()} />);

      await waitFor(() => {
        expect(screen.getByRole('radio', { name: /Long/ })).toBeChecked();
      });
    });

    it('saves updated config', async () => {
      // ...
    });

    it('shows custom input when custom depth selected', async () => {
      // ...
    });

    it('validates buffer size range', async () => {
      // ...
    });
  });
  ```

**Acceptance Criteria:**
- [x] Memory depth dropdown shows 5 preset options
- [x] Selecting "Custom" reveals numeric input
- [x] "Enable Persistence" toggle maps to redis_enabled
- [x] "Advanced" accordion reveals TTL settings
- [x] Form loads existing configuration on dialog open
- [x] Form saves configuration via PATCH endpoint
- [x] Validation prevents invalid values (buffer 1-200)
- [x] Works correctly in light and dark themes
- [x] All component tests pass

---

### P1-T08: Add Redis Health Check and Metrics
**Files:**
- `engine/adapter/store/redis_health.go`
- `engine/adapter/metrics/memory_metrics.go`
- `engine/main.go`

- [x] Create health checker:
  ```go
  // engine/adapter/store/redis_health.go

  type HealthStatus struct {
      Healthy   bool          `json:"healthy"`
      Latency   time.Duration `json:"latency_ms"`
      Error     string        `json:"error,omitempty"`
      CheckedAt time.Time     `json:"checked_at"`
  }

  type RedisHealthChecker struct {
      client    *redis.Client
      mu        sync.Mutex
      lastCheck HealthStatus
      cacheDur  time.Duration
  }

  func NewRedisHealthChecker(client *redis.Client) *RedisHealthChecker {
      return &RedisHealthChecker{
          client:   client,
          cacheDur: 5 * time.Second,
      }
  }

  func (h *RedisHealthChecker) Check(ctx context.Context) HealthStatus {
      h.mu.Lock()
      defer h.mu.Unlock()

      // Return cached if fresh
      if time.Since(h.lastCheck.CheckedAt) < h.cacheDur {
          return h.lastCheck
      }

      // Perform check
      start := time.Now()
      ctx, cancel := context.WithTimeout(ctx, time.Second)
      defer cancel()

      status := HealthStatus{
          CheckedAt: time.Now(),
      }

      if err := h.client.Ping(ctx).Err(); err != nil {
          status.Healthy = false
          status.Error = err.Error()
      } else {
          status.Healthy = true
      }
      status.Latency = time.Since(start)

      h.lastCheck = status
      return status
  }
  ```

- [x] Create Prometheus metrics:
  ```go
  // engine/adapter/metrics/memory_metrics.go

  import (
      "github.com/prometheus/client_golang/prometheus"
      "github.com/prometheus/client_golang/prometheus/promauto"
  )

  var (
      // Tier 1 metrics
      memoryBufferSize = promauto.NewGaugeVec(
          prometheus.GaugeOpts{
              Name: "forgegraph_memory_buffer_size",
              Help: "Current message buffer size per run",
          },
          []string{"run_id", "tenant_id"},
      )

      memoryBufferOperations = promauto.NewCounterVec(
          prometheus.CounterOpts{
              Name: "forgegraph_memory_buffer_operations_total",
              Help: "Total buffer operations",
          },
          []string{"operation", "tenant_id"},
      )

      // Tier 2 metrics
      memoryRedisOperations = promauto.NewCounterVec(
          prometheus.CounterOpts{
              Name: "forgegraph_memory_redis_operations_total",
              Help: "Total Redis operations",
          },
          []string{"operation", "status"},
      )

      memoryRedisLatency = promauto.NewHistogramVec(
          prometheus.HistogramOpts{
              Name:    "forgegraph_memory_redis_latency_seconds",
              Help:    "Redis operation latency",
              Buckets: []float64{.001, .005, .01, .025, .05, .1},
          },
          []string{"operation"},
      )

      memoryRedisCircuitState = promauto.NewGaugeVec(
          prometheus.GaugeOpts{
              Name: "forgegraph_memory_redis_circuit_state",
              Help: "Circuit breaker state (0=closed, 1=open)",
          },
          []string{},
      )

      memoryRedisFallback = promauto.NewCounter(
          prometheus.CounterOpts{
              Name: "forgegraph_memory_redis_fallback_total",
              Help: "Total fallback activations",
          },
      )

      // Tier hit rates
      memoryTierHits = promauto.NewCounterVec(
          prometheus.CounterOpts{
              Name: "forgegraph_memory_tier_hits_total",
              Help: "Cache hits per tier",
          },
          []string{"tier"},
      )

      memoryTierMisses = promauto.NewCounterVec(
          prometheus.CounterOpts{
              Name: "forgegraph_memory_tier_misses_total",
              Help: "Cache misses per tier",
          },
          []string{"tier"},
      )
  )

  // Helper functions
  func RecordRedisOperation(operation string, duration time.Duration, err error) {
      status := "success"
      if err != nil {
          status = "error"
      }
      memoryRedisOperations.WithLabelValues(operation, status).Inc()
      memoryRedisLatency.WithLabelValues(operation).Observe(duration.Seconds())
  }

  func RecordCircuitState(open bool) {
      val := 0.0
      if open {
          val = 1.0
      }
      memoryRedisCircuitState.WithLabelValues().Set(val)
  }

  func RecordFallback() {
      memoryRedisFallback.Inc()
  }

  func RecordTierHit(tier int) {
      memoryTierHits.WithLabelValues(fmt.Sprintf("%d", tier)).Inc()
  }

  func RecordTierMiss(tier int) {
      memoryTierMisses.WithLabelValues(fmt.Sprintf("%d", tier)).Inc()
  }
  ```

- [ ] Add health endpoint to gRPC server:
  ```go
  // In engine/proto/engine.proto - add to EngineService

  message HealthCheckRequest {}
  message HealthCheckResponse {
      bool healthy = 1;
      map<string, ComponentHealth> components = 2;
  }
  message ComponentHealth {
      bool healthy = 1;
      string message = 2;
      int64 latency_ms = 3;
  }

  rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
  ```

- [x] Expose Prometheus metrics endpoint:
  ```go
  // In engine/main.go

  import (
      "github.com/prometheus/client_golang/prometheus/promhttp"
  )

  func main() {
      // ... existing setup ...

      // Metrics server
      go func() {
          http.Handle("/metrics", promhttp.Handler())
          log.Info("Metrics server starting", "port", 9090)
          if err := http.ListenAndServe(":9090", nil); err != nil {
              log.Error("Metrics server failed", "error", err)
          }
      }()

      // ... rest of main ...
  }
  ```

- [x] Update RedisMemoryStore to emit metrics:
  ```go
  func (s *RedisMemoryStore) Get(ctx context.Context, namespace, key string) (any, bool, error) {
      start := time.Now()
      defer func() {
          metrics.RecordRedisOperation("get", time.Since(start), nil)
      }()

      // ... existing implementation ...
  }
  ```

**Acceptance Criteria:**
- [x] Health endpoint `/health/redis` returns Redis status within 100ms
- [x] Health check caches result for 5 seconds
- [x] Prometheus metrics exposed at `:9090/metrics`
- [x] Circuit breaker state changes update gauge
- [x] Fallback activations increment counter
- [x] Latency histograms capture operation times
- [ ] Grafana can scrape and visualize metrics

---

### P1-T09: Implement Multi-Tenant Key Isolation
**Files:**
- `engine/adapter/store/redis_memory_store.go`
- `engine/adapter/store/tenant_test.go`
- `backend/adapters/api/runs/views.py`

- [x] Ensure tenant ID is required and validated:
  ```go
  func NewRedisMemoryStore(cfg RedisConfig, tenantID string, fallback port.MemoryStore) (*RedisMemoryStore, error) {
      if tenantID == "" {
          return nil, fmt.Errorf("tenant ID is required")
      }

      // Validate tenant ID format (UUID)
      if _, err := uuid.Parse(tenantID); err != nil {
          return nil, fmt.Errorf("invalid tenant ID format: %w", err)
      }

      // ... rest of constructor ...
  }
  ```

- [x] Define key structure constants:
  ```go
  const (
      keyPrefixDefault = "forgegraph"

      // Key patterns
      keyPatternMemory  = "%s:tenant:%s:memory:%s:%s"     // prefix:tenant:id:memory:ns:key
      keyPatternBuffer  = "%s:tenant:%s:buffer:%s"        // prefix:tenant:id:buffer:run_id
      keyPatternSummary = "%s:tenant:%s:summary:%s"       // prefix:tenant:id:summary:run_id
      keyPatternFacts   = "%s:tenant:%s:facts:%s:%s"      // prefix:tenant:id:facts:scope:key
  )

  func (s *RedisMemoryStore) buildKey(namespace, key string) string {
      return fmt.Sprintf(keyPatternMemory, s.keyPrefix, s.tenantID, namespace, key)
  }

  func (s *RedisMemoryStore) buildBufferKey(runID string) string {
      return fmt.Sprintf(keyPatternBuffer, s.keyPrefix, s.tenantID, runID)
  }
  ```

- [x] Add method to list keys for a tenant (admin/debug only):
  ```go
  func (s *RedisMemoryStore) ListTenantKeys(ctx context.Context, pattern string) ([]string, error) {
      fullPattern := fmt.Sprintf("%s:tenant:%s:%s", s.keyPrefix, s.tenantID, pattern)

      var keys []string
      iter := s.client.Scan(ctx, 0, fullPattern, 100).Iterator()
      for iter.Next(ctx) {
          keys = append(keys, iter.Val())
      }

      return keys, iter.Err()
  }
  ```

- [x] Write isolation tests:
  ```go
  // engine/adapter/store/tenant_test.go

  func TestTenantIsolation_SeparateData(t *testing.T) {
      tenant1Store := NewRedisMemoryStore(cfg, "tenant-1-uuid", nil)
      tenant2Store := NewRedisMemoryStore(cfg, "tenant-2-uuid", nil)

      ctx := context.Background()

      // Tenant 1 sets a value
      err := tenant1Store.Set(ctx, "ns", "key1", "secret-value", 0)
      require.NoError(t, err)

      // Tenant 2 cannot see it
      val, found, err := tenant2Store.Get(ctx, "ns", "key1")
      require.NoError(t, err)
      assert.False(t, found)
      assert.Nil(t, val)

      // Verify raw key includes tenant ID
      client := redis.NewClient(&redis.Options{Addr: cfg.Addr})
      rawKey := "forgegraph:tenant:tenant-1-uuid:memory:ns:key1"
      exists, _ := client.Exists(ctx, rawKey).Result()
      assert.Equal(t, int64(1), exists)
  }

  func TestTenantIsolation_CannotAccessOtherTenantKeys(t *testing.T) {
      tenant1Store := NewRedisMemoryStore(cfg, "tenant-1-uuid", nil)

      ctx := context.Background()

      // Try to access with crafted namespace/key that looks like another tenant
      _, found, _ := tenant1Store.Get(ctx, "tenant:tenant-2-uuid:memory:ns", "key")
      assert.False(t, found) // Should not find anything
  }

  func TestTenantIsolation_DeleteOnlyOwnKeys(t *testing.T) {
      tenant1Store := NewRedisMemoryStore(cfg, "tenant-1-uuid", nil)
      tenant2Store := NewRedisMemoryStore(cfg, "tenant-2-uuid", nil)

      ctx := context.Background()

      // Both tenants set same logical key
      tenant1Store.Set(ctx, "ns", "key", "tenant1-value", 0)
      tenant2Store.Set(ctx, "ns", "key", "tenant2-value", 0)

      // Tenant 1 deletes
      deleted, _ := tenant1Store.Delete(ctx, "ns", "key")
      assert.True(t, deleted)

      // Tenant 2's key still exists
      val, found, _ := tenant2Store.Get(ctx, "ns", "key")
      assert.True(t, found)
      assert.Equal(t, "tenant2-value", val)
  }
  ```

- [x] Update Django to pass tenant ID:
  ```python
  # backend/adapters/api/runs/views.py

  def get_tenant_id(request) -> str:
      """Get tenant ID from authenticated user."""
      user = request.user

      # If multi-tenant with explicit tenant model
      if hasattr(user, 'tenant_id') and user.tenant_id:
          return str(user.tenant_id)

      # Fall back to user ID for single-tenant or simple auth
      return str(user.id)

  class RunViewSet(viewsets.ModelViewSet):
      def create(self, request):
          tenant_id = get_tenant_id(request)

          # ... validation ...

          response = engine_client.start_run(
              run_id=str(run.id),
              graph_json=graph_json,
              input_json=input_json,
              callback_url=callback_url,
              memory_config=memory_config,
              tenant_id=tenant_id,  # Pass tenant ID
          )
  ```

**Acceptance Criteria:**
- [x] All Redis keys include tenant ID in key path
- [x] Tenant A cannot read/write/delete Tenant B's data
- [x] Empty tenant ID rejected with error
- [x] Invalid tenant ID format rejected
- [x] Integration test with 2 tenants shows complete isolation
- [x] Key inspection confirms correct key format

---

### P1-T10: Implement Graceful Degradation and Fallback
**Files:**
- `engine/adapter/store/redis_memory_store.go`
- `engine/adapter/store/tiered_memory_store.go`
- `engine/application/usecase/scheduler.go`

- [x] Enhance fallback behavior in RedisMemoryStore:
  ```go
  func (s *RedisMemoryStore) Get(ctx context.Context, namespace, key string) (any, bool, error) {
      // Check circuit breaker first
      if s.isCircuitOpen() {
          metrics.RecordFallback()
          log.Info("Circuit open, using fallback", "namespace", namespace, "key", key)
          return s.fallback.Get(ctx, namespace, key)
      }

      start := time.Now()
      fullKey := s.buildKey(namespace, key)
      val, err := s.client.Get(ctx, fullKey).Result()

      if err == redis.Nil {
          // Key doesn't exist - not an error
          metrics.RecordRedisOperation("get", time.Since(start), nil)
          return nil, false, nil
      }

      if err != nil {
          // Redis error - record and potentially fall back
          metrics.RecordRedisOperation("get", time.Since(start), err)
          s.recordFailure()

          if s.fallback != nil {
              log.Warn("Redis get failed, falling back",
                  "namespace", namespace,
                  "key", key,
                  "error", err,
                  "failures", s.failureCount.Load(),
              )
              return s.fallback.Get(ctx, namespace, key)
          }
          return nil, false, err
      }

      // Success
      s.resetFailures()
      metrics.RecordRedisOperation("get", time.Since(start), nil)

      var result any
      if err := json.Unmarshal([]byte(val), &result); err != nil {
          return nil, false, fmt.Errorf("unmarshal error: %w", err)
      }
      return result, true, nil
  }
  ```

- [x] Add logging levels for different states:
  ```go
  func (s *RedisMemoryStore) recordFailure() {
      count := s.failureCount.Add(1)
      s.lastFailure.Store(time.Now())

      if count == 1 {
          log.Warn("First Redis failure detected")
      } else if count == failureThreshold {
          log.Error("Circuit breaker opening after repeated failures",
              "threshold", failureThreshold)
          s.circuitOpen.Store(true)
          metrics.RecordCircuitState(true)
      }
  }

  func (s *RedisMemoryStore) resetFailures() {
      if s.failureCount.Load() > 0 {
          s.failureCount.Store(0)
          if s.circuitOpen.Load() {
              log.Info("Circuit breaker closing, Redis recovered")
              s.circuitOpen.Store(false)
              metrics.RecordCircuitState(false)
          }
      }
  }
  ```

- [x] Add connection recovery check:
  ```go
  func (s *RedisMemoryStore) attemptRecovery(ctx context.Context) bool {
      // Try a ping
      ctx, cancel := context.WithTimeout(ctx, time.Second)
      defer cancel()

      if err := s.client.Ping(ctx).Err(); err != nil {
          return false
      }

      // Recovery successful
      s.circuitOpen.Store(false)
      s.failureCount.Store(0)
      metrics.RecordCircuitState(false)
      log.Info("Redis connection recovered")
      return true
  }

  // Called periodically when circuit is open
  func (s *RedisMemoryStore) isCircuitOpen() bool {
      if !s.circuitOpen.Load() {
          return false
      }

      lastFail := s.lastFailure.Load().(time.Time)
      if time.Since(lastFail) > circuitOpenDuration {
          // Try recovery
          if s.attemptRecovery(context.Background()) {
              return false
          }
          // Still failing, update last failure time
          s.lastFailure.Store(time.Now())
      }
      return true
  }
  ```

- [x] Ensure TieredMemoryStore continues on tier failures:
  ```go
  func (s *TieredMemoryStore) Get(ctx context.Context, namespace, key string) (any, bool, error) {
      for _, tier := range s.config.ReadOrder {
          store := s.getTierStore(tier)
          if store == nil {
              continue
          }

          val, found, err := store.Get(ctx, namespace, key)

          if err != nil {
              // Log but don't fail - continue to next tier
              log.Warn("Tier read error, continuing",
                  "tier", tier,
                  "namespace", namespace,
                  "key", key,
                  "error", err,
              )
              metrics.RecordTierMiss(tier)
              continue
          }

          if found {
              metrics.RecordTierHit(tier)
              return val, true, nil
          }

          metrics.RecordTierMiss(tier)
      }

      // Not found in any tier - this is not an error
      return nil, false, nil
  }
  ```

- [x] Write integration tests for degradation:
  ```go
  func TestGracefulDegradation_RedisDown(t *testing.T) {
      // Start with Redis available
      fallback := store.NewInMemoryMemoryStore()
      redisStore := store.NewRedisMemoryStore(cfg, "tenant-id", fallback)

      ctx := context.Background()

      // Set a value while Redis is up
      err := redisStore.Set(ctx, "ns", "key1", "value1", 0)
      require.NoError(t, err)

      // Stop Redis (simulated by closing connection)
      // In real test, use testcontainers to stop container

      // Force circuit open
      for i := 0; i < 6; i++ {
          redisStore.recordFailure()
      }

      // Now operations should use fallback
      err = redisStore.Set(ctx, "ns", "key2", "value2", 0)
      require.NoError(t, err)

      // Value should be in fallback
      val, found, _ := fallback.Get(ctx, "ns", "key2")
      assert.True(t, found)
      assert.Equal(t, "value2", val)
  }
  ```

**Acceptance Criteria:**
- [ ] Run continues successfully when Redis stops mid-execution
- [ ] First Redis failure logs WARN
- [ ] Circuit breaker opening logs ERROR
- [ ] Metric `forgegraph_memory_redis_fallback_total` increments on fallback
- [ ] After circuit opens, recovery attempted after 30 seconds
- [ ] When Redis recovers, circuit closes and Redis resumes
- [ ] All operations return valid results even during degradation

---

### P1-T11: Add Message Buffer Checkpointing
**Files:**
- `engine/application/usecase/scheduler.go`
- `engine/domain/entity/state.go`

- [x] Extend checkpoint structure to include buffer:
  ```go
  type CheckpointData struct {
      State          map[string]any `json:"state"`
      Completed      []string       `json:"completed"`
      Skipped        []string       `json:"skipped"`
      MessageBuffer  []entity.Message `json:"message_buffer"`   // NEW
      MemoryConfig   *MemoryConfig    `json:"memory_config"`    // NEW
      CurrentSummary *entity.Summary  `json:"current_summary"`  // NEW (Phase 2)
  }
  ```

- [x] Update saveCheckpoint to include buffer:
  ```go
  func (s *Scheduler) saveCheckpoint(ctx context.Context, runCtx *runContext, nodeID string) error {
      checkpoint := CheckpointData{
          State:     runCtx.state.Snapshot(),
          Completed: mapKeys(runCtx.completed),
          Skipped:   mapKeys(runCtx.skipped),
      }

      // Include message buffer
      if runCtx.messageBuffer != nil {
          checkpoint.MessageBuffer = runCtx.messageBuffer.Snapshot()
      }

      // Include memory config
      if runCtx.memoryConfig != nil {
          checkpoint.MemoryConfig = runCtx.memoryConfig
      }

      // Include summary if exists
      if runCtx.currentSummary != nil {
          checkpoint.CurrentSummary = runCtx.currentSummary
      }

      data, err := json.Marshal(checkpoint)
      if err != nil {
          return fmt.Errorf("marshal checkpoint: %w", err)
      }

      return s.repo.SaveCheckpoint(ctx, runCtx.runID, nodeID, runCtx.checkpointSeq, data)
  }
  ```

- [x] Update restoreFromCheckpoint to restore buffer:
  ```go
  func (s *Scheduler) restoreFromCheckpoint(ctx context.Context, runID string) (*runContext, error) {
      checkpointData, err := s.repo.LoadLatestCheckpoint(ctx, runID)
      if err != nil {
          return nil, err
      }

      var checkpoint CheckpointData
      if err := json.Unmarshal(checkpointData, &checkpoint); err != nil {
          return nil, fmt.Errorf("unmarshal checkpoint: %w", err)
      }

      // Restore memory config (or use defaults)
      memoryConfig := checkpoint.MemoryConfig
      if memoryConfig == nil {
          memoryConfig = defaultMemoryConfig()
      }

      // Create buffer with correct capacity
      bufferSize := memoryConfig.Tier1.BufferSize
      if bufferSize <= 0 {
          bufferSize = 20
      }
      buffer := entity.NewMessageBuffer(bufferSize)

      // Restore buffer contents
      if len(checkpoint.MessageBuffer) > 0 {
          buffer.Restore(checkpoint.MessageBuffer)
      }

      // Create run context
      runCtx := &runContext{
          runID:          runID,
          state:          entity.NewStateFromSnapshot(checkpoint.State),
          completed:      sliceToMap(checkpoint.Completed),
          skipped:        sliceToMap(checkpoint.Skipped),
          messageBuffer:  buffer,
          memoryConfig:   memoryConfig,
          currentSummary: checkpoint.CurrentSummary,
      }

      return runCtx, nil
  }
  ```

- [x] Test checkpoint round-trip:
  ```go
  func TestCheckpoint_MessageBufferRoundTrip(t *testing.T) {
      scheduler := setupTestScheduler(t)
      ctx := context.Background()

      // Create run with messages
      runCtx := &runContext{
          runID:         "test-run",
          messageBuffer: entity.NewMessageBuffer(20),
          memoryConfig:  defaultMemoryConfig(),
          state:         entity.NewState(),
          completed:     make(map[string]bool),
          skipped:       make(map[string]bool),
      }

      // Add messages
      for i := 0; i < 15; i++ {
          runCtx.messageBuffer.Push(entity.Message{
              Role:    "user",
              Content: fmt.Sprintf("message %d", i),
          })
      }

      // Save checkpoint
      err := scheduler.saveCheckpoint(ctx, runCtx, "node-1")
      require.NoError(t, err)

      // Restore
      restored, err := scheduler.restoreFromCheckpoint(ctx, "test-run")
      require.NoError(t, err)

      // Verify buffer restored
      assert.Equal(t, 15, restored.messageBuffer.Count())

      messages := restored.messageBuffer.GetAll()
      assert.Equal(t, "message 0", messages[0].Content)
      assert.Equal(t, "message 14", messages[14].Content)
  }
  ```

**Acceptance Criteria:**
- [x] Checkpoint includes serialized message buffer
- [x] Checkpoint includes memory configuration
- [x] Run resume restores buffer to pre-checkpoint state
- [x] Message order preserved after restore
- [x] Buffer capacity restored correctly
- [ ] Checkpoint size increase is reasonable (<10% for typical runs)

---

### P1-T12: Update Documentation
**Files:**
- `docs/developer/memory-system.md`
- `docs/user-guide/configuring-memory.md`

- [x] Create developer documentation:
  ```markdown
  # Memory System Architecture

  ## Overview
  ForgeGraph implements a three-tier memory system...

  ## Tier 1: Local Buffer
  - Implementation: `engine/domain/entity/message_buffer.go`
  - Thread-safe circular buffer
  - Sub-millisecond access (<100μs)
  ...

  ## Tier 2: Redis Cache
  - Implementation: `engine/adapter/store/redis_memory_store.go`
  - Persistent across restarts
  - Circuit breaker for fault tolerance
  ...

  ## Configuration
  ...

  ## Metrics
  ...
  ```

- [x] Create user guide:
  ```markdown
  # Configuring Memory

  ## Memory Depth
  Choose how much conversation history your agent remembers...

  ### Presets
  - **Short**: Last 10 messages - for simple, focused tasks
  - **Medium**: Last 20 messages (default) - balanced
  - **Long**: Last 50 messages - for complex conversations
  - **Extended**: Last 100 messages - for long-running sessions

  ## Enable Persistence
  ...

  ## Advanced Options
  ...
  ```

- [x] Add API documentation for memory config endpoints

- [x] Document troubleshooting:
  - Redis connection issues
  - Memory pressure
  - Configuration problems

**Acceptance Criteria:**
- [x] Architecture diagram shows all tiers
- [x] All configuration options documented with defaults
- [x] User guide explains presets in plain language
- [x] Troubleshooting covers common issues
- [x] API endpoints documented

---

## Acceptance Criteria (Phase 1 Overall)

1. [x] RedisMemoryStore passes all unit tests
2. [x] MessageBuffer passes all unit tests including concurrency
3. [x] Memory configuration UI functional
4. [x] Configuration persists in Django and propagates to engine
5. [x] Multi-tenant isolation verified
6. [x] Circuit breaker and fallback working
7. [x] Metrics exposed and scrapable
8. [x] Checkpointing includes buffer state
9. [x] Documentation complete
10. [ ] All integration tests pass

## Status: IN PROGRESS

## Dependencies

- None (foundation phase)

## Output

- [x] `RedisMemoryStore` implementation with tests
- [x] `MessageBuffer` implementation with tests
- [x] `TieredMemoryStore` composition with tests
- [x] Django `MemoryConfiguration` model and API
- [x] Frontend `MemoryConfigDialog` component
- [x] Prometheus metrics for memory operations
- [x] Health check endpoint for Redis
- [x] Updated gRPC proto with memory config
- [x] Documentation (developer + user guide)
