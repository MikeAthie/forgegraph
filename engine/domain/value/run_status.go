package value

// RunStatus represents the status of a workflow run
type RunStatus string

const (
	RunStatusPending   RunStatus = "pending"
	RunStatusRunning   RunStatus = "running"
	RunStatusPaused    RunStatus = "paused"
	RunStatusSucceeded RunStatus = "succeeded"
	RunStatusFailed    RunStatus = "failed"
	RunStatusCanceled  RunStatus = "canceled"
)

// String returns the string representation of the run status
func (s RunStatus) String() string {
	return string(s)
}

// IsValid returns true if the status is recognized
func (s RunStatus) IsValid() bool {
	switch s {
	case RunStatusPending, RunStatusRunning, RunStatusPaused,
		RunStatusSucceeded, RunStatusFailed, RunStatusCanceled:
		return true
	}
	return false
}

// IsTerminal returns true if the status is a final state
func (s RunStatus) IsTerminal() bool {
	switch s {
	case RunStatusSucceeded, RunStatusFailed, RunStatusCanceled:
		return true
	}
	return false
}

// IsActive returns true if the run is still active (not terminal)
func (s RunStatus) IsActive() bool {
	return !s.IsTerminal()
}

// CanTransitionTo returns true if the status can transition to the target
func (s RunStatus) CanTransitionTo(target RunStatus) bool {
	// Terminal states cannot transition
	if s.IsTerminal() {
		return false
	}

	// Valid transitions
	switch s {
	case RunStatusPending:
		return target == RunStatusRunning || target == RunStatusCanceled
	case RunStatusRunning:
		return target == RunStatusSucceeded || target == RunStatusFailed ||
			target == RunStatusPaused || target == RunStatusCanceled
	case RunStatusPaused:
		return target == RunStatusRunning || target == RunStatusCanceled
	}
	return false
}

// NodeRunStatus represents the status of a single node execution
type NodeRunStatus string

const (
	NodeRunStatusPending   NodeRunStatus = "pending"
	NodeRunStatusRunning   NodeRunStatus = "running"
	NodeRunStatusWaiting   NodeRunStatus = "waiting" // Human gate awaiting approval
	NodeRunStatusSucceeded NodeRunStatus = "succeeded"
	NodeRunStatusFailed    NodeRunStatus = "failed"
	NodeRunStatusSkipped   NodeRunStatus = "skipped"
)

// String returns the string representation of the node run status
func (s NodeRunStatus) String() string {
	return string(s)
}

// IsValid returns true if the status is recognized
func (s NodeRunStatus) IsValid() bool {
	switch s {
	case NodeRunStatusPending, NodeRunStatusRunning, NodeRunStatusWaiting,
		NodeRunStatusSucceeded, NodeRunStatusFailed, NodeRunStatusSkipped:
		return true
	}
	return false
}

// IsTerminal returns true if the status is a final state
func (s NodeRunStatus) IsTerminal() bool {
	switch s {
	case NodeRunStatusSucceeded, NodeRunStatusFailed, NodeRunStatusSkipped:
		return true
	}
	return false
}
