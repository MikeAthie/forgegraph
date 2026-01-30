package entity

import "time"

// Summary captures an aggregated memory summary for a run.
type Summary struct {
	ID             string
	Content        string
	SourceCount    int
	FactsExtracted []Fact
	CreatedAt      time.Time
}

// Fact captures an extracted fact from messages.
type Fact struct {
	Key          string
	Value        string
	Confidence   float64
	SourceNodeID string
}
