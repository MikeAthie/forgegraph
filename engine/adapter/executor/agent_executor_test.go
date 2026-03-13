package executor

import (
	"context"
	"strings"
	"testing"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

type sequenceLLMClient struct {
	responses []*LLMResponse
	received  []*LLMRequest
	calls     int
}

func (m *sequenceLLMClient) Complete(ctx context.Context, request *LLMRequest) (*LLMResponse, error) {
	m.calls++
	m.received = append(m.received, request)
	if len(m.responses) == 0 {
		return &LLMResponse{Content: `{"action":"final_answer","final_answer":"done"}`, Model: request.Model}, nil
	}
	index := m.calls - 1
	if index >= len(m.responses) {
		index = len(m.responses) - 1
	}
	return m.responses[index], nil
}

type mockAgentToolInvoker struct {
	calls  int
	tool   string
	input  any
	output any
	err    error
}

func (m *mockAgentToolInvoker) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	m.calls++
	m.tool = node.GetConfigString("tool")
	m.input = node.Config["input"]
	if m.err != nil {
		return nil, m.err
	}
	return port.NewSuccessResult(m.output), nil
}

func TestAgentExecutor_NodeType(t *testing.T) {
	executor := NewAgentExecutorWithToolInvoker(nil, nil)
	if executor.NodeType() != string(value.NodeTypeAgent) {
		t.Fatalf("NodeType() = %s, want %s", executor.NodeType(), string(value.NodeTypeAgent))
	}
}

func TestAgentExecutor_Execute_FinalAnswer(t *testing.T) {
	client := &sequenceLLMClient{
		responses: []*LLMResponse{
			{
				Content: `{"action":"final_answer","final_answer":"Issue resolved."}`,
				Model:   "gpt-4.1-mini",
				Usage: &LLMUsage{
					PromptTokens:     10,
					CompletionTokens: 4,
					TotalTokens:      14,
				},
			},
		},
	}

	executor := NewAgentExecutorWithToolInvoker(client, &mockAgentToolInvoker{})
	node := &entity.Node{
		ID:   "agent_1",
		Type: string(value.NodeTypeAgent),
		Config: map[string]any{
			"model": "gpt-4.1-mini",
			"tools": []any{"crm_lookup"},
		},
	}

	result, err := executor.Execute(context.Background(), node, entity.NewStateWithInput(map[string]any{"ticket": "T-123"}))
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("result.Output = %T, want map[string]any", result.Output)
	}
	if output["final_output"] != "Issue resolved." {
		t.Fatalf("final_output = %v, want Issue resolved.", output["final_output"])
	}
	if output["stop_reason"] != agentStopReasonFinal {
		t.Fatalf("stop_reason = %v, want %s", output["stop_reason"], agentStopReasonFinal)
	}
	if output["step_count"] != 1 {
		t.Fatalf("step_count = %v, want 1", output["step_count"])
	}
	if output["tool_call_count"] != 0 {
		t.Fatalf("tool_call_count = %v, want 0", output["tool_call_count"])
	}
}

func TestAgentExecutor_Execute_ToolCallThenFinalAnswer(t *testing.T) {
	client := &sequenceLLMClient{
		responses: []*LLMResponse{
			{Content: `{"action":"tool_call","tool":"crm_lookup","tool_input":{"customer_id":"cust_123"}}`, Model: "gpt-4.1-mini"},
			{Content: `{"action":"final_answer","final_answer":"Customer is active."}`, Model: "gpt-4.1-mini"},
		},
	}
	toolInvoker := &mockAgentToolInvoker{
		output: map[string]any{"status": "active"},
	}
	executor := NewAgentExecutorWithToolInvoker(client, toolInvoker)

	var chunks []string
	ctx := port.WithStreamChunkEmitter(context.Background(), func(chunk string) {
		chunks = append(chunks, chunk)
	})

	node := &entity.Node{
		ID:   "agent_1",
		Type: string(value.NodeTypeAgent),
		Config: map[string]any{
			"model":          "gpt-4.1-mini",
			"provider":       "openai",
			"tools":          []any{"crm_lookup"},
			"max_steps":      4,
			"max_tool_calls": 2,
		},
	}

	result, err := executor.Execute(ctx, node, entity.NewStateWithInput(map[string]any{"ticket": "T-123"}))
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}
	if toolInvoker.calls != 1 {
		t.Fatalf("tool invocations = %d, want 1", toolInvoker.calls)
	}
	if toolInvoker.tool != "crm_lookup" {
		t.Fatalf("tool = %s, want crm_lookup", toolInvoker.tool)
	}

	input, ok := toolInvoker.input.(map[string]any)
	if !ok || input["customer_id"] != "cust_123" {
		t.Fatalf("tool input = %#v, want customer_id=cust_123", toolInvoker.input)
	}

	output := result.Output.(map[string]any)
	if output["stop_reason"] != agentStopReasonFinal {
		t.Fatalf("stop_reason = %v, want %s", output["stop_reason"], agentStopReasonFinal)
	}
	if output["tool_call_count"] != 1 {
		t.Fatalf("tool_call_count = %v, want 1", output["tool_call_count"])
	}
	if output["step_count"] != 2 {
		t.Fatalf("step_count = %v, want 2", output["step_count"])
	}
	if len(chunks) == 0 {
		t.Fatal("expected agent stream chunks to be emitted")
	}
}

func TestAgentExecutor_Execute_StopsOnMaxSteps(t *testing.T) {
	client := &sequenceLLMClient{
		responses: []*LLMResponse{
			{Content: `{"action":"tool_call","tool":"crm_lookup","tool_input":{"customer_id":"cust_1"}}`, Model: "gpt-4.1-mini"},
			{Content: `{"action":"tool_call","tool":"crm_lookup","tool_input":{"customer_id":"cust_2"}}`, Model: "gpt-4.1-mini"},
		},
	}
	toolInvoker := &mockAgentToolInvoker{
		output: map[string]any{"status": "active"},
	}
	executor := NewAgentExecutorWithToolInvoker(client, toolInvoker)
	node := &entity.Node{
		ID:   "agent_1",
		Type: string(value.NodeTypeAgent),
		Config: map[string]any{
			"model":     "gpt-4.1-mini",
			"tools":     []any{"crm_lookup"},
			"max_steps": 2,
		},
	}

	result, err := executor.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	output := result.Output.(map[string]any)
	if output["stop_reason"] != agentStopReasonMaxSteps {
		t.Fatalf("stop_reason = %v, want %s", output["stop_reason"], agentStopReasonMaxSteps)
	}
	if output["step_count"] != 2 {
		t.Fatalf("step_count = %v, want 2", output["step_count"])
	}
	if output["tool_call_count"] != 2 {
		t.Fatalf("tool_call_count = %v, want 2", output["tool_call_count"])
	}
}

func TestAgentExecutor_Execute_DeniesDisallowedTool(t *testing.T) {
	client := &sequenceLLMClient{
		responses: []*LLMResponse{
			{Content: `{"action":"tool_call","tool":"delete_everything","tool_input":{"scope":"all"}}`, Model: "gpt-4.1-mini"},
		},
	}
	executor := NewAgentExecutorWithToolInvoker(client, &mockAgentToolInvoker{})
	node := &entity.Node{
		ID:   "agent_1",
		Type: string(value.NodeTypeAgent),
		Config: map[string]any{
			"model": "gpt-4.1-mini",
			"tools": []any{"crm_lookup"},
		},
	}

	result, err := executor.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	output := result.Output.(map[string]any)
	if output["stop_reason"] != agentStopReasonToolDeny {
		t.Fatalf("stop_reason = %v, want %s", output["stop_reason"], agentStopReasonToolDeny)
	}
	if output["tool_call_count"] != 0 {
		t.Fatalf("tool_call_count = %v, want 0", output["tool_call_count"])
	}
}

func TestAgentExecutor_Execute_BlocksProviderByPolicy(t *testing.T) {
	client := &sequenceLLMClient{
		responses: []*LLMResponse{
			{Content: `{"action":"final_answer","final_answer":"done"}`, Model: "gpt-4.1-mini"},
		},
	}
	executor := NewAgentExecutorWithToolInvoker(client, &mockAgentToolInvoker{})
	node := &entity.Node{
		ID:   "agent_policy",
		Type: string(value.NodeTypeAgent),
		Config: map[string]any{
			"provider": "openai",
			"model":    "gpt-4.1-mini",
			"tools":    []any{"crm_lookup"},
		},
	}

	ctx := port.WithRunContext(context.Background(), &port.RunContext{
		Policy: &entity.ExecutionPolicy{
			AllowedProviders: []string{"anthropic"},
		},
	})

	result, err := executor.Execute(ctx, node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("expected provider policy denial")
	}
	if !strings.Contains(result.Error.Error(), "policy denied: provider blocked by policy") {
		t.Fatalf("unexpected error: %v", result.Error)
	}
}

func TestAgentExecutor_Execute_PausesForApprovalRequiredTool(t *testing.T) {
	client := &sequenceLLMClient{
		responses: []*LLMResponse{
			{Content: `{"action":"tool_call","tool":"send_email","tool_input":{"to":"user@example.com"}}`, Model: "gpt-4.1-mini"},
		},
	}
	executor := NewAgentExecutorWithToolInvoker(client, &mockAgentToolInvoker{})
	state := entity.NewState()
	node := &entity.Node{
		ID:   "agent_approval",
		Type: string(value.NodeTypeAgent),
		Name: "Approval Agent",
		Config: map[string]any{
			"model":                   "gpt-4.1-mini",
			"tools":                   []any{"send_email"},
			"approval_required_tools": []any{"send_email"},
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if !result.Pause {
		t.Fatal("expected agent execution to pause")
	}

	payload, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("pause payload = %T, want map[string]any", result.Output)
	}
	if payload["tool"] != "send_email" {
		t.Fatalf("tool = %v, want send_email", payload["tool"])
	}
	agentTrace, ok := payload["agent_trace"].(map[string]any)
	if !ok {
		t.Fatalf("agent_trace = %T, want map[string]any", payload["agent_trace"])
	}
	if agentTrace["stop_reason"] != agentStopReasonApproval {
		t.Fatalf("stop_reason = %v, want %s", agentTrace["stop_reason"], agentStopReasonApproval)
	}
	if _, ok := state.Get(agentResumeStateKey(node.ID)); !ok {
		t.Fatal("expected resume state to be stored in state")
	}
}

func TestAgentExecutor_Execute_ResumesApprovedToolCall(t *testing.T) {
	client := &sequenceLLMClient{
		responses: []*LLMResponse{
			{Content: `{"action":"final_answer","final_answer":"Email approved and sent."}`, Model: "gpt-4.1-mini"},
		},
	}
	toolInvoker := &mockAgentToolInvoker{output: map[string]any{"queued": true}}
	executor := NewAgentExecutorWithToolInvoker(client, toolInvoker)
	state := entity.NewState()
	node := &entity.Node{
		ID:   "agent_approval",
		Type: string(value.NodeTypeAgent),
		Name: "Approval Agent",
		Config: map[string]any{
			"model":                   "gpt-4.1-mini",
			"tools":                   []any{"send_email"},
			"approval_required_tools": []any{"send_email"},
			"max_steps":               4,
		},
	}

	state.Set(agentResumeStateKey(node.ID), map[string]any{
		"step_index":      1,
		"tool_call_count": 0,
		"pending_tool":    "send_email",
		"pending_input":   map[string]any{"to": "user@example.com"},
		"steps": []any{
			map[string]any{
				"step_index":        1,
				"action":            "tool_call",
				"tool":              "send_email",
				"tool_input":        map[string]any{"to": "user@example.com"},
				"approval_required": true,
			},
		},
	})
	state.Set(agentApprovalDecisionKey(node.ID), map[string]any{
		"approved": true,
		"fields":   map[string]any{},
	})

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}
	if result.Pause {
		t.Fatal("expected resumed agent execution to complete without pausing")
	}
	if toolInvoker.calls != 1 {
		t.Fatalf("tool invocations = %d, want 1", toolInvoker.calls)
	}

	output := result.Output.(map[string]any)
	if output["final_output"] != "Email approved and sent." {
		t.Fatalf("final_output = %v, want Email approved and sent.", output["final_output"])
	}
	if output["tool_call_count"] != 1 {
		t.Fatalf("tool_call_count = %v, want 1", output["tool_call_count"])
	}
	steps := output["steps"].([]map[string]any)
	if len(steps) != 2 {
		t.Fatalf("steps len = %d, want 2", len(steps))
	}
	if steps[0]["tool_output"] == nil {
		t.Fatal("expected resumed step to include tool_output")
	}
	if _, ok := state.Get(agentResumeStateKey(node.ID)); ok {
		t.Fatal("expected resume state to be cleared after resume")
	}
}
