package usecase

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
)

func TestSummarizationWorker_SubmitAndProcess(t *testing.T) {
	mockSummarizer := &testSummarizer{}
	mockStore := &testSummaryStore{}
	worker := NewSummarizationWorker(mockSummarizer, mockStore, 1, 2)
	worker.Start(context.Background())
	defer worker.Stop()

	done := make(chan struct{})
	req := SummarizationRequest{
		RunID:             "run-1",
		TenantID:          "tenant-1",
		Messages:          []entity.Message{{Role: "user", Content: "hello"}},
		SummaryTTLSeconds: 60,
		FactsTTLSeconds:   120,
		Callback: func(summary *entity.Summary, err error) {
			if err != nil {
				t.Errorf("unexpected error: %v", err)
			}
			if summary == nil || summary.Content != "ok" {
				t.Errorf("unexpected summary: %#v", summary)
			}
			close(done)
		},
	}

	if err := worker.Submit(req); err != nil {
		t.Fatalf("Submit failed: %v", err)
	}

	<-done

	if mockStore.storeCalls != 1 {
		t.Fatalf("expected store summary call, got %d", mockStore.storeCalls)
	}
	if mockStore.factCalls != 1 {
		t.Fatalf("expected store facts call, got %d", mockStore.factCalls)
	}
}

func TestSummarizationWorker_QueueFull(t *testing.T) {
	worker := NewSummarizationWorker(&testSummarizer{}, nil, 1, 1)

	if err := worker.Submit(SummarizationRequest{RunID: "run-1"}); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if err := worker.Submit(SummarizationRequest{RunID: "run-2"}); !errors.Is(err, ErrSummarizationQueueFull) {
		t.Fatalf("expected queue full error, got %v", err)
	}
}

type testSummarizer struct{}

func (t *testSummarizer) Summarize(ctx context.Context, messages []entity.Message, opts port.SummarizeOptions) (*entity.Summary, error) {
	return &entity.Summary{
		ID:             "summary-1",
		Content:        "ok",
		SourceCount:    len(messages),
		FactsExtracted: []entity.Fact{{Key: "k", Value: "v"}},
		CreatedAt:      time.Now().UTC(),
	}, nil
}

func (t *testSummarizer) ExtractFacts(ctx context.Context, messages []entity.Message) ([]entity.Fact, error) {
	return nil, nil
}

type testSummaryStore struct {
	mu         sync.Mutex
	storeCalls int
	factCalls  int
}

func (t *testSummaryStore) StoreSummary(ctx context.Context, tenantID, runID string, summary *entity.Summary, ttlSeconds int) error {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.storeCalls++
	return nil
}

func (t *testSummaryStore) StoreFacts(ctx context.Context, tenantID, runID string, facts []entity.Fact, ttlSeconds int) error {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.factCalls++
	return nil
}

func (t *testSummaryStore) GetSummary(ctx context.Context, tenantID, runID string) (*entity.Summary, bool, error) {
	return nil, false, nil
}

func (t *testSummaryStore) GetFact(ctx context.Context, tenantID, runID, factKey string) (*entity.Fact, bool, error) {
	return nil, false, nil
}
