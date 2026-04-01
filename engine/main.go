package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/adapter/gateway"
	"github.com/forgegraph/engine/adapter/repository"
	"github.com/forgegraph/engine/adapter/store"
	"github.com/forgegraph/engine/adapter/summarizer"
	"github.com/forgegraph/engine/adapter/tool"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/application/usecase"
	"github.com/forgegraph/engine/infrastructure/logger"

	_ "github.com/lib/pq"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/otel"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/reflection"
	"google.golang.org/grpc/status"
)

// Config holds engine configuration
type Config struct {
	GRPCPort                          string
	DatabaseURL                       string
	MaxWorkers                        int
	DefaultTimeout                    int
	CacheTTLSeconds                   int
	CheckpointMode                    string
	CheckpointBatchSize               int
	CheckpointIntervalMs              int
	ToolManifestDir                   string
	RedisAddr                         string
	RedisPassword                     string
	RedisDB                           int
	RedisPoolSize                     int
	RedisDialTimeoutMs                int
	RedisReadTimeoutMs                int
	RedisWriteTimeoutMs               int
	TenantID                          string
	MetricsPort                       string
	MemoryGRPCHost                    string
	MemoryGRPCPort                    string
	CallbackSecret                    string
	CallbackURL                       string
	ControlPlaneURL                   string
	EventMaxRetries                   int
	EventRetryDelayMs                 int
	EventBufferSize                   int
	EventSpoolPath                    string
	MarketplaceManifestRefreshSeconds int
	RuntimeMode                       string
}

// LoadConfig loads configuration from environment variables
func LoadConfig() *Config {
	cfg := &Config{
		GRPCPort:                          getEnv("GRPC_PORT", "50051"),
		DatabaseURL:                       getEnv("DATABASE_URL", ""),
		MaxWorkers:                        getEnvInt("MAX_WORKERS", 10),
		DefaultTimeout:                    getEnvInt("DEFAULT_TIMEOUT_MS", 30000),
		CacheTTLSeconds:                   getEnvInt("CACHE_DEFAULT_TTL_SECONDS", 3600),
		CheckpointMode:                    strings.ToLower(getEnv("CHECKPOINT_MODE", "node")),
		CheckpointBatchSize:               getEnvInt("CHECKPOINT_BATCH_SIZE", 10),
		CheckpointIntervalMs:              getEnvInt("CHECKPOINT_INTERVAL_MS", 0),
		ToolManifestDir:                   getEnv("TOOL_MANIFEST_DIR", ""),
		RedisAddr:                         getEnv("REDIS_ADDR", ""),
		RedisPassword:                     getEnv("REDIS_PASSWORD", ""),
		RedisDB:                           getEnvInt("REDIS_DB", 0),
		RedisPoolSize:                     getEnvInt("REDIS_POOL_SIZE", 0),
		RedisDialTimeoutMs:                getEnvInt("REDIS_DIAL_TIMEOUT_MS", 0),
		RedisReadTimeoutMs:                getEnvInt("REDIS_READ_TIMEOUT_MS", 0),
		RedisWriteTimeoutMs:               getEnvInt("REDIS_WRITE_TIMEOUT_MS", 0),
		TenantID:                          getEnv("TENANT_ID", "00000000-0000-0000-0000-000000000000"),
		MetricsPort:                       getEnv("METRICS_PORT", "9090"),
		MemoryGRPCHost:                    getEnv("MEMORY_GRPC_HOST", ""),
		MemoryGRPCPort:                    getEnv("MEMORY_GRPC_PORT", ""),
		CallbackSecret:                    getEnv("ENGINE_CALLBACK_SECRET", ""),
		CallbackURL:                       getEnv("ENGINE_CALLBACK_URL", ""),
		ControlPlaneURL:                   getEnv("CONTROL_PLANE_URL", ""),
		EventMaxRetries:                   getEnvInt("ENGINE_EVENT_MAX_RETRIES", 3),
		EventRetryDelayMs:                 getEnvInt("ENGINE_EVENT_RETRY_DELAY_MS", 100),
		EventBufferSize:                   getEnvInt("ENGINE_EVENT_BUFFER_SIZE", 100),
		EventSpoolPath:                    getEnv("ENGINE_EVENT_SPOOL_PATH", ""),
		MarketplaceManifestRefreshSeconds: getEnvInt("MARKETPLACE_MANIFEST_REFRESH_SECONDS", 0),
		RuntimeMode:                       tool.NormalizeRuntimeMode(getEnv("FORGEGRAPH_RUNTIME_MODE", tool.RuntimeModeCloud)),
	}
	return cfg
}

func refreshMarketplaceManifests(
	ctx context.Context,
	log *logger.Logger,
	client *gateway.MarketplaceManifestClient,
	registry *tool.Registry,
	tenantID string,
	previousChecksum string,
) string {
	if client == nil || registry == nil || tenantID == "" {
		return previousChecksum
	}

	payload, unchanged, err := client.Fetch(ctx, tenantID, previousChecksum)
	if err != nil {
		log.Warn("marketplace_manifest_fetch_failed", "tenant_id", tenantID, "error", err.Error())
		return previousChecksum
	}
	if unchanged || payload == nil {
		return previousChecksum
	}

	if err := registry.LoadDefinitions(payload.Tools); err != nil {
		log.Warn("marketplace_manifest_load_failed", "tenant_id", tenantID, "checksum", payload.Checksum, "error", err.Error())
		return previousChecksum
	}

	log.Info(
		"marketplace_manifest_loaded",
		"tenant_id", tenantID,
		"checksum", payload.Checksum,
		"tool_count", len(payload.Tools),
	)
	return payload.Checksum
}

func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

func getEnvInt(key string, defaultVal int) int {
	if val := os.Getenv(key); val != "" {
		if i, err := strconv.Atoi(val); err == nil {
			return i
		}
	}
	return defaultVal
}

// EngineServer implements the Engine gRPC service
type EngineServer struct {
	UnimplementedEngineServiceServer
	scheduler  *usecase.Scheduler
	repository port.RunRepository
	logger     *logger.Logger
}

// NewEngineServer creates a new engine server with all dependencies
func NewEngineServer(scheduler *usecase.Scheduler, repository port.RunRepository, log *logger.Logger) *EngineServer {
	return &EngineServer{
		scheduler:  scheduler,
		repository: repository,
		logger:     log.WithComponent("grpc"),
	}
}

// Ping implements the Ping RPC method for health checking
func (s *EngineServer) Ping(ctx context.Context, req *PingRequest) (*PingResponse, error) {
	s.logger.Debug("ping_request", "message", req.Message)
	return &PingResponse{
		Message: "pong",
	}, nil
}

// StartRun begins executing a workflow graph
func (s *EngineServer) StartRun(ctx context.Context, req *StartRunRequest) (*StartRunResponse, error) {
	s.logger.Info("start_run_request", "run_id", req.RunId)

	// Validate required fields
	if req.RunId == "" {
		return &StartRunResponse{
			Accepted: false,
			Error:    "run_id is required",
		}, nil
	}
	if req.GraphJson == "" {
		return &StartRunResponse{
			Accepted: false,
			Error:    "graph_json is required",
		}, nil
	}

	// Start the run
	err := s.scheduler.StartRun(
		ctx,
		req.RunId,
		req.GraphJson,
		req.InputJson,
		req.CallbackUrl,
		req.MemoryConfigJson,
		req.TenantId,
		req.SessionId,
		req.Traceparent,
		req.Tracestate,
	)
	if err != nil {
		s.logger.Error("start_run_failed", "run_id", req.RunId, "error", err.Error())
		return &StartRunResponse{
			Accepted: false,
			Error:    err.Error(),
		}, nil
	}

	s.logger.Info("start_run_accepted", "run_id", req.RunId)
	return &StartRunResponse{
		Accepted: true,
	}, nil
}

// GetRunStatus returns the current status of a run
func (s *EngineServer) GetRunStatus(ctx context.Context, req *GetRunStatusRequest) (*GetRunStatusResponse, error) {
	s.logger.Debug("get_run_status_request", "run_id", req.RunId)

	if req.RunId == "" {
		return nil, status.Errorf(codes.InvalidArgument, "run_id is required")
	}

	// Try to get status from scheduler (active runs)
	runStatus, currentNodeId, err := s.scheduler.GetRunStatus(req.RunId)
	if err == nil {
		return &GetRunStatusResponse{
			Status:        runStatus,
			CurrentNodeId: currentNodeId,
		}, nil
	}

	// If not found in scheduler, check repository for completed runs
	run, err := s.repository.GetRun(ctx, req.RunId)
	if err != nil {
		return nil, status.Errorf(codes.NotFound, "run not found: %v", err)
	}

	return &GetRunStatusResponse{
		Status: run.Status,
		Error:  run.ErrorMessage,
	}, nil
}

// CancelRun cancels an active run
func (s *EngineServer) CancelRun(ctx context.Context, req *CancelRunRequest) (*CancelRunResponse, error) {
	s.logger.Info("cancel_run_request", "run_id", req.RunId)

	if req.RunId == "" {
		return &CancelRunResponse{
			Success: false,
			Error:   "run_id is required",
		}, nil
	}

	err := s.scheduler.CancelRun(req.RunId)
	if err != nil {
		s.logger.Error("cancel_run_failed", "run_id", req.RunId, "error", err.Error())
		return &CancelRunResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	s.logger.Info("cancel_run_success", "run_id", req.RunId)
	return &CancelRunResponse{
		Success: true,
	}, nil
}

// ResumeRun resumes a paused run (e.g., after human gate approval)
func (s *EngineServer) ResumeRun(ctx context.Context, req *ResumeRunRequest) (*ResumeRunResponse, error) {
	s.logger.Info("resume_run_request", "run_id", req.RunId, "node_id", req.NodeId)

	// Validate request
	if req.RunId == "" {
		return &ResumeRunResponse{
			Accepted: false,
			Error:    "run_id is required",
		}, nil
	}
	if req.NodeId == "" {
		return &ResumeRunResponse{
			Accepted: false,
			Error:    "node_id is required",
		}, nil
	}

	// Resume the run via scheduler
	err := s.scheduler.ResumeRun(
		ctx,
		req.RunId,
		req.NodeId,
		req.InputJson,
		req.Traceparent,
		req.Tracestate,
	)
	if err != nil {
		s.logger.Error("resume_run_failed", "run_id", req.RunId, "error", err.Error())
		return &ResumeRunResponse{
			Accepted: false,
			Error:    err.Error(),
		}, nil
	}

	s.logger.Info("resume_run_accepted", "run_id", req.RunId, "node_id", req.NodeId)
	return &ResumeRunResponse{
		Accepted: true,
	}, nil
}

func main() {
	// Initialize structured logger
	logCfg := logger.ConfigFromEnv()
	log := logger.New(logCfg)
	otel.SetTracerProvider(sdktrace.NewTracerProvider())

	log.Info("engine_starting", "version", "0.1.0")

	// Load configuration
	cfg := LoadConfig()
	log.Info("config_loaded",
		"grpc_port", cfg.GRPCPort,
		"max_workers", cfg.MaxWorkers,
		"default_timeout_ms", cfg.DefaultTimeout,
		"cache_default_ttl_seconds", cfg.CacheTTLSeconds,
		"checkpoint_mode", cfg.CheckpointMode,
		"checkpoint_batch_size", cfg.CheckpointBatchSize,
		"checkpoint_interval_ms", cfg.CheckpointIntervalMs,
		"tool_manifest_dir", cfg.ToolManifestDir,
		"marketplace_manifest_refresh_seconds", cfg.MarketplaceManifestRefreshSeconds,
		"runtime_mode", cfg.RuntimeMode,
	)

	// Initialize repository and memory store
	var repo port.RunRepository
	var memoryStore port.MemoryStore
	var redisStore *store.RedisMemoryStore
	var redisHealth *store.RedisHealthChecker
	var db *sql.DB
	var err error
	if cfg.DatabaseURL != "" {
		// Connect to PostgreSQL
		db, err = sql.Open("postgres", cfg.DatabaseURL)
		if err != nil {
			log.Error("database_connection_failed", "error", err.Error())
			os.Exit(1)
		}
		defer db.Close()

		// Test connection
		if err := db.Ping(); err != nil {
			log.Error("database_ping_failed", "error", err.Error())
			os.Exit(1)
		}
		log.Info("database_connected", "driver", "postgres")

		repo = repository.NewPostgresRunRepository(db)
		memoryStore = store.NewPostgresMemoryStore(db)
	} else {
		log.Warn("database_url_not_set", "fallback", "in-memory")
		repo = repository.NewMemoryRunRepository()
		memoryStore = store.NewInMemoryMemoryStore()
	}

	// Optional Redis-backed memory store
	if cfg.RedisAddr != "" {
		redisCfg := store.RedisConfig{
			Addr:         cfg.RedisAddr,
			Password:     cfg.RedisPassword,
			DB:           cfg.RedisDB,
			PoolSize:     cfg.RedisPoolSize,
			DialTimeout:  time.Duration(cfg.RedisDialTimeoutMs) * time.Millisecond,
			ReadTimeout:  time.Duration(cfg.RedisReadTimeoutMs) * time.Millisecond,
			WriteTimeout: time.Duration(cfg.RedisWriteTimeoutMs) * time.Millisecond,
		}
		redisStore, err = store.NewRedisMemoryStore(redisCfg, cfg.TenantID, memoryStore)
		if err != nil {
			log.Error("redis_store_init_failed", "error", err.Error())
		} else {
			log.Info("redis_store_initialized", "addr", cfg.RedisAddr)
			memoryStore = redisStore
			redisHealth = store.NewRedisHealthChecker(redisStore)
		}
	}

	// Initialize event emitter
	var emitter port.EventEmitter
	if cfg.CallbackURL != "" {
		emitterCfg := gateway.DefaultHTTPEventEmitterConfig(cfg.CallbackURL)
		emitterCfg.SignatureSecret = cfg.CallbackSecret
		emitterCfg.MaxRetries = cfg.EventMaxRetries
		emitterCfg.RetryDelay = time.Duration(cfg.EventRetryDelayMs) * time.Millisecond
		emitterCfg.BufferSize = cfg.EventBufferSize
		emitterCfg.SpoolPath = cfg.EventSpoolPath
		emitter = gateway.NewHTTPEventEmitter(emitterCfg)
	} else {
		emitter = port.NewNoOpEventEmitter()
	}

	// Initialize node executors
	registry := port.NewExecutorRegistry()
	toolRegistry := tool.NewRegistryWithRuntimeMode(cfg.RuntimeMode)
	if err := toolRegistry.LoadManifests(cfg.ToolManifestDir); err != nil {
		log.Warn("tool_manifest_load_failed", "error", err.Error())
	}

	var manifestClient *gateway.MarketplaceManifestClient

	// Shared credential resolver for executors that support credential_id.
	var resolver gateway.CredentialResolver
	if cfg.ControlPlaneURL != "" && cfg.CallbackSecret != "" {
		resolver = gateway.NewBackendCredentialResolver(cfg.ControlPlaneURL, cfg.CallbackSecret)
		manifestClient = gateway.NewMarketplaceManifestClient(cfg.ControlPlaneURL, cfg.CallbackSecret)
	}
	lastManifestChecksum := ""
	if manifestClient != nil && cfg.TenantID != "" {
		lastManifestChecksum = refreshMarketplaceManifests(
			context.Background(),
			log.WithComponent("marketplace"),
			manifestClient,
			toolRegistry,
			cfg.TenantID,
			lastManifestChecksum,
		)
		if cfg.MarketplaceManifestRefreshSeconds > 0 {
			go func() {
				ticker := time.NewTicker(time.Duration(cfg.MarketplaceManifestRefreshSeconds) * time.Second)
				defer ticker.Stop()
				manifestLog := log.WithComponent("marketplace")
				for range ticker.C {
					lastManifestChecksum = refreshMarketplaceManifests(
						context.Background(),
						manifestLog,
						manifestClient,
						toolRegistry,
						cfg.TenantID,
						lastManifestChecksum,
					)
				}
			}()
		}
	}

	registry.RegisterAll(
		executor.NewOutputExecutor(),
		executor.NewTransformExecutor(),
		executor.NewHTTPExecutorWithResolver(resolver),
		executor.NewBranchExecutor(),
		executor.NewMergeExecutor(),
		executor.NewHumanGateExecutor(),
		executor.NewMemoryExecutor(memoryStore),
		executor.NewObservationSaveExecutor(nil),
		executor.NewObservationSearchExecutor(nil),
		executor.NewObservationContextExecutor(nil),
		executor.NewObservationTimelineExecutor(nil),
		executor.NewToolExecutorWithResolverAndRuntimeMode(toolRegistry, resolver, cfg.RuntimeMode),
		executor.NewSubgraphExecutor(registry),
	)

	// Initialize LLM client for Prompt and Agent nodes (multi-provider)
	fallbackKey := os.Getenv("OPENAI_API_KEY")
	llmClient := gateway.NewMultiProviderClient(resolver, fallbackKey)
	registry.Register(executor.NewAgentExecutorWithRuntimeMode(llmClient, toolRegistry, resolver, cfg.RuntimeMode))
	registry.Register(executor.NewPromptExecutor(llmClient))
	if fallbackKey == "" && resolver == nil {
		log.Warn("llm_client_not_configured", "note", "Prompt and agent nodes require credentials or OPENAI_API_KEY")
	} else {
		log.Info("llm_client_initialized", "note", "Prompt and agent nodes enabled")
	}

	// Initialize scheduler
	schedulerConfig := usecase.SchedulerConfig{
		MaxWorkers:             cfg.MaxWorkers,
		DefaultTimeoutMs:       cfg.DefaultTimeout,
		CheckpointMode:         usecase.CheckpointMode(cfg.CheckpointMode),
		CheckpointBatchSize:    cfg.CheckpointBatchSize,
		CheckpointIntervalMs:   cfg.CheckpointIntervalMs,
		CacheDefaultTTLSeconds: cfg.CacheTTLSeconds,
	}
	scheduler := usecase.NewScheduler(schedulerConfig, registry, repo, emitter, memoryStore)
	log.Info("scheduler_initialized")

	if cfg.MemoryGRPCHost != "" && cfg.MemoryGRPCPort != "" {
		retriever, err := NewGrpcMemoryRetriever(cfg.MemoryGRPCHost, cfg.MemoryGRPCPort)
		if err != nil {
			log.Warn("memory_retriever_init_failed", "error", err.Error())
		} else {
			scheduler.SetMemoryRetriever(retriever)
			scheduler.SetObservationClient(retriever)
			registry.RegisterAll(
				executor.NewObservationSaveExecutor(retriever),
				executor.NewObservationSearchExecutor(retriever),
				executor.NewObservationContextExecutor(retriever),
				executor.NewObservationTimelineExecutor(retriever),
			)
			log.Info("memory_retriever_initialized", "host", cfg.MemoryGRPCHost, "port", cfg.MemoryGRPCPort)
		}
	}

	log.Info(
		"executors_registered",
		"types",
		[]string{
			"agent",
			"output",
			"transform",
			"http",
			"branch",
			"merge",
			"human_gate",
			"memory",
			"observation_save",
			"observation_search",
			"observation_context",
			"observation_timeline",
			"tool",
			"subgraph",
			"prompt",
		},
	)

	if llmClient != nil {
		var summaryStore port.SummaryStore
		if redisStore != nil {
			summaryStore = redisStore
		}
		var costTracker *summarizer.CostTracker
		if db != nil {
			costTracker = summarizer.NewCostTracker(db)
		}
		summaryAdapter := summarizer.NewLLMSummarizerWithTracker(llmClient, "", costTracker)
		summaryWorker := usecase.NewSummarizationWorker(summaryAdapter, summaryStore, 2, 100)
		summaryWorker.Start(context.Background())
		scheduler.SetSummarizationWorker(summaryWorker)
		log.Info("summarization_worker_initialized")
	}

	// Metrics & health server
	if cfg.MetricsPort != "" {
		go func() {
			mux := http.NewServeMux()
			mux.Handle("/metrics", promhttp.Handler())
			mux.HandleFunc("/health/redis", func(w http.ResponseWriter, r *http.Request) {
				status := store.HealthStatus{Healthy: false, Error: "redis not configured"}
				if redisHealth != nil {
					status = redisHealth.Check(r.Context())
				}
				payload, _ := json.Marshal(status)
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusOK)
				_, _ = w.Write(payload)
			})

			log.Info("metrics_server_listening", "port", cfg.MetricsPort)
			if err := http.ListenAndServe(":"+cfg.MetricsPort, mux); err != nil {
				log.Error("metrics_server_failed", "error", err.Error())
			}
		}()
	}

	// Create gRPC server
	listener, err := net.Listen("tcp", fmt.Sprintf(":%s", cfg.GRPCPort))
	if err != nil {
		log.Error("listen_failed", "port", cfg.GRPCPort, "error", err.Error())
		os.Exit(1)
	}

	grpcServer := grpc.NewServer()
	engineServer := NewEngineServer(scheduler, repo, log)
	RegisterEngineServiceServer(grpcServer, engineServer)

	// Enable server reflection for debugging
	reflection.Register(grpcServer)

	log.Info("grpc_server_listening", "port", cfg.GRPCPort)

	if err := grpcServer.Serve(listener); err != nil {
		log.Error("grpc_serve_failed", "error", err.Error())
		os.Exit(1)
	}
}
