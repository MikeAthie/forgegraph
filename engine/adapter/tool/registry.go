package tool

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
)

type Definition struct {
	Name               string           `json:"name"`
	Version            string           `json:"version"`
	Category           string           `json:"category,omitempty"`
	Description        string           `json:"description,omitempty"`
	Visibility         string           `json:"visibility,omitempty"`
	InputSchema        map[string]any   `json:"input_schema,omitempty"`
	OutputSchema       map[string]any   `json:"output_schema,omitempty"`
	ConfigSchema       map[string]any   `json:"config_schema,omitempty"`
	DefaultConfig      map[string]any   `json:"default_config,omitempty"`
	MaxResultSize      int              `json:"max_result_size_chars,omitempty"`
	Execution          ExecutionConfig  `json:"execution"`
	SideEffects        SideEffectConfig `json:"side_effects"`
	AgentHints         map[string]any   `json:"agent_hints,omitempty"`
	DefinitionChecksum string           `json:"definition_checksum,omitempty"`
	Kind               string           `json:"kind,omitempty"`
	HTTP               *HTTPToolConfig  `json:"http,omitempty"`
	Local              *LocalToolConfig `json:"local,omitempty"`
}

type ExecutionConfig struct {
	Type           string           `json:"type"`
	TimeoutSeconds int              `json:"timeout_seconds,omitempty"`
	HTTP           *HTTPToolConfig  `json:"http,omitempty"`
	Local          *LocalToolConfig `json:"local,omitempty"`
}

type HTTPToolConfig struct {
	URL     string            `json:"url"`
	Method  string            `json:"method,omitempty"`
	Headers map[string]string `json:"headers,omitempty"`
}

type LocalToolConfig struct {
	Handler string `json:"handler"`
}

type SideEffectConfig struct {
	Type       string `json:"type"`
	Idempotent bool   `json:"idempotent"`
}

type manifestFile struct {
	Tools []Definition `json:"tools"`
}

const (
	RuntimeModeCloud      = "cloud"
	RuntimeModeSelfHosted = "self_hosted"
	VisibilityPublic      = "public"
	VisibilityInternal    = "internal"
)

func NormalizeRuntimeMode(runtimeMode string) string {
	normalized := strings.ToLower(strings.TrimSpace(runtimeMode))
	if normalized == RuntimeModeSelfHosted {
		return RuntimeModeSelfHosted
	}
	return RuntimeModeCloud
}

func normalizeVisibility(visibility string) string {
	if strings.EqualFold(strings.TrimSpace(visibility), VisibilityInternal) {
		return VisibilityInternal
	}
	return VisibilityPublic
}

func (d Definition) IsAgentVisible() bool {
	return normalizeVisibility(d.Visibility) != VisibilityInternal
}

type Registry struct {
	tools       map[string]map[string]*Definition
	mu          sync.RWMutex
	runtimeMode string
}

func NewRegistry() *Registry {
	return NewRegistryWithRuntimeMode(RuntimeModeSelfHosted)
}

func NewRegistryWithRuntimeMode(runtimeMode string) *Registry {
	reg := &Registry{
		tools:       make(map[string]map[string]*Definition),
		runtimeMode: NormalizeRuntimeMode(runtimeMode),
	}
	for _, toolDef := range BuiltinTools() {
		reg.Register(toolDef)
	}
	return reg
}

func (r *Registry) Register(def Definition) {
	if def.Name == "" || def.Version == "" {
		return
	}
	def = normalizeLegacyAliases(def)
	r.mu.Lock()
	defer r.mu.Unlock()
	name := strings.ToLower(def.Name)
	version := strings.ToLower(def.Version)
	if r.tools[name] == nil {
		r.tools[name] = make(map[string]*Definition)
	}
	copyDef := def
	copyDef.Visibility = normalizeVisibility(copyDef.Visibility)
	r.tools[name][version] = &copyDef
}

func (r *Registry) LoadDefinitions(defs []Definition) error {
	for _, def := range defs {
		if err := ValidateDefinitionForRuntimeMode(def, r.runtimeMode); err != nil {
			return err
		}
		r.Register(def)
	}
	return nil
}

func (r *Registry) Resolve(name, version string) (*Definition, bool) {
	if name == "" {
		return nil, false
	}
	r.mu.RLock()
	defer r.mu.RUnlock()
	nameKey := strings.ToLower(name)
	versions := r.tools[nameKey]
	if versions == nil {
		return nil, false
	}
	if version == "" {
		return latestVersion(versions)
	}
	def, ok := versions[strings.ToLower(version)]
	return def, ok
}

func (r *Registry) List() []*Definition {
	r.mu.RLock()
	defer r.mu.RUnlock()
	var result []*Definition
	for _, versions := range r.tools {
		for _, def := range versions {
			result = append(result, def)
		}
	}
	sort.Slice(result, func(i, j int) bool {
		if result[i].Name == result[j].Name {
			return result[i].Version < result[j].Version
		}
		return result[i].Name < result[j].Name
	})
	return result
}

func (r *Registry) LoadManifests(dir string) error {
	if dir == "" {
		return nil
	}
	info, err := os.Stat(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	if !info.IsDir() {
		return fmt.Errorf("tool manifest path is not a directory: %s", dir)
	}

	matches, err := filepath.Glob(filepath.Join(dir, "*.json"))
	if err != nil {
		return err
	}
	for _, path := range matches {
		content, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		var manifest manifestFile
		if err := json.Unmarshal(content, &manifest); err != nil {
			return fmt.Errorf("parse tool manifest %s: %w", path, err)
		}
		if err := r.LoadDefinitions(manifest.Tools); err != nil {
			return fmt.Errorf("load tool manifest %s: %w", path, err)
		}
	}
	return nil
}

func ValidateDefinition(def Definition) error {
	return ValidateDefinitionForRuntimeMode(def, RuntimeModeSelfHosted)
}

func ValidateDefinitionForRuntimeMode(def Definition, runtimeMode string) error {
	def = normalizeLegacyAliases(def)
	runtimeMode = NormalizeRuntimeMode(runtimeMode)
	if strings.TrimSpace(def.Name) == "" {
		return fmt.Errorf("tool definition requires name")
	}
	if strings.TrimSpace(def.Version) == "" {
		return fmt.Errorf("tool definition %s requires version", def.Name)
	}
	if strings.TrimSpace(def.Category) == "" {
		return fmt.Errorf("tool definition %s requires category", def.Name)
	}
	if def.InputSchema == nil {
		return fmt.Errorf("tool definition %s requires input_schema", def.Name)
	}
	if def.OutputSchema != nil {
		if _, ok := def.OutputSchema["type"]; !ok && len(def.OutputSchema) > 0 {
			return fmt.Errorf("tool definition %s output_schema must be a JSON Schema object", def.Name)
		}
	}
	if def.MaxResultSize < 0 {
		return fmt.Errorf("tool definition %s max_result_size_chars must be >= 0", def.Name)
	}
	if def.Execution.TimeoutSeconds < 0 {
		return fmt.Errorf("tool definition %s execution.timeout_seconds must be >= 0", def.Name)
	}
	if def.SideEffects.Type != "read" && def.SideEffects.Type != "write" && def.SideEffects.Type != "external" {
		return fmt.Errorf("tool definition %s side_effects.type must be read, write, or external", def.Name)
	}

	switch strings.ToLower(strings.TrimSpace(def.Execution.Type)) {
	case "http":
		if def.Execution.HTTP == nil {
			return fmt.Errorf("http tool %s requires execution.http", def.Name)
		}
		if strings.TrimSpace(def.Execution.HTTP.URL) == "" {
			return fmt.Errorf("http tool %s requires execution.http.url", def.Name)
		}
	case "local":
		if def.Execution.Local == nil {
			return fmt.Errorf("local tool %s requires execution.local", def.Name)
		}
		if strings.TrimSpace(def.Execution.Local.Handler) == "" {
			return fmt.Errorf("local tool %s requires execution.local.handler", def.Name)
		}
	default:
		return fmt.Errorf("tool %s has unsupported execution.type %q", def.Name, def.Execution.Type)
	}

	_ = runtimeMode
	return nil
}

func normalizeLegacyAliases(def Definition) Definition {
	if strings.TrimSpace(def.Execution.Type) == "" {
		switch strings.ToLower(strings.TrimSpace(def.Kind)) {
		case "http":
			def.Execution.Type = "http"
			def.Execution.HTTP = def.HTTP
		case "local":
			def.Execution.Type = "local"
			def.Execution.Local = def.Local
		}
	}
	if def.Execution.HTTP == nil && def.HTTP != nil {
		def.Execution.HTTP = def.HTTP
	}
	if def.Execution.Local == nil && def.Local != nil {
		def.Execution.Local = def.Local
	}
	if strings.TrimSpace(def.Category) == "" {
		def.Category = "other"
	}
	if strings.TrimSpace(def.SideEffects.Type) == "" {
		switch strings.ToLower(strings.TrimSpace(def.Execution.Type)) {
		case "http":
			def.SideEffects = SideEffectConfig{Type: "read", Idempotent: true}
		case "local":
			def.SideEffects = SideEffectConfig{Type: "external", Idempotent: false}
		}
	}
	if def.Visibility == "" {
		def.Visibility = VisibilityPublic
	}
	return def
}

func latestVersion(versions map[string]*Definition) (*Definition, bool) {
	if len(versions) == 0 {
		return nil, false
	}
	keys := make([]string, 0, len(versions))
	for k := range versions {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return versions[keys[len(keys)-1]], true
}
