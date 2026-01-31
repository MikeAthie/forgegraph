package entity

// MemoryConfig describes memory tiers configuration for a run.
type MemoryConfig struct {
	Tier1         Tier1Config         `json:"tier1"`
	Tier2         Tier2Config         `json:"tier2"`
	Tier3         Tier3Config         `json:"tier3"`
	Summarization SummarizationConfig `json:"summarization"`
	CrossSession  CrossSessionConfig  `json:"cross_session"`
}

// Tier1Config controls the local message buffer.
type Tier1Config struct {
	Enabled     bool   `json:"enabled"`
	BufferSize  int    `json:"buffer_size"`
	LimitMode   string `json:"limit_mode"`
	MaxTokens   int    `json:"max_tokens"`
	AutoPrepend bool   `json:"auto_prepend"`
}

// Tier2Config controls Redis-backed summaries/facts.
type Tier2Config struct {
	Enabled    bool   `json:"enabled"`
	Namespace  string `json:"namespace"`
	SummaryTTL int    `json:"summary_ttl_seconds"`
	FactsTTL   int    `json:"facts_ttl_seconds"`
}

// Tier3Config controls vector memory retrieval (Phase 3).
type Tier3Config struct {
	Enabled        bool    `json:"enabled"`
	TopK           int     `json:"top_k"`
	Threshold      float64 `json:"threshold"`
	RecencyWeight  float64 `json:"recency_weight"`
	EmbeddingModel string  `json:"embedding_model"`
}

// SummarizationConfig controls when and how to summarize memory.
type SummarizationConfig struct {
	Enabled          bool   `json:"enabled"`
	TriggerThreshold int    `json:"trigger_threshold"`
	KeepRecentCount  int    `json:"keep_recent_count"`
	CooldownMessages int    `json:"cooldown_messages"`
	Model            string `json:"model"`
}

// CrossSessionConfig controls shared memory across runs.
type CrossSessionConfig struct {
	Enabled         bool `json:"enabled"`
	SessionTTLHours int  `json:"session_ttl_hours"`
	ShareWithAgent  bool `json:"share_with_agent"`
}
