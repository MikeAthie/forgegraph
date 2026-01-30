package usecase

import (
	"context"
	"errors"
	"sync"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
)

// ErrSummarizationQueueFull indicates the queue is at capacity.
var ErrSummarizationQueueFull = errors.New("summarization queue full")

// SummarizationRequest describes an async summarization job.
type SummarizationRequest struct {
	RunID             string
	TenantID          string
	Messages          []entity.Message
	Options           port.SummarizeOptions
	SummaryTTLSeconds int
	FactsTTLSeconds   int
	Callback          func(*entity.Summary, error)
}

// SummarizationWorker processes summarization requests asynchronously.
type SummarizationWorker struct {
	summarizer port.Summarizer
	store      port.SummaryStore
	queue      chan SummarizationRequest
	workers    int
	startOnce  sync.Once
	ctx        context.Context
	cancel     context.CancelFunc
	wg         sync.WaitGroup
}

// NewSummarizationWorker creates a worker with bounded queue.
func NewSummarizationWorker(summarizer port.Summarizer, store port.SummaryStore, workers, queueSize int) *SummarizationWorker {
	if workers <= 0 {
		workers = 2
	}
	if queueSize <= 0 {
		queueSize = 100
	}

	return &SummarizationWorker{
		summarizer: summarizer,
		store:      store,
		queue:      make(chan SummarizationRequest, queueSize),
		workers:    workers,
	}
}

// Start launches worker goroutines bound to the provided context.
func (w *SummarizationWorker) Start(ctx context.Context) {
	w.startOnce.Do(func() {
		w.ctx, w.cancel = context.WithCancel(ctx)
		for i := 0; i < w.workers; i++ {
			w.wg.Add(1)
			go w.loop()
		}
	})
}

// Stop gracefully shuts down workers.
func (w *SummarizationWorker) Stop() {
	if w.cancel != nil {
		w.cancel()
	}
	w.wg.Wait()
}

// Submit enqueues a summarization request or returns ErrSummarizationQueueFull.
func (w *SummarizationWorker) Submit(req SummarizationRequest) error {
	select {
	case w.queue <- req:
		return nil
	default:
		return ErrSummarizationQueueFull
	}
}

func (w *SummarizationWorker) loop() {
	defer w.wg.Done()

	for {
		select {
		case <-w.ctx.Done():
			return
		case req := <-w.queue:
			w.handle(req)
		}
	}
}

func (w *SummarizationWorker) handle(req SummarizationRequest) {
	if w.summarizer == nil {
		if req.Callback != nil {
			req.Callback(nil, errors.New("summarizer not configured"))
		}
		return
	}

	ctx := port.WithTenantID(w.ctx, req.TenantID)
	summary, err := w.summarizer.Summarize(ctx, req.Messages, req.Options)
	if err == nil && w.store != nil && summary != nil {
		if storeErr := w.store.StoreSummary(ctx, req.TenantID, req.RunID, summary, req.SummaryTTLSeconds); storeErr != nil {
			err = storeErr
		} else if len(summary.FactsExtracted) > 0 {
			if factsErr := w.store.StoreFacts(ctx, req.TenantID, req.RunID, summary.FactsExtracted, req.FactsTTLSeconds); factsErr != nil {
				err = factsErr
			}
		}
	}

	if req.Callback != nil {
		req.Callback(summary, err)
	}
}
