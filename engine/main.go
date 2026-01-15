package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"

	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

// EngineServer implements the Engine gRPC service
type EngineServer struct {
	UnimplementedEngineServiceServer
}

// Ping implements the Ping RPC method
func (s *EngineServer) Ping(ctx context.Context, req *PingRequest) (*PingResponse, error) {
	log.Printf("Received Ping request with message: %s", req.Message)
	return &PingResponse{
		Message: "pong",
	}, nil
}

func main() {
	port := os.Getenv("GRPC_PORT")
	if port == "" {
		port = "50051"
	}

	listener, err := net.Listen("tcp", fmt.Sprintf(":%s", port))
	if err != nil {
		log.Fatalf("Failed to listen on port %s: %v", port, err)
	}

	grpcServer := grpc.NewServer()
	RegisterEngineServiceServer(grpcServer, &EngineServer{})

	// Enable server reflection for debugging
	reflection.Register(grpcServer)

	log.Printf("ForgeGraph Engine gRPC server listening on port %s", port)

	if err := grpcServer.Serve(listener); err != nil {
		log.Fatalf("Failed to serve gRPC server: %v", err)
	}
}
