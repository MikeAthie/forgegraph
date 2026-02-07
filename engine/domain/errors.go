// Package domain contains core domain logic for the ForgeGraph engine.
package domain

import (
	"errors"
	"fmt"
)

// Graph validation errors
var (
	ErrEmptyGraph      = errors.New("graph has no nodes")
	ErrNoStartNode     = errors.New("graph has no start node (no node with indegree 0)")
	ErrNoOutputNode    = errors.New("graph has no output node")
	ErrCycleDetected   = errors.New("graph contains a cycle")
	ErrOrphanedNode    = errors.New("graph has orphaned nodes")
	ErrInvalidNodeType = errors.New("node has invalid type")
	ErrDuplicateNodeID = errors.New("duplicate node ID found")
	ErrInvalidEdge     = errors.New("edge references non-existent node")
	ErrSelfLoop        = errors.New("edge creates a self-loop")
)

// Execution errors
var (
	ErrRunNotFound        = errors.New("run not found")
	ErrRunAlreadyEnded    = errors.New("run has already ended")
	ErrRunNotPaused       = errors.New("run is not paused")
	ErrNodeNotFound       = errors.New("node not found")
	ErrExecutorNotFound   = errors.New("no executor registered for node type")
	ErrCheckpointNotFound = errors.New("checkpoint not found")
)

// Node execution errors
var (
	ErrNodeTimeout          = errors.New("node execution timed out")
	ErrNodePanic            = errors.New("node execution panicked")
	ErrConditionEvalFailed  = errors.New("branch condition evaluation failed")
	ErrInvalidCondition     = errors.New("invalid branch condition")
	ErrMissingRequiredInput = errors.New("missing required input")
)

// State errors
var (
	ErrStateKeyNotFound = errors.New("state key not found")
)

// Human gate errors
var (
	ErrHumanGateNotPaused = errors.New("run is not paused at a human gate")
	ErrWrongHumanGate     = errors.New("resume node does not match paused gate")
)

// RetryableError wraps an error that can be retried
type RetryableError struct {
	Err          error
	Message      string
	Code         string
	RetryAfterMs int
	Details      map[string]any
}

// NewRetryableError creates a new retryable error
func NewRetryableError(err error, message string) *RetryableError {
	return NewRetryableErrorWithDetails(err, message, "", 0, nil)
}

// NewRetryableErrorWithDetails creates a new retryable error with structured metadata.
func NewRetryableErrorWithDetails(
	err error,
	message string,
	code string,
	retryAfterMs int,
	details map[string]any,
) *RetryableError {
	if retryAfterMs < 0 {
		retryAfterMs = 0
	}
	copiedDetails := make(map[string]any, len(details))
	for key, value := range details {
		copiedDetails[key] = value
	}
	return &RetryableError{
		Err:          err,
		Message:      message,
		Code:         code,
		RetryAfterMs: retryAfterMs,
		Details:      copiedDetails,
	}
}

func (e *RetryableError) Error() string {
	if e.Message != "" {
		return fmt.Sprintf("%s: %v", e.Message, e.Err)
	}
	return e.Err.Error()
}

func (e *RetryableError) Unwrap() error {
	return e.Err
}

// IsRetryable checks if an error should trigger a retry
func IsRetryable(err error) bool {
	var retryable *RetryableError
	return errors.As(err, &retryable)
}

// RetryAfterMsFromError returns the suggested retry-after delay in milliseconds (if any).
func RetryAfterMsFromError(err error) int {
	var retryable *RetryableError
	if errors.As(err, &retryable) && retryable.RetryAfterMs > 0 {
		return retryable.RetryAfterMs
	}
	return 0
}

// RetryCodeFromError returns the retry classification code (if any).
func RetryCodeFromError(err error) string {
	var retryable *RetryableError
	if errors.As(err, &retryable) {
		return retryable.Code
	}
	return ""
}

// RetryDetailsFromError returns structured retry diagnostics (if any).
func RetryDetailsFromError(err error) map[string]any {
	var retryable *RetryableError
	if !errors.As(err, &retryable) || len(retryable.Details) == 0 {
		return nil
	}
	details := make(map[string]any, len(retryable.Details))
	for key, value := range retryable.Details {
		details[key] = value
	}
	return details
}

// NodeError wraps an error that occurred during node execution
type NodeError struct {
	NodeID   string
	NodeType string
	Err      error
}

func NewNodeError(nodeID, nodeType string, err error) *NodeError {
	return &NodeError{
		NodeID:   nodeID,
		NodeType: nodeType,
		Err:      err,
	}
}

func (e *NodeError) Error() string {
	return fmt.Sprintf("node %s (%s): %v", e.NodeID, e.NodeType, e.Err)
}

func (e *NodeError) Unwrap() error {
	return e.Err
}

// ValidationError represents a graph validation error with details
type ValidationError struct {
	Field   string
	Message string
	Err     error
}

func NewValidationError(field, message string) *ValidationError {
	return &ValidationError{
		Field:   field,
		Message: message,
	}
}

func (e *ValidationError) Error() string {
	if e.Field != "" {
		return fmt.Sprintf("%s: %s", e.Field, e.Message)
	}
	return e.Message
}

func (e *ValidationError) Unwrap() error {
	return e.Err
}
