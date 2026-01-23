// Package executor contains node executor implementations for the ForgeGraph engine.
package executor

import (
	"context"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// HumanGateExecutor handles human gate nodes that pause execution for human approval.
// When executed, this node returns a Pause result that halts the workflow until
// a human decision (approve/reject) is received via the ResumeRun gRPC call.
type HumanGateExecutor struct{}

// NewHumanGateExecutor creates a new human gate executor
func NewHumanGateExecutor() *HumanGateExecutor {
	return &HumanGateExecutor{}
}

// NodeType returns the node type this executor handles
func (e *HumanGateExecutor) NodeType() string {
	return string(value.NodeTypeHumanGate)
}

// Execute pauses the workflow and returns a payload for the approval UI.
//
// Config options:
//   - prompt_message: string - message displayed to the approver
//   - required_fields: []string - fields the approver must fill in
//
// On resume (via ResumeRun gRPC):
//   - Approved: decision is stored in state["node.<id>.output"] and workflow continues
//   - Rejected: workflow terminates with failed status
func (e *HumanGateExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	// Extract config
	promptMessage := ""
	if msg, ok := node.Config["prompt_message"].(string); ok {
		promptMessage = msg
	}

	var requiredFields []string
	if fields, ok := node.Config["required_fields"].([]any); ok {
		for _, f := range fields {
			if fieldStr, ok := f.(string); ok {
				requiredFields = append(requiredFields, fieldStr)
			}
		}
	}

	// Build pause payload for the approval UI
	payload := map[string]any{
		"prompt_message":  promptMessage,
		"required_fields": requiredFields,
		"node_id":         node.ID,
		"node_name":       node.Name,
	}

	// Return pause result - the scheduler will handle pausing the run
	return port.NewPauseResult(payload), nil
}
