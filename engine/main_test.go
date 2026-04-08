package main

import (
	"path/filepath"
	"testing"
)

func TestNormalizeRunStateModeDefaultsToControlPlaneHTTP(t *testing.T) {
	if got := normalizeRunStateMode(""); got != runStateModeControlPlaneHTTP {
		t.Fatalf("normalizeRunStateMode(\"\") = %s, want %s", got, runStateModeControlPlaneHTTP)
	}
	if got := normalizeRunStateMode("postgres"); got != runStateModeLegacyDualWrite {
		t.Fatalf("normalizeRunStateMode(postgres) = %s, want %s", got, runStateModeLegacyDualWrite)
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

func TestSelectRunRepositoryDriverAllowsInMemoryFallback(t *testing.T) {
	cfg := &Config{RunStateMode: runStateModeInMemory}

	got, err := selectRunRepositoryDriver(cfg)
	if err != nil {
		t.Fatalf("selectRunRepositoryDriver() error = %v", err)
	}
	if got != runStateModeInMemory {
		t.Fatalf("selectRunRepositoryDriver() = %s, want %s", got, runStateModeInMemory)
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
