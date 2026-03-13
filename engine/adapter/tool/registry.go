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

// Definition describes a tool entry loaded from manifests.
type Definition struct {
	Name          string          `json:"name"`
	Version       string          `json:"version"`
	Description   string          `json:"description,omitempty"`
	Kind          string          `json:"kind"` // "http" or "exec"
	ConfigSchema  map[string]any  `json:"config_schema,omitempty"`
	DefaultConfig map[string]any  `json:"default_config,omitempty"`
	HTTP          *HTTPToolConfig `json:"http,omitempty"`
	Exec          *ExecToolConfig `json:"exec,omitempty"`
}

type HTTPToolConfig struct {
	URL       string            `json:"url"`
	Method    string            `json:"method,omitempty"`
	Headers   map[string]string `json:"headers,omitempty"`
	TimeoutMs int               `json:"timeout_ms,omitempty"`
}

type ExecToolConfig struct {
	Command      string   `json:"command"`
	Args         []string `json:"args,omitempty"`
	TimeoutMs    int      `json:"timeout_ms,omitempty"`
	WorkDir      string   `json:"workdir,omitempty"`
	EnvWhitelist []string `json:"env_whitelist,omitempty"`
}

type manifestFile struct {
	Tools []Definition `json:"tools"`
}

const (
	RuntimeModeCloud      = "cloud"
	RuntimeModeSelfHosted = "self_hosted"
)

func NormalizeRuntimeMode(runtimeMode string) string {
	normalized := strings.ToLower(strings.TrimSpace(runtimeMode))
	if normalized == RuntimeModeSelfHosted {
		return RuntimeModeSelfHosted
	}
	return RuntimeModeCloud
}

// Registry stores tools by name/version.
type Registry struct {
	tools       map[string]map[string]*Definition
	mu          sync.RWMutex
	runtimeMode string
}

// NewRegistry creates a registry with builtin tools.
func NewRegistry() *Registry {
	return NewRegistryWithRuntimeMode(RuntimeModeSelfHosted)
}

// NewRegistryWithRuntimeMode creates a registry with builtin tools and runtime policy mode.
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

// Register adds or overwrites a tool definition.
func (r *Registry) Register(def Definition) {
	if def.Name == "" || def.Version == "" {
		return
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	name := strings.ToLower(def.Name)
	version := strings.ToLower(def.Version)
	if r.tools[name] == nil {
		r.tools[name] = make(map[string]*Definition)
	}
	copyDef := def
	r.tools[name][version] = &copyDef
}

// LoadDefinitions validates and registers a batch of tool definitions.
func (r *Registry) LoadDefinitions(defs []Definition) error {
	for _, def := range defs {
		if err := ValidateDefinitionForRuntimeMode(def, r.runtimeMode); err != nil {
			return err
		}
		r.Register(def)
	}
	return nil
}

// Resolve returns a tool definition by name/version (latest if version empty).
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

// List returns all tool definitions.
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

// LoadManifests loads tool definitions from a directory of JSON manifest files.
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

// ValidateDefinition validates a tool definition before it becomes executable.
func ValidateDefinition(def Definition) error {
	return ValidateDefinitionForRuntimeMode(def, RuntimeModeSelfHosted)
}

// ValidateDefinitionForRuntimeMode validates a tool definition before it becomes executable.
func ValidateDefinitionForRuntimeMode(def Definition, runtimeMode string) error {
	runtimeMode = NormalizeRuntimeMode(runtimeMode)
	if strings.TrimSpace(def.Name) == "" {
		return fmt.Errorf("tool definition requires name")
	}
	if strings.TrimSpace(def.Version) == "" {
		return fmt.Errorf("tool definition %s requires version", def.Name)
	}

	switch strings.ToLower(strings.TrimSpace(def.Kind)) {
	case "http":
		if def.HTTP == nil {
			return fmt.Errorf("http tool %s requires http config", def.Name)
		}
		if strings.TrimSpace(def.HTTP.URL) == "" {
			return fmt.Errorf("http tool %s requires http.url", def.Name)
		}
	case "exec":
		if def.Exec == nil {
			return fmt.Errorf("exec tool %s requires exec config", def.Name)
		}
		if strings.TrimSpace(def.Exec.Command) == "" {
			return fmt.Errorf("exec tool %s requires exec.command", def.Name)
		}
		if runtimeMode == RuntimeModeCloud {
			return fmt.Errorf("policy denied: exec tools are disabled in cloud mode")
		}
	default:
		return fmt.Errorf("tool %s has unsupported kind %q", def.Name, def.Kind)
	}

	return nil
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
