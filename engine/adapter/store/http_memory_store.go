package store

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// HTTPMemoryStore persists memory through signed control-plane HTTP APIs.
type HTTPMemoryStore struct {
	baseURL string
	secret  string
	client  *http.Client
}

type memoryStoreEnvelope[T any] struct {
	Data T `json:"data"`
}

type memoryStoreErrorEnvelope struct {
	Error struct {
		Code    string `json:"code"`
		Message string `json:"message"`
	} `json:"error"`
}

type memoryStoreError struct {
	Status  int
	Code    string
	Message string
}

func (e *memoryStoreError) Error() string {
	if e == nil {
		return ""
	}
	if e.Code != "" && e.Message != "" {
		return fmt.Sprintf("%s: %s", e.Code, e.Message)
	}
	if e.Message != "" {
		return e.Message
	}
	return fmt.Sprintf("memory store request failed with status %d", e.Status)
}

// NewHTTPMemoryStore creates a control-plane-backed memory store.
func NewHTTPMemoryStore(baseURL, secret string, client *http.Client) *HTTPMemoryStore {
	if client == nil {
		client = &http.Client{Timeout: 10 * time.Second}
	}
	return &HTTPMemoryStore{
		baseURL: strings.TrimRight(baseURL, "/"),
		secret:  secret,
		client:  client,
	}
}

func (s *HTTPMemoryStore) Get(ctx context.Context, namespace, key string) (value any, found bool, err error) {
	var payload struct {
		Value any `json:"value"`
	}
	err = s.do(ctx, http.MethodGet, s.memoryEntryPath(namespace, key), nil, &payload)
	if err != nil {
		var apiErr *memoryStoreError
		if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound {
			return nil, false, nil
		}
		return nil, false, err
	}
	return payload.Value, true, nil
}

func (s *HTTPMemoryStore) Set(ctx context.Context, namespace, key string, value any, ttlSeconds int) error {
	payload := map[string]any{
		"value":       value,
		"ttl_seconds": ttlSeconds,
	}
	return s.do(ctx, http.MethodPut, s.memoryEntryPath(namespace, key), payload, nil)
}

func (s *HTTPMemoryStore) Delete(ctx context.Context, namespace, key string) (bool, error) {
	err := s.do(ctx, http.MethodDelete, s.memoryEntryPath(namespace, key), nil, nil)
	if err != nil {
		var apiErr *memoryStoreError
		if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound {
			return false, nil
		}
		return false, err
	}
	return true, nil
}

func (s *HTTPMemoryStore) do(ctx context.Context, method, relativePath string, payload any, out any) error {
	body, err := s.marshalBody(payload)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, method, s.resolveURL(relativePath), bytes.NewReader(body))
	if err != nil {
		return err
	}
	if len(body) > 0 {
		req.Header.Set("Content-Type", "application/json")
	}
	s.sign(req, body)

	resp, err := s.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	if resp.StatusCode >= http.StatusBadRequest {
		return decodeMemoryStoreError(resp.StatusCode, respBody)
	}
	if out == nil || len(respBody) == 0 {
		return nil
	}

	wrapper := memoryStoreEnvelope[json.RawMessage]{}
	if err := json.Unmarshal(respBody, &wrapper); err != nil {
		return err
	}
	if len(wrapper.Data) == 0 {
		return nil
	}
	return json.Unmarshal(wrapper.Data, out)
}

func (s *HTTPMemoryStore) marshalBody(payload any) ([]byte, error) {
	if payload == nil {
		return nil, nil
	}
	return json.Marshal(payload)
}

func (s *HTTPMemoryStore) resolveURL(relativePath string) string {
	base, err := url.Parse(s.baseURL)
	if err != nil {
		return s.baseURL + relativePath
	}
	rel, err := url.Parse(relativePath)
	if err != nil {
		return s.baseURL + relativePath
	}
	return base.ResolveReference(rel).String()
}

func (s *HTTPMemoryStore) sign(req *http.Request, body []byte) {
	if req == nil || s.secret == "" {
		return
	}
	timestamp := fmt.Sprintf("%d", time.Now().UnixMilli())
	message := append([]byte(timestamp+"."), body...)
	mac := hmac.New(sha256.New, []byte(s.secret))
	mac.Write(message)
	req.Header.Set("X-Forgegraph-Timestamp", timestamp)
	req.Header.Set("X-Forgegraph-Signature", hex.EncodeToString(mac.Sum(nil)))
}

func decodeMemoryStoreError(statusCode int, body []byte) error {
	envelope := memoryStoreErrorEnvelope{}
	if err := json.Unmarshal(body, &envelope); err == nil && (envelope.Error.Code != "" || envelope.Error.Message != "") {
		return &memoryStoreError{
			Status:  statusCode,
			Code:    envelope.Error.Code,
			Message: envelope.Error.Message,
		}
	}
	return &memoryStoreError{
		Status:  statusCode,
		Message: strings.TrimSpace(string(body)),
	}
}

func (s *HTTPMemoryStore) memoryEntryPath(namespace, key string) string {
	values := url.Values{}
	values.Set("namespace", namespace)
	values.Set("key", key)
	return "/api/engine/memory/entries?" + values.Encode()
}
