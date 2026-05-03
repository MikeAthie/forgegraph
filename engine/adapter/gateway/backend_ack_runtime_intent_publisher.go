package gateway

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path"
	"strings"
	"time"

	"github.com/forgegraph/engine/application/port"
)

type RuntimeIntentOutcomeWaitConfig struct {
	Timeout      time.Duration
	PollInterval time.Duration
}

func DefaultRuntimeIntentOutcomeWaitConfig() RuntimeIntentOutcomeWaitConfig {
	return RuntimeIntentOutcomeWaitConfig{
		Timeout:      10 * time.Second,
		PollInterval: 100 * time.Millisecond,
	}
}

type BackendAcknowledgedRuntimeIntentPublisher struct {
	inner      port.RuntimeIntentPublisher
	baseURL    string
	secret     string
	client     *http.Client
	waitConfig RuntimeIntentOutcomeWaitConfig
}

type runtimeIntentOutcomeEnvelope struct {
	Data runtimeIntentOutcome `json:"data"`
}

type runtimeIntentOutcome struct {
	Outcome    string `json:"outcome"`
	Reason     string `json:"reason"`
	ErrorClass string `json:"error_class"`
}

type RuntimeIntentOutcomeError struct {
	IntentID   string
	IntentType string
	RunID      string
	Outcome    string
	Reason     string
	ErrorClass string
}

func (e *RuntimeIntentOutcomeError) Error() string {
	if e == nil {
		return ""
	}
	detail := strings.TrimSpace(e.Reason)
	if detail == "" {
		detail = strings.TrimSpace(e.ErrorClass)
	}
	if detail == "" {
		detail = "no backend reason supplied"
	}
	return fmt.Sprintf(
		"runtime intent %s outcome=%s type=%s run_id=%s: %s",
		e.IntentID,
		e.Outcome,
		e.IntentType,
		e.RunID,
		detail,
	)
}

func NewBackendAcknowledgedRuntimeIntentPublisher(
	inner port.RuntimeIntentPublisher,
	baseURL string,
	secret string,
	client *http.Client,
	config RuntimeIntentOutcomeWaitConfig,
) (*BackendAcknowledgedRuntimeIntentPublisher, error) {
	if inner == nil {
		return nil, fmt.Errorf("backend-ack runtime intent publisher requires an inner publisher")
	}
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if baseURL == "" {
		return nil, fmt.Errorf("backend-ack runtime intent publisher requires a control plane URL")
	}
	if client == nil {
		client = &http.Client{Timeout: 10 * time.Second}
	}
	defaults := DefaultRuntimeIntentOutcomeWaitConfig()
	if config.Timeout <= 0 {
		config.Timeout = defaults.Timeout
	}
	if config.PollInterval <= 0 {
		config.PollInterval = defaults.PollInterval
	}
	return &BackendAcknowledgedRuntimeIntentPublisher{
		inner:      inner,
		baseURL:    baseURL,
		secret:     secret,
		client:     client,
		waitConfig: config,
	}, nil
}

func (p *BackendAcknowledgedRuntimeIntentPublisher) Publish(ctx context.Context, intent *port.RuntimeIntentEnvelope) error {
	if err := p.inner.Publish(ctx, intent); err != nil {
		return err
	}
	return p.waitForOutcome(ctx, intent)
}

func (p *BackendAcknowledgedRuntimeIntentPublisher) waitForOutcome(ctx context.Context, intent *port.RuntimeIntentEnvelope) error {
	if intent == nil {
		return fmt.Errorf("runtime intent is required")
	}
	waitCtx, cancel := context.WithTimeout(ctx, p.waitConfig.Timeout)
	defer cancel()

	ticker := time.NewTicker(p.waitConfig.PollInterval)
	defer ticker.Stop()

	for {
		outcome, pending, err := p.fetchOutcome(waitCtx, intent.IntentID)
		if err != nil {
			if waitCtx.Err() != nil {
				return fmt.Errorf(
					"runtime intent %s outcome wait timed out after %s: %w",
					intent.IntentID,
					p.waitConfig.Timeout,
					waitCtx.Err(),
				)
			}
			return err
		}
		if !pending {
			switch outcome.Outcome {
			case "processed", "duplicate":
				return nil
			default:
				return &RuntimeIntentOutcomeError{
					IntentID:   intent.IntentID,
					IntentType: intent.IntentType,
					RunID:      intent.RunID,
					Outcome:    outcome.Outcome,
					Reason:     outcome.Reason,
					ErrorClass: outcome.ErrorClass,
				}
			}
		}

		select {
		case <-waitCtx.Done():
			return fmt.Errorf(
				"runtime intent %s outcome wait timed out after %s",
				intent.IntentID,
				p.waitConfig.Timeout,
			)
		case <-ticker.C:
		}
	}
}

func (p *BackendAcknowledgedRuntimeIntentPublisher) fetchOutcome(ctx context.Context, intentID string) (runtimeIntentOutcome, bool, error) {
	req, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		p.resolveURL(fmt.Sprintf("/api/engine/runtime-intents/%s", url.PathEscape(intentID))),
		bytes.NewReader(nil),
	)
	if err != nil {
		return runtimeIntentOutcome{}, false, err
	}
	p.sign(req, nil)

	resp, err := p.client.Do(req)
	if err != nil {
		return runtimeIntentOutcome{}, false, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return runtimeIntentOutcome{}, false, err
	}
	if resp.StatusCode == http.StatusNotFound {
		return runtimeIntentOutcome{}, true, nil
	}
	if resp.StatusCode >= http.StatusBadRequest {
		return runtimeIntentOutcome{}, false, fmt.Errorf(
			"runtime intent outcome lookup failed status=%d body=%s",
			resp.StatusCode,
			strings.TrimSpace(string(body)),
		)
	}
	envelope := runtimeIntentOutcomeEnvelope{}
	if err := json.Unmarshal(body, &envelope); err != nil {
		return runtimeIntentOutcome{}, false, err
	}
	return envelope.Data, false, nil
}

func (p *BackendAcknowledgedRuntimeIntentPublisher) resolveURL(relativePath string) string {
	base, err := url.Parse(p.baseURL)
	if err != nil {
		return p.baseURL + relativePath
	}
	base.Path = path.Join(base.Path, relativePath)
	return base.String()
}

func (p *BackendAcknowledgedRuntimeIntentPublisher) sign(req *http.Request, body []byte) {
	if req == nil || p.secret == "" {
		return
	}
	timestamp := fmt.Sprintf("%d", time.Now().UnixMilli())
	message := append([]byte(timestamp+"."), body...)
	mac := hmac.New(sha256.New, []byte(p.secret))
	mac.Write(message)
	req.Header.Set("X-Forgegraph-Timestamp", timestamp)
	req.Header.Set("X-Forgegraph-Signature", hex.EncodeToString(mac.Sum(nil)))
}
