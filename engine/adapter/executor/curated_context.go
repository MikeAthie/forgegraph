package executor

import (
	"fmt"
	"strings"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
)

type curatedObservation struct {
	ID       string
	Type     string
	Title    string
	Content  string
	Scope    string
	TopicKey string
	ToolName string
}

type curatedContextAssembly struct {
	Paths        []string
	Observations []curatedObservation
	Degraded     bool
	Strategies   []string
}

func resolveCuratedContext(node *entity.Node, state *entity.State) (*curatedContextAssembly, error) {
	paths := coerceStringSlice(node.Config["observation_context_paths"])
	if len(paths) == 0 {
		return nil, nil
	}

	assembly := &curatedContextAssembly{
		Paths:        append([]string(nil), paths...),
		Observations: make([]curatedObservation, 0),
		Strategies:   make([]string, 0),
	}
	seenObservations := make(map[string]bool)
	seenStrategies := make(map[string]bool)

	for _, path := range paths {
		value, ok := resolveStateValue(state, path)
		if !ok {
			return nil, domain.NewValidationError(
				"observation_context_paths",
				fmt.Sprintf("observation context path did not resolve: %s", path),
			)
		}
		if err := appendCuratedContextValue(
			assembly,
			value,
			seenObservations,
			seenStrategies,
		); err != nil {
			return nil, domain.NewValidationError(
				"observation_context_paths",
				fmt.Sprintf("invalid observation context payload at %s: %v", path, err),
			)
		}
	}

	return assembly, nil
}

func appendCuratedContextValue(
	assembly *curatedContextAssembly,
	value any,
	seenObservations map[string]bool,
	seenStrategies map[string]bool,
) error {
	switch typed := value.(type) {
	case map[string]any:
		if observations, ok := typed["observations"]; ok {
			if degraded, ok := typed["degraded"].(bool); ok {
				assembly.Degraded = assembly.Degraded || degraded
			}
			for _, strategy := range coerceStringSlice(typed["strategies"]) {
				if !seenStrategies[strategy] {
					assembly.Strategies = append(assembly.Strategies, strategy)
					seenStrategies[strategy] = true
				}
			}
			return appendCuratedContextValue(assembly, observations, seenObservations, seenStrategies)
		}
		observation, err := normalizeCuratedObservation(typed)
		if err != nil {
			return err
		}
		appendCuratedObservation(assembly, observation, seenObservations)
		return nil
	case []map[string]any:
		for _, item := range typed {
			if err := appendCuratedContextValue(assembly, item, seenObservations, seenStrategies); err != nil {
				return err
			}
		}
		return nil
	case []any:
		for _, item := range typed {
			if err := appendCuratedContextValue(assembly, item, seenObservations, seenStrategies); err != nil {
				return err
			}
		}
		return nil
	default:
		return fmt.Errorf("unsupported payload type %T", value)
	}
}

func normalizeCuratedObservation(raw map[string]any) (curatedObservation, error) {
	content := strings.TrimSpace(stringValue(raw["content"]))
	if content == "" {
		return curatedObservation{}, fmt.Errorf("observation content is required")
	}
	return curatedObservation{
		ID:       strings.TrimSpace(stringValue(raw["id"])),
		Type:     strings.TrimSpace(stringValue(raw["type"])),
		Title:    strings.TrimSpace(stringValue(raw["title"])),
		Content:  content,
		Scope:    strings.TrimSpace(stringValue(raw["scope"])),
		TopicKey: strings.TrimSpace(stringValue(raw["topic_key"])),
		ToolName: strings.TrimSpace(stringValue(raw["tool_name"])),
	}, nil
}

func appendCuratedObservation(
	assembly *curatedContextAssembly,
	observation curatedObservation,
	seenObservations map[string]bool,
) {
	key := observation.ID
	if key == "" {
		key = observation.Type + "|" + observation.Title + "|" + observation.Content
	}
	if seenObservations[key] {
		return
	}
	seenObservations[key] = true
	assembly.Observations = append(assembly.Observations, observation)
}

func resolveStateValue(state *entity.State, path string) (any, bool) {
	if state == nil {
		return nil, false
	}
	if value, ok := state.Get(path); ok {
		return value, true
	}
	if value := resolveNestedPath(path, state); value != nil {
		return value, true
	}
	return nil, false
}

func coerceStringSlice(raw any) []string {
	switch typed := raw.(type) {
	case []string:
		return compactNonEmptyStrings(typed)
	case []any:
		values := make([]string, 0, len(typed))
		for _, item := range typed {
			str, ok := item.(string)
			if !ok {
				continue
			}
			values = append(values, str)
		}
		return compactNonEmptyStrings(values)
	default:
		return nil
	}
}

func compactNonEmptyStrings(values []string) []string {
	compacted := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" {
			compacted = append(compacted, value)
		}
	}
	return compacted
}

func stringValue(raw any) string {
	switch typed := raw.(type) {
	case string:
		return typed
	case fmt.Stringer:
		return typed.String()
	case nil:
		return ""
	default:
		return fmt.Sprintf("%v", typed)
	}
}

func buildPromptWithMemory(
	basePrompt string,
	curated *curatedContextAssembly,
	buffer *entity.MessageBuffer,
	summary *entity.Summary,
	vectorMemories []port.MemoryChunk,
) string {
	block := buildMemoryContextBlock(curated, buffer, summary, vectorMemories)
	if block == "" {
		return basePrompt
	}

	var sb strings.Builder
	sb.WriteString(block)
	sb.WriteString("Current input:\n")
	sb.WriteString(basePrompt)
	return sb.String()
}

func buildAgentMemoryBlock(
	curated *curatedContextAssembly,
	buffer *entity.MessageBuffer,
	summary *entity.Summary,
	vectorMemories []port.MemoryChunk,
) string {
	return buildMemoryContextBlock(curated, buffer, summary, vectorMemories)
}

func buildMemoryContextBlock(
	curated *curatedContextAssembly,
	buffer *entity.MessageBuffer,
	summary *entity.Summary,
	vectorMemories []port.MemoryChunk,
) string {
	var sb strings.Builder
	if curated != nil {
		appendCuratedObservationSection(&sb, curated)
		appendSummarySection(&sb, summary)
		appendVectorSection(&sb, vectorMemories)
		appendBufferSection(&sb, buffer)
		return sb.String()
	}

	appendSummarySection(&sb, summary)
	appendBufferSection(&sb, buffer)
	appendVectorSection(&sb, vectorMemories)
	return sb.String()
}

func appendCuratedObservationSection(sb *strings.Builder, curated *curatedContextAssembly) {
	if sb == nil || curated == nil || len(curated.Observations) == 0 {
		return
	}
	sb.WriteString("Curated observations:\n")
	for _, observation := range curated.Observations {
		sb.WriteString("- ")
		if observation.Type != "" {
			sb.WriteString("[")
			sb.WriteString(observation.Type)
			sb.WriteString("] ")
		}
		if observation.Title != "" {
			sb.WriteString(observation.Title)
			sb.WriteString(": ")
		}
		sb.WriteString(observation.Content)
		sb.WriteString("\n")
	}
	sb.WriteString("\n")
}

func appendSummarySection(sb *strings.Builder, summary *entity.Summary) {
	if sb == nil || summary == nil || strings.TrimSpace(summary.Content) == "" {
		return
	}
	sb.WriteString("Summary of earlier conversation:\n")
	sb.WriteString(strings.TrimSpace(summary.Content))
	sb.WriteString("\n\n")
	if len(summary.FactsExtracted) == 0 {
		return
	}
	sb.WriteString("Key facts:\n")
	for _, fact := range summary.FactsExtracted {
		if fact.Key == "" && fact.Value == "" {
			continue
		}
		sb.WriteString(fmt.Sprintf("- %s: %s\n", fact.Key, fact.Value))
	}
	sb.WriteString("\n")
}

func appendVectorSection(sb *strings.Builder, vectorMemories []port.MemoryChunk) {
	if sb == nil || len(vectorMemories) == 0 {
		return
	}
	sb.WriteString("Relevant memories:\n")
	for _, memory := range vectorMemories {
		content := strings.TrimSpace(memory.Content)
		if content == "" {
			continue
		}
		sb.WriteString(fmt.Sprintf("- %s\n", content))
	}
	sb.WriteString("\n")
}

func appendBufferSection(sb *strings.Builder, buffer *entity.MessageBuffer) {
	if sb == nil || buffer == nil {
		return
	}
	messages := buffer.GetAll()
	if len(messages) == 0 {
		return
	}
	sb.WriteString("Recent messages:\n")
	for _, msg := range messages {
		role := strings.Title(msg.Role)
		sb.WriteString(fmt.Sprintf("%s: %s\n", role, msg.Content))
	}
	sb.WriteString("\n")
}

func buildMemoryContextTrace(
	curated *curatedContextAssembly,
	buffer *entity.MessageBuffer,
	summary *entity.Summary,
	vectorMemories []port.MemoryChunk,
) map[string]any {
	if curated == nil {
		return nil
	}

	trace := map[string]any{
		"curated_context_paths":     append([]string(nil), curated.Paths...),
		"curated_observation_count": len(curated.Observations),
		"curated_degraded":          curated.Degraded,
		"curated_strategies":        append([]string(nil), curated.Strategies...),
		"summary_present":           summary != nil && strings.TrimSpace(summary.Content) != "",
		"fact_count":                0,
		"vector_memory_count":       len(vectorMemories),
		"buffer_message_count":      0,
		"curated_observations":      buildCuratedObservationTrace(curated.Observations),
	}
	if summary != nil {
		trace["fact_count"] = len(summary.FactsExtracted)
	}
	if buffer != nil {
		trace["buffer_message_count"] = len(buffer.GetAll())
	}
	return trace
}

func buildCuratedObservationTrace(observations []curatedObservation) []map[string]any {
	items := make([]map[string]any, 0, len(observations))
	for _, observation := range observations {
		items = append(items, map[string]any{
			"id":        observation.ID,
			"type":      observation.Type,
			"title":     observation.Title,
			"content":   observation.Content,
			"scope":     observation.Scope,
			"topic_key": observation.TopicKey,
			"tool_name": observation.ToolName,
		})
	}
	return items
}
