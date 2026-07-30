package main

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync/atomic"
	"syscall"
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

	"github.com/prometheus/client_golang/prometheus/promhttp"
	redis "github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/reflection"
	"google.golang.org/grpc/status"
)

// Config holds engine configuration
type Config struct {
	GRPCPort                             string
	MaxWorkers                           int
	DefaultTimeout                       int
	CacheTTLSeconds                      int
	CheckpointMode                       string
	CheckpointBatchSize                  int
	CheckpointIntervalMs                 int
	ToolManifestDir                      string
	RedisAddr                            string
	RedisUsername                        string
	RedisPassword                        string
	RedisDB                              int
	RedisPoolSize                        int
	RedisDialTimeoutMs                   int
	RedisReadTimeoutMs                   int
	RedisWriteTimeoutMs                  int
	RedisSentinelAddrs                   string
	RedisSentinelMasterName              string
	RedisSentinelUsername                string
	RedisSentinelPassword                string
	TenantID                             string
	MetricsPort                          string
	MemoryGRPCHost                       string
	MemoryGRPCPort                       string
	GRPCTLSCertFile                      string
	GRPCTLSKeyFile                       string
	GRPCTLSClientCAFile                  string
	GRPCTLSRequireClientCert             bool
	CallbackSecret                       string
	CallbackURL                          string
	ControlPlaneURL                      string
	EngineHost                           string
	EventMaxRetries                      int
	EventRetryDelayMs                    int
	EventBufferSize                      int
	EventWorkerCount                     int
	EventSpoolPath                       string
	EventVerbosity                       string
	EngineInstanceID                     string
	EngineAllowInMemoryMode              bool
	MarketplaceManifestRefreshSeconds    int
	RuntimeMode                          string
	LegacyToolAdapterMode                string
	RunStateMode                         string
	RuntimeWriteMode                     string
	RuntimeIntentStream                  string
	RuntimeIntentPublishInitialBackoffMs int
	RuntimeIntentPublishMaxBackoffMs     int
	RuntimeIntentPublishMaxElapsedTimeMs int
	RuntimeIntentStreamMaxLen            int64
	RuntimeIntentOutcomeWaitTimeoutMs    int
	RuntimeIntentOutcomePollIntervalMs   int
}

type runtimeIntentRedisClient interface {
	gateway.RuntimeIntentStreamClient
	Ping(context.Context) *redis.StatusCmd
	Close() error
}

type redisStatusPinger struct {
	client interface {
		Ping(context.Context) *redis.StatusCmd
	}
}

func (p redisStatusPinger) Ping(ctx context.Context) error {
	if p.client == nil {
		return fmt.Errorf("runtime intent redis client is not configured")
	}
	return p.client.Ping(ctx).Err()
}

type grpcLifecycleServer interface {
	GracefulStop()
	Stop()
}

type eventEmitterCloser interface {
	Close(context.Context) error
}

type stoppableWorker interface {
	Stop()
}

type shutdownScheduler interface {
	Shutdown(context.Context) error
}

type closeableResource interface {
	Close() error
}

type engineRuntimeResources struct {
	cancel              context.CancelFunc
	grpcServer          grpcLifecycleServer
	metricsServer       *http.Server
	scheduler           shutdownScheduler
	eventEmitter        eventEmitterCloser
	summarizationWorker stoppableWorker
	memoryRetriever     closeableResource
	redisClient         closeableResource
}

const (
	runStateModeLegacyDualWrite  = "dual-write"
	runStateModeControlPlaneHTTP = "control-plane-http"
	runStateModeInMemory         = "in-memory"
	defaultRunStateMode          = runStateModeControlPlaneHTTP
)

// LoadConfig loads configuration from environment variables
func LoadConfig() *Config {
	cfg := &Config{
		GRPCPort:                             getEnv("GRPC_PORT", "50051"),
		MaxWorkers:                           getEnvInt("MAX_WORKERS", 10),
		DefaultTimeout:                       getEnvInt("DEFAULT_TIMEOUT_MS", 30000),
		CacheTTLSeconds:                      getEnvInt("CACHE_DEFAULT_TTL_SECONDS", 3600),
		CheckpointMode:                       strings.ToLower(getEnv("CHECKPOINT_MODE", "node")),
		CheckpointBatchSize:                  getEnvInt("CHECKPOINT_BATCH_SIZE", 10),
		CheckpointIntervalMs:                 getEnvInt("CHECKPOINT_INTERVAL_MS", 0),
		ToolManifestDir:                      getEnv("TOOL_MANIFEST_DIR", ""),
		RedisAddr:                            getEnv("REDIS_ADDR", ""),
		RedisUsername:                        getEnv("REDIS_USERNAME", ""),
		RedisPassword:                        getEnv("REDIS_PASSWORD", ""),
		RedisDB:                              getEnvInt("REDIS_DB", 0),
		RedisPoolSize:                        getEnvInt("REDIS_POOL_SIZE", 0),
		RedisDialTimeoutMs:                   getEnvInt("REDIS_DIAL_TIMEOUT_MS", 0),
		RedisReadTimeoutMs:                   getEnvInt("REDIS_READ_TIMEOUT_MS", 0),
		RedisWriteTimeoutMs:                  getEnvInt("REDIS_WRITE_TIMEOUT_MS", 0),
		RedisSentinelAddrs:                   getEnv("REDIS_SENTINEL_ADDRS", ""),
		RedisSentinelMasterName:              getEnv("REDIS_SENTINEL_MASTER_NAME", ""),
		RedisSentinelUsername:                getEnv("REDIS_SENTINEL_USERNAME", ""),
		RedisSentinelPassword:                getEnv("REDIS_SENTINEL_PASSWORD", ""),
		TenantID:                             getEnv("TENANT_ID", "00000000-0000-0000-0000-000000000000"),
		MetricsPort:                          getEnv("METRICS_PORT", "9090"),
		MemoryGRPCHost:                       getEnv("MEMORY_GRPC_HOST", ""),
		MemoryGRPCPort:                       getEnv("MEMORY_GRPC_PORT", ""),
		GRPCTLSCertFile:                      getEnv("GRPC_TLS_CERT_FILE", ""),
		GRPCTLSKeyFile:                       getEnv("GRPC_TLS_KEY_FILE", ""),
		GRPCTLSClientCAFile:                  getEnv("GRPC_TLS_CLIENT_CA_FILE", ""),
		GRPCTLSRequireClientCert:             strings.EqualFold(getEnv("GRPC_TLS_REQUIRE_CLIENT_CERT", "false"), "true"),
		CallbackSecret:                       getEnv("ENGINE_CALLBACK_SECRET", ""),
		CallbackURL:                          getEnv("ENGINE_CALLBACK_URL", ""),
		ControlPlaneURL:                      getEnv("CONTROL_PLANE_URL", ""),
		EngineHost:                           strings.TrimSpace(getEnv("ENGINE_HOST", "localhost")),
		EventMaxRetries:                      getEnvInt("ENGINE_EVENT_MAX_RETRIES", 3),
		EventRetryDelayMs:                    getEnvInt("ENGINE_EVENT_RETRY_DELAY_MS", 100),
		EventBufferSize:                      getEnvInt("ENGINE_EVENT_BUFFER_SIZE", 100),
		EventWorkerCount:                     getEnvInt("ENGINE_EVENT_WORKERS", 1),
		EventSpoolPath:                       getEnv("ENGINE_EVENT_SPOOL_PATH", ""),
		EventVerbosity:                       normalizeEventVerbosity(getEnv("ENGINE_EVENT_VERBOSITY", "default")),
		EngineInstanceID:                     strings.TrimSpace(getEnv("ENGINE_INSTANCE_ID", "")),
		EngineAllowInMemoryMode:              strings.EqualFold(getEnv("ENGINE_ALLOW_IN_MEMORY_MODE", "false"), "true"),
		MarketplaceManifestRefreshSeconds:    getEnvInt("MARKETPLACE_MANIFEST_REFRESH_SECONDS", 0),
		RuntimeMode:                          tool.NormalizeRuntimeMode(getEnv("FORGEGRAPH_RUNTIME_MODE", tool.RuntimeModeCloud)),
		LegacyToolAdapterMode:                executor.NormalizeLegacyNodeAdapterMode(getEnv("ENGINE_RUNTIME_MODE", executor.LegacyNodeAdapterModeLegacy)),
		RunStateMode:                         normalizeRunStateMode(getEnv("ENGINE_RUN_STATE_MODE", defaultRunStateMode)),
		RuntimeWriteMode:                     getEnv("ENGINE_RUNTIME_WRITE_MODE", usecase.RuntimeWriteModePauseIntents),
		RuntimeIntentStream:                  getEnv("ENGINE_RUNTIME_INTENT_STREAM", gateway.DefaultRuntimeIntentStream),
		RuntimeIntentPublishInitialBackoffMs: getEnvInt("ENGINE_RUNTIME_INTENT_RETRY_INITIAL_BACKOFF_MS", 100),
		RuntimeIntentPublishMaxBackoffMs:     getEnvInt("ENGINE_RUNTIME_INTENT_RETRY_MAX_BACKOFF_MS", 2000),
		RuntimeIntentPublishMaxElapsedTimeMs: getEnvInt("ENGINE_RUNTIME_INTENT_RETRY_MAX_ELAPSED_MS", 20000),
		RuntimeIntentStreamMaxLen:            int64(getEnvInt("ENGINE_RUNTIME_INTENT_STREAM_MAXLEN", 0)),
		RuntimeIntentOutcomeWaitTimeoutMs:    getEnvInt("ENGINE_RUNTIME_INTENT_OUTCOME_TIMEOUT_MS", 10000),
		RuntimeIntentOutcomePollIntervalMs:   getEnvInt("ENGINE_RUNTIME_INTENT_OUTCOME_POLL_MS", 100),
	}
	return cfg
}

func normalizeRunStateMode(raw string) string {
	normalized := strings.ToLower(strings.TrimSpace(raw))
	switch normalized {
	case "":
		return defaultRunStateMode
	case "dual-write":
		return runStateModeLegacyDualWrite
	case "control-plane-http", "control_plane_http", "control-plane", "control_plane", "http":
		return runStateModeControlPlaneHTTP
	case "in-memory", "in_memory", "memory":
		return runStateModeInMemory
	default:
		return normalized
	}
}

func normalizeEventVerbosity(raw string) string {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "", "default":
		return "default"
	case "minimal":
		return "minimal"
	case "verbose":
		return "verbose"
	default:
		return "default"
	}
}

func hasControlPlaneRepositoryConfig(cfg *Config) bool {
	if cfg == nil {
		return false
	}
	return strings.TrimSpace(cfg.ControlPlaneURL) != "" && strings.TrimSpace(cfg.CallbackSecret) != ""
}

func selectRunRepositoryDriver(cfg *Config) (string, error) {
	mode := normalizeRunStateMode("")
	if cfg != nil {
		mode = cfg.RunStateMode
	}

	switch mode {
	case runStateModeLegacyDualWrite:
		return "", fmt.Errorf(
			"ENGINE_RUN_STATE_MODE=%s is no longer supported; use %s",
			runStateModeLegacyDualWrite,
			runStateModeControlPlaneHTTP,
		)
	case runStateModeControlPlaneHTTP:
		if hasControlPlaneRepositoryConfig(cfg) {
			return runStateModeControlPlaneHTTP, nil
		}
		return "", fmt.Errorf("ENGINE_RUN_STATE_MODE=%s requires CONTROL_PLANE_URL and ENGINE_CALLBACK_SECRET", runStateModeControlPlaneHTTP)
	case runStateModeInMemory:
		if cfg == nil || !cfg.EngineAllowInMemoryMode {
			return "", fmt.Errorf("ENGINE_RUN_STATE_MODE=%s requires ENGINE_ALLOW_IN_MEMORY_MODE=true", runStateModeInMemory)
		}
		return runStateModeInMemory, nil
	default:
		return "", fmt.Errorf("unsupported ENGINE_RUN_STATE_MODE: %s", mode)
	}
}

func resolveEngineInstanceID(cfg *Config) string {
	if cfg != nil && strings.TrimSpace(cfg.EngineInstanceID) != "" {
		return strings.TrimSpace(cfg.EngineInstanceID)
	}
	if cfg != nil && strings.TrimSpace(cfg.EngineHost) != "" {
		port := "50051"
		if strings.TrimSpace(cfg.GRPCPort) != "" {
			port = strings.TrimSpace(cfg.GRPCPort)
		}
		return fmt.Sprintf("%s:%s", strings.TrimSpace(cfg.EngineHost), port)
	}
	hostname, err := os.Hostname()
	if err != nil || strings.TrimSpace(hostname) == "" {
		hostname = "engine"
	}
	port := "50051"
	if cfg != nil && strings.TrimSpace(cfg.GRPCPort) != "" {
		port = strings.TrimSpace(cfg.GRPCPort)
	}
	return fmt.Sprintf("%s:%s", hostname, port)
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

	if err := registry.ReplaceDefinitions(payload.Tools); err != nil {
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

func hasRuntimeIntentRedisConfig(cfg *Config) bool {
	if cfg == nil {
		return false
	}
	if strings.TrimSpace(cfg.RedisSentinelMasterName) != "" && len(parseCSVStrings(cfg.RedisSentinelAddrs)) > 0 {
		return true
	}
	return strings.TrimSpace(cfg.RedisAddr) != ""
}

func runtimeIntentRedisMode(cfg *Config) string {
	if cfg == nil {
		return "none"
	}
	if strings.TrimSpace(cfg.RedisSentinelMasterName) != "" && len(parseCSVStrings(cfg.RedisSentinelAddrs)) > 0 {
		return "sentinel"
	}
	if strings.TrimSpace(cfg.RedisAddr) != "" {
		return "direct"
	}
	return "none"
}

func parseCSVStrings(raw string) []string {
	parts := strings.FieldsFunc(raw, func(r rune) bool {
		return r == ',' || r == ';'
	})
	values := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		values = append(values, part)
	}
	return values
}

func buildRuntimeIntentRedisClient(cfg *Config) (runtimeIntentRedisClient, error) {
	if cfg == nil {
		return nil, fmt.Errorf("runtime intent redis config is required")
	}
	if strings.TrimSpace(cfg.RedisSentinelMasterName) != "" && len(parseCSVStrings(cfg.RedisSentinelAddrs)) > 0 {
		return redis.NewFailoverClient(&redis.FailoverOptions{
			MasterName:       strings.TrimSpace(cfg.RedisSentinelMasterName),
			SentinelAddrs:    parseCSVStrings(cfg.RedisSentinelAddrs),
			SentinelUsername: strings.TrimSpace(cfg.RedisSentinelUsername),
			SentinelPassword: strings.TrimSpace(cfg.RedisSentinelPassword),
			Username:         strings.TrimSpace(cfg.RedisUsername),
			Password:         strings.TrimSpace(cfg.RedisPassword),
			DB:               cfg.RedisDB,
			PoolSize:         cfg.RedisPoolSize,
			DialTimeout:      time.Duration(cfg.RedisDialTimeoutMs) * time.Millisecond,
			ReadTimeout:      time.Duration(cfg.RedisReadTimeoutMs) * time.Millisecond,
			WriteTimeout:     time.Duration(cfg.RedisWriteTimeoutMs) * time.Millisecond,
		}), nil
	}
	if strings.TrimSpace(cfg.RedisAddr) == "" {
		return nil, fmt.Errorf("runtime intent redis requires REDIS_ADDR or Redis Sentinel configuration")
	}
	return redis.NewClient(&redis.Options{
		Addr:         cfg.RedisAddr,
		Username:     strings.TrimSpace(cfg.RedisUsername),
		Password:     cfg.RedisPassword,
		DB:           cfg.RedisDB,
		PoolSize:     cfg.RedisPoolSize,
		DialTimeout:  time.Duration(cfg.RedisDialTimeoutMs) * time.Millisecond,
		ReadTimeout:  time.Duration(cfg.RedisReadTimeoutMs) * time.Millisecond,
		WriteTimeout: time.Duration(cfg.RedisWriteTimeoutMs) * time.Millisecond,
	}), nil
}

func resolveEventCallbackURL(cfg *Config) string {
	if cfg == nil {
		return ""
	}
	if strings.TrimSpace(cfg.CallbackURL) != "" {
		return strings.TrimSpace(cfg.CallbackURL)
	}
	if strings.TrimSpace(cfg.ControlPlaneURL) == "" {
		return ""
	}
	return strings.TrimRight(strings.TrimSpace(cfg.ControlPlaneURL), "/") + "/api/runs/engine-events"
}

func resolveEventSpoolPath(cfg *Config, callbackURL string) string {
	if cfg == nil {
		return ""
	}
	if strings.TrimSpace(cfg.EventSpoolPath) != "" {
		return strings.TrimSpace(cfg.EventSpoolPath)
	}
	if strings.TrimSpace(callbackURL) == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(callbackURL))
	return filepath.Join(
		os.TempDir(),
		fmt.Sprintf("forgegraph-engine-events-%x.jsonl", sum[:8]),
	)
}

func buildGRPCServerOptions(cfg *Config) ([]grpc.ServerOption, bool, error) {
	if cfg == nil {
		return nil, false, nil
	}

	certFile := strings.TrimSpace(cfg.GRPCTLSCertFile)
	keyFile := strings.TrimSpace(cfg.GRPCTLSKeyFile)
	clientCAFile := strings.TrimSpace(cfg.GRPCTLSClientCAFile)
	if certFile == "" && keyFile == "" {
		return nil, false, nil
	}
	if certFile == "" || keyFile == "" {
		return nil, false, fmt.Errorf("both GRPC_TLS_CERT_FILE and GRPC_TLS_KEY_FILE must be set together")
	}

	certificate, err := tls.LoadX509KeyPair(certFile, keyFile)
	if err != nil {
		return nil, false, fmt.Errorf("failed to load gRPC TLS key pair: %w", err)
	}

	tlsConfig := &tls.Config{
		MinVersion:   tls.VersionTLS12,
		Certificates: []tls.Certificate{certificate},
	}

	if clientCAFile != "" {
		clientCAPEM, err := os.ReadFile(clientCAFile)
		if err != nil {
			return nil, false, fmt.Errorf("failed to read gRPC client CA file: %w", err)
		}
		clientCAs := x509.NewCertPool()
		if !clientCAs.AppendCertsFromPEM(clientCAPEM) {
			return nil, false, fmt.Errorf("failed to parse gRPC client CA file")
		}
		tlsConfig.ClientCAs = clientCAs
		if cfg.GRPCTLSRequireClientCert {
			tlsConfig.ClientAuth = tls.RequireAndVerifyClientCert
		} else {
			tlsConfig.ClientAuth = tls.VerifyClientCertIfGiven
		}
	}

	return []grpc.ServerOption{grpc.Creds(credentials.NewTLS(tlsConfig))}, true, nil
}

func readinessReady(cfg *Config, grpcReady bool, redisHealth store.HealthStatus) bool {
	if !grpcReady {
		return false
	}
	if cfg == nil || !hasRuntimeIntentRedisConfig(cfg) {
		return true
	}
	return redisHealth.Healthy
}

func readinessHTTPStatus(cfg *Config, grpcReady bool, redisHealth store.HealthStatus) int {
	if readinessReady(cfg, grpcReady, redisHealth) {
		return http.StatusOK
	}
	return http.StatusServiceUnavailable
}

func readinessPayload(cfg *Config, grpcReady bool, redisHealth store.HealthStatus) map[string]any {
	redisConfigured := hasRuntimeIntentRedisConfig(cfg)
	ready := readinessReady(cfg, grpcReady, redisHealth)
	statusValue := "not_ready"
	if ready {
		statusValue = "ready"
	}
	runStateMode := ""
	if cfg != nil {
		runStateMode = cfg.RunStateMode
	}
	return map[string]any{
		"status":                    statusValue,
		"grpc_ready":                grpcReady,
		"redis_configured":          redisConfigured,
		"redis_healthy":             redisHealth.Healthy,
		"redis_error":               redisHealth.Error,
		"redis_mode":                runtimeIntentRedisMode(cfg),
		"runtime_intent_redis_mode": runtimeIntentRedisMode(cfg),
		"run_state_mode":            runStateMode,
		"control_plane_configured":  hasControlPlaneRepositoryConfig(cfg),
	}
}

func defaultRuntimeIntentRedisHealth(cfg *Config) store.HealthStatus {
	status := store.HealthStatus{CheckedAt: time.Now().UTC()}
	if hasRuntimeIntentRedisConfig(cfg) {
		status.Healthy = false
		status.Error = "runtime intent redis health checker is not configured"
		return status
	}
	status.Healthy = true
	return status
}

func runtimeRedisHealthPayload(cfg *Config, redisHealth store.HealthStatus) map[string]any {
	return map[string]any{
		"transport":                 "runtime_intents",
		"configured":                hasRuntimeIntentRedisConfig(cfg),
		"mode":                      runtimeIntentRedisMode(cfg),
		"redis_mode":                runtimeIntentRedisMode(cfg),
		"runtime_intent_redis_mode": runtimeIntentRedisMode(cfg),
		"healthy":                   redisHealth.Healthy,
		"latency_ms":                redisHealth.LatencyMs,
		"checked_at":                redisHealth.CheckedAt,
		"error":                     redisHealth.Error,
	}
}

func gracefulStopGRPC(ctx context.Context, server grpcLifecycleServer) error {
	if server == nil {
		return nil
	}

	done := make(chan struct{})
	go func() {
		server.GracefulStop()
		close(done)
	}()

	select {
	case <-done:
		return nil
	case <-ctx.Done():
		server.Stop()
		<-done
		return ctx.Err()
	}
}

func shutdownEngineRuntime(ctx context.Context, resources engineRuntimeResources) error {
	if ctx == nil {
		ctx = context.Background()
	}
	var shutdownErrors []error

	if resources.cancel != nil {
		resources.cancel()
	}
	if resources.grpcServer != nil {
		if err := gracefulStopGRPC(ctx, resources.grpcServer); err != nil {
			shutdownErrors = append(shutdownErrors, fmt.Errorf("grpc shutdown: %w", err))
		}
	}
	if resources.metricsServer != nil {
		if err := resources.metricsServer.Shutdown(ctx); err != nil && !errors.Is(err, http.ErrServerClosed) {
			shutdownErrors = append(shutdownErrors, fmt.Errorf("metrics shutdown: %w", err))
		}
	}
	if resources.scheduler != nil {
		if err := resources.scheduler.Shutdown(ctx); err != nil {
			shutdownErrors = append(shutdownErrors, fmt.Errorf("scheduler shutdown: %w", err))
		}
	}
	if resources.summarizationWorker != nil {
		resources.summarizationWorker.Stop()
	}
	if resources.eventEmitter != nil {
		if err := resources.eventEmitter.Close(ctx); err != nil {
			shutdownErrors = append(shutdownErrors, fmt.Errorf("event emitter shutdown: %w", err))
		}
	}
	if resources.memoryRetriever != nil {
		if err := resources.memoryRetriever.Close(); err != nil {
			shutdownErrors = append(shutdownErrors, fmt.Errorf("memory retriever close: %w", err))
		}
	}
	if resources.redisClient != nil {
		if err := resources.redisClient.Close(); err != nil {
			shutdownErrors = append(shutdownErrors, fmt.Errorf("redis close: %w", err))
		}
	}
	return errors.Join(shutdownErrors...)
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
		req.ResumeAttemptId,
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
	rootCtx, stopSignals := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stopSignals()

	// Initialize structured logger
	logCfg := logger.ConfigFromEnv()
	log := logger.New(logCfg)
	slog.SetDefault(log.Logger)
	log.RedirectStdlib()
	otel.SetTracerProvider(sdktrace.NewTracerProvider())

	log.Info("engine_starting", "version", "0.1.0")

	// Load configuration
	cfg := LoadConfig()
	var grpcReady atomic.Bool
	log.Info("config_loaded",
		"grpc_port", cfg.GRPCPort,
		"max_workers", cfg.MaxWorkers,
		"default_timeout_ms", cfg.DefaultTimeout,
		"cache_default_ttl_seconds", cfg.CacheTTLSeconds,
		"checkpoint_mode", cfg.CheckpointMode,
		"checkpoint_batch_size", cfg.CheckpointBatchSize,
		"checkpoint_interval_ms", cfg.CheckpointIntervalMs,
		"tool_manifest_dir", cfg.ToolManifestDir,
		"runtime_intent_redis_mode", runtimeIntentRedisMode(cfg),
		"runtime_intent_sentinel_count", len(parseCSVStrings(cfg.RedisSentinelAddrs)),
		"marketplace_manifest_refresh_seconds", cfg.MarketplaceManifestRefreshSeconds,
		"runtime_mode", cfg.RuntimeMode,
		"legacy_tool_adapter_mode", cfg.LegacyToolAdapterMode,
		"run_state_mode", cfg.RunStateMode,
		"runtime_write_mode", cfg.RuntimeWriteMode,
		"runtime_intent_stream", cfg.RuntimeIntentStream,
		"engine_event_verbosity", cfg.EventVerbosity,
		"engine_event_workers", cfg.EventWorkerCount,
		"engine_instance_id", resolveEngineInstanceID(cfg),
		"engine_allow_in_memory_mode", cfg.EngineAllowInMemoryMode,
		"grpc_tls_enabled", strings.TrimSpace(cfg.GRPCTLSCertFile) != "" && strings.TrimSpace(cfg.GRPCTLSKeyFile) != "",
	)

	// Initialize repository and memory store
	var repo port.RunRepository
	var memoryStore port.MemoryStore
	var runtimeIntentPublisher port.RuntimeIntentPublisher
	var runtimeIntentRedisClient runtimeIntentRedisClient
	var redisHealthChecker *store.RedisHealthChecker
	var llmMetricsSnapshot func() gateway.LLMMetricsSnapshot
	var httpEventEmitter *gateway.HTTPEventEmitter
	var summaryWorker *usecase.SummarizationWorker
	var memoryRetriever *GrpcMemoryRetriever
	var metricsServer *http.Server
	var err error
	repoDriver, err := selectRunRepositoryDriver(cfg)
	if err != nil {
		log.Error("run_repository_config_invalid", "error", err.Error())
		os.Exit(1)
	}

	runtimeWriteMode := usecase.RuntimeWriteModeLegacySync
	if strings.TrimSpace(cfg.RuntimeWriteMode) != "" {
		runtimeWriteMode = cfg.RuntimeWriteMode
	}
	if runtimeWriteMode != usecase.RuntimeWriteModePauseIntents {
		log.Error(
			"runtime_write_mode_invalid",
			"error", fmt.Sprintf(
				"ENGINE_RUNTIME_WRITE_MODE=%s is not supported; use %s",
				runtimeWriteMode,
				usecase.RuntimeWriteModePauseIntents,
			),
		)
		os.Exit(1)
	}
	if !hasRuntimeIntentRedisConfig(cfg) {
		log.Error(
			"runtime_intent_publisher_config_invalid",
			"error", "ENGINE_RUNTIME_WRITE_MODE requires REDIS_ADDR or Redis Sentinel configuration",
		)
		os.Exit(1)
	}
	runtimeIntentRedisClient, err = buildRuntimeIntentRedisClient(cfg)
	if err != nil {
		log.Error("runtime_intent_publisher_config_invalid", "error", err.Error())
		os.Exit(1)
	}
	redisHealthChecker = store.NewRedisHealthChecker(redisStatusPinger{client: runtimeIntentRedisClient})
	runtimeIntentPublisher, err = gateway.NewRedisRuntimeIntentPublisherWithConfig(
		runtimeIntentRedisClient,
		cfg.RuntimeIntentStream,
		gateway.RuntimeIntentPublisherConfig{
			InitialBackoff: time.Duration(cfg.RuntimeIntentPublishInitialBackoffMs) * time.Millisecond,
			MaxBackoff:     time.Duration(cfg.RuntimeIntentPublishMaxBackoffMs) * time.Millisecond,
			MaxElapsedTime: time.Duration(cfg.RuntimeIntentPublishMaxElapsedTimeMs) * time.Millisecond,
			StreamMaxLen:   cfg.RuntimeIntentStreamMaxLen,
		},
	)
	if err != nil {
		log.Error("runtime_intent_publisher_init_failed", "error", err.Error())
		os.Exit(1)
	}
	if repoDriver == runStateModeControlPlaneHTTP {
		ackPublisher, ackErr := gateway.NewBackendAcknowledgedRuntimeIntentPublisher(
			runtimeIntentPublisher,
			cfg.ControlPlaneURL,
			cfg.CallbackSecret,
			nil,
			gateway.RuntimeIntentOutcomeWaitConfig{
				Timeout:      time.Duration(cfg.RuntimeIntentOutcomeWaitTimeoutMs) * time.Millisecond,
				PollInterval: time.Duration(cfg.RuntimeIntentOutcomePollIntervalMs) * time.Millisecond,
			},
		)
		if ackErr != nil {
			log.Error("runtime_intent_outcome_publisher_init_failed", "error", ackErr.Error())
			os.Exit(1)
		}
		runtimeIntentPublisher = ackPublisher
	}
	log.Info(
		"runtime_intent_publisher_initialized",
		"stream", cfg.RuntimeIntentStream,
		"mode", runtimeWriteMode,
		"redis_mode", runtimeIntentRedisMode(cfg),
	)

	switch repoDriver {
	case runStateModeControlPlaneHTTP:
		repo = repository.NewHTTPRunRepository(
			cfg.ControlPlaneURL,
			cfg.CallbackSecret,
			nil,
			runtimeIntentPublisher,
		)
		memoryStore = store.NewHTTPMemoryStore(cfg.ControlPlaneURL, cfg.CallbackSecret, nil)
		log.Info(
			"run_repository_initialized",
			"driver", "control-plane-http",
			"migration_mode", runStateModeControlPlaneHTTP,
			"control_plane_url", cfg.ControlPlaneURL,
		)
	case runStateModeInMemory:
		repo = repository.NewMemoryRunRepository()
		memoryStore = store.NewInMemoryMemoryStore()
		log.Warn(
			"run_repository_local_mode",
			"driver", "in-memory",
			"migration_mode", repoDriver,
		)
	default:
		log.Error("run_repository_driver_unreachable", "driver", repoDriver)
		os.Exit(1)
	}

	// Initialize event emitter
	var emitter port.EventEmitter
	callbackURL := resolveEventCallbackURL(cfg)
	if callbackURL == "" {
		log.Error("event_callback_not_configured", "note", "engine must be able to deliver execution events to the control plane")
		os.Exit(1)
	}
	emitterCfg := gateway.DefaultHTTPEventEmitterConfig(callbackURL)
	emitterCfg.SignatureSecret = cfg.CallbackSecret
	emitterCfg.MaxRetries = cfg.EventMaxRetries
	emitterCfg.RetryDelay = time.Duration(cfg.EventRetryDelayMs) * time.Millisecond
	emitterCfg.BufferSize = cfg.EventBufferSize
	emitterCfg.WorkerCount = cfg.EventWorkerCount
	emitterCfg.SpoolPath = resolveEventSpoolPath(cfg, callbackURL)
	emitterCfg.EventVerbosity = cfg.EventVerbosity
	emitterCfg.EngineInstanceID = resolveEngineInstanceID(cfg)
	httpEventEmitter, err = gateway.NewHTTPEventEmitter(emitterCfg)
	if err != nil {
		log.Error("event_emitter_init_failed", "error", err.Error())
		os.Exit(1)
	}
	emitter = httpEventEmitter
	log.Info("event_emitter_initialized", "callback_url", callbackURL, "spool_path", emitterCfg.SpoolPath)

	// Initialize node executors
	registry := port.NewExecutorRegistry()
	toolRegistry := tool.NewRegistryWithRuntimeMode(cfg.RuntimeMode)

	var manifestClient *gateway.MarketplaceManifestClient

	// Shared credential resolver for executors that support credential_id.
	var resolver gateway.CredentialResolver
	if cfg.ControlPlaneURL != "" && cfg.CallbackSecret != "" {
		resolver = gateway.NewBackendCredentialResolver(cfg.ControlPlaneURL, cfg.CallbackSecret)
		manifestClient = gateway.NewMarketplaceManifestClient(cfg.ControlPlaneURL, cfg.CallbackSecret)
	}
	switch {
	case strings.TrimSpace(cfg.ToolManifestDir) == "":
	case cfg.RuntimeMode == tool.RuntimeModeCloud:
		log.Info("tool_manifest_dir_ignored", "reason", "cloud_runtime_disables_local_tool_manifests")
	case manifestClient != nil:
		log.Info("tool_manifest_dir_ignored", "reason", "backend_manifest_delivery_configured")
	default:
		if err := toolRegistry.LoadManifests(cfg.ToolManifestDir); err != nil {
			log.Warn("tool_manifest_load_failed", "error", err.Error())
		} else {
			log.Info("tool_manifest_dir_loaded", "path", cfg.ToolManifestDir)
		}
	}
	lastManifestChecksum := ""
	if manifestClient != nil && cfg.TenantID != "" {
		lastManifestChecksum = refreshMarketplaceManifests(
			rootCtx,
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
				for {
					select {
					case <-rootCtx.Done():
						return
					case <-ticker.C:
					}
					lastManifestChecksum = refreshMarketplaceManifests(
						rootCtx,
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
		executor.NewToolExecutorWithModes(toolRegistry, resolver, cfg.RuntimeMode, cfg.LegacyToolAdapterMode),
		executor.NewSubgraphExecutor(registry),
	)

	// Initialize LLM client for Prompt and Agent nodes (multi-provider)
	fallbackKey := os.Getenv("OPENAI_API_KEY")
	llmGateway := gateway.NewLLMGatewayFromEnv(
		gateway.NewLocalLLMClient(
			gateway.NewLLMChaosClientFromEnv(
				gateway.NewMultiProviderClient(resolver, fallbackKey),
			),
		),
		gateway.NewFallbackLLMClientFromEnv(),
	)
	llmMetricsSnapshot = llmGateway.MetricsSnapshot
	llmClient := gateway.NewExecutorLLMClient(llmGateway)
	registry.Register(
		executor.NewAgentExecutorWithModes(
			llmClient,
			toolRegistry,
			resolver,
			cfg.RuntimeMode,
			cfg.LegacyToolAdapterMode,
		),
	)
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
	scheduler.SetRuntimeIntentPublisher(runtimeIntentPublisher, runtimeWriteMode)
	log.Info("scheduler_initialized")

	if cfg.MemoryGRPCHost != "" && cfg.MemoryGRPCPort != "" {
		retriever, err := NewGrpcMemoryRetriever(cfg.MemoryGRPCHost, cfg.MemoryGRPCPort)
		if err != nil {
			log.Warn("memory_retriever_init_failed", "error", err.Error())
		} else {
			memoryRetriever = retriever
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
		summaryAdapter := summarizer.NewLLMSummarizerWithTracker(llmClient, "", nil)
		summaryWorker = usecase.NewSummarizationWorker(summaryAdapter, 2, 100)
		summaryWorker.Start(rootCtx)
		scheduler.SetSummarizationWorker(summaryWorker)
		log.Info("backend_memory_summary_intents_initialized", "persistence", "backend_event_intents")
	}

	// Metrics & health server
	if cfg.MetricsPort != "" {
		mux := http.NewServeMux()
		mux.Handle("/metrics", promhttp.Handler())
		mux.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
			redisStatus := defaultRuntimeIntentRedisHealth(cfg)
			if redisHealthChecker != nil {
				redisStatus = redisHealthChecker.Check(r.Context())
			}
			payload, _ := json.Marshal(readinessPayload(cfg, grpcReady.Load(), redisStatus))
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(readinessHTTPStatus(cfg, grpcReady.Load(), redisStatus))
			_, _ = w.Write(payload)
		})
		mux.HandleFunc("/health/redis", func(w http.ResponseWriter, r *http.Request) {
			redisStatus := defaultRuntimeIntentRedisHealth(cfg)
			if redisHealthChecker != nil {
				redisStatus = redisHealthChecker.Check(r.Context())
			}
			payload, _ := json.Marshal(runtimeRedisHealthPayload(cfg, redisStatus))
			w.Header().Set("Content-Type", "application/json")
			if redisStatus.Healthy || !hasRuntimeIntentRedisConfig(cfg) {
				w.WriteHeader(http.StatusOK)
			} else {
				w.WriteHeader(http.StatusServiceUnavailable)
			}
			_, _ = w.Write(payload)
		})
		mux.HandleFunc("/metrics/llm", func(w http.ResponseWriter, r *http.Request) {
			snapshot := gateway.LLMMetricsSnapshot{}
			if llmMetricsSnapshot != nil {
				snapshot = llmMetricsSnapshot()
			}
			payload, _ := json.Marshal(snapshot)
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(payload)
		})
		metricsServer = &http.Server{
			Addr:              ":" + cfg.MetricsPort,
			Handler:           mux,
			ReadHeaderTimeout: 5 * time.Second,
		}
		go func() {
			log.Info("metrics_server_listening", "port", cfg.MetricsPort)
			if err := metricsServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
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

	grpcServerOptions, grpcTLSEnabled, err := buildGRPCServerOptions(cfg)
	if err != nil {
		log.Error("grpc_tls_config_invalid", "error", err.Error())
		os.Exit(1)
	}

	grpcServer := grpc.NewServer(grpcServerOptions...)
	engineServer := NewEngineServer(scheduler, repo, log)
	RegisterEngineServiceServer(grpcServer, engineServer)

	// Enable server reflection for debugging
	reflection.Register(grpcServer)

	if grpcTLSEnabled {
		log.Info("grpc_server_listening", "port", cfg.GRPCPort, "transport_security", "tls")
	} else {
		log.Warn("grpc_server_insecure", "port", cfg.GRPCPort, "note", "set GRPC_TLS_CERT_FILE and GRPC_TLS_KEY_FILE to enable TLS")
	}
	grpcReady.Store(true)

	serveErr := make(chan error, 1)
	go func() {
		serveErr <- grpcServer.Serve(listener)
	}()

	select {
	case err := <-serveErr:
		if err != nil && !errors.Is(err, grpc.ErrServerStopped) {
			log.Error("grpc_serve_failed", "error", err.Error())
			os.Exit(1)
		}
	case <-rootCtx.Done():
		log.Info("engine_shutdown_started", "reason", rootCtx.Err().Error())
		grpcReady.Store(false)
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		if err := shutdownEngineRuntime(shutdownCtx, engineRuntimeResources{
			cancel:              stopSignals,
			grpcServer:          grpcServer,
			metricsServer:       metricsServer,
			scheduler:           scheduler,
			eventEmitter:        httpEventEmitter,
			summarizationWorker: summaryWorker,
			memoryRetriever:     memoryRetriever,
			redisClient:         runtimeIntentRedisClient,
		}); err != nil {
			log.Error("engine_shutdown_failed", "error", err.Error())
			os.Exit(1)
		}
		log.Info("engine_shutdown_complete")
	}
}
