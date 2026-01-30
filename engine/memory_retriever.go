package main

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/forgegraph/engine/application/port"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// GrpcMemoryRetriever calls the control plane memory gRPC service.
type GrpcMemoryRetriever struct {
	client MemoryServiceClient
}

func NewGrpcMemoryRetriever(host, port string) (*GrpcMemoryRetriever, error) {
	target := fmt.Sprintf("%s:%s", host, port)
	conn, err := grpc.Dial(target, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, err
	}
	return &GrpcMemoryRetriever{client: NewMemoryServiceClient(conn)}, nil
}

func (r *GrpcMemoryRetriever) Retrieve(ctx context.Context, request port.MemoryRetrieveRequest) (port.MemoryRetrieveResponse, error) {
	if r == nil || r.client == nil {
		return port.MemoryRetrieveResponse{}, fmt.Errorf("memory retriever not configured")
	}

	topK := request.TopK
	if topK <= 0 {
		topK = 5
	}
	threshold := request.Threshold
	if threshold <= 0 {
		threshold = 0.7
	}
	recency := request.RecencyWeight
	if recency < 0 {
		recency = 0.2
	}

	resp, err := r.client.RetrieveMemory(ctx, &RetrieveMemoryRequest{
		TenantId:       request.TenantID,
		Query:          request.Query,
		AgentId:        request.AgentID,
		RunId:          request.RunID,
		SessionId:      request.SessionID,
		TopK:           int32(topK),
		Threshold:      threshold,
		RecencyWeight:  recency,
		EmbeddingModel: request.EmbeddingModel,
	})
	if err != nil {
		return port.MemoryRetrieveResponse{}, err
	}
	if resp.Error != "" {
		return port.MemoryRetrieveResponse{}, fmt.Errorf(resp.Error)
	}

	chunks := make([]port.MemoryChunk, 0, len(resp.Chunks))
	for _, chunk := range resp.Chunks {
		ts := time.Time{}
		if chunk.SourceTimestamp != "" {
			if parsed, err := time.Parse(time.RFC3339, chunk.SourceTimestamp); err == nil {
				ts = parsed
			}
		}
		metadata := map[string]any{}
		if chunk.MetadataJson != "" {
			_ = json.Unmarshal([]byte(chunk.MetadataJson), &metadata)
		}
		chunks = append(chunks, port.MemoryChunk{
			Content:         chunk.Content,
			Score:           chunk.Score,
			SourceTimestamp: ts,
			Metadata:        metadata,
		})
	}

	return port.MemoryRetrieveResponse{Chunks: chunks}, nil
}
