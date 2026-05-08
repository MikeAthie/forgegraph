package gateway

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/domain"
)

const defaultGeminiBaseURL = "https://generativelanguage.googleapis.com/v1beta"

type GeminiClient struct {
	apiKey     string
	baseURL    string
	httpClient *http.Client
}

type geminiPart struct {
	Text string `json:"text,omitempty"`
}

type geminiContent struct {
	Role  string       `json:"role,omitempty"`
	Parts []geminiPart `json:"parts"`
}

type geminiGenerationConfig struct {
	Temperature     *float64 `json:"temperature,omitempty"`
	MaxOutputTokens int      `json:"maxOutputTokens,omitempty"`
}

type geminiGenerateContentRequest struct {
	Contents          []geminiContent         `json:"contents"`
	SystemInstruction *geminiContent          `json:"systemInstruction,omitempty"`
	GenerationConfig  *geminiGenerationConfig `json:"generationConfig,omitempty"`
}

type geminiGenerateContentResponse struct {
	Candidates []struct {
		Content *geminiContent `json:"content,omitempty"`
		// Gemini returns this as an enum-like string such as STOP, MAX_TOKENS, or SAFETY.
		FinishReason string `json:"finishReason,omitempty"`
	} `json:"candidates,omitempty"`
	UsageMetadata *struct {
		PromptTokenCount     int `json:"promptTokenCount,omitempty"`
		CandidatesTokenCount int `json:"candidatesTokenCount,omitempty"`
		TotalTokenCount      int `json:"totalTokenCount,omitempty"`
	} `json:"usageMetadata,omitempty"`
	ModelVersion string       `json:"modelVersion,omitempty"`
	Error        *geminiError `json:"error,omitempty"`
}

type geminiError struct {
	Code    int    `json:"code,omitempty"`
	Message string `json:"message,omitempty"`
	Status  string `json:"status,omitempty"`
}

func resolveGeminiBaseURL() string {
	if value := strings.TrimSpace(os.Getenv("GEMINI_API_BASE_URL")); value != "" {
		return strings.TrimRight(value, "/")
	}
	return defaultGeminiBaseURL
}

// NewGeminiClientWithKey creates a Gemini Developer API client using an API key.
func NewGeminiClientWithKey(apiKey string) *GeminiClient {
	return &GeminiClient{
		apiKey:  apiKey,
		baseURL: resolveGeminiBaseURL(),
		httpClient: &http.Client{
			Timeout: 120 * time.Second,
		},
	}
}

func (c *GeminiClient) Complete(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	model := strings.TrimSpace(request.Model)
	if model == "" {
		model = "gemini-2.5-flash"
	}

	payload := geminiGenerateContentRequest{
		Contents: buildGeminiContents(request),
	}
	if strings.TrimSpace(request.SystemPrompt) != "" {
		payload.SystemInstruction = &geminiContent{
			Parts: []geminiPart{{Text: request.SystemPrompt}},
		}
	}
	if request.Temperature > 0 || request.MaxTokens > 0 {
		config := &geminiGenerationConfig{}
		if request.Temperature > 0 {
			temperature := request.Temperature
			config.Temperature = &temperature
		}
		if request.MaxTokens > 0 {
			config.MaxOutputTokens = request.MaxTokens
		}
		payload.GenerationConfig = config
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("marshal gemini request: %w", err)
	}

	endpoint := fmt.Sprintf("%s/models/%s:generateContent", c.baseURL, url.PathEscape(strings.TrimPrefix(model, "models/")))
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create gemini request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-goog-api-key", c.apiKey)

	start := time.Now()
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, domain.NewRetryableErrorWithDetails(
			err,
			"gemini request failed",
			"network_error",
			0,
			map[string]any{"provider": "google"},
		)
	}
	defer resp.Body.Close()

	latencyMs := time.Since(start).Milliseconds()
	if resp.StatusCode >= 400 {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return nil, geminiHTTPError(resp, bodyBytes)
	}

	var parsed geminiGenerateContentResponse
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return nil, fmt.Errorf("decode gemini response: %w", err)
	}
	if parsed.Error != nil {
		return nil, fmt.Errorf("gemini error: %s", parsed.Error.Message)
	}

	content, finishReason := extractGeminiText(parsed)
	usage := geminiUsage(parsed)
	responseModel := parsed.ModelVersion
	if strings.TrimSpace(responseModel) == "" {
		responseModel = model
	}

	return &executor.LLMResponse{
		Content:          content,
		Model:            responseModel,
		Provider:         "google",
		LatencyMS:        latencyMs,
		LLMMode:          request.LLMMode,
		CredentialSource: request.CredentialSource,
		Usage:            usage,
		FinishReason:     finishReason,
	}, nil
}

func (c *GeminiClient) StreamComplete(
	ctx context.Context,
	request *executor.LLMRequest,
	onChunk func(string),
) (*executor.LLMResponse, error) {
	response, err := c.Complete(ctx, request)
	if err != nil {
		return nil, err
	}
	if onChunk != nil && response != nil && response.Content != "" {
		onChunk(response.Content)
	}
	return response, nil
}

func buildGeminiContents(request *executor.LLMRequest) []geminiContent {
	if len(request.Messages) == 0 {
		return []geminiContent{{
			Role:  "user",
			Parts: []geminiPart{{Text: request.Prompt}},
		}}
	}

	contents := make([]geminiContent, 0, len(request.Messages))
	for _, message := range request.Messages {
		role := strings.ToLower(strings.TrimSpace(message.Role))
		switch role {
		case "assistant", "model":
			role = "model"
		default:
			role = "user"
		}
		if strings.TrimSpace(message.Content) == "" {
			continue
		}
		contents = append(contents, geminiContent{
			Role:  role,
			Parts: []geminiPart{{Text: message.Content}},
		})
	}
	if len(contents) == 0 {
		return []geminiContent{{
			Role:  "user",
			Parts: []geminiPart{{Text: request.Prompt}},
		}}
	}
	return contents
}

func extractGeminiText(parsed geminiGenerateContentResponse) (string, string) {
	if len(parsed.Candidates) == 0 || parsed.Candidates[0].Content == nil {
		return "", ""
	}
	parts := parsed.Candidates[0].Content.Parts
	textParts := make([]string, 0, len(parts))
	for _, part := range parts {
		if strings.TrimSpace(part.Text) != "" {
			textParts = append(textParts, part.Text)
		}
	}
	return strings.Join(textParts, ""), parsed.Candidates[0].FinishReason
}

func geminiUsage(parsed geminiGenerateContentResponse) *executor.LLMUsage {
	if parsed.UsageMetadata == nil {
		return nil
	}
	total := parsed.UsageMetadata.TotalTokenCount
	if total <= 0 {
		total = parsed.UsageMetadata.PromptTokenCount + parsed.UsageMetadata.CandidatesTokenCount
	}
	return &executor.LLMUsage{
		PromptTokens:     parsed.UsageMetadata.PromptTokenCount,
		CompletionTokens: parsed.UsageMetadata.CandidatesTokenCount,
		TotalTokens:      total,
	}
}

func geminiHTTPError(resp *http.Response, body []byte) error {
	bodyText := strings.TrimSpace(string(body))
	var parsed struct {
		Error *geminiError `json:"error,omitempty"`
	}
	if err := json.Unmarshal(body, &parsed); err == nil && parsed.Error != nil {
		bodyText = strings.TrimSpace(parsed.Error.Message)
		if bodyText == "" {
			bodyText = strings.TrimSpace(parsed.Error.Status)
		}
	}
	if resp.StatusCode == http.StatusTooManyRequests {
		retryAfterMs := parseRetryAfterMs(resp.Header.Get("Retry-After"), time.Now())
		if isOpenAIQuotaExhausted("", bodyText) {
			return fmt.Errorf(
				"gemini quota exhausted (HTTP 429). Increase provider quota/billing and retry: %s",
				bodyText,
			)
		}
		return domain.NewRetryableErrorWithDetails(
			fmt.Errorf("gemini error: status %d: %s", resp.StatusCode, bodyText),
			"gemini rate limited",
			"rate_limited",
			retryAfterMs,
			map[string]any{
				"provider":        "google",
				"status_code":     resp.StatusCode,
				"retry_after_ms":  retryAfterMs,
				"rate_limit_type": "throttled",
			},
		)
	}
	if resp.StatusCode >= 500 {
		return domain.NewRetryableErrorWithDetails(
			fmt.Errorf("gemini error: status %d: %s", resp.StatusCode, bodyText),
			"gemini upstream server error",
			"transient_http_5xx",
			0,
			map[string]any{
				"provider":    "google",
				"status_code": resp.StatusCode,
			},
		)
	}
	return fmt.Errorf("gemini error: status %d: %s", resp.StatusCode, bodyText)
}
