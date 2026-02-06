package executor

import (
	"context"
	"fmt"
	"regexp"
	"strconv"
	"strings"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// TransformExecutor handles transform nodes that manipulate state data.
// Transform nodes evaluate expressions and store results in state variables.
type TransformExecutor struct{}

// NewTransformExecutor creates a new transform executor
func NewTransformExecutor() *TransformExecutor {
	return &TransformExecutor{}
}

// NodeType returns the node type this executor handles
func (e *TransformExecutor) NodeType() string {
	return string(value.NodeTypeTransform)
}

// Execute evaluates the transform expression and stores the result.
//
// Config options:
//   - expression_type: string - one of "static", "key_lookup", "json_path", "template"
//   - expression: string - the expression to evaluate
//   - output_key: string - where to store the result in vars (e.g., "result" -> vars.result)
//   - value: any - for static type, the value to set directly
//
// Expression types:
//   - static: Sets a literal value (use "value" config key)
//   - key_lookup: Gets a value from state by key path (e.g., "node.http_1.output.data")
//   - json_path: Basic JSONPath expressions ($.node.http_1.output.data)
//   - template: String template with {{key}} placeholders
func (e *TransformExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	// Get output key (required)
	outputKey, ok := node.Config["output_key"].(string)
	if !ok || outputKey == "" {
		return port.NewErrorResult(domain.NewValidationError("output_key", "transform node requires output_key")), nil
	}

	// Get expression type (default to key_lookup)
	exprType, _ := node.Config["expression_type"].(string)
	if exprType == "" {
		exprType = "key_lookup"
	}

	var result any
	var err error

	switch exprType {
	case "static":
		result = node.Config["value"]
	case "key_lookup":
		result, err = e.evaluateKeyLookup(node, state)
	case "json_path":
		result, err = e.evaluateJSONPath(node, state)
	case "template":
		result, err = e.evaluateTemplate(node, state)
	default:
		return port.NewErrorResult(domain.NewValidationError("expression_type", fmt.Sprintf("unknown expression_type: %s", exprType))), nil
	}

	if err != nil {
		return port.NewErrorResult(err), nil
	}

	// Store result in state
	state.SetVar(outputKey, result)

	return port.NewSuccessResult(result), nil
}

// evaluateKeyLookup retrieves a value from state by key path
func (e *TransformExecutor) evaluateKeyLookup(node *entity.Node, state *entity.State) (any, error) {
	expr, ok := node.Config["expression"].(string)
	if !ok {
		return nil, domain.NewValidationError("expression", "key_lookup requires expression")
	}

	val, exists := state.Get(expr)
	if !exists {
		// Try to resolve as a nested path (e.g., "node.http_1.output.data")
		val = e.resolveNestedPath(expr, state)
	}

	return val, nil
}

// resolveNestedPath handles nested object access in state values
func (e *TransformExecutor) resolveNestedPath(path string, state *entity.State) any {
	parts := strings.Split(path, ".")
	if len(parts) < 2 {
		return nil
	}

	// Try progressively longer base keys
	for i := len(parts) - 1; i >= 1; i-- {
		baseKey := strings.Join(parts[:i], ".")
		if val, exists := state.Get(baseKey); exists {
			// Navigate remaining parts
			remaining := parts[i:]
			return navigateValue(val, remaining)
		}
	}

	return nil
}

// navigateValue navigates through nested maps/slices
func navigateValue(val any, path []string) any {
	current := val
	for _, key := range path {
		switch v := current.(type) {
		case map[string]any:
			current = v[key]
		case map[string]string:
			current = v[key]
		case []any:
			idx, err := strconv.Atoi(key)
			if err != nil || idx < 0 || idx >= len(v) {
				return nil
			}
			current = v[idx]
		default:
			return nil
		}
		if current == nil {
			return nil
		}
	}
	return current
}

// evaluateJSONPath handles basic JSONPath expressions
func (e *TransformExecutor) evaluateJSONPath(node *entity.Node, state *entity.State) (any, error) {
	expr, ok := node.Config["expression"].(string)
	if !ok {
		return nil, domain.NewValidationError("expression", "json_path requires expression")
	}

	// Handle basic JSONPath: $.node.xxx.output.yyy
	if strings.HasPrefix(expr, "$.") {
		// Convert $.key.path to key.path
		path := strings.TrimPrefix(expr, "$.")
		return e.resolveNestedPath(path, state), nil
	}

	return nil, domain.NewValidationError("expression", fmt.Sprintf("unsupported JSONPath expression: %s", expr))
}

// evaluateTemplate substitutes {{key}} placeholders in a template string
func (e *TransformExecutor) evaluateTemplate(node *entity.Node, state *entity.State) (any, error) {
	expr, ok := node.Config["expression"].(string)
	if !ok {
		return nil, domain.NewValidationError("expression", "template requires expression")
	}

	// Find all {{key}} patterns
	re := regexp.MustCompile(`\{\{([^}]+)\}\}`)
	result := re.ReplaceAllStringFunc(expr, func(match string) string {
		// Extract key from {{key}}
		key := strings.TrimPrefix(strings.TrimSuffix(match, "}}"), "{{")
		key = strings.TrimSpace(key)

		// Look up value in state
		if val, exists := state.Get(key); exists {
			return fmt.Sprintf("%v", val)
		}

		// Try nested path resolution
		if val := e.resolveNestedPath(key, state); val != nil {
			return fmt.Sprintf("%v", val)
		}

		// Return empty string for missing values
		return ""
	})

	return result, nil
}

// SubstituteTemplate is a utility function for template substitution (used by other executors)
func SubstituteTemplate(template string, state *entity.State) string {
	return SubstituteTemplateWithExtras(template, state, nil)
}

// SubstituteTemplateWithExtras substitutes template placeholders with state values and optional extras.
func SubstituteTemplateWithExtras(template string, state *entity.State, extras map[string]string) string {
	re := regexp.MustCompile(`\{\{([^}]+)\}\}`)
	return re.ReplaceAllStringFunc(template, func(match string) string {
		key := strings.TrimPrefix(strings.TrimSuffix(match, "}}"), "{{")
		key = strings.TrimSpace(key)

		if extras != nil {
			if val, exists := extras[key]; exists {
				return val
			}
		}

		if val, exists := state.Get(key); exists {
			return fmt.Sprintf("%v", val)
		}

		// Try resolving as nested path
		parts := strings.Split(key, ".")
		if len(parts) >= 2 {
			// Try progressively longer base keys
			for i := len(parts) - 1; i >= 1; i-- {
				baseKey := strings.Join(parts[:i], ".")
				if val, exists := state.Get(baseKey); exists {
					remaining := parts[i:]
					if result := navigateValue(val, remaining); result != nil {
						return fmt.Sprintf("%v", result)
					}
				}
			}
		}

		return ""
	})
}
