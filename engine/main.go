package main

import (
	"context"
	"database/sql"
	"fmt"
	"net"
	"os"
	"strconv"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/adapter/repository"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/application/usecase"
	"github.com/forgegraph/engine/infrastructure/logger"

	_ "github.com/lib/pq"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/reflection"
	"google.golang.org/grpc/status"
)

// Config holds engine configuration
type Config struct {
	GRPCPort       string
	DatabaseURL    string
	MaxWorkers     int
	DefaultTimeout int
}

// LoadConfig loads configuration from environment variables
func LoadConfig() *Config {
	cfg := &Config{
		GRPCPort:       getEnv("GRPC_PORT", "50051"),
		DatabaseURL:    getEnv("DATABASE_URL", ""),
		MaxWorkers:     getEnvInt("MAX_WORKERS", 10),
		DefaultTimeout: getEnvInt("DEFAULT_TIMEOUT_MS", 30000),
	}
	return cfg
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
	err := s.scheduler.StartRun(ctx, req.RunId, req.GraphJson, req.InputJson, req.CallbackUrl)
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
// TODO: Implement in Phase 6 (Human Gate)
func (s *EngineServer) ResumeRun(ctx context.Context, req *ResumeRunRequest) (*ResumeRunResponse, error) {
	s.logger.Info("resume_run_request", "run_id", req.RunId, "node_id", req.NodeId)

	// ResumeRun is deferred to Phase 6 (Human Gate)
	return nil, status.Errorf(codes.Unimplemented, "ResumeRun not yet implemented - coming in Phase 6")
}

func main() {
	// Initialize structured logger
	logCfg := logger.ConfigFromEnv()
	log := logger.New(logCfg)

	log.Info("engine_starting", "version", "0.1.0")

	// Load configuration
	cfg := LoadConfig()
	log.Info("config_loaded",
		"grpc_port", cfg.GRPCPort,
		"max_workers", cfg.MaxWorkers,
		"default_timeout_ms", cfg.DefaultTimeout,
	)

	// Initialize repository
	var repo port.RunRepository
	if cfg.DatabaseURL != "" {
		// Connect to PostgreSQL
		db, err := sql.Open("postgres", cfg.DatabaseURL)
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
	} else {
		log.Warn("database_url_not_set", "fallback", "in-memory")
		repo = repository.NewMemoryRunRepository()
	}

	// Initialize event emitter (no-op for now, callback URL comes per-request)
	// The actual emitter will be created per-run with the callback URL
	emitter := port.NewNoOpEventEmitter()

	// Initialize node executors
	registry := port.NewExecutorRegistry()
	registry.RegisterAll(
		executor.NewOutputExecutor(),
		executor.NewTransformExecutor(),
		executor.NewHTTPExecutor(),
		executor.NewBranchExecutor(),
		executor.NewMergeExecutor(),
		// PromptExecutor requires LLM client, skip for MVP
		// executor.NewPromptExecutor(llmClient),
	)
	log.Info("executors_registered", "types", []string{"output", "transform", "http", "branch", "merge"})

	// Initialize scheduler
	schedulerConfig := usecase.SchedulerConfig{
		MaxWorkers:       cfg.MaxWorkers,
		DefaultTimeoutMs: cfg.DefaultTimeout,
	}
	scheduler := usecase.NewScheduler(schedulerConfig, registry, repo, emitter)
	log.Info("scheduler_initialized")

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
