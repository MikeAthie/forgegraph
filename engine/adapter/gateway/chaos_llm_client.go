package gateway

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/domain"
)

const (
	llmChaosModeOff         = "off"
	llmChaosModeDelay       = "delay"
	llmChaosModeTimeout     = "timeout"
	llmChaosModeUnavailable = "unavailable"
	llmChaosModeHang        = "hang"
)

type llmChaosConfig struct {
	Mode         string
	Delay        time.Duration
	ErrorMessage string
}

// NewLLMChaosClientFromEnv wraps an LLM client with opt-in fault injection.
func NewLLMChaosClientFromEnv(base executor.LLMClient) executor.LLMClient {
	cfg := loadLLMChaosConfigFromEnv()
	if cfg.Mode == llmChaosModeOff {
		return base
	}
	return &chaosLLMClient{
		base: base,
		cfg:  cfg,
	}
}

func loadLLMChaosConfigFromEnv() llmChaosConfig {
	mode := strings.ToLower(strings.TrimSpace(os.Getenv("FORGEGRAPH_LLM_CHAOS_MODE")))
	switch mode {
	case "", "none":
		mode = llmChaosModeOff
	case llmChaosModeDelay, llmChaosModeTimeout, llmChaosModeUnavailable, llmChaosModeHang:
	default:
		mode = llmChaosModeOff
	}

	delayMs, err := strconv.Atoi(strings.TrimSpace(os.Getenv("FORGEGRAPH_LLM_CHAOS_DELAY_MS")))
	if err != nil || delayMs < 0 {
		delayMs = 0
	}

	errorMessage := strings.TrimSpace(os.Getenv("FORGEGRAPH_LLM_CHAOS_ERROR_MESSAGE"))
	if errorMessage == "" {
		errorMessage = "simulated llm degradation"
	}

	return llmChaosConfig{
		Mode:         mode,
		Delay:        time.Duration(delayMs) * time.Millisecond,
		ErrorMessage: errorMessage,
	}
}

type chaosLLMClient struct {
	base executor.LLMClient
	cfg  llmChaosConfig
}

func (c *chaosLLMClient) Complete(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	if err := c.beforeCall(ctx, request); err != nil {
		return nil, err
	}
	return c.base.Complete(ctx, request)
}

func (c *chaosLLMClient) StreamComplete(
	ctx context.Context,
	request *executor.LLMRequest,
	onChunk func(string),
) (*executor.LLMResponse, error) {
	if err := c.beforeCall(ctx, request); err != nil {
		return nil, err
	}
	streamer, ok := c.base.(executor.LLMStreamingClient)
	if !ok {
		return c.base.Complete(ctx, request)
	}
	return streamer.StreamComplete(ctx, request, onChunk)
}

func (c *chaosLLMClient) beforeCall(ctx context.Context, request *executor.LLMRequest) error {
	if c.cfg.Delay > 0 {
		if err := sleepWithContextForChaos(ctx, c.cfg.Delay); err != nil {
			return c.timeoutError(request, err)
		}
	}

	switch c.cfg.Mode {
	case llmChaosModeDelay:
		return nil
	case llmChaosModeTimeout:
		return c.timeoutError(request, context.DeadlineExceeded)
	case llmChaosModeUnavailable:
		return c.unavailableError(request)
	case llmChaosModeHang:
		<-ctx.Done()
		return c.timeoutError(request, ctx.Err())
	default:
		return nil
	}
}

func (c *chaosLLMClient) timeoutError(request *executor.LLMRequest, err error) error {
	if err == nil {
		err = context.DeadlineExceeded
	}
	return domain.NewRetryableErrorWithDetails(
		err,
		c.cfg.ErrorMessage,
		"llm_chaos_timeout",
		0,
		map[string]any{
			"provider":   request.Provider,
			"model":      request.Model,
			"chaos_mode": c.cfg.Mode,
		},
	)
}

func (c *chaosLLMClient) unavailableError(request *executor.LLMRequest) error {
	return domain.NewRetryableErrorWithDetails(
		fmt.Errorf("%s", c.cfg.ErrorMessage),
		"LLM unavailable",
		"llm_chaos_unavailable",
		0,
		map[string]any{
			"provider":   request.Provider,
			"model":      request.Model,
			"chaos_mode": c.cfg.Mode,
		},
	)
}

func sleepWithContextForChaos(ctx context.Context, delay time.Duration) error {
	if delay <= 0 {
		return nil
	}
	timer := time.NewTimer(delay)
	defer timer.Stop()

	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}
