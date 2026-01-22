// Package logger provides structured logging for the ForgeGraph engine.
// It uses Go's slog package for structured, leveled logging with JSON output.
package logger

import (
	"context"
	"log/slog"
	"os"
	"strings"
)

// Logger wraps slog.Logger with ForgeGraph-specific functionality
type Logger struct {
	*slog.Logger
}

// Config holds logger configuration
type Config struct {
	Level  string // debug, info, warn, error
	Format string // json, text
}

// DefaultConfig returns sensible defaults
func DefaultConfig() Config {
	return Config{
		Level:  "info",
		Format: "json",
	}
}

// ConfigFromEnv loads logger configuration from environment variables
func ConfigFromEnv() Config {
	cfg := DefaultConfig()
	if level := os.Getenv("LOG_LEVEL"); level != "" {
		cfg.Level = strings.ToLower(level)
	}
	if format := os.Getenv("LOG_FORMAT"); format != "" {
		cfg.Format = strings.ToLower(format)
	}
	return cfg
}

// New creates a new structured logger with the given configuration
func New(cfg Config) *Logger {
	var level slog.Level
	switch strings.ToLower(cfg.Level) {
	case "debug":
		level = slog.LevelDebug
	case "info":
		level = slog.LevelInfo
	case "warn", "warning":
		level = slog.LevelWarn
	case "error":
		level = slog.LevelError
	default:
		level = slog.LevelInfo
	}

	opts := &slog.HandlerOptions{
		Level: level,
	}

	var handler slog.Handler
	switch strings.ToLower(cfg.Format) {
	case "text":
		handler = slog.NewTextHandler(os.Stdout, opts)
	default:
		handler = slog.NewJSONHandler(os.Stdout, opts)
	}

	return &Logger{
		Logger: slog.New(handler),
	}
}

// Default creates a logger with default configuration
func Default() *Logger {
	return New(DefaultConfig())
}

// WithRunID returns a logger with run_id attached
func (l *Logger) WithRunID(runID string) *Logger {
	return &Logger{
		Logger: l.Logger.With("run_id", runID),
	}
}

// WithNodeID returns a logger with node_id attached
func (l *Logger) WithNodeID(nodeID string) *Logger {
	return &Logger{
		Logger: l.Logger.With("node_id", nodeID),
	}
}

// WithComponent returns a logger with component name attached
func (l *Logger) WithComponent(component string) *Logger {
	return &Logger{
		Logger: l.Logger.With("component", component),
	}
}

// GRPCRequest logs a gRPC request
func (l *Logger) GRPCRequest(ctx context.Context, method string, req any) {
	l.Logger.InfoContext(ctx, "grpc_request",
		"method", method,
		"request", req,
	)
}

// GRPCResponse logs a gRPC response
func (l *Logger) GRPCResponse(ctx context.Context, method string, resp any, err error) {
	if err != nil {
		l.Logger.ErrorContext(ctx, "grpc_response",
			"method", method,
			"error", err.Error(),
		)
	} else {
		l.Logger.InfoContext(ctx, "grpc_response",
			"method", method,
			"response", resp,
		)
	}
}

// RunStarted logs when a run begins
func (l *Logger) RunStarted(runID string, nodeCount int) {
	l.Logger.Info("run_started",
		"run_id", runID,
		"node_count", nodeCount,
	)
}

// RunCompleted logs when a run completes successfully
func (l *Logger) RunCompleted(runID string) {
	l.Logger.Info("run_completed",
		"run_id", runID,
	)
}

// RunFailed logs when a run fails
func (l *Logger) RunFailed(runID string, err error) {
	l.Logger.Error("run_failed",
		"run_id", runID,
		"error", err.Error(),
	)
}

// RunCanceled logs when a run is canceled
func (l *Logger) RunCanceled(runID string) {
	l.Logger.Info("run_canceled",
		"run_id", runID,
	)
}

// NodeStarted logs when a node begins execution
func (l *Logger) NodeStarted(runID, nodeID, nodeType string) {
	l.Logger.Info("node_started",
		"run_id", runID,
		"node_id", nodeID,
		"node_type", nodeType,
	)
}

// NodeCompleted logs when a node completes successfully
func (l *Logger) NodeCompleted(runID, nodeID, nodeType string) {
	l.Logger.Info("node_completed",
		"run_id", runID,
		"node_id", nodeID,
		"node_type", nodeType,
	)
}

// NodeFailed logs when a node fails
func (l *Logger) NodeFailed(runID, nodeID, nodeType string, err error) {
	l.Logger.Error("node_failed",
		"run_id", runID,
		"node_id", nodeID,
		"node_type", nodeType,
		"error", err.Error(),
	)
}

// NodeRetrying logs when a node is being retried
func (l *Logger) NodeRetrying(runID, nodeID string, attempt int, err error) {
	l.Logger.Warn("node_retrying",
		"run_id", runID,
		"node_id", nodeID,
		"attempt", attempt,
		"error", err.Error(),
	)
}

// NodeSkipped logs when a node is skipped (e.g., branch not taken)
func (l *Logger) NodeSkipped(runID, nodeID string) {
	l.Logger.Info("node_skipped",
		"run_id", runID,
		"node_id", nodeID,
	)
}
