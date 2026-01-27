package executor

import (
	"context"
	"fmt"
	"strings"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// MemoryExecutor handles memory nodes that read/write from a shared memory store.
type MemoryExecutor struct {
	store port.MemoryStore
}

// NewMemoryExecutor creates a new memory executor with the given store.
func NewMemoryExecutor(store port.MemoryStore) *MemoryExecutor {
	return &MemoryExecutor{store: store}
}

// NodeType returns the node type this executor handles.
func (e *MemoryExecutor) NodeType() string {
	return string(value.NodeTypeMemory)
}

// Execute reads/writes values in the memory store.
//
// Config options:
//   - action: string - "get", "set", or "delete" (default: "get")
//   - key: string - key to read/write
//   - namespace: string - optional namespace prefix
//   - namespace_path: string - optional state path for namespace (overrides namespace)
//   - value: any - static value to set (for set)
//   - value_path: string - state path to resolve value (for set)
//   - value_template: string - template string with {{key}} placeholders (for set)
//   - ttl_seconds: int - optional TTL in seconds (for set)
//
// Output:
//   - action: string
//   - namespace: string
//   - key: string
//   - found/value (get)
//   - stored/ttl_seconds (set)
//   - deleted (delete)
func (e *MemoryExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	if e.store == nil {
		return port.NewErrorResult(domain.NewValidationError("store", "memory store not configured")), nil
	}

	action := strings.ToLower(node.GetConfigString("action"))
	if action == "" {
		action = "get"
	}

	key := strings.TrimSpace(node.GetConfigString("key"))
	if key == "" {
		return port.NewErrorResult(domain.NewValidationError("key", "memory node requires key")), nil
	}

	namespace := e.resolveNamespace(node, state)

	switch action {
	case "get":
		val, found, err := e.store.Get(ctx, namespace, key)
		if err != nil {
			return port.NewErrorResult(err), nil
		}
		output := map[string]any{
			"action":    action,
			"namespace": namespace,
			"key":       key,
			"found":     found,
		}
		if found {
			output["value"] = val
		}
		return port.NewSuccessResult(output), nil

	case "set":
		value, err := e.resolveValue(node, state)
		if err != nil {
			return port.NewErrorResult(err), nil
		}
		ttlSeconds := node.GetConfigInt("ttl_seconds")
		if err := e.store.Set(ctx, namespace, key, value, ttlSeconds); err != nil {
			return port.NewErrorResult(err), nil
		}
		output := map[string]any{
			"action":     action,
			"namespace":  namespace,
			"key":        key,
			"stored":     true,
			"ttl_seconds": ttlSeconds,
		}
		return port.NewSuccessResult(output), nil

	case "delete":
		deleted, err := e.store.Delete(ctx, namespace, key)
		if err != nil {
			return port.NewErrorResult(err), nil
		}
		output := map[string]any{
			"action":    action,
			"namespace": namespace,
			"key":       key,
			"deleted":   deleted,
		}
		return port.NewSuccessResult(output), nil

	default:
		return port.NewErrorResult(domain.NewValidationError("action", fmt.Sprintf("unsupported action: %s", action))), nil
	}
}

func (e *MemoryExecutor) resolveNamespace(node *entity.Node, state *entity.State) string {
	if namespacePath := strings.TrimSpace(node.GetConfigString("namespace_path")); namespacePath != "" {
		if val, ok := state.Get(namespacePath); ok {
			resolved := strings.TrimSpace(fmt.Sprintf("%v", val))
			if resolved != "" {
				return e.applyNamespacePrefix(node, resolved)
			}
		}
		if resolved := resolveNestedPath(namespacePath, state); resolved != nil {
			resolvedStr := strings.TrimSpace(fmt.Sprintf("%v", resolved))
			if resolvedStr != "" {
				return e.applyNamespacePrefix(node, resolvedStr)
			}
		}
	}

	if namespace := strings.TrimSpace(node.GetConfigString("namespace")); namespace != "" {
		return e.applyNamespacePrefix(node, namespace)
	}

	return e.applyNamespacePrefix(node, "global")
}

func (e *MemoryExecutor) applyNamespacePrefix(node *entity.Node, namespace string) string {
	prefix := strings.TrimSpace(node.GetConfigString("namespace_prefix"))
	if prefix == "" {
		return namespace
	}
	if namespace == "" {
		return prefix
	}
	return prefix + ":" + namespace
}

func (e *MemoryExecutor) resolveValue(node *entity.Node, state *entity.State) (any, error) {
	if valuePath := strings.TrimSpace(node.GetConfigString("value_path")); valuePath != "" {
		if val, ok := state.Get(valuePath); ok {
			return val, nil
		}
		if resolved := resolveNestedPath(valuePath, state); resolved != nil {
			return resolved, nil
		}
		return nil, domain.NewValidationError("value_path", "value_path did not resolve to a value")
	}

	if valueTemplate := node.GetConfigString("value_template"); valueTemplate != "" {
		return SubstituteTemplate(valueTemplate, state), nil
	}

	if value, ok := node.Config["value"]; ok {
		return value, nil
	}

	return nil, domain.NewValidationError("value", "memory set requires value, value_path, or value_template")
}

func resolveNestedPath(path string, state *entity.State) any {
	parts := strings.Split(path, ".")
	if len(parts) < 2 {
		return nil
	}

	for i := len(parts) - 1; i >= 1; i-- {
		baseKey := strings.Join(parts[:i], ".")
		if val, exists := state.Get(baseKey); exists {
			remaining := parts[i:]
			return navigateValue(val, remaining)
		}
	}

	return nil
}
