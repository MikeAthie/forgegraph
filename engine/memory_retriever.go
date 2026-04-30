package main

import (
	"context"
	"encoding/json"
	"errors"
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
		return port.MemoryRetrieveResponse{}, errors.New(resp.Error)
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

func (r *GrpcMemoryRetriever) SaveObservation(ctx context.Context, request port.ObservationSaveRequest) (port.Observation, error) {
	if r == nil || r.client == nil {
		return port.Observation{}, fmt.Errorf("memory retriever not configured")
	}

	resp, err := r.client.SaveObservation(ctx, &SaveObservationRequest{
		TenantId:      request.TenantID,
		ObservationId: request.ObservationID,
		GraphId:       request.GraphID,
		RunId:         request.RunID,
		SessionId:     request.SessionID,
		AgentId:       request.AgentID,
		Type:          request.Type,
		Title:         request.Title,
		Content:       request.Content,
		Scope:         request.Scope,
		TopicKey:      request.TopicKey,
		ToolName:      request.ToolName,
		Dedupe:        request.Dedupe,
		UpdateTopic:   request.UpdateTopic,
	})
	if err != nil {
		return port.Observation{}, err
	}
	if resp.GetError() != "" {
		return port.Observation{}, errors.New(resp.GetError())
	}
	if resp.GetObservation() == nil {
		return port.Observation{}, fmt.Errorf("memory service returned no observation")
	}
	return observationFromProto(resp.GetObservation()), nil
}

func (r *GrpcMemoryRetriever) SearchObservations(ctx context.Context, request port.ObservationSearchRequest) ([]port.Observation, error) {
	if r == nil || r.client == nil {
		return nil, fmt.Errorf("memory retriever not configured")
	}

	resp, err := r.client.SearchObservations(ctx, &SearchObservationsRequest{
		TenantId:       request.TenantID,
		Query:          request.Query,
		GraphId:        request.GraphID,
		RunId:          request.RunID,
		SessionId:      request.SessionID,
		AgentId:        request.AgentID,
		Scope:          request.Scope,
		Type:           request.Type,
		TopicKey:       request.TopicKey,
		Limit:          int32(request.Limit),
		IncludeDeleted: request.IncludeDeleted,
	})
	if err != nil {
		return nil, err
	}
	if resp.GetError() != "" {
		return nil, errors.New(resp.GetError())
	}
	return observationsFromProto(resp.GetObservations()), nil
}

func (r *GrpcMemoryRetriever) GetContext(ctx context.Context, request port.ObservationContextRequest) (port.ObservationContextResponse, error) {
	if r == nil || r.client == nil {
		return port.ObservationContextResponse{}, fmt.Errorf("memory retriever not configured")
	}

	resp, err := r.client.GetContext(ctx, &GetContextRequest{
		TenantId:  request.TenantID,
		GraphId:   request.GraphID,
		RunId:     request.RunID,
		SessionId: request.SessionID,
		AgentId:   request.AgentID,
		Query:     request.Query,
		Limit:     int32(request.Limit),
	})
	if err != nil {
		return port.ObservationContextResponse{}, err
	}
	if resp.GetError() != "" {
		return port.ObservationContextResponse{}, errors.New(resp.GetError())
	}
	return port.ObservationContextResponse{
		Observations: observationsFromProto(resp.GetObservations()),
		Degraded:     resp.GetDegraded(),
		Strategies:   append([]string(nil), resp.GetStrategies()...),
	}, nil
}

func (r *GrpcMemoryRetriever) GetTimeline(ctx context.Context, request port.ObservationTimelineRequest) ([]port.Observation, error) {
	if r == nil || r.client == nil {
		return nil, fmt.Errorf("memory retriever not configured")
	}

	resp, err := r.client.GetTimeline(ctx, &GetTimelineRequest{
		TenantId:       request.TenantID,
		GraphId:        request.GraphID,
		RunId:          request.RunID,
		SessionId:      request.SessionID,
		AgentId:        request.AgentID,
		Scope:          request.Scope,
		Limit:          int32(request.Limit),
		IncludeDeleted: request.IncludeDeleted,
	})
	if err != nil {
		return nil, err
	}
	if resp.GetError() != "" {
		return nil, errors.New(resp.GetError())
	}
	return observationsFromProto(resp.GetObservations()), nil
}

func observationsFromProto(items []*Observation) []port.Observation {
	if len(items) == 0 {
		return nil
	}

	observations := make([]port.Observation, 0, len(items))
	for _, item := range items {
		if item == nil {
			continue
		}
		observations = append(observations, observationFromProto(item))
	}
	return observations
}

func observationFromProto(item *Observation) port.Observation {
	if item == nil {
		return port.Observation{}
	}

	return port.Observation{
		ID:             item.GetId(),
		TenantID:       item.GetTenantId(),
		GraphID:        item.GetGraphId(),
		RunID:          item.GetRunId(),
		SessionID:      item.GetSessionId(),
		AgentID:        item.GetAgentId(),
		Type:           item.GetType(),
		Title:          item.GetTitle(),
		Content:        item.GetContent(),
		Scope:          item.GetScope(),
		TopicKey:       item.GetTopicKey(),
		ToolName:       item.GetToolName(),
		RevisionCount:  int(item.GetRevisionCount()),
		DuplicateCount: int(item.GetDuplicateCount()),
		LastSeenAt:     parseObservationTime(item.GetLastSeenAt()),
		CreatedAt:      parseObservationTime(item.GetCreatedAt()),
		UpdatedAt:      parseObservationTime(item.GetUpdatedAt()),
		DeletedAt:      parseObservationTimePtr(item.GetDeletedAt()),
		IsDeleted:      item.GetIsDeleted(),
	}
}

func parseObservationTime(raw string) time.Time {
	if raw == "" {
		return time.Time{}
	}
	parsed, err := time.Parse(time.RFC3339, raw)
	if err != nil {
		return time.Time{}
	}
	return parsed
}

func parseObservationTimePtr(raw string) *time.Time {
	if raw == "" {
		return nil
	}
	parsed := parseObservationTime(raw)
	if parsed.IsZero() {
		return nil
	}
	return &parsed
}
