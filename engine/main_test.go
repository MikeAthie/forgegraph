package main

import (
	"context"
	"errors"
	"net/http"
	"path/filepath"
	"testing"
	"time"

	"github.com/forgegraph/engine/adapter/store"
)

func TestNormalizeRunStateModeDefaultsToControlPlaneHTTP(t *testing.T) {
	if got := normalizeRunStateMode(""); got != runStateModeControlPlaneHTTP {
		t.Fatalf("normalizeRunStateMode(\"\") = %s, want %s", got, runStateModeControlPlaneHTTP)
	}
	if got := normalizeRunStateMode("postgres"); got != "postgres" {
		t.Fatalf("normalizeRunStateMode(postgres) = %s, want postgres", got)
	}
}

func TestBoundedProtoLimit(t *testing.T) {
	const maxInt32 = int32(1<<31 - 1)
	tests := []struct {
		name  string
		input int
		want  int32
	}{
		{name: "negative", input: -1, want: 0},
		{name: "zero", input: 0, want: 0},
		{name: "normal", input: 25, want: 25},
		{name: "maximum", input: int(maxInt32), want: maxInt32},
	}
	if ^uint(0)>>63 == 1 {
		tests = append(tests, struct {
			name  string
			input int
			want  int32
		}{name: "overflow", input: int(int64(maxInt32) + 1), want: maxInt32})
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := boundedProtoLimit(test.input); got != test.want {
				t.Fatalf("boundedProtoLimit(%d) = %d, want %d", test.input, got, test.want)
			}
		})
	}
}

func TestSelectRunRepositoryDriverRejectsLegacyDualWrite(t *testing.T) {
	cfg := &Config{RunStateMode: runStateModeLegacyDualWrite}

	if _, err := selectRunRepositoryDriver(cfg); err == nil {
		t.Fatal("expected dual-write mode to be rejected")
	}
}

func TestSelectRunRepositoryDriverRequiresControlPlaneConfigForCutover(t *testing.T) {
	cfg := &Config{RunStateMode: runStateModeControlPlaneHTTP}

	if _, err := selectRunRepositoryDriver(cfg); err == nil {
		t.Fatal("expected explicit cutover mode to require control-plane config")
	}
}

func TestSelectRunRepositoryDriverAllowsInMemoryWithExplicitOverride(t *testing.T) {
	cfg := &Config{RunStateMode: runStateModeInMemory, EngineAllowInMemoryMode: true}

	got, err := selectRunRepositoryDriver(cfg)
	if err != nil {
		t.Fatalf("selectRunRepositoryDriver() error = %v", err)
	}
	if got != runStateModeInMemory {
		t.Fatalf("selectRunRepositoryDriver() = %s, want %s", got, runStateModeInMemory)
	}
}

func TestSelectRunRepositoryDriverRejectsInMemoryWithoutExplicitOverride(t *testing.T) {
	cfg := &Config{RunStateMode: runStateModeInMemory}

	if _, err := selectRunRepositoryDriver(cfg); err == nil {
		t.Fatal("expected in-memory mode to require explicit override")
	}
}

func TestBuildGRPCServerOptionsDisabledByDefault(t *testing.T) {
	options, enabled, err := buildGRPCServerOptions(&Config{})
	if err != nil {
		t.Fatalf("buildGRPCServerOptions() error = %v", err)
	}
	if enabled {
		t.Fatal("expected TLS to be disabled by default")
	}
	if len(options) != 0 {
		t.Fatalf("expected no grpc server options, got %d", len(options))
	}
}

func TestBuildGRPCServerOptionsRequiresCertAndKeyTogether(t *testing.T) {
	_, _, err := buildGRPCServerOptions(&Config{GRPCTLSCertFile: "server.crt"})
	if err == nil {
		t.Fatal("expected TLS config validation error")
	}
}

func TestResolveEventCallbackURLUsesControlPlaneURL(t *testing.T) {
	cfg := &Config{
		ControlPlaneURL: "http://backend:8000",
	}

	got := resolveEventCallbackURL(cfg)
	want := "http://backend:8000/api/runs/engine-events"
	if got != want {
		t.Fatalf("resolveEventCallbackURL() = %s, want %s", got, want)
	}
}

func TestResolveEventSpoolPathDefaultsStable(t *testing.T) {
	cfg := &Config{}
	callbackURL := "http://backend:8000/api/runs/engine-events"

	first := resolveEventSpoolPath(cfg, callbackURL)
	second := resolveEventSpoolPath(cfg, callbackURL)

	if first == "" {
		t.Fatal("expected non-empty spool path")
	}
	if first != second {
		t.Fatalf("resolveEventSpoolPath() unstable: %s != %s", first, second)
	}
	if filepath.Ext(first) != ".jsonl" {
		t.Fatalf("spool path extension = %s, want .jsonl", filepath.Ext(first))
	}
}

func TestResolveEngineInstanceIDPrefersConfiguredEngineHost(t *testing.T) {
	cfg := &Config{
		EngineHost: "engine",
		GRPCPort:   "50051",
	}

	if got := resolveEngineInstanceID(cfg); got != "engine:50051" {
		t.Fatalf("resolveEngineInstanceID() = %s, want engine:50051", got)
	}
}

func TestReadinessRuntimeIntentRedisDirectFailureBlocksReadiness(t *testing.T) {
	cfg := &Config{
		RedisAddr:    "redis:6379",
		RunStateMode: runStateModeControlPlaneHTTP,
	}
	redisStatus := store.HealthStatus{Healthy: false, Error: "dial tcp redis:6379: connect refused"}

	if got := readinessHTTPStatus(cfg, true, redisStatus); got != http.StatusServiceUnavailable {
		t.Fatalf("readinessHTTPStatus() = %d, want %d", got, http.StatusServiceUnavailable)
	}
	payload := readinessPayload(cfg, true, redisStatus)
	if got := payload["status"]; got != "not_ready" {
		t.Fatalf("payload status = %v, want not_ready", got)
	}
	if got := payload["redis_configured"]; got != true {
		t.Fatalf("payload redis_configured = %v, want true", got)
	}
	if got := payload["redis_mode"]; got != "direct" {
		t.Fatalf("payload redis_mode = %v, want direct", got)
	}
	if got := payload["redis_error"]; got != redisStatus.Error {
		t.Fatalf("payload redis_error = %v, want %s", got, redisStatus.Error)
	}
}

func TestReadinessRuntimeIntentRedisDirectHealthyIsReady(t *testing.T) {
	cfg := &Config{
		RedisAddr:    "redis:6379",
		RunStateMode: runStateModeControlPlaneHTTP,
	}
	redisStatus := store.HealthStatus{Healthy: true}

	if got := readinessHTTPStatus(cfg, true, redisStatus); got != http.StatusOK {
		t.Fatalf("readinessHTTPStatus() = %d, want %d", got, http.StatusOK)
	}
	payload := readinessPayload(cfg, true, redisStatus)
	if got := payload["status"]; got != "ready" {
		t.Fatalf("payload status = %v, want ready", got)
	}
	if got := payload["runtime_intent_redis_mode"]; got != "direct" {
		t.Fatalf("payload runtime_intent_redis_mode = %v, want direct", got)
	}
}

func TestReadinessRuntimeIntentRedisSentinelHealthyIsReady(t *testing.T) {
	cfg := &Config{
		RedisSentinelAddrs:      "sentinel-a:26379, sentinel-b:26379",
		RedisSentinelMasterName: "mymaster",
		RunStateMode:            runStateModeControlPlaneHTTP,
	}
	redisStatus := store.HealthStatus{Healthy: true}

	if got := readinessHTTPStatus(cfg, true, redisStatus); got != http.StatusOK {
		t.Fatalf("readinessHTTPStatus() = %d, want %d", got, http.StatusOK)
	}
	payload := readinessPayload(cfg, true, redisStatus)
	if got := payload["redis_configured"]; got != true {
		t.Fatalf("payload redis_configured = %v, want true", got)
	}
	if got := payload["redis_mode"]; got != "sentinel" {
		t.Fatalf("payload redis_mode = %v, want sentinel", got)
	}
}

func TestReadinessWithoutRuntimeIntentRedisAllowsLocalHealth(t *testing.T) {
	cfg := &Config{RunStateMode: runStateModeInMemory}
	redisStatus := defaultRuntimeIntentRedisHealth(cfg)

	if got := readinessHTTPStatus(cfg, true, redisStatus); got != http.StatusOK {
		t.Fatalf("readinessHTTPStatus() = %d, want %d", got, http.StatusOK)
	}
	payload := readinessPayload(cfg, true, redisStatus)
	if got := payload["redis_configured"]; got != false {
		t.Fatalf("payload redis_configured = %v, want false", got)
	}
	if got := payload["redis_mode"]; got != "none" {
		t.Fatalf("payload redis_mode = %v, want none", got)
	}
	if got := payload["redis_healthy"]; got != true {
		t.Fatalf("payload redis_healthy = %v, want true", got)
	}
}

func TestRuntimeRedisHealthPayloadDescribesRuntimeIntentTransport(t *testing.T) {
	checkedAt := time.Date(2026, 5, 25, 12, 0, 0, 0, time.UTC)
	cfg := &Config{RedisAddr: "redis:6379"}
	redisStatus := store.HealthStatus{
		Healthy:   false,
		LatencyMs: 17,
		CheckedAt: checkedAt,
		Error:     "redis down",
	}

	payload := runtimeRedisHealthPayload(cfg, redisStatus)
	if got := payload["transport"]; got != "runtime_intents" {
		t.Fatalf("payload transport = %v, want runtime_intents", got)
	}
	if got := payload["configured"]; got != true {
		t.Fatalf("payload configured = %v, want true", got)
	}
	if got := payload["mode"]; got != "direct" {
		t.Fatalf("payload mode = %v, want direct", got)
	}
	if got := payload["latency_ms"]; got != int64(17) {
		t.Fatalf("payload latency_ms = %v, want 17", got)
	}
	if got := payload["checked_at"]; got != checkedAt {
		t.Fatalf("payload checked_at = %v, want %v", got, checkedAt)
	}
	if got := payload["error"]; got != "redis down" {
		t.Fatalf("payload error = %v, want redis down", got)
	}
}

func TestRedisHealthCheckerFailureBlocksReadiness(t *testing.T) {
	checker := store.NewRedisHealthChecker(fakeRedisPinger{err: errors.New("redis down")})
	cfg := &Config{RedisAddr: "redis:6379"}

	status := checker.Check(context.Background())
	if status.Healthy {
		t.Fatal("expected redis health to be unhealthy")
	}
	if status.Error != "redis down" {
		t.Fatalf("redis health error = %q, want redis down", status.Error)
	}
	if got := readinessHTTPStatus(cfg, true, status); got != http.StatusServiceUnavailable {
		t.Fatalf("readinessHTTPStatus() = %d, want %d", got, http.StatusServiceUnavailable)
	}
}

func TestShutdownEngineRuntimeStopsResources(t *testing.T) {
	grpcServer := &fakeGRPCServer{}
	emitter := &fakeEventEmitter{}
	worker := &fakeWorker{}
	scheduler := &fakeScheduler{}
	memoryRetriever := &fakeCloser{}
	redisClient := &fakeCloser{}
	cancelled := false

	err := shutdownEngineRuntime(context.Background(), engineRuntimeResources{
		cancel:              func() { cancelled = true },
		grpcServer:          grpcServer,
		scheduler:           scheduler,
		eventEmitter:        emitter,
		summarizationWorker: worker,
		memoryRetriever:     memoryRetriever,
		redisClient:         redisClient,
	})
	if err != nil {
		t.Fatalf("shutdownEngineRuntime() error = %v", err)
	}
	if !cancelled {
		t.Fatal("expected root context cancel to be called")
	}
	if !grpcServer.gracefulStopped {
		t.Fatal("expected gRPC server to be gracefully stopped")
	}
	if grpcServer.stopped {
		t.Fatal("did not expect forced gRPC stop during graceful shutdown")
	}
	if !worker.stopped {
		t.Fatal("expected summarization worker to stop")
	}
	if !scheduler.stopped {
		t.Fatal("expected scheduler to stop")
	}
	if !emitter.closed {
		t.Fatal("expected event emitter to close")
	}
	if !redisClient.closed {
		t.Fatal("expected runtime intent redis client to close")
	}
	if !memoryRetriever.closed {
		t.Fatal("expected memory retriever to close")
	}
}

type fakeRedisPinger struct {
	err error
}

func (p fakeRedisPinger) Ping(context.Context) error {
	return p.err
}

type fakeGRPCServer struct {
	gracefulStopped bool
	stopped         bool
}

func (s *fakeGRPCServer) GracefulStop() {
	s.gracefulStopped = true
}

func (s *fakeGRPCServer) Stop() {
	s.stopped = true
}

type fakeEventEmitter struct {
	closed bool
}

func (e *fakeEventEmitter) Close(context.Context) error {
	e.closed = true
	return nil
}

type fakeWorker struct {
	stopped bool
}

type fakeScheduler struct {
	stopped bool
}

func (s *fakeScheduler) Shutdown(context.Context) error {
	s.stopped = true
	return nil
}

func (w *fakeWorker) Stop() {
	w.stopped = true
}

type fakeCloser struct {
	closed bool
}

func (c *fakeCloser) Close() error {
	c.closed = true
	return nil
}
