package executor

import (
	"context"
	"encoding/json"
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

type marketingExecutionState struct {
	Goal             string           `json:"goal"`
	Strategy         map[string]any   `json:"strategy"`
	ContentAssets    []map[string]any `json:"content_assets"`
	DistributionPlan map[string]any   `json:"distribution_plan"`
	Analytics        map[string]any   `json:"analytics"`
	Iteration        int              `json:"iteration"`
}

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
//   - expression_type: string - one of "static", "key_lookup", "json_path", "template", "state_patch"
//   - expression: string - the expression to evaluate
//   - output_key: string - where to store the result in vars (e.g., "result" -> vars.result)
//   - value: any - for static type, the value to set directly
//
// Expression types:
//   - static: Sets a literal value (use "value" config key)
//   - key_lookup: Gets a value from state by key path (e.g., "node.http_1.output.data")
//   - json_path: Basic JSONPath expressions ($.node.http_1.output.data)
//   - template: String template with {{key}} placeholders
//   - state_patch: Merges a partial object or appends array items into an existing state object
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
	case "state_patch":
		payload, updatedState, stepErr := e.evaluateStatePatch(node, state, outputKey)
		if stepErr != nil {
			return port.NewErrorResult(stepErr), nil
		}
		state.SetVar(outputKey, updatedState)
		return port.NewSuccessResult(payload), nil
	case "simulation_step":
		payload, updatedState, stepErr := e.evaluateSimulationStep(node, state)
		if stepErr != nil {
			return port.NewErrorResult(stepErr), nil
		}
		state.SetVar(outputKey, updatedState)
		return port.NewSuccessResult(payload), nil
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

func (e *TransformExecutor) evaluateStatePatch(node *entity.Node, state *entity.State, outputKey string) (map[string]any, map[string]any, error) {
	patchSource := strings.TrimSpace(node.GetConfigString("expression"))
	if patchSource == "" {
		return nil, nil, domain.NewValidationError("expression", "state_patch requires expression")
	}

	stateSource := strings.TrimSpace(node.GetConfigString("state_source"))
	if stateSource == "" {
		stateSource = "vars." + outputKey
	}

	currentValue, exists := e.resolveStateValue(stateSource, state)
	if !exists || currentValue == nil {
		currentValue = map[string]any{}
	}

	currentMap, err := cloneMapStringAny(currentValue)
	if err != nil {
		return nil, nil, domain.NewValidationError("state_source", fmt.Sprintf("state_patch requires object state at %s", stateSource))
	}

	patchValue, exists := e.resolveStateValue(patchSource, state)
	if !exists {
		return nil, nil, domain.NewValidationError("expression", fmt.Sprintf("state_patch source not found: %s", patchSource))
	}

	patchMode := strings.ToLower(strings.TrimSpace(node.GetConfigString("patch_mode")))
	if patchMode == "" {
		patchMode = "deep_merge"
	}
	targetPath := strings.TrimSpace(node.GetConfigString("target_path"))

	switch patchMode {
	case "deep_merge":
		patchMap, err := cloneMapStringAny(patchValue)
		if err != nil {
			return nil, nil, domain.NewValidationError("expression", "state_patch deep_merge requires object patch")
		}
		if targetPath == "" {
			deepMergeStringAnyMap(currentMap, patchMap)
		} else {
			existing, _ := getNestedValue(currentMap, targetPath)
			targetMap := map[string]any{}
			if existing != nil {
				targetMap, err = cloneMapStringAny(existing)
				if err != nil {
					return nil, nil, domain.NewValidationError("target_path", "state_patch deep_merge target must be an object")
				}
			}
			deepMergeStringAnyMap(targetMap, patchMap)
			setNestedValue(currentMap, targetPath, targetMap)
		}
	case "replace":
		if targetPath == "" {
			currentMap, err = cloneMapStringAny(patchValue)
			if err != nil {
				return nil, nil, domain.NewValidationError("expression", "state_patch replace without target_path requires object patch")
			}
		} else {
			setNestedValue(currentMap, targetPath, cloneTransformValue(patchValue))
		}
	case "append_array":
		if targetPath == "" {
			return nil, nil, domain.NewValidationError("target_path", "state_patch append_array requires target_path")
		}
		existingValue, _ := getNestedValue(currentMap, targetPath)
		existingItems, err := cloneToAnySlice(existingValue)
		if err != nil {
			return nil, nil, domain.NewValidationError("target_path", "state_patch append_array target must be an array")
		}
		appendItems, err := normalizeAppendItems(patchValue)
		if err != nil {
			return nil, nil, domain.NewValidationError("expression", err.Error())
		}
		setNestedValue(currentMap, targetPath, append(existingItems, appendItems...))
	default:
		return nil, nil, domain.NewValidationError("patch_mode", fmt.Sprintf("unknown state_patch mode: %s", patchMode))
	}

	payload := map[string]any{
		"patch_mode":   patchMode,
		"patch_source": patchSource,
		"state":        currentMap,
	}
	if targetPath != "" {
		payload["target_path"] = targetPath
	}
	return payload, currentMap, nil
}

func (e *TransformExecutor) evaluateSimulationStep(node *entity.Node, state *entity.State) (map[string]any, map[string]any, error) {
	role := strings.TrimSpace(node.GetConfigString("simulation_role"))
	if role == "" {
		role = strings.TrimSpace(node.GetConfigString("role"))
	}
	if role == "" {
		return nil, nil, domain.NewValidationError("simulation_role", "simulation_step requires simulation_role")
	}

	currentState, err := e.loadMarketingExecutionState(node, state)
	if err != nil {
		return nil, nil, err
	}

	if e.shouldFailSimulationStep(node, currentState, state) {
		return nil, nil, fmt.Errorf("simulated %s failure at iteration %d", role, currentState.Iteration+1)
	}

	updatedState, changes, err := e.applySimulationRole(role, currentState)
	if err != nil {
		return nil, nil, err
	}

	updatedMap, err := marketingExecutionStateToMap(updatedState)
	if err != nil {
		return nil, nil, err
	}

	payload := map[string]any{
		"role":      role,
		"state":     updatedMap,
		"changes":   changes,
		"iteration": updatedState.Iteration,
	}
	if department := strings.TrimSpace(node.GetConfigString("department")); department != "" {
		payload["department"] = department
	}
	return payload, updatedMap, nil
}

func (e *TransformExecutor) loadMarketingExecutionState(node *entity.Node, state *entity.State) (marketingExecutionState, error) {
	if existing, ok := state.Get("vars.execution_state"); ok {
		return marketingExecutionStateFromValue(existing)
	}
	if existing, ok := state.Get("input.execution_state"); ok {
		return marketingExecutionStateFromValue(existing)
	}

	goal := strings.TrimSpace(node.GetConfigString("default_goal"))
	if goal == "" {
		if inputGoal, ok := state.GetInput("goal"); ok {
			goal = strings.TrimSpace(fmt.Sprintf("%v", inputGoal))
		}
	}
	if goal == "" {
		goal = "Launch a deterministic digital marketing campaign."
	}

	return marketingExecutionState{
		Goal:          goal,
		Strategy:      nil,
		ContentAssets: make([]map[string]any, 0),
		Iteration:     0,
	}, nil
}

func (e *TransformExecutor) shouldFailSimulationStep(node *entity.Node, current marketingExecutionState, state *entity.State) bool {
	role := strings.TrimSpace(node.GetConfigString("simulation_role"))
	if role == "" {
		role = strings.TrimSpace(node.GetConfigString("role"))
	}
	if !strings.Contains(role, "content") {
		return false
	}

	if raw, ok := state.GetInput("force_content_failure"); ok {
		if enabled, ok := raw.(bool); ok && enabled {
			targetIteration := node.GetConfigInt("simulate_failure_on_iteration")
			if targetIteration <= 0 {
				return current.Iteration == 0
			}
			return current.Iteration+1 == targetIteration
		}
	}

	targetIteration := node.GetConfigInt("simulate_failure_on_iteration")
	return targetIteration > 0 && current.Iteration+1 == targetIteration
}

func (e *TransformExecutor) applySimulationRole(role string, current marketingExecutionState) (marketingExecutionState, map[string]any, error) {
	next := cloneMarketingExecutionState(current)
	switch role {
	case "strategy_agent":
		next.Strategy = map[string]any{
			"company":         "ForgeGraph Digital Marketing Co",
			"objective":       current.Goal,
			"primary_channel": "linkedin",
			"audience":        "B2B operators evaluating AI workflow tooling",
			"positioning":     fmt.Sprintf("Iteration %d message focused on replayable execution and observability.", current.Iteration+1),
			"content_pillars": []any{
				"reliability",
				"traceability",
				"measurable campaign loops",
			},
		}
		return next, map[string]any{"strategy": next.Strategy}, nil
	case "content_copywriter_specialist":
		asset := map[string]any{
			"asset_id":    fmt.Sprintf("copy-%d", current.Iteration+1),
			"specialist":  "copywriter_specialist",
			"channel":     "linkedin",
			"format":      "post",
			"headline":    fmt.Sprintf("Replayable growth loop v%d", current.Iteration+1),
			"body":        fmt.Sprintf("Campaign draft for %s.", current.Goal),
			"iteration":   current.Iteration + 1,
			"reviewed":    false,
			"department":  "content",
			"state_field": "content_assets",
		}
		next.ContentAssets = append(next.ContentAssets, asset)
		return next, map[string]any{"content_assets_added": []any{asset}}, nil
	case "content_editor_specialist":
		editorial := map[string]any{
			"asset_id":    fmt.Sprintf("editorial-%d", current.Iteration+1),
			"specialist":  "editor_specialist",
			"channel":     "email",
			"format":      "brief",
			"headline":    fmt.Sprintf("Editorial QA pass v%d", current.Iteration+1),
			"body":        "Reviewed copy for clarity, CTA alignment, and deterministic messaging.",
			"iteration":   current.Iteration + 1,
			"reviewed":    true,
			"department":  "content",
			"state_field": "content_assets",
		}
		next.ContentAssets = append(next.ContentAssets, editorial)
		return next, map[string]any{"content_assets_added": []any{editorial}}, nil
	case "content_agent":
		reviewedCount := 0
		for _, asset := range next.ContentAssets {
			if reviewed, ok := asset["reviewed"].(bool); ok && reviewed {
				reviewedCount++
			}
		}
		return next, map[string]any{
			"content_assets_total":     len(next.ContentAssets),
			"reviewed_assets_total":    reviewedCount,
			"department_checkpoint":    "content",
			"department_ready_to_ship": len(next.ContentAssets) > 0,
		}, nil
	case "distribution_agent":
		channels := make([]any, 0, len(next.ContentAssets))
		assetIDs := make([]any, 0, len(next.ContentAssets))
		for _, asset := range next.ContentAssets {
			channels = append(channels, asset["channel"])
			assetIDs = append(assetIDs, asset["asset_id"])
		}
		next.DistributionPlan = map[string]any{
			"asset_ids": assetIDs,
			"channels":  channels,
			"cadence":   fmt.Sprintf("day-%d morning publish window", current.Iteration+1),
			"owner":     "distribution_agent",
		}
		return next, map[string]any{"distribution_plan": next.DistributionPlan}, nil
	case "analytics_agent":
		next.Iteration = current.Iteration + 1
		impressions := 1200 + (next.Iteration * 250)
		clicks := 90 + (next.Iteration * 18)
		conversions := 12 + next.Iteration
		next.Analytics = map[string]any{
			"iteration":   next.Iteration,
			"impressions": impressions,
			"clicks":      clicks,
			"conversions": conversions,
			"ctr":         float64(clicks) / float64(impressions),
			"summary":     fmt.Sprintf("Iteration %d improved distribution efficiency.", next.Iteration),
		}
		return next, map[string]any{"analytics": next.Analytics, "iteration": next.Iteration}, nil
	default:
		return current, nil, domain.NewValidationError("simulation_role", fmt.Sprintf("unknown simulation role: %s", role))
	}
}

// evaluateKeyLookup retrieves a value from state by key path
func (e *TransformExecutor) evaluateKeyLookup(node *entity.Node, state *entity.State) (any, error) {
	expr, ok := node.Config["expression"].(string)
	if !ok {
		return nil, domain.NewValidationError("expression", "key_lookup requires expression")
	}

	val, _ := e.resolveStateValue(expr, state)
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

func (e *TransformExecutor) resolveStateValue(path string, state *entity.State) (any, bool) {
	val, exists := state.Get(path)
	if exists {
		return val, true
	}

	val = e.resolveNestedPath(path, state)
	if val == nil {
		return nil, false
	}
	return val, true
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
			return renderTemplateValue(val)
		}

		// Try nested path resolution
		if val := e.resolveNestedPath(key, state); val != nil {
			return renderTemplateValue(val)
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
			return renderTemplateValue(val)
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
						return renderTemplateValue(result)
					}
				}
			}
		}

		return ""
	})
}

func renderTemplateValue(value any) string {
	switch typed := value.(type) {
	case map[string]any, []any, []map[string]any:
		if encoded, err := json.MarshalIndent(typed, "", "  "); err == nil {
			return string(encoded)
		}
	}
	return fmt.Sprintf("%v", value)
}

func cloneMapStringAny(value any) (map[string]any, error) {
	switch typed := value.(type) {
	case nil:
		return map[string]any{}, nil
	case map[string]any:
		cloned := make(map[string]any, len(typed))
		for key, item := range typed {
			cloned[key] = cloneTransformValue(item)
		}
		return cloned, nil
	default:
		encoded, err := json.Marshal(value)
		if err != nil {
			return nil, err
		}
		var decoded map[string]any
		if err := json.Unmarshal(encoded, &decoded); err != nil {
			return nil, err
		}
		return decoded, nil
	}
}

func cloneToAnySlice(value any) ([]any, error) {
	switch typed := value.(type) {
	case nil:
		return []any{}, nil
	case []any:
		cloned := make([]any, len(typed))
		for i, item := range typed {
			cloned[i] = cloneTransformValue(item)
		}
		return cloned, nil
	case []map[string]any:
		cloned := make([]any, len(typed))
		for i, item := range typed {
			cloned[i] = cloneTransformValue(item)
		}
		return cloned, nil
	case []string:
		cloned := make([]any, len(typed))
		for i, item := range typed {
			cloned[i] = item
		}
		return cloned, nil
	default:
		return nil, fmt.Errorf("value is not an array")
	}
}

func normalizeAppendItems(value any) ([]any, error) {
	if value == nil {
		return []any{}, nil
	}
	switch typed := value.(type) {
	case []any, []map[string]any:
		return cloneToAnySlice(typed)
	default:
		return []any{cloneTransformValue(value)}, nil
	}
}

func cloneTransformValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		cloned := make(map[string]any, len(typed))
		for key, item := range typed {
			cloned[key] = cloneTransformValue(item)
		}
		return cloned
	case []any:
		cloned := make([]any, len(typed))
		for i, item := range typed {
			cloned[i] = cloneTransformValue(item)
		}
		return cloned
	case []map[string]any:
		cloned := make([]map[string]any, len(typed))
		for i, item := range typed {
			cloned[i] = cloneTransformValue(item).(map[string]any)
		}
		return cloned
	case []string:
		cloned := make([]any, len(typed))
		for i, item := range typed {
			cloned[i] = item
		}
		return cloned
	default:
		return value
	}
}

func deepMergeStringAnyMap(target map[string]any, patch map[string]any) {
	for key, patchValue := range patch {
		existingValue, exists := target[key]
		existingMap, existingIsMap := existingValue.(map[string]any)
		patchMap, patchIsMap := patchValue.(map[string]any)
		if exists && existingIsMap && patchIsMap {
			deepMergeStringAnyMap(existingMap, patchMap)
			target[key] = existingMap
			continue
		}
		target[key] = cloneTransformValue(patchValue)
	}
}

func getNestedValue(root map[string]any, path string) (any, bool) {
	if strings.TrimSpace(path) == "" {
		return root, true
	}
	current := any(root)
	for _, part := range strings.Split(path, ".") {
		if strings.TrimSpace(part) == "" {
			continue
		}
		nextMap, ok := current.(map[string]any)
		if !ok {
			return nil, false
		}
		next, exists := nextMap[part]
		if !exists {
			return nil, false
		}
		current = next
	}
	return current, true
}

func setNestedValue(root map[string]any, path string, value any) {
	if strings.TrimSpace(path) == "" {
		return
	}
	parts := strings.Split(path, ".")
	current := root
	for index, part := range parts {
		if strings.TrimSpace(part) == "" {
			continue
		}
		if index == len(parts)-1 {
			current[part] = value
			return
		}
		next, ok := current[part].(map[string]any)
		if !ok || next == nil {
			next = map[string]any{}
			current[part] = next
		}
		current = next
	}
}

func marketingExecutionStateFromValue(value any) (marketingExecutionState, error) {
	if value == nil {
		return marketingExecutionState{
			ContentAssets: make([]map[string]any, 0),
		}, nil
	}

	encoded, err := json.Marshal(value)
	if err != nil {
		return marketingExecutionState{}, err
	}

	var executionState marketingExecutionState
	if err := json.Unmarshal(encoded, &executionState); err != nil {
		return marketingExecutionState{}, err
	}
	if executionState.ContentAssets == nil {
		executionState.ContentAssets = make([]map[string]any, 0)
	}
	return executionState, nil
}

func marketingExecutionStateToMap(state marketingExecutionState) (map[string]any, error) {
	encoded, err := json.Marshal(state)
	if err != nil {
		return nil, err
	}

	var payload map[string]any
	if err := json.Unmarshal(encoded, &payload); err != nil {
		return nil, err
	}
	return payload, nil
}

func cloneMarketingExecutionState(state marketingExecutionState) marketingExecutionState {
	cloned := marketingExecutionState{
		Goal:          state.Goal,
		Iteration:     state.Iteration,
		ContentAssets: make([]map[string]any, len(state.ContentAssets)),
	}
	if state.Strategy != nil {
		cloned.Strategy = cloneStringAnyMap(state.Strategy)
	}
	if state.DistributionPlan != nil {
		cloned.DistributionPlan = cloneStringAnyMap(state.DistributionPlan)
	}
	if state.Analytics != nil {
		cloned.Analytics = cloneStringAnyMap(state.Analytics)
	}
	for i, asset := range state.ContentAssets {
		cloned.ContentAssets[i] = cloneStringAnyMap(asset)
	}
	return cloned
}

func cloneStringAnyMap(value map[string]any) map[string]any {
	if value == nil {
		return nil
	}
	cloned := make(map[string]any, len(value))
	for key, item := range value {
		cloned[key] = item
	}
	return cloned
}
