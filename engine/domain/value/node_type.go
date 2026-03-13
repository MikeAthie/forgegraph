// Package value contains value objects for the ForgeGraph engine domain.
package value

// NodeType represents the type of a workflow node
type NodeType string

const (
	NodeTypeAgent     NodeType = "agent"
	NodeTypePrompt    NodeType = "prompt"
	NodeTypeHTTP      NodeType = "http"
	NodeTypeTransform NodeType = "transform"
	NodeTypeBranch    NodeType = "branch"
	NodeTypeMerge     NodeType = "merge"
	NodeTypeHumanGate NodeType = "human_gate"
	NodeTypeMemory    NodeType = "memory"
	NodeTypeTool      NodeType = "tool"
	NodeTypeSubgraph  NodeType = "subgraph"
	NodeTypeOutput    NodeType = "output"
)

// String returns the string representation of the node type
func (t NodeType) String() string {
	return string(t)
}

// IsValid returns true if the node type is recognized
func (t NodeType) IsValid() bool {
	switch t {
	case NodeTypeAgent, NodeTypePrompt, NodeTypeHTTP, NodeTypeTransform,
		NodeTypeBranch, NodeTypeMerge, NodeTypeHumanGate, NodeTypeMemory, NodeTypeTool, NodeTypeSubgraph, NodeTypeOutput:
		return true
	}
	return false
}

// RequiresExternalCall returns true if the node type makes external API calls
func (t NodeType) RequiresExternalCall() bool {
	switch t {
	case NodeTypeAgent, NodeTypePrompt, NodeTypeHTTP:
		return true
	}
	return false
}

// IsControlFlow returns true if the node type controls execution flow
func (t NodeType) IsControlFlow() bool {
	switch t {
	case NodeTypeBranch, NodeTypeMerge, NodeTypeHumanGate:
		return true
	}
	return false
}

// AllNodeTypes returns all valid node types
func AllNodeTypes() []NodeType {
	return []NodeType{
		NodeTypeAgent,
		NodeTypePrompt,
		NodeTypeHTTP,
		NodeTypeTransform,
		NodeTypeBranch,
		NodeTypeMerge,
		NodeTypeHumanGate,
		NodeTypeMemory,
		NodeTypeTool,
		NodeTypeSubgraph,
		NodeTypeOutput,
	}
}

// ParseNodeType converts a string to a NodeType
func ParseNodeType(s string) (NodeType, bool) {
	t := NodeType(s)
	return t, t.IsValid()
}
