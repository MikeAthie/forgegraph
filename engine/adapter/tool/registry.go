package tool

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// Definition describes a tool entry loaded from manifests.
type Definition struct {
	Name          string                 `json:"name"`
	Version       string                 `json:"version"`
	Description   string                 `json:"description,omitempty"`
	Kind          string                 `json:"kind"` // "http" or "exec"
	ConfigSchema  map[string]any         `json:"config_schema,omitempty"`
	DefaultConfig map[string]any         `json:"default_config,omitempty"`
	HTTP          *HTTPToolConfig        `json:"http,omitempty"`
	Exec          *ExecToolConfig        `json:"exec,omitempty"`
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

// Registry stores tools by name/version.
type Registry struct {
	tools map[string]map[string]*Definition
}

// NewRegistry creates a registry with builtin tools.
func NewRegistry() *Registry {
	reg := &Registry{
		tools: make(map[string]map[string]*Definition),
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
	name := strings.ToLower(def.Name)
	version := strings.ToLower(def.Version)
	if r.tools[name] == nil {
		r.tools[name] = make(map[string]*Definition)
	}
	copyDef := def
	r.tools[name][version] = &copyDef
}

// Resolve returns a tool definition by name/version (latest if version empty).
func (r *Registry) Resolve(name, version string) (*Definition, bool) {
	if name == "" {
		return nil, false
	}
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
		for _, def := range manifest.Tools {
			r.Register(def)
		}
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
