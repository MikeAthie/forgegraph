package usecase

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
)

func TestSummarizationWorker_SubmitAndProcess(t *testing.T) {
	mockSummarizer := &testSummarizer{}
	worker := NewSummarizationWorker(mockSummarizer, 1, 2)
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
}

func TestSummarizationWorker_QueueFull(t *testing.T) {
	worker := NewSummarizationWorker(&testSummarizer{}, 1, 1)

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
