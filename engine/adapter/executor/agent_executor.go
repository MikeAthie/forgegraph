package executor

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/forgegraph/engine/adapter/tool"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

const (
	defaultAgentMaxSteps     = 6
	defaultAgentTemperature  = 0.2
	defaultAgentMaxTokens    = 800
	defaultAgentTokenBudget  = 0
	agentStopReasonFinal     = "final_answer"
	agentStopReasonMaxSteps  = "max_steps_reached"
	agentStopReasonMaxTools  = "max_tool_calls_reached"
	agentStopReasonToolDeny  = "tool_policy_denied"
	agentStopReasonApproval  = "approval_required"
	agentStreamEventStarted  = "agent.step.started"
	agentStreamEventDecision = "agent.step.completed"
	agentStreamEventCalled   = "agent.tool.called"
	agentStreamEventDone     = "agent.tool.completed"
	agentStreamEventFinish   = "agent.completed"
)

type agentResumeState struct {
	StepIndex     int
	ToolCallCount int
	PendingTool   string
	PendingInput  any
	Steps         []map[string]any
	Usage         *LLMUsage
}

type agentToolInvoker interface {
	Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error)
}

type agentDecision struct {
	Action      string `json:"action"`
	FinalAnswer string `json:"final_answer,omitempty"`
	Tool        string `json:"tool,omitempty"`
	ToolInput   any    `json:"tool_input,omitempty"`
}

// AgentExecutor runs a bounded model-to-tool loop inside one node.
type AgentExecutor struct {
	client      LLMClient
	toolInvoker agentToolInvoker
	registry    *tool.Registry
}

// NewAgentExecutor creates an agent executor using the shared tool registry.
func NewAgentExecutor(client LLMClient, registry *tool.Registry, resolver CredentialResolver) *AgentExecutor {
	return NewAgentExecutorWithRuntimeMode(client, registry, resolver, tool.RuntimeModeSelfHosted)
}

// NewAgentExecutorWithRuntimeMode creates an agent executor using the shared tool registry and runtime mode.
func NewAgentExecutorWithRuntimeMode(client LLMClient, registry *tool.Registry, resolver CredentialResolver, runtimeMode string) *AgentExecutor {
	agent := NewAgentExecutorWithToolInvoker(
		client,
		NewToolExecutorWithResolverAndRuntimeMode(registry, resolver, runtimeMode),
	)
	agent.registry = registry
	return agent
}

// NewAgentExecutorWithToolInvoker creates an agent executor with a custom tool invoker.
func NewAgentExecutorWithToolInvoker(client LLMClient, toolInvoker agentToolInvoker) *AgentExecutor {
	return &AgentExecutor{
		client:      client,
		toolInvoker: toolInvoker,
	}
}

// NodeType returns the node type this executor handles.
func (e *AgentExecutor) NodeType() string {
	return string(value.NodeTypeAgent)
}

// Execute runs the bounded internal loop for an agent node.
func (e *AgentExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	if e.client == nil {
		return port.NewErrorResult(domain.NewValidationError("client", "agent executor requires LLM client")), nil
	}

	allowedTools := normalizeAgentToolList(node.Config["tools"])
	if len(allowedTools) == 0 {
		return port.NewErrorResult(domain.NewValidationError("tools", "agent node requires at least one tool")), nil
	}

	model := strings.TrimSpace(node.GetConfigString("model"))
	if model == "" {
		return port.NewErrorResult(domain.NewValidationError("model", "agent node requires model")), nil
	}

	provider := strings.ToLower(strings.TrimSpace(node.GetConfigString("provider")))
	credentialID := strings.TrimSpace(node.GetConfigString("credential_id"))
	if provider == "" && credentialID == "" {
		provider = "openai"
	}
	if provider == "" {
		provider = "openai"
	}
	var toolSpecs []ToolSpec
	if provider == "openai" && e.registry != nil {
		specs, err := e.buildToolSpecs(allowedTools)
		if err != nil {
			log.Printf("agent executor: falling back to legacy tool planning for provider %s: %v", provider, err)
		} else {
			toolSpecs = specs
		}
	}

	runCtx := port.RunContextFrom(ctx)
	if validation := validateLLMPolicy(runCtx, provider, model); validation != nil {
		return port.NewErrorResult(validation), nil
	}
	curatedContext, err := resolveCuratedContext(node, state)
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	maxSteps := getConfigInt(node.Config["max_steps"])
	if maxSteps <= 0 {
		maxSteps = defaultAgentMaxSteps
	}
	maxToolCalls := getConfigInt(node.Config["max_tool_calls"])
	if maxToolCalls <= 0 {
		maxToolCalls = maxSteps
	}
	if maxToolCalls > maxSteps {
		maxToolCalls = maxSteps
	}

	temperature := defaultAgentTemperature
	if temp, ok := node.Config["temperature"].(float64); ok {
		temperature = temp
	}

	maxTokens := getConfigInt(node.Config["max_tokens"])
	if maxTokens <= 0 {
		maxTokens = defaultAgentMaxTokens
	}
	tokenBudget := getConfigInt(node.Config["token_budget"])
	if tokenBudget < 0 {
		tokenBudget = defaultAgentTokenBudget
	}

	systemPrompt := SubstituteTemplate(node.GetConfigString("system_prompt"), state)
	approvalRequired := make(map[string]struct{})
	for _, toolName := range normalizeAgentToolList(node.Config["approval_required_tools"]) {
		approvalRequired[toolName] = struct{}{}
	}

	stateSnapshot := state.SnapshotNested()
	var vectorMemories []port.MemoryChunk
	if curatedContext != nil && runCtx != nil && runCtx.MemoryConfig != nil && runCtx.MemoryConfig.Tier3.Enabled && runCtx.MemoryRetriever != nil {
		tenantID := port.TenantIDFrom(ctx)
		query := buildAgentContextQuery(node, stateSnapshot)
		if tenantID != "" && query != "" {
			req := port.MemoryRetrieveRequest{
				TenantID:       tenantID,
				Query:          query,
				TopK:           runCtx.MemoryConfig.Tier3.TopK,
				Threshold:      runCtx.MemoryConfig.Tier3.Threshold,
				RecencyWeight:  runCtx.MemoryConfig.Tier3.RecencyWeight,
				EmbeddingModel: runCtx.MemoryConfig.Tier3.EmbeddingModel,
			}
			retrieveCtx, cancel := context.WithTimeout(ctx, 100*time.Millisecond)
			response, err := runCtx.MemoryRetriever.Retrieve(retrieveCtx, req)
			cancel()
			if err != nil {
				log.Printf("memory_retrieve_failed: %v", err)
			} else {
				vectorMemories = response.Chunks
			}
		}
	}
	var buffer *entity.MessageBuffer
	var summary *entity.Summary
	if curatedContext != nil && runCtx != nil {
		summary = runCtx.CurrentSummary
		if runCtx.MemoryConfig != nil && runCtx.MemoryConfig.Tier1.AutoPrepend {
			buffer = runCtx.MemoryBuffer
		}
	}
	memoryContextBlock := buildAgentMemoryBlock(curatedContext, buffer, summary, vectorMemories)
	memoryContextTrace := buildMemoryContextTrace(curatedContext, buffer, summary, vectorMemories)
	steps := make([]map[string]any, 0, maxSteps)
	toolCallCount := 0
	var usageTotals *LLMUsage
	var budgetCompletion *tokenBudgetCompletion
	budgetTracker := newBudgetTracker(time.Now())
	startStepIndex := 1

	if resumeState, ok := loadAgentResumeState(state, node.ID); ok {
		steps = resumeState.Steps
		toolCallCount = resumeState.ToolCallCount
		usageTotals = resumeState.Usage
		startStepIndex = resumeState.StepIndex + 1

		if strings.TrimSpace(resumeState.PendingTool) != "" {
			resumedStep, err := e.executeApprovedToolCall(
				ctx,
				node,
				state,
				resumeState.StepIndex,
				resumeState.PendingTool,
				resumeState.PendingInput,
			)
			if err != nil {
				return port.NewErrorResult(err), nil
			}
			steps = upsertAgentStep(steps, resumedStep)
			toolCallCount++
			clearAgentResumeState(state, node.ID)
		}
		clearAgentApprovalDecision(state, node.ID)
		stateSnapshot = state.SnapshotNested()
	}

	for stepIndex := startStepIndex; stepIndex <= maxSteps; stepIndex++ {
		emitAgentStreamEvent(ctx, map[string]any{
			"event":      agentStreamEventStarted,
			"step_index": stepIndex,
		})

		request := &LLMRequest{
			Prompt:       buildAgentPrompt(node, stateSnapshot, allowedTools, steps, memoryContextBlock),
			Provider:     provider,
			Model:        model,
			Temperature:  temperature,
			MaxTokens:    maxTokens,
			SystemPrompt: systemPrompt,
			CredentialID: credentialID,
			TenantID:     port.TenantIDFrom(ctx),
		}
		if runCtx != nil && runCtx.TrackLLMCall != nil {
			if err := runCtx.TrackLLMCall(); err != nil {
				return port.NewErrorResult(err), nil
			}
		}
		if provider == "openai" && len(toolSpecs) > 0 {
			request.Tools = toolSpecs
			request.ToolChoice = "auto"
		}

		response, err := e.client.Complete(ctx, request)
		if err != nil {
			if domain.IsRetryable(err) {
				return port.NewErrorResult(err), nil
			}
			return port.NewErrorResult(fmt.Errorf("agent LLM call failed: %w", err)), nil
		}
		if response == nil {
			return port.NewErrorResult(domain.NewRetryableError(fmt.Errorf("agent LLM call failed: empty response"), "agent LLM API error")), nil
		}
		accumulateUsage(&usageTotals, response.Usage)

		decision, err := deriveAgentDecision(provider, response)
		if err != nil {
			return port.NewErrorResult(domain.NewValidationError("agent_response", err.Error())), nil
		}

		step := map[string]any{
			"step_index": stepIndex,
			"action":     decision.Action,
		}
		if response.Model != "" {
			step["response_model"] = response.Model
		}
		if response.FinishReason != "" {
			step["finish_reason"] = response.FinishReason
		}
		if response.Usage != nil {
			step["usage"] = usageMap(response.Usage)
		}

		switch decision.Action {
		case "final_answer":
			step["final_answer"] = decision.FinalAnswer
			if tokenBudget > 0 {
				action, nudgeMessage, completion := budgetTracker.check(tokenBudget, usageTotalTokens(usageTotals), time.Now())
				if action == "continue" {
					step["budget"] = map[string]any{
						"action":             "continue",
						"continuation_count": budgetTracker.ContinuationCount,
						"turn_tokens":        usageTotalTokens(usageTotals),
						"budget":             tokenBudget,
					}
					step["draft_final_answer"] = decision.FinalAnswer
					step["continuation_nudge"] = nudgeMessage
					steps = append(steps, step)
					emitAgentStreamEvent(ctx, map[string]any{
						"event":              agentStreamEventDecision,
						"step_index":         stepIndex,
						"action":             "continue_budget",
						"continuation_count": budgetTracker.ContinuationCount,
					})
					stateSnapshot = state.SnapshotNested()
					continue
				}
				if completion != nil {
					budgetCompletion = completion
					step["budget"] = map[string]any{
						"action":              "stop",
						"continuation_count":  completion.ContinuationCount,
						"pct":                 completion.Pct,
						"turn_tokens":         completion.TurnTokens,
						"budget":              completion.Budget,
						"diminishing_returns": completion.DiminishingReturns,
						"duration_ms":         completion.DurationMs,
					}
				}
			}
			steps = append(steps, step)
			emitAgentStreamEvent(ctx, map[string]any{
				"event":       agentStreamEventDecision,
				"step_index":  stepIndex,
				"action":      decision.Action,
				"stop_reason": agentStopReasonFinal,
			})
			output := buildAgentOutput(node, provider, model, decision.FinalAnswer, agentStopReasonFinal, stepIndex, toolCallCount, steps, usageTotals, memoryContextTrace)
			if budgetCompletion != nil {
				output["token_budget_completion"] = tokenBudgetCompletionMap(budgetCompletion)
			}
			emitAgentStreamEvent(ctx, map[string]any{
				"event":       agentStreamEventFinish,
				"step_index":  stepIndex,
				"stop_reason": agentStopReasonFinal,
			})
			return port.NewSuccessResult(output), nil

		case "tool_call":
			toolName := strings.TrimSpace(decision.Tool)
			step["tool"] = toolName
			step["tool_input"] = decision.ToolInput

			if _, ok := approvalRequired[toolName]; ok {
				step["approval_required"] = true
				steps = append(steps, step)
				state.Set(agentResumeStateKey(node.ID), map[string]any{
					"step_index":      stepIndex,
					"tool_call_count": toolCallCount,
					"pending_tool":    toolName,
					"pending_input":   decision.ToolInput,
					"steps":           steps,
					"usage":           usageMap(usageTotals),
				})
				agentTrace := buildAgentOutput(
					node,
					provider,
					model,
					"",
					agentStopReasonApproval,
					stepIndex,
					toolCallCount,
					steps,
					usageTotals,
					memoryContextTrace,
				)
				agentTrace["approval_pending"] = true
				emitAgentStreamEvent(ctx, map[string]any{
					"event":       agentStreamEventDecision,
					"step_index":  stepIndex,
					"action":      decision.Action,
					"tool":        toolName,
					"stop_reason": agentStopReasonApproval,
				})
				return port.NewPauseResult(map[string]any{
					"prompt_message":  fmt.Sprintf("Approve agent tool call '%s'", toolName),
					"required_fields": []string{},
					"node_id":         node.ID,
					"node_name":       node.Name,
					"tool":            toolName,
					"tool_input":      decision.ToolInput,
					"step_index":      stepIndex,
					"agent_trace":     agentTrace,
				}), nil
			}

			if !containsTool(allowedTools, toolName) {
				step["error"] = "tool not allowed"
				steps = append(steps, step)
				emitAgentStreamEvent(ctx, map[string]any{
					"event":       agentStreamEventDecision,
					"step_index":  stepIndex,
					"action":      decision.Action,
					"tool":        toolName,
					"stop_reason": agentStopReasonToolDeny,
				})
				return port.NewSuccessResult(buildAgentOutput(node, provider, model, "", agentStopReasonToolDeny, stepIndex, toolCallCount, steps, usageTotals, memoryContextTrace)), nil
			}

			if toolCallCount >= maxToolCalls {
				step["error"] = "tool call budget exceeded"
				steps = append(steps, step)
				emitAgentStreamEvent(ctx, map[string]any{
					"event":       agentStreamEventDecision,
					"step_index":  stepIndex,
					"action":      decision.Action,
					"tool":        toolName,
					"stop_reason": agentStopReasonMaxTools,
				})
				return port.NewSuccessResult(buildAgentOutput(node, provider, model, "", agentStopReasonMaxTools, stepIndex, toolCallCount, steps, usageTotals, memoryContextTrace)), nil
			}

			if e.toolInvoker == nil {
				return port.NewErrorResult(domain.NewValidationError("tool", "agent executor requires tool invoker")), nil
			}

			emitAgentStreamEvent(ctx, map[string]any{
				"event":      agentStreamEventCalled,
				"step_index": stepIndex,
				"tool":       toolName,
			})

			toolNode := &entity.Node{
				ID:   fmt.Sprintf("%s__tool__%d", node.ID, stepIndex),
				Type: string(value.NodeTypeTool),
				Name: toolName,
				Config: map[string]any{
					"tool":  toolName,
					"input": decision.ToolInput,
				},
			}

			toolResult, err := e.toolInvoker.Execute(ctx, toolNode, state)
			if err != nil {
				return port.NewErrorResult(fmt.Errorf("agent tool call failed: %w", err)), nil
			}
			if toolResult == nil {
				return port.NewErrorResult(domain.NewRetryableError(fmt.Errorf("agent tool call failed: empty result"), "agent tool error")), nil
			}
			if toolResult.Error != nil {
				return port.NewErrorResult(fmt.Errorf("agent tool call failed: %w", toolResult.Error)), nil
			}

			toolCallCount++
			step["tool_output"] = toolResult.Output
			steps = append(steps, step)
			emitAgentStreamEvent(ctx, map[string]any{
				"event":      agentStreamEventDone,
				"step_index": stepIndex,
				"tool":       toolName,
				"status":     "ok",
			})

		default:
			return port.NewErrorResult(domain.NewValidationError("action", "agent action must be final_answer or tool_call")), nil
		}
	}

	output := buildAgentOutput(node, provider, model, "", agentStopReasonMaxSteps, maxSteps, toolCallCount, steps, usageTotals, memoryContextTrace)
	emitAgentStreamEvent(ctx, map[string]any{
		"event":       agentStreamEventFinish,
		"step_index":  maxSteps,
		"stop_reason": agentStopReasonMaxSteps,
	})
	return port.NewSuccessResult(output), nil
}

func buildAgentPrompt(node *entity.Node, stateSnapshot map[string]any, allowedTools []string, steps []map[string]any, memoryContextBlock string) string {
	var builder strings.Builder
	builder.WriteString("You are executing inside a ForgeGraph agent node.\n")
	builder.WriteString("You must return a single JSON object with one of these shapes:\n")
	builder.WriteString(`{"action":"final_answer","final_answer":"..."}` + "\n")
	builder.WriteString(`{"action":"tool_call","tool":"tool_name","tool_input":{}}` + "\n")
	builder.WriteString("Rules:\n")
	builder.WriteString("- Do not use markdown or code fences.\n")
	builder.WriteString("- Only call tools from the allowed list.\n")
	builder.WriteString("- Prefer final_answer once the task is complete.\n\n")
	builder.WriteString("- If a prior step contains continuation_nudge, keep working instead of stopping yet.\n\n")

	if instructions := strings.TrimSpace(node.GetConfigString("instructions")); instructions != "" {
		builder.WriteString("Task instructions:\n")
		builder.WriteString(SubstituteTemplate(instructions, entity.NewStateFromSnapshot(flattenNestedState(stateSnapshot))))
		builder.WriteString("\n\n")
	}
	if strings.TrimSpace(memoryContextBlock) != "" {
		builder.WriteString(memoryContextBlock)
	}

	builder.WriteString("Allowed tools:\n")
	for _, toolName := range allowedTools {
		builder.WriteString("- ")
		builder.WriteString(toolName)
		builder.WriteString("\n")
	}
	builder.WriteString("\nCurrent workflow state:\n")
	builder.WriteString(mustJSON(stateSnapshot))
	builder.WriteString("\n\nPrior agent steps:\n")
	if len(steps) == 0 {
		builder.WriteString("[]")
	} else {
		builder.WriteString(mustJSON(steps))
	}
	return builder.String()
}

func buildAgentOutput(node *entity.Node, provider string, model string, finalOutput string, stopReason string, stepCount int, toolCallCount int, steps []map[string]any, usage *LLMUsage, memoryContext map[string]any) map[string]any {
	output := map[string]any{
		"final_output":    finalOutput,
		"stop_reason":     stopReason,
		"step_count":      stepCount,
		"tool_call_count": toolCallCount,
		"steps":           steps,
		"model":           model,
		"provider":        provider,
		"allowed_tools":   normalizeAgentToolList(node.Config["tools"]),
		"agent_node_id":   node.ID,
		"agent_node_name": node.Name,
	}
	if usage != nil {
		output["usage"] = usageMap(usage)
	}
	if memoryContext != nil {
		output["memory_context"] = memoryContext
	}
	return output
}

func buildAgentContextQuery(node *entity.Node, stateSnapshot map[string]any) string {
	if instructions := strings.TrimSpace(node.GetConfigString("instructions")); instructions != "" {
		return SubstituteTemplate(instructions, entity.NewStateFromSnapshot(flattenNestedState(stateSnapshot)))
	}
	return mustJSON(stateSnapshot)
}

func parseAgentDecision(raw string) (*agentDecision, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return nil, fmt.Errorf("agent returned empty response")
	}

	var decision agentDecision
	if err := json.Unmarshal([]byte(trimmed), &decision); err == nil {
		return normalizeAgentDecision(&decision)
	}

	if strings.HasPrefix(trimmed, "```") {
		trimmed = strings.TrimPrefix(trimmed, "```json")
		trimmed = strings.TrimPrefix(trimmed, "```")
		trimmed = strings.TrimSuffix(trimmed, "```")
		trimmed = strings.TrimSpace(trimmed)
		if err := json.Unmarshal([]byte(trimmed), &decision); err == nil {
			return normalizeAgentDecision(&decision)
		}
	}

	start := strings.Index(trimmed, "{")
	end := strings.LastIndex(trimmed, "}")
	if start >= 0 && end > start {
		candidate := trimmed[start : end+1]
		if err := json.Unmarshal([]byte(candidate), &decision); err == nil {
			return normalizeAgentDecision(&decision)
		}
	}

	return nil, fmt.Errorf("agent response must be valid JSON action object")
}

func deriveAgentDecision(provider string, response *LLMResponse) (*agentDecision, error) {
	if response == nil {
		return nil, fmt.Errorf("agent returned empty response")
	}
	if provider == "openai" && len(response.ToolCalls) > 0 {
		call := response.ToolCalls[0]
		if strings.TrimSpace(call.Name) == "" {
			return nil, fmt.Errorf("tool call missing function name")
		}
		return &agentDecision{
			Action:    "tool_call",
			Tool:      call.Name,
			ToolInput: call.Arguments,
		}, nil
	}
	if provider == "openai" {
		if parsed, err := parseAgentDecision(response.Content); err == nil {
			return parsed, nil
		}
		finalAnswer := strings.TrimSpace(response.Content)
		if finalAnswer == "" {
			return nil, fmt.Errorf("agent returned empty response")
		}
		return &agentDecision{
			Action:      "final_answer",
			FinalAnswer: finalAnswer,
		}, nil
	}
	return parseAgentDecision(response.Content)
}

func normalizeAgentDecision(decision *agentDecision) (*agentDecision, error) {
	decision.Action = strings.TrimSpace(strings.ToLower(decision.Action))
	decision.Tool = strings.TrimSpace(decision.Tool)

	switch decision.Action {
	case "final_answer":
		if strings.TrimSpace(decision.FinalAnswer) == "" {
			return nil, fmt.Errorf("final_answer action requires final_answer")
		}
	case "tool_call":
		if decision.Tool == "" {
			return nil, fmt.Errorf("tool_call action requires tool")
		}
	default:
		return nil, fmt.Errorf("action must be final_answer or tool_call")
	}

	return decision, nil
}

func normalizeAgentToolList(raw any) []string {
	switch typed := raw.(type) {
	case []string:
		return compactAgentToolNames(typed)
	case []any:
		tools := make([]string, 0, len(typed))
		for _, item := range typed {
			if name, ok := item.(string); ok {
				tools = append(tools, name)
			}
		}
		return compactAgentToolNames(tools)
	default:
		return nil
	}
}

func compactAgentToolNames(items []string) []string {
	normalized := make([]string, 0, len(items))
	for _, item := range items {
		trimmed := strings.TrimSpace(item)
		if trimmed == "" {
			continue
		}
		normalized = append(normalized, trimmed)
	}
	return normalized
}

func containsTool(allowedTools []string, toolName string) bool {
	for _, candidate := range allowedTools {
		if candidate == toolName {
			return true
		}
	}
	return false
}

func (e *AgentExecutor) buildToolSpecs(allowedTools []string) ([]ToolSpec, error) {
	if len(allowedTools) == 0 {
		return nil, nil
	}
	if e.registry == nil {
		return nil, fmt.Errorf("agent executor requires tool registry for native tool calling")
	}
	specs := make([]ToolSpec, 0, len(allowedTools))
	for _, toolName := range allowedTools {
		def, ok := e.registry.Resolve(toolName, "")
		if !ok {
			return nil, fmt.Errorf("tool not found: %s", toolName)
		}
		if len(def.InputSchema) == 0 {
			return nil, fmt.Errorf("tool %s requires input_schema for agent autonomy", toolName)
		}
		specs = append(specs, ToolSpec{
			Name:         def.Name,
			Description:  def.Description,
			InputSchema:  def.InputSchema,
			OutputSchema: def.OutputSchema,
			Strict:       true,
		})
	}
	return specs, nil
}

func (e *AgentExecutor) executeApprovedToolCall(
	ctx context.Context,
	node *entity.Node,
	state *entity.State,
	stepIndex int,
	toolName string,
	toolInput any,
) (map[string]any, error) {
	if e.toolInvoker == nil {
		return nil, domain.NewValidationError("tool", "agent executor requires tool invoker")
	}

	emitAgentStreamEvent(ctx, map[string]any{
		"event":      agentStreamEventCalled,
		"step_index": stepIndex,
		"tool":       toolName,
	})

	toolNode := &entity.Node{
		ID:   fmt.Sprintf("%s__tool__%d", node.ID, stepIndex),
		Type: string(value.NodeTypeTool),
		Name: toolName,
		Config: map[string]any{
			"tool":  toolName,
			"input": toolInput,
		},
	}

	toolResult, err := e.toolInvoker.Execute(ctx, toolNode, state)
	if err != nil {
		return nil, fmt.Errorf("agent tool call failed: %w", err)
	}
	if toolResult == nil {
		return nil, domain.NewRetryableError(fmt.Errorf("agent tool call failed: empty result"), "agent tool error")
	}
	if toolResult.Error != nil {
		return nil, fmt.Errorf("agent tool call failed: %w", toolResult.Error)
	}

	emitAgentStreamEvent(ctx, map[string]any{
		"event":      agentStreamEventDone,
		"step_index": stepIndex,
		"tool":       toolName,
		"status":     "ok",
	})

	return map[string]any{
		"step_index":        stepIndex,
		"action":            "tool_call",
		"tool":              toolName,
		"tool_input":        toolInput,
		"approval_required": true,
		"approval_resolved": true,
		"tool_output":       toolResult.Output,
	}, nil
}

func agentResumeStateKey(nodeID string) string {
	return "node." + nodeID + ".agent_resume"
}

func agentApprovalDecisionKey(nodeID string) string {
	return "node." + nodeID + ".approval_decision"
}

func loadAgentResumeState(state *entity.State, nodeID string) (*agentResumeState, bool) {
	raw, ok := state.Get(agentResumeStateKey(nodeID))
	if !ok {
		return nil, false
	}
	data, ok := raw.(map[string]any)
	if !ok {
		return nil, false
	}
	resume := &agentResumeState{
		StepIndex:     getConfigInt(data["step_index"]),
		ToolCallCount: getConfigInt(data["tool_call_count"]),
		PendingTool:   strings.TrimSpace(toStringValue(data["pending_tool"])),
		PendingInput:  data["pending_input"],
		Steps:         coerceAgentSteps(data["steps"]),
		Usage:         coerceAgentUsage(data["usage"]),
	}
	if resume.StepIndex <= 0 {
		return nil, false
	}
	return resume, true
}

func clearAgentResumeState(state *entity.State, nodeID string) {
	state.Delete(agentResumeStateKey(nodeID))
}

func clearAgentApprovalDecision(state *entity.State, nodeID string) {
	state.Delete(agentApprovalDecisionKey(nodeID))
}

func upsertAgentStep(steps []map[string]any, step map[string]any) []map[string]any {
	stepIndex := getConfigInt(step["step_index"])
	for index, existing := range steps {
		if getConfigInt(existing["step_index"]) == stepIndex {
			steps[index] = step
			return steps
		}
	}
	return append(steps, step)
}

func coerceAgentSteps(raw any) []map[string]any {
	if raw == nil {
		return nil
	}
	if typed, ok := raw.([]map[string]any); ok {
		return typed
	}
	items, ok := raw.([]any)
	if !ok {
		return nil
	}
	steps := make([]map[string]any, 0, len(items))
	for _, item := range items {
		if step, ok := item.(map[string]any); ok {
			steps = append(steps, step)
		}
	}
	return steps
}

func coerceAgentUsage(raw any) *LLMUsage {
	usage, ok := raw.(map[string]any)
	if !ok {
		return nil
	}
	return &LLMUsage{
		PromptTokens:     getConfigInt(usage["prompt_tokens"]),
		CompletionTokens: getConfigInt(usage["completion_tokens"]),
		TotalTokens:      getConfigInt(usage["total_tokens"]),
	}
}

func toStringValue(raw any) string {
	if value, ok := raw.(string); ok {
		return value
	}
	return ""
}

func emitAgentStreamEvent(ctx context.Context, payload map[string]any) {
	emitter := port.StreamChunkEmitterFrom(ctx)
	if emitter == nil || len(payload) == 0 {
		return
	}
	emitter(mustJSON(payload))
}

func mustJSON(value any) string {
	raw, err := json.Marshal(value)
	if err != nil {
		return "{}"
	}
	return string(raw)
}

func usageMap(usage *LLMUsage) map[string]any {
	if usage == nil {
		return nil
	}
	return map[string]any{
		"prompt_tokens":     usage.PromptTokens,
		"completion_tokens": usage.CompletionTokens,
		"total_tokens":      usage.TotalTokens,
	}
}

func usageTotalTokens(usage *LLMUsage) int {
	if usage == nil {
		return 0
	}
	return usage.TotalTokens
}

func tokenBudgetCompletionMap(completion *tokenBudgetCompletion) map[string]any {
	if completion == nil {
		return nil
	}
	return map[string]any{
		"continuation_count":  completion.ContinuationCount,
		"pct":                 completion.Pct,
		"turn_tokens":         completion.TurnTokens,
		"budget":              completion.Budget,
		"diminishing_returns": completion.DiminishingReturns,
		"duration_ms":         completion.DurationMs,
	}
}

func accumulateUsage(total **LLMUsage, usage *LLMUsage) {
	if usage == nil {
		return
	}
	if *total == nil {
		*total = &LLMUsage{}
	}
	(*total).PromptTokens += usage.PromptTokens
	(*total).CompletionTokens += usage.CompletionTokens
	(*total).TotalTokens += usage.TotalTokens
}

func flattenNestedState(snapshot map[string]any) map[string]any {
	flat := make(map[string]any)
	flattenNestedStateInto(flat, "", snapshot)
	return flat
}

func flattenNestedStateInto(target map[string]any, prefix string, value any) {
	nested, ok := value.(map[string]any)
	if !ok {
		if prefix != "" {
			target[prefix] = value
		}
		return
	}
	for key, child := range nested {
		nextPrefix := key
		if prefix != "" {
			nextPrefix = prefix + "." + key
		}
		flattenNestedStateInto(target, nextPrefix, child)
	}
}
