package summarizer

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/adapter/metrics"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/google/uuid"
)

const (
	defaultSummaryModel      = "gpt-4"
	defaultMaxOutputTokens   = 512
	defaultRetryDelay        = 200 * time.Millisecond
	defaultMaxRetries        = 3
	summarizeSystemPrompt    = "You are a summarization service. Return only JSON with keys: summary (string), facts (array of {key,value,confidence,source_node_id})."
	extractFactsSystemPrompt = "You are a fact extraction service. Return only JSON with key: facts (array of {key,value,confidence,source_node_id})."
)

// UsageTracker records summarization usage through a backend-owned contract.
type UsageTracker interface {
	RecordSummarizationUsage(ctx context.Context, tenantID, model string, usage *executor.LLMUsage) error
}

// LLMSummarizer implements Summarizer using an LLM client.
type LLMSummarizer struct {
	client     executor.LLMClient
	model      string
	maxRetries int
	retryDelay time.Duration
	costs      UsageTracker
}

// NewLLMSummarizer creates a new summarizer with sensible defaults.
func NewLLMSummarizer(client executor.LLMClient, model string) *LLMSummarizer {
	return NewLLMSummarizerWithTracker(client, model, nil)
}

// NewLLMSummarizerWithTracker creates a summarizer with an optional usage tracker.
func NewLLMSummarizerWithTracker(client executor.LLMClient, model string, tracker UsageTracker) *LLMSummarizer {
	if model == "" {
		model = defaultSummaryModel
	}
	return &LLMSummarizer{
		client:     client,
		model:      model,
		maxRetries: defaultMaxRetries,
		retryDelay: defaultRetryDelay,
		costs:      tracker,
	}
}

// Summarize generates a summary and extracted facts for the provided messages.
func (s *LLMSummarizer) Summarize(ctx context.Context, messages []entity.Message, opts port.SummarizeOptions) (*entity.Summary, error) {
	if s.client == nil {
		return nil, errors.New("summarizer requires LLM client")
	}

	model := s.model
	if opts.Model != "" {
		model = opts.Model
	}

	maxTokens := opts.MaxOutputTokens
	if maxTokens <= 0 {
		maxTokens = defaultMaxOutputTokens
	}

	prompt := buildSummaryPrompt(messages, opts.PreserveFacts)
	request := &executor.LLMRequest{
		Model:        model,
		SystemPrompt: summarizeSystemPrompt,
		Prompt:       prompt,
		MaxTokens:    maxTokens,
		Temperature:  0.2,
	}

	response, err := s.completeWithRetry(ctx, request)
	if err != nil {
		return nil, err
	}
	if s.costs != nil && response.Usage != nil {
		tenantId := port.TenantIDFrom(ctx)

		if err := s.recordCostsWithRetry(ctx, tenantId, model, response.Usage); err != nil {
			log.Printf(
				"cost tracking failed after retries tentant_id=%s model=%s input_tokens=%d output_tokens=%d err=%v",
				tenantId,
				model,
				response.Usage.PromptTokens,
				response.Usage.CompletionTokens,
				err,
			)
			metrics.RecordCostTrackingFailures("summarization", categorizeError(err))
		}
	}

	payload, err := ExtractJSON(response.Content)
	if err != nil {
		cleaned := stripMarkdownCodeBlocks(response.Content)
		payload, err = ExtractJSON(cleaned)
		if err != nil {
			return nil, fmt.Errorf("failed to extract JSON: %w", err)
		}
	}

	var parsed struct {
		Summary string        `json:"summary"`
		Facts   []entity.Fact `json:"facts"`
	}
	if err := json.Unmarshal([]byte(payload), &parsed); err != nil {
		return nil, fmt.Errorf("failed to parse summary JSON: %w", err)
	}

	if strings.TrimSpace(parsed.Summary) == "" {
		return nil, errors.New("summary content is empty")
	}

	return &entity.Summary{
		ID:             uuid.NewString(),
		Content:        parsed.Summary,
		SourceCount:    len(messages),
		FactsExtracted: parsed.Facts,
		CreatedAt:      time.Now().UTC(),
	}, nil
}

// ExtractFacts extracts facts from the provided messages.
func (s *LLMSummarizer) ExtractFacts(ctx context.Context, messages []entity.Message) ([]entity.Fact, error) {
	if s.client == nil {
		return nil, errors.New("summarizer requires LLM client")
	}

	request := &executor.LLMRequest{
		Model:        s.model,
		SystemPrompt: extractFactsSystemPrompt,
		Prompt:       buildFactsPrompt(messages),
		MaxTokens:    defaultMaxOutputTokens,
		Temperature:  0.0,
	}

	response, err := s.completeWithRetry(ctx, request)
	if err != nil {
		return nil, err
	}
	if s.costs != nil && response.Usage != nil {
		tenantID := port.TenantIDFrom(ctx)
		if err := s.recordCostsWithRetry(ctx, tenantID, s.model, response.Usage); err != nil {
			log.Printf("cost tracking failed (extract_facts) tenant_id=%v model=%s err=%v", tenantID, s.model, err)
			metrics.RecordCostTrackingFailures("extract_facts", categorizeError(err))
		}
	}

	payload, err := ExtractJSON(response.Content)
	if err != nil {
		cleaned := stripMarkdownCodeBlocks(response.Content)
		payload, err = ExtractJSON(cleaned)
		if err != nil {
			return nil, fmt.Errorf("failed to extract JSON: %w", err)
		}
	}

	var parsed struct {
		Facts []entity.Fact `json:"facts"`
	}
	if err := json.Unmarshal([]byte(payload), &parsed); err != nil {
		return nil, fmt.Errorf("failed to parse facts JSON: %w", err)
	}

	return parsed.Facts, nil
}

func (s *LLMSummarizer) completeWithRetry(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	var lastErr error
	maxRetries := s.maxRetries
	if maxRetries <= 0 {
		maxRetries = 1
	}

	for attempt := 1; attempt <= maxRetries; attempt++ {
		response, err := s.client.Complete(ctx, request)
		if err == nil {
			return response, nil
		}

		lastErr = err
		if !isRetryable(err) || attempt == maxRetries {
			break
		}

		delay := s.retryDelay
		if delay <= 0 {
			delay = defaultRetryDelay
		}

		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(delay * time.Duration(attempt)):
		}
	}

	return nil, fmt.Errorf("summarizer failed after %d attempts: %w", maxRetries, lastErr)
}

func isRetryable(err error) bool {
	if domain.IsRetryable(err) {
		return true
	}

	type retryable interface {
		IsRetryable() bool
	}

	var r retryable
	if errors.As(err, &r) {
		return r.IsRetryable()
	}

	return false
}

func buildSummaryPrompt(messages []entity.Message, preserveFacts bool) string {
	var builder strings.Builder
	builder.WriteString("Summarize the conversation below.")
	if preserveFacts {
		builder.WriteString(" Preserve key facts and decisions.")
	}
	builder.WriteString("\n\nConversation:\n")
	builder.WriteString(formatMessages(messages))
	return builder.String()
}

func buildFactsPrompt(messages []entity.Message) string {
	return fmt.Sprintf("Extract key facts from the conversation below.\n\nConversation:\n%s", formatMessages(messages))
}

func formatMessages(messages []entity.Message) string {
	var builder strings.Builder
	for _, msg := range messages {
		role := msg.Role
		if role == "" {
			role = "unknown"
		}
		builder.WriteString(role)
		builder.WriteString(": ")
		builder.WriteString(strings.TrimSpace(msg.Content))
		builder.WriteString("\n")
	}
	return strings.TrimSpace(builder.String())
}

func (s *LLMSummarizer) recordCostsWithRetry(
	ctx context.Context,
	tenantId, model string,
	usage *executor.LLMUsage,
) error {
	const maxRetries = 3
	var lastErr error

	for attempt := 1; attempt <= maxRetries; attempt++ {
		err := s.costs.RecordSummarizationUsage(ctx, tenantId, model, usage)
		if err == nil {
			return nil
		}
		lastErr = err

		if ctx.Err() != nil {
			return ctx.Err()
		}

		// Don't retry on validation errors - they won't succeed on retry
		if isValidationError(err) {
			return err
		}

		if attempt < maxRetries {
			metrics.RecordCostTrackingRetry()
			backoff := time.Duration(attempt*100) * time.Millisecond
			select {
			case <-time.After(backoff):
			case <-ctx.Done():
				return ctx.Err()
			}
		}
	}
	return fmt.Errorf("cost tracking failed after %d attempts: %w", maxRetries, lastErr)
}

func categorizeError(err error) string {
	if err == nil {
		return "none"
	}
	s := strings.ToLower(err.Error())

	switch {
	case strings.Contains(s, "connection"):
		return "connection"
	case strings.Contains(s, "timeout"):
		return "timeout"
	case strings.Contains(s, "constraint"):
		return "constraint"
	default:
		return "unknown"
	}
}

func isValidationError(err error) bool {
	if err == nil {
		return false
	}
	s := strings.ToLower(err.Error())
	return strings.Contains(s, "invalid") ||
		strings.Contains(s, "validation") ||
		strings.Contains(s, "constraint")
}
