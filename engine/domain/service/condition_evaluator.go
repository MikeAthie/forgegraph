// Package service contains domain services for the ForgeGraph engine.
package service

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"

	"github.com/forgegraph/engine/domain/entity"
)

// ConditionEvaluator evaluates boolean expressions against workflow state.
// It supports a safe, limited expression language for conditional routing in branch nodes.
//
// Supported grammar:
//
//	expression     = comparison | boolean_literal | path
//	comparison     = path operator value
//	path           = key ("." key)*
//	operator       = "==" | "!=" | ">" | "<" | ">=" | "<="
//	value          = string_literal | number_literal | boolean_literal | null | path
//
// Example conditions:
//   - vars.score > 80
//   - node.http_1.output.status == 200
//   - vars.approved == true
//   - input.mode != "test"
type ConditionEvaluator struct{}

// NewConditionEvaluator creates a new condition evaluator
func NewConditionEvaluator() *ConditionEvaluator {
	return &ConditionEvaluator{}
}

// Evaluate parses and evaluates a condition expression against state.
// Returns the result value and any error encountered.
func (e *ConditionEvaluator) Evaluate(condition string, state *entity.State) (any, error) {
	condition = strings.TrimSpace(condition)
	if condition == "" {
		return nil, fmt.Errorf("empty condition")
	}

	// Check for boolean literals
	if condition == "true" {
		return true, nil
	}
	if condition == "false" {
		return false, nil
	}

	// Try to parse as comparison expression
	result, err := e.evaluateComparison(condition, state)
	if err == nil {
		return result, nil
	}

	// Try as simple path (truthy check)
	value := e.resolvePath(condition, state)
	return e.IsTruthy(value), nil
}

// EvaluateBool is a convenience method that evaluates a condition and returns a boolean
func (e *ConditionEvaluator) EvaluateBool(condition string, state *entity.State) (bool, error) {
	result, err := e.Evaluate(condition, state)
	if err != nil {
		return false, err
	}
	return e.IsTruthy(result), nil
}

// comparisonPattern matches expressions like "path == value"
// Operators: ==, !=, >=, <=, >, <
var comparisonPattern = regexp.MustCompile(`^([a-zA-Z_][a-zA-Z0-9_.*]*)\s*(==|!=|>=|<=|>|<)\s*(.+)$`)

// evaluateComparison handles expressions like "path == value"
func (e *ConditionEvaluator) evaluateComparison(condition string, state *entity.State) (bool, error) {
	matches := comparisonPattern.FindStringSubmatch(condition)

	if len(matches) != 4 {
		return false, fmt.Errorf("invalid comparison expression: %s", condition)
	}

	path := matches[1]
	operator := matches[2]
	valueStr := strings.TrimSpace(matches[3])

	// Resolve left side (path)
	leftValue := e.resolvePath(path, state)

	// Parse right side (literal or path)
	rightValue := e.parseValue(valueStr, state)

	// Perform comparison
	return e.compare(leftValue, operator, rightValue)
}

// resolvePath resolves a dotted path against state
// Supports: node.<id>.output, vars.<name>, input.<name>
func (e *ConditionEvaluator) resolvePath(path string, state *entity.State) any {
	// Try direct lookup first
	if val, exists := state.Get(path); exists {
		return val
	}

	// Try nested resolution
	parts := strings.Split(path, ".")
	if len(parts) < 2 {
		return nil
	}

	// Try progressively longer base keys
	for i := len(parts) - 1; i >= 1; i-- {
		baseKey := strings.Join(parts[:i], ".")
		if val, exists := state.Get(baseKey); exists {
			remaining := parts[i:]
			return navigatePath(val, remaining)
		}
	}

	return nil
}

// navigatePath navigates through nested maps/slices
func navigatePath(val any, path []string) any {
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

// parseValue parses a string value into appropriate type
func (e *ConditionEvaluator) parseValue(s string, state *entity.State) any {
	s = strings.TrimSpace(s)

	// Boolean literals
	if s == "true" {
		return true
	}
	if s == "false" {
		return false
	}

	// Null literals
	if s == "null" || s == "nil" {
		return nil
	}

	// String literals (double-quoted)
	if strings.HasPrefix(s, `"`) && strings.HasSuffix(s, `"`) && len(s) >= 2 {
		return s[1 : len(s)-1]
	}

	// String literals (single-quoted)
	if strings.HasPrefix(s, `'`) && strings.HasSuffix(s, `'`) && len(s) >= 2 {
		return s[1 : len(s)-1]
	}

	// Integer literals
	if i, err := strconv.ParseInt(s, 10, 64); err == nil {
		return i
	}

	// Float literals
	if f, err := strconv.ParseFloat(s, 64); err == nil {
		return f
	}

	// Try as path reference
	return e.resolvePath(s, state)
}

// compare performs the comparison operation
func (e *ConditionEvaluator) compare(left any, op string, right any) (bool, error) {
	// Handle nil comparisons
	if left == nil && right == nil {
		return op == "==", nil
	}
	if left == nil || right == nil {
		return op == "!=", nil
	}

	switch op {
	case "==":
		return e.equals(left, right), nil
	case "!=":
		return !e.equals(left, right), nil
	case ">", "<", ">=", "<=":
		return e.compareNumeric(left, op, right)
	default:
		return false, fmt.Errorf("unknown operator: %s", op)
	}
}

// equals compares two values for equality with type coercion
func (e *ConditionEvaluator) equals(left, right any) bool {
	// Try direct comparison
	if left == right {
		return true
	}

	// Boolean comparison with strings
	if leftBool, ok := left.(bool); ok {
		if rightStr, ok := right.(string); ok {
			return (leftBool && rightStr == "true") || (!leftBool && rightStr == "false")
		}
	}
	if rightBool, ok := right.(bool); ok {
		if leftStr, ok := left.(string); ok {
			return (rightBool && leftStr == "true") || (!rightBool && leftStr == "false")
		}
	}

	// Numeric comparison
	leftNum, leftOk := toFloat64(left)
	rightNum, rightOk := toFloat64(right)
	if leftOk && rightOk {
		return leftNum == rightNum
	}

	// String comparison as fallback
	return fmt.Sprintf("%v", left) == fmt.Sprintf("%v", right)
}

// compareNumeric performs numeric comparison
func (e *ConditionEvaluator) compareNumeric(left any, op string, right any) (bool, error) {
	leftNum, leftOk := toFloat64(left)
	rightNum, rightOk := toFloat64(right)

	if !leftOk || !rightOk {
		return false, fmt.Errorf("numeric comparison requires numeric values: %v %s %v", left, op, right)
	}

	switch op {
	case ">":
		return leftNum > rightNum, nil
	case "<":
		return leftNum < rightNum, nil
	case ">=":
		return leftNum >= rightNum, nil
	case "<=":
		return leftNum <= rightNum, nil
	default:
		return false, fmt.Errorf("unknown operator: %s", op)
	}
}

// IsTruthy returns whether a value is considered truthy
func (e *ConditionEvaluator) IsTruthy(val any) bool {
	if val == nil {
		return false
	}
	switch v := val.(type) {
	case bool:
		return v
	case int:
		return v != 0
	case int64:
		return v != 0
	case float64:
		return v != 0
	case string:
		return v != "" && v != "false" && v != "0"
	case []any:
		return len(v) > 0
	case map[string]any:
		return len(v) > 0
	default:
		return true
	}
}

// toFloat64 attempts to convert a value to float64
func toFloat64(val any) (float64, bool) {
	switch v := val.(type) {
	case float64:
		return v, true
	case float32:
		return float64(v), true
	case int:
		return float64(v), true
	case int64:
		return float64(v), true
	case int32:
		return float64(v), true
	case string:
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f, true
		}
	}
	return 0, false
}
