package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"net/url"
	"os"
	"sort"
	"strings"
	"time"
)

const (
	defaultBaseURL             = "http://127.0.0.1:8000"
	defaultTenantEmailDomain   = "loadgen.forgegraph.local"
	defaultPassword            = "LoadgenPass!234"
	defaultOutputDir           = "logs/loadgen"
	defaultCapacityReportDir   = "docs/ops/capacity"
	defaultRequestTimeout      = 15 * time.Second
	defaultObservationDeadline = 2 * time.Minute
)

type Config struct {
	BaseURL                  string        `json:"base_url"`
	EngineCallbackSecret     string        `json:"-"`
	Gate                     string        `json:"gate,omitempty"`
	OutputDir                string        `json:"output_dir"`
	CapacityReportDir        string        `json:"capacity_report_dir"`
	TenantCredentialsFile    string        `json:"tenant_credentials_file,omitempty"`
	TenantEmailDomain        string        `json:"tenant_email_domain"`
	Password                 string        `json:"-"`
	RequestTimeout           time.Duration `json:"request_timeout"`
	ObservationDeadline      time.Duration `json:"observation_deadline"`
	Tenants                  int           `json:"tenants"`
	Agents                   int           `json:"agents"`
	RunsPerTenant            int           `json:"runs_per_tenant"`
	WSClients                int           `json:"ws_clients"`
	Duration                 time.Duration `json:"duration"`
	WithHITL                 bool          `json:"with_hitl"`
	WithMemory               bool          `json:"with_memory"`
	WithAccounting           bool          `json:"with_accounting"`
	DuplicateEventStorm      bool          `json:"duplicate_event_storm"`
	ReconnectStorm           bool          `json:"reconnect_storm"`
	LLMThrottling            bool          `json:"llm_throttling"`
	EngineRestartHook        string        `json:"engine_restart_hook,omitempty"`
	BackendWorkerRestartHook string        `json:"backend_worker_restart_hook,omitempty"`
	RedisDegradeHook         string        `json:"redis_degrade_hook,omitempty"`
	RedisRecoverHook         string        `json:"redis_recover_hook,omitempty"`
	LLMThrottleOnHook        string        `json:"llm_throttle_on_hook,omitempty"`
	LLMThrottleOffHook       string        `json:"llm_throttle_off_hook,omitempty"`
	DryRun                   bool          `json:"dry_run"`
}

type GateSpec struct {
	Name                 string
	TargetAgents         int
	MinTenants           int
	RunsPerTenant        int
	WSClients            int
	Duration             time.Duration
	RequireHITL          bool
	RequireMemory        bool
	RequireAccounting    bool
	RequireDuplicates    bool
	RequireReconnects    bool
	RequireLLMThrottling bool
	RequireDisruptions   bool
}

var gateSpecs = map[string]GateSpec{
	"A": {
		Name:          "A",
		TargetAgents:  25,
		MinTenants:    1,
		RunsPerTenant: 1,
		Duration:      time.Hour,
	},
	"B": {
		Name:          "B",
		TargetAgents:  50,
		MinTenants:    1,
		RunsPerTenant: 1,
		Duration:      2 * time.Hour,
	},
	"C": {
		Name:              "C",
		TargetAgents:      100,
		MinTenants:        5,
		RunsPerTenant:     20,
		Duration:          4 * time.Hour,
		RequireHITL:       true,
		RequireMemory:     true,
		RequireAccounting: true,
	},
	"D": {
		Name:              "D",
		TargetAgents:      250,
		MinTenants:        10,
		RunsPerTenant:     20,
		WSClients:         250,
		Duration:          4 * time.Hour,
		RequireHITL:       true,
		RequireMemory:     true,
		RequireAccounting: true,
		RequireReconnects: true,
	},
	"E": {
		Name:                 "E",
		TargetAgents:         500,
		MinTenants:           25,
		RunsPerTenant:        20,
		WSClients:            500,
		Duration:             8 * time.Hour,
		RequireHITL:          true,
		RequireMemory:        true,
		RequireAccounting:    true,
		RequireDuplicates:    true,
		RequireReconnects:    true,
		RequireLLMThrottling: true,
		RequireDisruptions:   true,
	},
}

type rawConfig struct {
	Config
	RequestTimeout      string
	Duration            string
	ObservationDeadline string
}

func ParseConfig(args []string) (Config, error) {
	cfg := Config{
		BaseURL:              getenv("LOADGEN_BASE_URL", defaultBaseURL),
		EngineCallbackSecret: os.Getenv("ENGINE_CALLBACK_SECRET"),
		OutputDir:            defaultOutputDir,
		CapacityReportDir:    defaultCapacityReportDir,
		TenantEmailDomain:    defaultTenantEmailDomain,
		Password:             defaultPassword,
		RequestTimeout:       defaultRequestTimeout,
		ObservationDeadline:  defaultObservationDeadline,
		Tenants:              1,
		Agents:               1,
		RunsPerTenant:        1,
		WSClients:            0,
		Duration:             time.Minute,
	}

	fs := flag.NewFlagSet("loadgen", flag.ContinueOnError)
	fs.StringVar(&cfg.BaseURL, "base-url", cfg.BaseURL, "Backend base URL.")
	fs.StringVar(&cfg.EngineCallbackSecret, "engine-callback-secret", cfg.EngineCallbackSecret, "Shared secret for signed engine callbacks.")
	fs.StringVar(&cfg.Gate, "gate", "", "Capacity gate to evaluate: A, B, C, D, or E.")
	fs.StringVar(&cfg.OutputDir, "output-dir", cfg.OutputDir, "Directory for raw loadgen artifacts.")
	fs.StringVar(&cfg.CapacityReportDir, "capacity-report-dir", cfg.CapacityReportDir, "Directory for checked-in capacity gate reports.")
	fs.StringVar(&cfg.TenantCredentialsFile, "tenant-credentials-file", "", "JSON tenant credentials file.")
	fs.StringVar(&cfg.TenantEmailDomain, "tenant-email-domain", cfg.TenantEmailDomain, "Domain for generated tenant owner emails.")
	fs.StringVar(&cfg.Password, "password", cfg.Password, "Password for generated tenant owner users.")
	fs.DurationVar(&cfg.RequestTimeout, "request-timeout", cfg.RequestTimeout, "Per-request timeout.")
	fs.DurationVar(&cfg.ObservationDeadline, "observation-deadline", cfg.ObservationDeadline, "Max time to wait for accepted work to appear in backend read models or dead letters.")
	fs.IntVar(&cfg.Tenants, "tenants", cfg.Tenants, "Number of tenants to simulate.")
	fs.IntVar(&cfg.Agents, "agents", cfg.Agents, "Number of active agents to simulate.")
	fs.IntVar(&cfg.RunsPerTenant, "runs-per-tenant", cfg.RunsPerTenant, "Runs to start per tenant.")
	fs.IntVar(&cfg.WSClients, "ws-clients", cfg.WSClients, "Organization websocket clients to open.")
	fs.DurationVar(&cfg.Duration, "duration", cfg.Duration, "Load test duration.")
	fs.BoolVar(&cfg.WithHITL, "with-hitl", false, "Exercise HITL decision resume flows.")
	fs.BoolVar(&cfg.WithMemory, "with-memory", false, "Exercise backend memory observation writes.")
	fs.BoolVar(&cfg.WithAccounting, "with-accounting", false, "Exercise backend-owned accounting writes through signed engine callbacks.")
	fs.BoolVar(&cfg.DuplicateEventStorm, "duplicate-event-storm", false, "Send deterministic duplicate signed callbacks.")
	fs.BoolVar(&cfg.ReconnectStorm, "reconnect-storm", false, "Reconnect websocket clients during the run.")
	fs.BoolVar(&cfg.LLMThrottling, "llm-throttling", false, "Record LLM throttling coverage and run throttle hooks when supplied.")
	fs.StringVar(&cfg.EngineRestartHook, "engine-restart-hook", "", "External hook command for engine restart evidence.")
	fs.StringVar(&cfg.BackendWorkerRestartHook, "backend-worker-restart-hook", "", "External hook command for backend worker restart evidence.")
	fs.StringVar(&cfg.RedisDegradeHook, "redis-degrade-hook", "", "External hook command for Redis degradation evidence.")
	fs.StringVar(&cfg.RedisRecoverHook, "redis-recover-hook", "", "External hook command for Redis recovery evidence.")
	fs.StringVar(&cfg.LLMThrottleOnHook, "llm-throttle-on-hook", "", "External hook command that enables LLM throttling.")
	fs.StringVar(&cfg.LLMThrottleOffHook, "llm-throttle-off-hook", "", "External hook command that disables LLM throttling.")
	fs.BoolVar(&cfg.DryRun, "dry-run", false, "Validate configuration and render a planned workload without sending mutations.")

	if err := fs.Parse(args); err != nil {
		return Config{}, err
	}
	if fs.NArg() != 0 {
		return Config{}, fmt.Errorf("unexpected positional arguments: %s", strings.Join(fs.Args(), " "))
	}

	cfg.Gate = strings.ToUpper(strings.TrimSpace(cfg.Gate))
	applyGateDefaults(&cfg)
	return cfg, cfg.Validate()
}

func (cfg Config) Validate() error {
	var errs []string
	if cfg.Tenants <= 0 {
		errs = append(errs, "--tenants must be greater than zero")
	}
	if cfg.Agents <= 0 {
		errs = append(errs, "--agents must be greater than zero")
	}
	if cfg.RunsPerTenant <= 0 {
		errs = append(errs, "--runs-per-tenant must be greater than zero")
	}
	if cfg.WSClients < 0 {
		errs = append(errs, "--ws-clients cannot be negative")
	}
	if cfg.Duration <= 0 {
		errs = append(errs, "--duration must be greater than zero")
	}
	if cfg.RequestTimeout <= 0 {
		errs = append(errs, "--request-timeout must be greater than zero")
	}
	if cfg.ObservationDeadline <= 0 {
		errs = append(errs, "--observation-deadline must be greater than zero")
	}
	if cfg.Gate != "" {
		if _, ok := gateSpecs[cfg.Gate]; !ok {
			errs = append(errs, "--gate must be one of A, B, C, D, or E")
		}
	}
	if _, err := url.ParseRequestURI(cfg.BaseURL); err != nil {
		errs = append(errs, fmt.Sprintf("--base-url is invalid: %v", err))
	}
	if strings.TrimSpace(cfg.OutputDir) == "" {
		errs = append(errs, "--output-dir cannot be blank")
	}
	if cfg.Gate != "" && strings.TrimSpace(cfg.CapacityReportDir) == "" {
		errs = append(errs, "--capacity-report-dir cannot be blank when --gate is set")
	}
	if cfg.WithAccounting && !cfg.DryRun && strings.TrimSpace(cfg.EngineCallbackSecret) == "" {
		errs = append(errs, "--engine-callback-secret is required for live accounting callback stress")
	}
	if len(errs) > 0 {
		return errors.New(strings.Join(errs, "; "))
	}
	return nil
}

func applyGateDefaults(cfg *Config) {
	if cfg.Gate == "" {
		return
	}
	spec, ok := gateSpecs[cfg.Gate]
	if !ok {
		return
	}
	if cfg.Agents < spec.TargetAgents {
		cfg.Agents = spec.TargetAgents
	}
	if cfg.Tenants < spec.MinTenants {
		cfg.Tenants = spec.MinTenants
	}
	if cfg.RunsPerTenant < spec.RunsPerTenant {
		cfg.RunsPerTenant = spec.RunsPerTenant
	}
	if spec.WSClients > 0 && cfg.WSClients < spec.WSClients {
		cfg.WSClients = spec.WSClients
	}
	if cfg.Duration < spec.Duration {
		cfg.Duration = spec.Duration
	}
	cfg.WithHITL = cfg.WithHITL || spec.RequireHITL
	cfg.WithMemory = cfg.WithMemory || spec.RequireMemory
	cfg.WithAccounting = cfg.WithAccounting || spec.RequireAccounting
	cfg.DuplicateEventStorm = cfg.DuplicateEventStorm || spec.RequireDuplicates
	cfg.ReconnectStorm = cfg.ReconnectStorm || spec.RequireReconnects
	cfg.LLMThrottling = cfg.LLMThrottling || spec.RequireLLMThrottling
}

func getenv(key string, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

type TenantCredential struct {
	Email          string `json:"email"`
	Password       string `json:"password"`
	AccessToken    string `json:"access_token,omitempty"`
	OrganizationID string `json:"organization_id,omitempty"`
	GraphVersionID string `json:"graph_version_id,omitempty"`
}

func LoadTenantCredentials(path string) ([]TenantCredential, error) {
	if strings.TrimSpace(path) == "" {
		return nil, nil
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var wrapped struct {
		Tenants []TenantCredential `json:"tenants"`
	}
	if err := json.Unmarshal(data, &wrapped); err == nil && len(wrapped.Tenants) > 0 {
		return normalizedCredentials(wrapped.Tenants)
	}
	var tenants []TenantCredential
	if err := json.Unmarshal(data, &tenants); err != nil {
		return nil, err
	}
	return normalizedCredentials(tenants)
}

func normalizedCredentials(tenants []TenantCredential) ([]TenantCredential, error) {
	for index, tenant := range tenants {
		if strings.TrimSpace(tenant.Email) == "" {
			return nil, fmt.Errorf("tenant credential %d is missing email", index)
		}
		if strings.TrimSpace(tenant.Password) == "" && strings.TrimSpace(tenant.AccessToken) == "" {
			return nil, fmt.Errorf("tenant credential %d must include password or access_token", index)
		}
	}
	sort.SliceStable(tenants, func(i, j int) bool {
		return tenants[i].Email < tenants[j].Email
	})
	return tenants, nil
}
