// Package entity contains core domain entities for the ForgeGraph engine.
package entity

// Graph represents a workflow graph loaded for execution
type Graph struct {
	ID          string `json:"id"`
	VersionID   string `json:"version_id"`
	Name        string `json:"name"`
	Description string `json:"description"`
	Nodes       []Node `json:"nodes"`
	Edges       []Edge `json:"edges"`
}

// Node represents a single node in the workflow
type Node struct {
	ID          string         `json:"id"`
	Type        string         `json:"type"`
	Name        string         `json:"name"`
	Config      map[string]any `json:"config"`
	RetryPolicy *RetryPolicy   `json:"retry_policy,omitempty"`
	TimeoutMs   int            `json:"timeout_ms,omitempty"`
	Position    *Position      `json:"position,omitempty"`
}

// Edge represents a directed connection between two nodes
type Edge struct {
	ID        string `json:"id"`
	From      string `json:"from"`
	To        string `json:"to"`
	Condition string `json:"condition,omitempty"`
	Label     string `json:"label,omitempty"`
}

// Position stores x,y coordinates (UI metadata, not used by engine)
type Position struct {
	X float64 `json:"x"`
	Y float64 `json:"y"`
}

// RetryPolicy defines retry behavior for a node
type RetryPolicy struct {
	MaxAttempts     int    `json:"max_attempts"`
	BackoffMs       int    `json:"backoff_ms"`
	BackoffStrategy string `json:"backoff_strategy"` // "fixed" or "exponential"
}

// DefaultRetryPolicy returns the default retry policy
func DefaultRetryPolicy() *RetryPolicy {
	return &RetryPolicy{
		MaxAttempts:     3,
		BackoffMs:       1000,
		BackoffStrategy: "exponential",
	}
}

// GetConfig retrieves a config value by key with type assertion
func (n *Node) GetConfig(key string) (any, bool) {
	if n.Config == nil {
		return nil, false
	}
	val, ok := n.Config[key]
	return val, ok
}

// GetConfigString retrieves a string config value
func (n *Node) GetConfigString(key string) string {
	val, ok := n.GetConfig(key)
	if !ok {
		return ""
	}
	if s, ok := val.(string); ok {
		return s
	}
	return ""
}

// GetConfigInt retrieves an int config value
func (n *Node) GetConfigInt(key string) int {
	val, ok := n.GetConfig(key)
	if !ok {
		return 0
	}
	switch v := val.(type) {
	case int:
		return v
	case float64:
		return int(v)
	case int64:
		return int(v)
	default:
		return 0
	}
}

// GetConfigBool retrieves a bool config value
func (n *Node) GetConfigBool(key string) bool {
	val, ok := n.GetConfig(key)
	if !ok {
		return false
	}
	if b, ok := val.(bool); ok {
		return b
	}
	return false
}

// GetConfigMap retrieves a map config value
func (n *Node) GetConfigMap(key string) map[string]any {
	val, ok := n.GetConfig(key)
	if !ok {
		return nil
	}
	if m, ok := val.(map[string]any); ok {
		return m
	}
	return nil
}
